#!/usr/bin/env python3
"""Hardware metrics of the presentation test cases -> out/tables/T2_hw_steady_state, T3_hw_events, T7_energy (csv + md).

    python3 hwmetrics.py [--only B06]

T2: per RUN segment (>= 5 s, first 2 s and last 1 s skipped) mean / std / pk-pk / detrended RMS / dominant frequency of
    the controlled and measured signals, steady-state error of vd and ic against their 0 references (closed loop).
T3: per event inside a RUN segment (loop close, duty step, load step, mismatch on/off, irradiance change, kscale apply):
    the step / disturbance metrics of stepmetrics.step_metrics on the relevant signals. Hardware is sampled at ~45 Hz
    (11-14 Hz on some 200 kHz runs), so rise / peak / settling times shorter than one sample are reported as bounds.
T7: energies of the solar cases (energy.py definitions).
"""
import argparse
import os

import numpy as np
import pandas as pd

import config
import energy
import stepmetrics as sm
from phases import hardware as hw

TAB = os.path.join(config.OUT, "tables")
SS_SIGNALS = ["vd1", "vd2", "ic1", "ic2", "id1", "id2", "dA1", "dB1", "dA2", "dB2", "VM1", "VM2", "VM3", "Istr_i", "Vel_i", "Pstr_i", "IM1", "IM2", "IM3"]
REF0 = {"vd1": 0.0, "vd2": 0.0, "ic1": 0.0, "ic2": 0.0}
# event kind -> (signals, pre window [s], post window [s], band floors)
EVENT_SPEC = {
    "close":          (["vd2", "vd1", "ic2", "ic1", "id2", "id1"], (0.0, 0.0), 3.0),
    "duty_step":      (["vd1", "vd2", "id1", "id2", "ic1", "ic2", "VM1", "VM2", "VM3", "Istr_i"], (-3.0, 0.0), 6.0),
    "load_step":      (["Istr_i", "Vel_i", "Pstr_i", "vd1", "vd2", "id1", "id2", "ic1", "ic2"], (-3.0, 0.0), 10.0),
    "mismatch_on":    (["id1", "id2", "vd1", "vd2", "Pstr_i", "Istr_i", "IM1", "IM2", "IM3"], (-5.0, 0.0), 20.0),
    "mismatch_off":   (["id1", "id2", "vd1", "vd2", "Pstr_i", "Istr_i", "IM1", "IM2", "IM3"], (-5.0, 0.0), 20.0),
    "irradiance_up":  (["Pstr_i", "Istr_i", "id1", "id2", "vd1", "vd2"], (-5.0, 0.0), 20.0),
    "irradiance_down": (["Pstr_i", "Istr_i", "id1", "id2", "vd1", "vd2"], (-5.0, 0.0), 20.0),
    "kscale_apply":   (["vd2", "vd1", "ic2", "ic1"], (-2.0, 0.0), 5.0),
}
BAND_FLOOR = {"vd1": 0.1, "vd2": 0.1, "ic1": 0.3, "ic2": 0.3, "id1": 0.3, "id2": 0.3, "VM1": 0.3, "VM2": 0.3, "VM3": 0.3,
              "Istr_i": 0.05, "Vel_i": 0.5, "Pstr_i": 3.0, "IM1": 0.2, "IM2": 0.2, "IM3": 0.2}
ABS_BAND = {"vd1": 0.1, "vd2": 0.1, "ic1": 0.2, "ic2": 0.2}
FILT = {"vd1": ("median", 3), "vd2": ("median", 3)}


def steady_rows(cid):
    spec = config.TEST_CASES[cid]
    run = hw.run_frame(cid)
    rows = []
    for _, s in hw.run_segments(cid).iterrows():
        if s["duration_s"] < 5:
            continue
        t0, t1 = pd.Timestamp(s["start_utc"]) + pd.Timedelta(seconds=2), pd.Timestamp(s["end_utc"]) - pd.Timedelta(seconds=1)
        g = run[(run["t_utc"] >= t0) & (run["t_utc"] <= t1)]
        if len(g) < 20:
            continue
        t = (g["t_utc"] - t0).dt.total_seconds().to_numpy()
        row = {"cid": cid, "slide": spec["slide"] or "", "setup": spec["setup"], "f_khz": spec["f_khz"], "loop": spec["loop"], "state": s["state"],
               "kscale": s["kscale"], "pver": str(s["pver"]).replace("sps-params-2.", ""), "start_local": s["start_local"][11:19],
               "duration_s": round(float((t1 - t0).total_seconds()), 1), "n": len(g), "rate_hz": round(float(1 / np.median(np.diff(t))), 1)}
        for sig in SS_SIGNALS:
            if sig not in g or g[sig].notna().sum() < 10:
                continue
            r = sm.ripple_stats(t, g[sig].to_numpy(float), f_min=0.2)
            row[f"{sig}_mean"] = r["mean"]
            row[f"{sig}_std"] = r["std"]
            row[f"{sig}_pkpk"] = r["pk_pk_robust"]
            row[f"{sig}_rms"] = r["rms_detrended"]
            if sig in ("vd1", "vd2", "ic1", "ic2", "id1", "id2"):
                row[f"{sig}_fdom_hz"] = r["f_dominant_hz"]
            if sig in REF0 and s["state"].startswith("RUN_CL"):
                row[f"{sig}_sse"] = r["mean"] - REF0[sig]
        rows.append(row)
    return rows


def _cut(run, t_ev, pre, post):
    g = run[(run["t_utc"] >= t_ev + pd.Timedelta(seconds=pre)) & (run["t_utc"] <= t_ev + pd.Timedelta(seconds=post))]
    return (g["t_utc"] - t_ev).dt.total_seconds().to_numpy(), g


def event_rows(cid):
    spec = config.TEST_CASES[cid]
    w = hw.case(cid)
    run = hw.run_frame(cid)
    ev = w["events"]
    segs = hw.run_segments(cid)
    rows = []
    n_in = 0
    cmd_times = [pd.Timestamp(t) for t in ev.loc[ev["kind"].isin(("duty_step", "kscale_apply")), "time_utc"]]
    for _, e in ev.iterrows():
        kind = e["kind"]
        if kind not in EVENT_SPEC:
            continue
        t_ev = pd.Timestamp(e["time_utc"])
        if kind == "load_step" and e.get("source") == "detector" and any(abs((t_ev - tc).total_seconds()) < 4 for tc in cmd_times):
            continue                                     # the detector saw the commanded step itself
        signals, pre, post = EVENT_SPEC[kind]
        # the event must sit inside (or, for a close, at the start of) a RUN segment
        inside = segs[(pd.to_datetime(segs["start_utc"], utc=True) <= t_ev + pd.Timedelta(seconds=0.5)) & (pd.to_datetime(segs["end_utc"], utc=True) >= t_ev)]
        if inside.empty:
            continue
        seg = inside.iloc[0]
        post_eff = min(post, (pd.Timestamp(seg["end_utc"]) - t_ev).total_seconds() - 0.2)
        if post_eff < 0.5:
            continue
        n_in += 1
        tt, g = _cut(run, t_ev, pre[0] - 0.5, post_eff)
        idle = w["tel"][(w["tel"]["t_utc"] < t_ev - pd.Timedelta(seconds=0.2)) & (w["tel"]["t_utc"] >= t_ev - pd.Timedelta(seconds=3)) & (w["tel"]["state"] == "IDLE")]
        for sig in signals:
            if sig not in g or g[sig].notna().sum() < 4:
                continue
            y = g[sig].to_numpy(float)
            kw = dict(pre=pre, band_floor=BAND_FLOOR.get(sig, 0.1), filt=FILT.get(sig), abs_band=ABS_BAND.get(sig))
            if kind == "close":
                after = tt >= 0
                if after.sum() < 4:
                    continue
                kw["y_initial"] = float(y[after][0])             # the first controlled sample: the residual the loop has to remove
                kw["pre"] = (0.0, 0.0)
            ref = REF0.get(sig) if (kind in ("close", "kscale_apply") or seg["state"].startswith("RUN_CL")) and sig in REF0 else None
            m = sm.step_metrics(tt, y, 0.0, ref=ref, **kw)
            row = {"cid": cid, "slide": spec["slide"] or "", "setup": spec["setup"], "f_khz": spec["f_khz"], "loop": spec["loop"], "state": seg["state"],
                   "kscale": seg["kscale"], "event": kind, "time_local": t_ev.tz_convert(config.LOCAL_TZ).strftime("%H:%M:%S"),
                   "detail": str(e.get("detail", ""))[:80], "signal": sig, "post_s": round(post_eff, 1)}
            if kind == "close" and len(idle) and sig in idle:
                row["idle_level"] = float(idle[sig].median())
            row.update({k: m.get(k) for k in sm.KEYS})
            row["rise_txt"], row["peak_txt"] = sm.bound(m, "rise_10_90"), sm.peak_text(m)
            row["settle2_txt"], row["settle5_txt"] = sm.bound(m, "t_settle_2"), sm.bound(m, "t_settle_5")
            rows.append(row)
    return rows


def energy_rows(cid):
    return energy.case_energy(cid)


# ----------------------------------------------------------------------------- markdown
def _f(v, nd=3, unit=""):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "-"
    if isinstance(v, str):
        return v
    return f"{v:.{nd}g}{unit}"


def steady_md(df):
    cols = [("cid", "case"), ("slide", "slide"), ("f_khz", "f_sw"), ("state", "state"), ("kscale", "k"), ("duration_s", "s"), ("rate_hz", "Hz"),
            ("vd1_mean", "vd1 mean [V]"), ("vd1_std", "vd1 std"), ("vd2_mean", "vd2 mean [V]"), ("vd2_std", "vd2 std"), ("vd2_pkpk", "vd2 pk-pk"),
            ("ic1_mean", "ic1 mean [A]"), ("ic1_std", "ic1 std"), ("ic2_mean", "ic2 mean [A]"), ("ic2_std", "ic2 std"), ("ic2_pkpk", "ic2 pk-pk"),
            ("id1_mean", "i_sh1 mean [A]"), ("id2_mean", "i_sh2 mean [A]"), ("dA2_std", "dA2 std"), ("Istr_i_mean", "I_str [A]"), ("Vel_i_mean", "V_str [V]"),
            ("Pstr_i_mean", "P [W]")]
    lines = ["| " + " | ".join(h for _c, h in cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(_f(r.get(c)) if c not in ("cid", "slide", "state") else str(r.get(c, "")) for c, _h in cols) + " |")
    return "\n".join(lines) + "\n"


def events_md(df):
    cols = ["cid", "event", "time_local", "state", "kscale", "signal", "kind", "y_initial", "y_final", "delta", "ss_error", "noise", "rise_txt", "peak_txt",
            "overshoot_pct", "peak_dev", "settle2_txt", "t_settle_abs", "band_abs", "iae", "n_transient_samples"]
    head = {"y_initial": "y0", "y_final": "y_final", "delta": "delta", "ss_error": "ss err", "noise": "noise (MAD)", "rise_txt": "rise 10-90", "peak_txt": "t peak",
            "overshoot_pct": "overshoot %", "peak_dev": "peak dev", "settle2_txt": "settle 2 % band", "t_settle_abs": "settle abs [s]", "band_abs": "abs band",
            "iae": "IAE", "n_transient_samples": "n"}
    lines = ["| " + " | ".join(head.get(c, c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        vals = []
        for c in cols:
            v = r.get(c)
            vals.append(str(v) if c in ("cid", "event", "time_local", "state", "signal", "kind", "rise_txt", "peak_txt", "settle2_txt", "settle5_txt") else _f(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines) + "\n"


def energy_md(df):
    cols = [("cid", "case"), ("loop", "loop"), ("state", "state"), ("kscale", "k"), ("scope", "scope"), ("start_local", "start"), ("seconds", "s"),
            ("P_load_W", "P_load [W]"), ("P_mod_W", "P_modules [W]"), ("efficiency", "eff"), ("P_shuffled_W", "P_shuffled [W]"),
            ("P_returned_W", "P_returned [W]"), ("P_returned_max_W", "P_returned max [W]"), ("E_load_Wh", "E_load [Wh]"),
            ("E_shuffled_Wh", "E_shuffled [Wh]"), ("E_returned_Wh", "E_returned [Wh]"), ("returned_frac", "returned / load"),
            ("I_M1_A", "I_M1 [A]"), ("I_M2_A", "I_M2 [A]"), ("I_M3_A", "I_M3 [A]"), ("I_str_A", "I_str [A]")]
    lines = ["| " + " | ".join(h for _c, h in cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(_f(r.get(c)) if c not in ("cid", "loop", "state", "scope", "start_local") else str(r.get(c, "")) for c, _h in cols) + " |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only")
    a = ap.parse_args()
    os.makedirs(TAB, exist_ok=True)
    ss, evs, ens = [], [], []
    for cid in config.TEST_CASES:
        if a.only and a.only not in cid:
            continue
        s, e, n = steady_rows(cid), event_rows(cid), energy_rows(cid)
        ss += s; evs += e; ens += n
        print(f"{cid}: {len(s)} steady segments, {len(e)} event-signal rows, {len(n)} energy rows")
    T2, T3, T7 = pd.DataFrame(ss), pd.DataFrame(evs), pd.DataFrame(ens)
    if a.only:
        print(steady_md(T2)); print(events_md(T3)); print(energy_md(T7))
        return
    T2.to_csv(os.path.join(TAB, "T2_hw_steady_state.csv"), index=False)
    open(os.path.join(TAB, "T2_hw_steady_state.md"), "w").write(steady_md(T2))
    T3.to_csv(os.path.join(TAB, "T3_hw_events.csv"), index=False)
    open(os.path.join(TAB, "T3_hw_events.md"), "w").write(events_md(T3))
    T7.to_csv(os.path.join(TAB, "T7_energy.csv"), index=False)
    open(os.path.join(TAB, "T7_energy.md"), "w").write(energy_md(T7))


if __name__ == "__main__":
    main()
