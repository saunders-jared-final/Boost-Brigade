#!/usr/bin/env python3
"""Switching ripple of the winding currents per switching frequency (T6): the analytical law, QSPICE (device model,
S10i open-loop identification stages at u_d = 0, 2-3 ms settled), the switching twin values already extracted in
3_Analytical/shuffler_notebooks/data/qspice_ud_sweep.json, and the hardware's sample-to-sample noise (45 Hz
telemetry of a sensing-filtered current: NOT the switching ripple) for contrast.

    python3 ripple.py            # -> out/tables/T6_ripple.{csv,md}, out/qspice/ripple_<f>k.csv (two-period waveforms)

Analytical (shuffler_nstring.ipynb section 8.1, as built: the circulating mode sees L + M):
    delta i_c = Vbar / (2 f_sw (L + M)),   per leg  delta i_A = Vbar / (4 f_sw (L + M)),   Vbar = string / N-1 ... = 2 x 23.3 V
"""
import json
import os
import sys

import numpy as np
import pandas as pd

import config

TAB = os.path.join(config.OUT, "tables")
QOUT = os.path.join(config.OUT, "qspice")
L_PLUS_M = 7.9e-6 + 5.85e-6
RAW = {300: ("S10i3.qraw", 1), 400: ("S10i4.qraw", 1)}          # stage, run index (1 = baseline, du = 0)


def analytical(vbar, f_hz):
    return {"ic_pp": vbar / (2 * f_hz * L_PLUS_M), "leg_pp": vbar / (4 * f_hz * L_PLUS_M)}


def from_sweep():
    rows = []
    sw = json.load(open(os.path.join(config.NOTEBOOKS, "data", "qspice_ud_sweep.json")))
    for r in sw:
        if r.get("run") == 1 and abs(r.get("du", 0)) < 1e-9:
            rows.append({"f_khz": r["f_khz"], "source": "QSPICE S10i (ud sweep, du = 0)", "ic_pp_A": r["ic1_pp"], "leg_pp_A": r["iA1_pp"],
                         "im_pp_A": r["im1_pp"], "vbar_V": r["vm"][0] + r["vm"][1]})
    return rows


def from_raw(f_khz, n_periods=2):
    """Two settled switching periods of i(vsa1), i(vsb1) from the raw QSPICE file of the S10i stage at f_khz."""
    stage, run = RAW[f_khz]
    path = os.path.join(config.PCB_BASELINE, "stages", stage)
    if not os.path.exists(path):
        return None, None
    sys.path.insert(0, config.PCB_BASELINE)
    from s10_metrics import read
    names, D = read(path)
    col = {n.lower(): k for k, n in enumerate(names)}
    t_all = np.asarray(D[:, 0])
    starts = [0] + list(np.nonzero(np.diff(t_all) < 0)[0] + 1) + [len(t_all)]
    a, b = starts[run - 1], starts[run]
    t = t_all[a:b]
    T = 1.0 / (f_khz * 1e3)
    t0 = 2.5e-3
    m = (t >= t0) & (t < t0 + n_periods * T)
    ia, ib = np.asarray(D[a:b, col["i(vsa1)"]])[m], np.asarray(D[a:b, col["i(vsb1)"]])[m]
    pv1, pv2, pv3 = (np.asarray(D[a:b, col[n]])[m] for n in ("v(pv1p)", "v(pv2p)", "v(pv3p)"))
    tt = t[m] - t0
    # firmware sign: ILB = -i(vsb)  ->  i_c = ILA + ILB = ia - ib,  i_sh = ILA - ILB = ia + ib
    df = pd.DataFrame({"t_s": tt, "ILA1": ia, "ILB1": -ib, "ic1": ia - ib, "id1": ia + ib})
    row = {"f_khz": f_khz, "source": f"QSPICE {stage} raw, run {run} (du = 0), 2.5 ms", "ic_pp_A": float(df["ic1"].max() - df["ic1"].min()),
           "leg_pp_A": float(df["ILA1"].max() - df["ILA1"].min()), "im_pp_A": float(df["id1"].max() - df["id1"].min()),
           "vbar_V": float((pv1 - pv3).mean()), "n_samples": int(m.sum())}
    return df, row


def hardware_noise():
    """Sample-to-sample pk-pk and std of the winding currents per frequency (T2 settled segments) for contrast."""
    p = os.path.join(TAB, "T2_hw_steady_state.csv")
    if not os.path.exists(p):
        return []
    t2 = pd.read_csv(p)
    rows = []
    for f, g in t2.groupby("f_khz"):
        g = g[g["duration_s"] > 20]
        if g.empty:
            continue
        rows.append({"f_khz": int(f), "source": f"hardware telemetry noise ({g['rate_hz'].median():.0f} Hz samples, {len(g)} segments)",
                     "ic_pp_A": float(g["ic2_pkpk"].median()), "leg_pp_A": float(np.nan), "im_pp_A": float(g["id2_pkpk"].median()),
                     "vbar_V": float(2 * g["VM2_mean"].median()) if "VM2_mean" in g else np.nan, "ic_std_A": float(g["ic2_std"].median())})
    return rows


def main():
    os.makedirs(TAB, exist_ok=True)
    os.makedirs(QOUT, exist_ok=True)
    rows = []
    for f in (200, 300, 400):
        a = analytical(46.6, f * 1e3)
        rows.append({"f_khz": f, "source": "analytical Vbar/(2 f (L+M)), Vbar 46.6 V", "ic_pp_A": a["ic_pp"], "leg_pp_A": a["leg_pp"], "im_pp_A": 0.0, "vbar_V": 46.6})
    rows += from_sweep()
    for f in (300, 400):
        cache = os.path.join(QOUT, f"ripple_{f}k.csv")
        if os.path.exists(cache + ".json"):
            rows.append(json.load(open(cache + ".json")))
            continue
        df, row = from_raw(f)
        if df is not None:
            df.to_csv(cache, index=False)
            json.dump(row, open(cache + ".json", "w"))
            rows.append(row)
            print(f"{f} kHz raw: ic pk-pk {row['ic_pp_A']:.2f} A, leg {row['leg_pp_A']:.2f} A ({row['n_samples']} samples)")
    rows += hardware_noise()
    T6 = pd.DataFrame(rows).sort_values(["f_khz", "source"])
    T6.to_csv(os.path.join(TAB, "T6_ripple.csv"), index=False)
    lines = ["| f_sw [kHz] | source | i_c pk-pk [A] | per-leg pk-pk [A] | i_sh pk-pk [A] | Vbar [V] |", "|---|---|---|---|---|---|"]
    for _, r in T6.iterrows():
        f_ = lambda v: "-" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.3g}"
        lines.append(f"| {int(r['f_khz'])} | {r['source']} | {f_(r['ic_pp_A'])} | {f_(r['leg_pp_A'])} | {f_(r['im_pp_A'])} | {f_(r['vbar_V'])} |")
    open(os.path.join(TAB, "T6_ripple.md"), "w").write("\n".join(lines) + "\n")
    print(T6.to_string(index=False))


if __name__ == "__main__":
    main()
