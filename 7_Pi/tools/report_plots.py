#!/usr/bin/env python3
"""Report-quality vector figures (SVG + PDF) and steady-state operating points from plots.py exports.

    python3 report_plots.py ../../8_Results/Bench_Open_Loop_100kHz/ol100k_a [more prefixes...]

For each prefix it reads <prefix>.csv (telemetry) and <prefix>_eload.csv (DL3021) and writes:
  <prefix>_overview.svg/.pdf   module voltages (VM1 estimated from the e-load), e-load V/I, duties, inductor currents
  <prefix>_oppoints.csv        mean/std of every signal over each steady segment (constant duties, RUN_OL,
                               e-load above 60 V, modules powered) - the QSPICE calibration targets
  <prefix>_oppoints.svg/.pdf   per-segment means vs duty for the active shuffler
Long traces are drawn as a 1 s mean line inside a min/max envelope, so spikes stay visible in a small file.
VM1 is not measured when U10 (CS3) is offline; VM1_est = V_eload - VM2 - VM3 (valid while the e-load is in CV
and cable drop is small).
"""
import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

TZ = "Australia/Brisbane"
plt.rcParams.update({
    "svg.fonttype": "none", "pdf.fonttype": 42, "font.size": 9, "axes.titlesize": 10,
    "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "figure.dpi": 100, "lines.linewidth": 1.0,
})
COL = {"VM1_est": "#7a7a7a", "VM2": "#1f77b4", "VM3": "#d62728", "v": "#2ca02c", "i": "#9467bd",
       "ILA1": "#1f77b4", "ILB1": "#aec7e8", "ILA2": "#d62728", "ILB2": "#ff9896",
       "dA1": "#1f77b4", "dB1": "#aec7e8", "dA2": "#d62728", "dB2": "#ff9896"}


def load(prefix):
    t = pd.read_csv(prefix + ".csv", parse_dates=["_time"], low_memory=False)
    t = t.set_index(t["_time"].dt.tz_convert(TZ)).drop(columns="_time").sort_index()
    e = pd.DataFrame()
    if os.path.exists(prefix + "_eload.csv"):
        e = pd.read_csv(prefix + "_eload.csv", parse_dates=["_time"])
        e = e.set_index(e["_time"].dt.tz_convert(TZ)).drop(columns="_time").sort_index()
    num = t.select_dtypes("number").columns
    t[num] = t[num].astype(float)
    if not e.empty and "v" in e:
        ev = e["v"].dropna()
        # e-load V onto the telemetry clock (5 Hz -> 50 Hz, hold-free linear interpolation)
        t["V_eload"] = np.interp(t.index.asi8, ev.index.asi8, ev.values, left=np.nan, right=np.nan)
        t["VM1_est"] = t["V_eload"] - t["VM2"] - t["VM3"]
    return t, e


def envelope(ax, s, color, label, rule="1s"):
    s = s.dropna()
    if s.empty:
        return
    r = s.resample(rule)
    lo, hi, mu = r.min(), r.max(), r.mean()
    ax.fill_between(mu.index, lo.values, hi.values, color=color, alpha=0.18, lw=0)
    ax.plot(mu.index, mu.values, color=color, label=label)


def overview(prefix, t, e):
    fig, axs = plt.subplots(4, 1, figsize=(7.2, 8.4), sharex=True, constrained_layout=True)
    for c in ("VM1_est", "VM2", "VM3"):
        if c in t:
            envelope(axs[0], t[c], COL[c], c.replace("_est", " (e-load − VM2 − VM3)"))
    axs[0].set_ylabel("Module voltage [V]")
    if not e.empty:
        ax2 = axs[1].twinx()
        ax2.spines["right"].set_visible(True)
        envelope(axs[1], e["v"], COL["v"], "V e-load")
        envelope(ax2, e["i"], COL["i"], "I e-load")
        axs[1].set_ylabel("E-load V [V]", color=COL["v"])
        ax2.set_ylabel("E-load I [A]", color=COL["i"])
        ax2.grid(False)
        h1, l1 = axs[1].get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        axs[1].legend(h1 + h2, l1 + l2, loc="upper left", ncol=2, fontsize=8)
    for c in ("dA1", "dB1", "dA2", "dB2"):
        envelope(axs[2], t[c], COL[c], c)
    axs[2].set_ylabel("Duty")
    for c in ("ILA1", "ILB1", "ILA2", "ILB2"):
        envelope(axs[3], t[c], COL[c], c)
    axs[3].set_ylabel("Inductor current [A]")
    axs[3].set_xlabel(f"Time ({TZ}), 13 Oct 2026" if t.index[0].day == 13 else f"Time ({TZ})")
    for ax in (axs[0], axs[2], axs[3]):
        ax.legend(loc="upper left", ncol=4, fontsize=8)
    axs[3].xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M", tz=t.index.tz))
    fig.suptitle(f"Bench open loop: {os.path.basename(prefix)} (line = 1 s mean, band = min/max)")
    for ext in ("svg", "pdf"):
        fig.savefig(f"{prefix}_overview.{ext}")
    plt.close(fig)


def oppoints(prefix, t, min_s=5.0, settle_s=1.0):
    duty = ["dA1", "dB1", "dA2", "dB2"]
    t = t.dropna(subset=["state"] + duty)   # 1 Hz status rows (heatsink etc.) carry no control fields
    ok =(t["state"] == "RUN_OL") & (t["VM2"] > 5) & (t["VM3"] > 5)
    if "V_eload" in t:
        ok &= t["V_eload"] > 60
    key = t[duty].round(3).astype(str).agg("/".join, axis=1)
    seg = ((key != key.shift()) | (ok != ok.shift())).cumsum()
    rows = []
    sig = [c for c in ("VM1_est", "VM2", "VM3", "V_eload", "ILA1", "ILB1", "ILA2", "ILB2", "IM1r", "IM2r", "T1", "T2")
           if c in t]
    for _, g in t[ok].groupby(seg[ok]):
        g = g[g.index >= g.index[0] + pd.Timedelta(seconds=settle_s)]   # drop the step transient
        if len(g) < 2 or (g.index[-1] - g.index[0]).total_seconds() < min_s:
            continue
        r = {"start": g.index[0], "stop": g.index[-1], "dur_s": (g.index[-1] - g.index[0]).total_seconds(),
             "n": len(g)}
        for d in duty:
            r[d] = g[d].iloc[0]
        for c in sig:
            r[c + "_mean"] = g[c].mean()
            r[c + "_std"] = g[c].std()
        r["ic1_mean"] = (g["ILA1"] + g["ILB1"]).mean()
        r["ic2_mean"] = (g["ILA2"] + g["ILB2"]).mean()
        r["id2_mean"] = (g["ILA2"] - g["ILB2"]).mean()
        rows.append(r)
    op = pd.DataFrame(rows)
    if op.empty:
        print(f"{prefix}: no steady segments found")
        return op
    op.to_csv(prefix + "_oppoints.csv", index=False, float_format="%.5g")

    active = "dA2" if op["dA2"].nunique() >= op["dA1"].nunique() else "dA1"
    k = active[-1]
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.2), constrained_layout=True)
    for c in ("VM1_est", "VM2", "VM3"):
        if c + "_mean" in op:
            axs[0].errorbar(op[active], op[c + "_mean"], yerr=op[c + "_std"], fmt="o", ms=3, capsize=2,
                            color=COL[c], label=c.replace("_est", " est"))
    axs[0].set_xlabel(f"duty {active} (= dB{k})")
    axs[0].set_ylabel("Mean module voltage [V]")
    for c in (f"ILA{k}", f"ILB{k}"):
        axs[1].errorbar(op[active], op[c + "_mean"], yerr=op[c + "_std"], fmt="o", ms=3, capsize=2,
                        color=COL[c], label=c)
    axs[1].plot(op[active], op[f"ic{k}_mean"], "k^", ms=4, label=f"ILA{k}+ILB{k}")
    axs[1].set_xlabel(f"duty {active}")
    axs[1].set_ylabel("Mean current [A]")
    for ax in axs:
        ax.legend(fontsize=8)
    fig.suptitle(f"Steady operating points ({len(op)} segments ≥ {min_s:.0f} s, error bar = 1σ)")
    for ext in ("svg", "pdf"):
        fig.savefig(f"{prefix}_oppoints.{ext}")
    plt.close(fig)
    return op


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prefix", nargs="+")
    ap.add_argument("--min-seg", type=float, default=5.0, help="shortest steady segment kept [s]")
    a = ap.parse_args()
    for p in a.prefix:
        t, e = load(p)
        overview(p, t, e)
        op = oppoints(p, t, a.min_seg)
        print(f"{p}: {len(t)} telemetry rows, {len(e)} e-load rows, {len(op)} steady segments")
        if not op.empty:
            cols = ["start", "dur_s", "dA1", "dA2", "dB2", "VM1_est_mean", "VM2_mean", "VM3_mean",
                    "ILA2_mean", "ILB2_mean", "ic2_mean"]
            cols = [c for c in cols if c in op]
            print(op[cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))


if __name__ == "__main__":
    main()
