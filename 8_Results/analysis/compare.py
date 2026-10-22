#!/usr/bin/env python3
"""Cross-phase comparison: one metric definition (stepmetrics) on every matched case -> out/tables/T4_sim_step_metrics,
T5_cross_phase (+ G_compare) and the comparison figures (figures.compare_*).

    python3 compare.py [--no-figures]

Scenarios (config.SCENARIOS): S1 loop close on the residual, S3 module-3 shade, S4 +1 V vref2 step, S5 open-loop
common-duty step; V2 / V4 = the validate suites' cold-start reference tests (decoupling, shade-refs).
Hardware rows come from out/tables/T3_hw_events.csv (hwmetrics.py): close -> S1, mismatch_on -> S3, duty_step -> S5.
"""
import argparse
import importlib
import math
import os
import sys

import numpy as np
import pandas as pd

import config
import stepmetrics as sm
import tidy

TAB = os.path.join(config.OUT, "tables")
PHASE_ORDER = ["analytical", "simulink_mil", "simulink", "qspice", "hardware"]
SIGNALS = {"S1": ["vd2", "vd1", "ic2", "ic1", "id2"], "S3": ["id2", "vd2", "Pstr", "IM3", "id1"], "S4": ["vd2", "ic2", "id2", "vd1"],
           "S5": ["vd1", "vd2", "id1", "id2"], "V2": ["vd1", "vd2", "vd3", "ic1", "ic2"], "V4": ["vd1", "vd2", "vd3", "ic1", "ic2"]}
REF = {"S1": {"vd1": 0.0, "vd2": 0.0, "ic1": 0.0, "ic2": 0.0}, "S4": {"vd1": 0.0, "vd2": 1.0, "ic1": 0.0, "ic2": 0.0}}
BAND_FLOOR = {"vd1": 0.05, "vd2": 0.05, "vd3": 0.05, "ic1": 0.1, "ic2": 0.1, "id1": 0.1, "id2": 0.1, "Pstr": 2.0, "IM3": 0.1}
ABS_BAND = {"vd1": 0.1, "vd2": 0.1, "vd3": 0.1, "ic1": 0.2, "ic2": 0.2}
HW_EVENT_SCEN = {"close": "S1", "mismatch_on": "S3", "duty_step": "S5"}


def load_phase(name):
    try:
        return importlib.import_module(f"phases.{name}")
    except ModuleNotFoundError:
        return None


def sim_frames():
    """Every simulation / analytical case with its scenario tag."""
    out = []
    an = load_phase("analytical")
    for scen in ("S1", "S3", "S4"):
        out += an.cases(scen, f_khz=(200, 300, 400))
    out += an.cases("S5", f_khz=(200,))
    for name in ("qspice", "simulink"):
        mod = load_phase(name)
        for scen in ("S1", "S3", "S4"):
            try:
                out += mod.cases(scen)
            except FileNotFoundError:
                pass
    va = load_phase("validate")
    for which in ("carpark", "mil"):
        for f in va.tests(which):
            if f.attrs.get("test") in ("decoupling", "shade-refs"):
                f.attrs["scenario"] = "V2" if f.attrs["test"] == "decoupling" else "V4"
                out.append(f)
    return out


def metrics_of(f):
    a = f.attrs
    scen = a.get("scenario")
    rows = []
    phase = a.get("phase")
    for sig in SIGNALS.get(scen, []):
        if sig not in f or f[sig].notna().sum() < 4:
            continue
        ref = REF.get(scen, {}).get(sig)
        if scen in ("V2", "V4") and sig.startswith("vd"):
            j = int(sig[2]) - 1
            rv = a.get("rv", [])
            ref = float(rv[j]) if j < len(rv) else None
        kw = dict(band_floor=BAND_FLOOR.get(sig, 0.1), abs_band=ABS_BAND.get(sig))
        if scen in ("V2", "V4"):
            kw.update(y_initial=0.0, pre=(0.0, 0.0))
        elif phase == "qspice" and scen == "S1":
            kw["pre"] = (-0.0003, 0.0)
        else:
            kw["pre"] = (-0.002, 0.0)
        m = sm.step_metrics(f["t"].to_numpy(), f[sig].to_numpy(float), 0.0, ref=ref, **kw)
        row = {"scenario": scen, "phase": phase, "setup": a.get("setup"), "f_khz": a.get("f_khz", 200), "kscale": a.get("kscale"),
               "signal": sig, "source": a.get("source"), "event": a.get("event", ""), "test": a.get("test", ""), "ref": ref}
        row.update({k: m.get(k) for k in sm.KEYS})
        row["rise_txt"], row["peak_txt"] = sm.bound(m, "rise_10_90"), sm.peak_text(m)
        row["settle2_txt"] = sm.bound(m, "t_settle_2")
        rows.append(row)
    return rows


def hardware_rows():
    p = os.path.join(TAB, "T3_hw_events.csv")
    if not os.path.exists(p):
        return pd.DataFrame()
    t3 = pd.read_csv(p)
    t3 = t3[t3["event"].isin(HW_EVENT_SCEN)].copy()
    t3["scenario"] = t3["event"].map(HW_EVENT_SCEN)
    t3["phase"] = "hardware"
    t3["signal"] = t3["signal"].replace({"Pstr_i": "Pstr"})
    t3 = t3[t3["signal"].isin(sum(SIGNALS.values(), []))]
    return t3


# ----------------------------------------------------------------------------- tables
def _f(v, nd=3):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "-"
    if isinstance(v, str):
        return v
    return f"{v:.{nd}g}"


def t4_md(df):
    cols = ["scenario", "phase", "setup", "f_khz", "kscale", "signal", "y_initial", "y_final", "delta", "ss_error", "rise_txt", "peak_txt", "overshoot_pct",
            "undershoot_pct", "settle2_txt", "t_settle_abs", "iae", "tau", "zeta", "fit_r2"]
    head = {"y_initial": "y0", "y_final": "y_final", "delta": "delta", "ss_error": "ss err", "rise_txt": "rise 10-90", "peak_txt": "t peak", "overshoot_pct": "overshoot %",
            "undershoot_pct": "undershoot %", "settle2_txt": "settle 2 %", "t_settle_abs": "settle abs [s]", "iae": "IAE", "tau": "tau [s]", "zeta": "zeta", "fit_r2": "fit r2"}
    lines = ["| " + " | ".join(head.get(c, c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.sort_values(["scenario", "signal", "setup", "kscale", "phase", "f_khz"]).iterrows():
        lines.append("| " + " | ".join(str(r.get(c, "")) if c in ("scenario", "phase", "setup", "signal", "rise_txt", "peak_txt", "settle2_txt") else _f(r.get(c)) for c in cols) + " |")
    return "\n".join(lines) + "\n"


def t5_rows(T4, HW):
    """Side-by-side per (scenario, setup, kscale, signal): one column group per phase."""
    keys = ["scenario", "setup", "kscale", "signal"]
    sims = T4[(T4["f_khz"] == 200) | T4["f_khz"].isna()]
    rows = {}
    for _, r in sims.iterrows():
        if r.get("kind") != "step" or abs(r.get("delta") or 0) < 2 * BAND_FLOOR.get(r["signal"], 0.1):
            continue                                     # no real step in this signal (reference at 0, or a disturbance target): nothing to compare
        k = (r["scenario"], r["setup"], round(float(r["kscale"]) if np.isfinite(float(r["kscale"] or np.nan)) else 0.0, 3), r["signal"])
        d = rows.setdefault(k, {"scenario": k[0], "setup": k[1], "kscale": k[2], "signal": k[3]})
        ph = r["phase"]
        d[f"{ph}_tau_ms"] = (r["tau"] * 1e3) if np.isfinite(r.get("tau", np.nan) or np.nan) else np.nan
        d[f"{ph}_rise_ms"] = r["rise_10_90"] * 1e3 if np.isfinite(r.get("rise_10_90", np.nan) or np.nan) else np.nan
        d[f"{ph}_settle2_ms"] = r["t_settle_2"] * 1e3 if np.isfinite(r.get("t_settle_2", np.nan) or np.nan) else np.nan
        d[f"{ph}_peak_ms"] = r["t_peak"] * 1e3 if r.get("has_overshoot") else np.nan
        d[f"{ph}_overshoot_pct"] = r["overshoot_pct"] if r.get("has_overshoot") else 0.0
        d[f"{ph}_sse"] = r["ss_error"]
        d[f"{ph}_delta"] = r["delta"]
    if len(HW):
        for _, r in HW.iterrows():
            if r["scenario"] == "S5":
                continue                                 # the three open-loop duty steps are compared one by one in REPORT section 3.2 / the S5 figure
            k = (r["scenario"], r["setup"], round(float(r["kscale"]) if np.isfinite(float(r["kscale"] or np.nan)) else 0.0, 3), r["signal"])
            d = rows.setdefault(k, {"scenario": k[0], "setup": k[1], "kscale": k[2], "signal": k[3]})
            n = d.get("hardware_n", 0)
            # several hardware events per key: keep medians, count them
            for src, dst in (("delta", "hardware_delta"), ("ss_error", "hardware_sse"), ("noise", "hardware_noise"), ("t_settle_abs", "hardware_settle_abs_s"), ("peak_dev", "hardware_peak_dev")):
                v = r.get(src)
                if v is not None and np.isfinite(v):
                    d[dst] = v if n == 0 else (d.get(dst, v) * n + v) / (n + 1)
            d["hardware_rise_txt"] = r.get("rise_txt", "")
            d["hardware_settle2_txt"] = r.get("settle2_txt", "")
            d["hardware_dt_ms"] = r.get("dt_median", np.nan) * 1e3 if np.isfinite(r.get("dt_median", np.nan) or np.nan) else np.nan
            d["hardware_n"] = n + 1
            d["hardware_cases"] = (d.get("hardware_cases", "") + " " + str(r["cid"])).strip()
    out = pd.DataFrame(list(rows.values()))
    return out.sort_values(["scenario", "signal", "setup", "kscale"]) if len(out) else out


def t5_md(T5):
    if T5.empty:
        return "_no rows_\n"
    phases = [p for p in ("analytical", "simulink", "simulink_mil", "qspice") if any(c.startswith(p + "_") for c in T5.columns)]
    cols = ["scenario", "setup", "kscale", "signal"]
    head = cols + [f"{config.PHASE_STYLE[p]['label'].split(' (')[0]} tau / rise / settle2 [ms], os %" for p in phases] + ["hardware: delta, ss err, noise, rise, settle abs [s] (n cases)"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for _, r in T5.iterrows():
        vals = [str(r[c]) for c in cols]
        for p in phases:
            if np.isfinite(r.get(f"{p}_tau_ms", np.nan) or np.nan) or np.isfinite(r.get(f"{p}_rise_ms", np.nan) or np.nan):
                vals.append(f"{_f(r.get(f'{p}_tau_ms'))} / {_f(r.get(f'{p}_rise_ms'))} / {_f(r.get(f'{p}_settle2_ms'))}, {_f(r.get(f'{p}_overshoot_pct'), 2)}")
            else:
                vals.append("-")
        hn = r.get("hardware_n")
        if hn is not None and np.isfinite(hn) and hn > 0:
            vals.append(f"{_f(r.get('hardware_delta'))}, {_f(r.get('hardware_sse'))}, {_f(r.get('hardware_noise'), 2)}, {r.get('hardware_rise_txt', '')}, {_f(r.get('hardware_settle_abs_s'), 2)} ({int(r['hardware_n'])}: {r.get('hardware_cases', '')})")
        else:
            vals.append("-")
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines) + "\n"


def g_tables():
    from compare_legacy import g_tables as g
    return g()


def build(figures=True):
    os.makedirs(TAB, exist_ok=True)
    frames = sim_frames()
    rows = []
    for f in frames:
        rows += metrics_of(f)
    T4 = pd.DataFrame(rows)
    T4.to_csv(os.path.join(TAB, "T4_sim_step_metrics.csv"), index=False)
    open(os.path.join(TAB, "T4_sim_step_metrics.md"), "w").write(t4_md(T4))
    HW = hardware_rows()
    T5 = t5_rows(T4, HW)
    T5.to_csv(os.path.join(TAB, "T5_cross_phase.csv"), index=False)
    open(os.path.join(TAB, "T5_cross_phase.md"), "w").write(t5_md(T5))
    g_tables()
    print(f"T4: {len(T4)} rows from {len(frames)} frames; T5: {len(T5)} matched keys")
    if figures:
        import figures as fg
        fg.compare_all(frames, T4, T5)
    return frames, T4, T5


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-figures", action="store_true")
    a = ap.parse_args()
    build(not a.no_figures)


if __name__ == "__main__":
    main()
