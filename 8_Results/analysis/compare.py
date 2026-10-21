#!/usr/bin/env python3
"""Matched-scenario comparison across phases: tables (CSV + markdown) and overlay figures in out/tables, out/figures.

    python3 compare.py [--phases hardware,qspice,simulink,analytical] [--scenarios S1,S2,S3,S4] [--no-figures]

Every phase module exposes cases(scenario) -> list of tidy frames (phases/*.py); each frame carries attrs
(phase, setup, kscale, scenario, event ...). One metric definition (stepmetrics.step_metrics) is applied to every
frame and signal.
"""
import argparse
import importlib
import math
import os

import numpy as np
import pandas as pd

import sys

import config
import stepmetrics as sm
import tidy

TAB = os.path.join(config.OUT, "tables")
FIG = os.path.join(config.OUT, "figures")
PHASE_ORDER = ["analytical", "simulink_mil", "simulink", "qspice", "hardware"]
PHASE_LABEL = {"analytical": "Analytical N=3", "simulink_mil": "Simulink MIL (4 mod, ideal)", "simulink": "Simulink carpark (3 mod)",
               "qspice": "QSPICE switching + DLL", "hardware": "Hardware"}


def load_phase(name):
    try:
        return importlib.import_module(f"phases.{name}")
    except ModuleNotFoundError:
        return None


# ----------------------------------------------------------------------------- case providers
def hardware_cases(scenario):
    hw = load_phase("hardware")
    out = []
    for name in config.WINDOWS:
        if scenario == "S1":
            out += hw.close_cases(name)
        elif scenario == "S3":
            out += hw.shade_cases(name)
    return out


def sim_cases(phase, scenario):
    mod = load_phase(phase)
    if mod is None or not hasattr(mod, "cases"):
        return []
    try:
        return mod.cases(scenario)
    except FileNotFoundError:
        return []


HW_SIGNALS = {"S1": ["vd2", "vd1"],                 # currents at 50 Hz are point samples of switching ripple: S2 statistics only
              "S3": ["Pstr", "id2", "VM3", "vd2"]}


def cases_for(scenario, phases):
    out, seen = [], set()
    for p in phases:
        for f in (hardware_cases(scenario) if p == "hardware" else sim_cases(p, scenario)):
            key = (f.attrs.get("phase"), f.attrs.get("setup"), f.attrs.get("event_utc") or id(f), round(float(f.attrs.get("kscale") or 0), 3))
            if key in seen:                                  # overlapping hardware windows hold the same engagement
                continue
            seen.add(key)
            if f.attrs.get("phase") == "hardware" and scenario == "S3" and f.attrs.get("setup") != "PV80":
                continue                                     # no shading on the bench: those candidates are PSU / load changes
            out.append(f)
    return out


# ----------------------------------------------------------------------------- metrics per case
def metrics_rows(scenario, frames):
    rows = []
    spec = config.SCENARIOS[scenario]
    for f in frames:
        a = f.attrs
        hw = a.get("phase") == "hardware"
        signals = HW_SIGNALS.get(scenario, spec["signals"]) if hw else spec["signals"]
        for sig in signals:
            if sig not in f or f[sig].notna().sum() < 4:
                continue
            ref = spec.get("ref") if sig in ("vd1", "vd2", "ic1", "ic2") else None
            if scenario == "S3":
                ref = None
            band_floor = {"vd1": 0.1, "vd2": 0.1, "ic1": 0.3, "ic2": 0.3, "id1": 0.3, "id2": 0.3, "VM3": 0.3, "Pstr": 3.0, "dA2": 0.005}.get(sig, 0.1)
            # hardware S1: the level the controller starts from is the last sample before RUN_CL (the soft-start ramp
            # to 0.5 duty has already removed most of the idle mismatch, kept in idle_level)
            pre = ((-0.03, 0.0) if scenario == "S1" else (-0.5, 0.0)) if hw else (-0.02, 0.0)
            if a.get("phase") == "qspice" and scenario == "S1":
                pre = (-0.0003, 0.0)          # the open loop had 0.5 ms of start-up before TEN: take the level at the closing instant
            m = sm.step_metrics(f["t"].to_numpy(), f[sig].to_numpy(float), 0.0, ref=ref, pre=pre, band_floor=band_floor,
                                filt=("median", 3) if hw else None)
            row = {"scenario": scenario, "phase": a.get("phase"), "setup": a.get("setup"), "kscale": a.get("kscale"),
                   "signal": sig, "source": a.get("source"), "event": a.get("event_utc", a.get("event", "")),
                   "ended_by": a.get("ended_by", ""), "run_duration_s": a.get("run_duration_s"),
                   "quality": ("VM1 via e-load 2.2 Hz" if hw and sig in ("vd1",) else "")}
            if hw and scenario == "S1":
                row["idle_level"] = a.get("idle_levels", {}).get(sig)
            row.update({k: m.get(k) for k in sm.KEYS})
            rows.append(row)
    return pd.DataFrame(rows)


def md_table(df, scenario):
    if df.empty:
        return "_no cases_\n"
    cols = ["phase", "setup", "kscale", "signal"]
    if scenario == "S1" and "idle_level" in df:
        cols.append("idle_level")
    lines = ["| " + " | ".join(cols + ["y0", "y_final", "delta", "ss err", "rise 10-90", "t peak", "overshoot", "t settle 2%", "t settle 5%", "n", "model", "tau / zeta, wn", "fit r2"]) + " |",
             "|" + "---|" * (len(cols) + 13)]
    for _, r in df.sort_values(["scenario", "signal", "phase", "setup", "kscale"]).iterrows():
        fitv = "-"
        if r.get("fit_model") == "first":
            fitv = f"tau {sm.fmt(r['tau'] * 1e3, ' ms')} +- {sm.fmt((r['tau_ci'] or 0) * 1e3, '', 2)}"
        elif r.get("fit_model") == "second":
            fitv = f"zeta {sm.fmt(r['zeta'], '', 2)}, wn {sm.fmt(r['wn'] / (2 * math.pi), ' Hz', 3)}"
        vals = [str(r.get(c, "")) if c != "idle_level" else sm.fmt(r.get(c)) for c in cols]
        vals += [sm.fmt(r["y_initial"]), sm.fmt(r["y_final"]), sm.fmt(r["delta"]), sm.fmt(r["ss_error"]),
                 sm.bound(r, "rise_10_90"), sm.bound(r, "t_peak"),
                 (sm.fmt(r["overshoot_pct"], " %", 3) if r["kind"] == "step" else f"peak dev {sm.fmt(r['peak_dev'])}"),
                 sm.bound(r, "t_settle_2"), sm.bound(r, "t_settle_5"), str(int(r["n_transient_samples"])) if np.isfinite(r["n_transient_samples"]) else "-",
                 str(r.get("fit_model") or "-"), fitv, sm.fmt(r.get("fit_r2"), "", 2)]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- S2: settled statistics
def s2_rows(phases):
    rows = []
    if "hardware" in phases:
        hw = load_phase("hardware")
        seen = set()
        for name in config.WINDOWS:
            seg = hw.segment_stats(name)
            for _, s in seg.iterrows():
                if (s["start_utc"], s["state"]) in seen:          # overlapping windows
                    continue
                seen.add((s["start_utc"], s["state"]))
                rows.append({"phase": "hardware", "setup": s["setup"], "state": s["state"], "kscale": s["kscale"], "pver": s["pver"],
                             "window": name, "start_local": s["start_local"], "duration_s": s["duration_s"], "ended_by": s["ended_by"],
                             **{k: s.get(k) for k in ("vd1_mean", "vd1_std", "vd2_mean", "vd2_std", "ic1_mean", "ic1_std", "ic2_mean", "ic2_std",
                                                      "id1_mean", "id2_mean", "dA1_std", "dA2_std", "dB2_std", "stress_mean", "Pstr_mean", "Vstr_mean")}})
    for p in phases:
        mod = load_phase(p) if p != "hardware" else None
        if mod is not None and hasattr(mod, "settled_stats"):
            rows += mod.settled_stats()
    return pd.DataFrame(rows)


def s2_md(df):
    if df.empty:
        return "_no segments_\n"
    cols = ["phase", "setup", "state", "kscale", "duration_s", "ended_by", "vd2_mean", "vd2_std", "ic2_mean", "ic2_std", "id1_mean", "id2_mean", "dA2_std", "stress_mean", "Pstr_mean"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.sort_values(["phase", "setup", "state", "kscale", "start_local"]).iterrows():
        lines.append("| " + " | ".join(sm.fmt(r.get(c)) if isinstance(r.get(c), float) else str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- figures
def _label(f):
    a = f.attrs
    lab = f"{PHASE_LABEL.get(a.get('phase'), a.get('phase'))} {a.get('setup', '')} k={a.get('kscale')}"
    if a.get("phase") == "hardware":
        ev = str(a.get("event_utc", ""))
        if ev:
            try:
                lab += " " + pd.Timestamp(ev).tz_convert(config.LOCAL_TZ).strftime("%d %H:%M:%S")
            except Exception:                  # noqa: BLE001
                pass
        if a.get("ended_by") == "FAULT":
            lab += " (FAULT)"
    return lab


def overlay(scenario, frames, sig, path):
    """Simulations on a ms axis in <path>; hardware cases (soft start + closing, seconds) in <path>_hw."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    palette = {"analytical": "#555555", "simulink_mil": "#8e6bbf", "simulink": "#1f6b46", "qspice": "#1b2d55"}
    sims = [f for f in frames if f.attrs.get("phase") != "hardware"]
    hw = [f for f in frames if f.attrs.get("phase") == "hardware"]
    if sims:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for f in sims:
            a = f.attrs
            ls = "--" if a.get("setup") == "BENCH" else "-"
            ax.plot(f["t"] * 1e3, f[sig], ls, lw=1.2, color=palette.get(a.get("phase"), "k"), alpha=0.9, label=_label(f))
        ax.axvline(0, color="k", lw=0.8, ls="--")
        ax.set_xlabel("ms from event")
        ax.set_ylabel(tidy.SIGNAL_LABELS.get(sig, sig))
        ax.set_title(f"{scenario} {config.SCENARIOS[scenario]['name']}: {sig} (simulations and analysis)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, loc="best")
        fig.tight_layout()
        fig.savefig(path, dpi=120)
        plt.close(fig)
    if hw:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        cmap = plt.get_cmap("tab10")
        for i, f in enumerate(hw[:10]):
            a = f.attrs
            g = f if scenario != "S1" else f[(f["t"] >= -0.4) & (f["t"] <= 1.0)]
            ax.plot(g["t"], g[sig], ".", ms=4, color=cmap(i % 10), alpha=0.8 if a.get("ended_by") != "FAULT" else 0.35, label=_label(f))
        ax.axvline(0, color="k", lw=0.8, ls="--")
        ax.set_xlabel("s from event")
        ax.set_ylabel(tidy.SIGNAL_LABELS.get(sig, sig))
        ax.set_title(f"{scenario} {config.SCENARIOS[scenario]['name']}: {sig} (hardware, 50 Hz telemetry)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=6, loc="best")
        fig.tight_layout()
        fig.savefig(path.replace(".png", "_hw.png"), dpi=120)
        plt.close(fig)


# ----------------------------------------------------------------------------- G matrices
def g_tables():
    """Identified G of every gain set against the analytical G(3) -> out/tables/G_compare.md."""
    sys.path.insert(0, config.NOTEBOOKS)
    import nstring
    os.makedirs(TAB, exist_ok=True)
    rows = ["| source | vd1/uc1 | vd2/uc2 | ic1/ud1 | ic2/ud2 | vd1/ud1 (cross) | cond(G) | note |", "|---|---|---|---|---|---|---|---|"]

    def row(name, G, note=""):
        G = np.asarray(G, float)
        return f"| {name} | {G[0, 0]:.1f} | {G[1, 1]:.1f} | {G[2, 2]:.1f} | {G[3, 3]:.1f} | {G[0, 2]:.1f} | {np.linalg.cond(G):.1f} | {note} |"

    for label, p in (("analytical PV80, averaged R 61 mOhm (Simulink)", nstring.pv80()), ("analytical PV80, switching R 0.29 ohm (200 kHz)", nstring.pv80(R_w=0.29)),
                     ("analytical PV80, switching R 1.72 ohm (400 kHz)", nstring.pv80(R_w=1.72)),
                     ("analytical BENCH QSPICE point (all CC), R 0.29 ohm", nstring.bench_qspice(R_w=0.29)), ("analytical BENCH ch1 CC / ch2,3 CV, R 0.29 ohm", nstring.bench(R_w=0.29))):
        rows.append(row(label, nstring.dc_gain(p), f"modes {[(f'{f:.0f} Hz', f'z {z:.2f}') for f, z, k in nstring.modes(p) if k == 'oscillatory'][:2]}"))
    for name, G in nstring.identified_G().items():
        if isinstance(G, str):
            continue
        rows.append(row(f"identified {name}", G, "diag(kI) M^-1 of the gain set"))
    md = "\n".join(rows) + "\n\nRows [vd1 vd2 ic1 ic2], columns [uc1 uc2 ud1 ud2]; V per unit modal duty, A per unit modal duty.\n"
    open(os.path.join(TAB, "G_compare.md"), "w").write(md)
    return md


# ----------------------------------------------------------------------------- main
def build(scenarios, phases, figures=True):
    os.makedirs(TAB, exist_ok=True)
    os.makedirs(FIG, exist_ok=True)
    report = {}
    if "G" in scenarios:
        g_tables()
        scenarios = [s for s in scenarios if s != "G"]
    for s in scenarios:
        if s == "S2":
            df = s2_rows(phases)
            df.to_csv(os.path.join(TAB, "S2_settled.csv"), index=False)
            open(os.path.join(TAB, "S2_settled.md"), "w").write(s2_md(df))
            report[s] = df
            print(f"S2: {len(df)} segments")
            continue
        frames = cases_for(s, phases)
        df = metrics_rows(s, frames)
        df.to_csv(os.path.join(TAB, f"{s}_{config.SCENARIOS[s]['name']}.csv"), index=False)
        open(os.path.join(TAB, f"{s}_{config.SCENARIOS[s]['name']}.md"), "w").write(md_table(df, s))
        report[s] = df
        print(f"{s}: {len(frames)} cases, {len(df)} metric rows")
        if figures and frames:
            for sig in config.SCENARIOS[s]["signals"][:3]:
                for ks in sorted({round(float(f.attrs.get("kscale") or 0), 2) for f in frames}):
                    sel = [f for f in frames if round(float(f.attrs.get("kscale") or 0), 2) == ks and sig in f and f[sig].notna().sum() > 3]
                    if sel:
                        overlay(s, sel[:8], sig, os.path.join(FIG, f"{s}_k{ks:g}_{sig}.png"))
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phases", default="hardware,qspice,simulink,simulink_mil,analytical")
    ap.add_argument("--scenarios", default="S1,S2,S3,S4,G")
    ap.add_argument("--no-figures", action="store_true")
    a = ap.parse_args()
    build(a.scenarios.split(","), a.phases.split(","), not a.no_figures)


if __name__ == "__main__":
    main()
