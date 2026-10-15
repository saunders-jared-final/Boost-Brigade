#!/usr/bin/env python3
"""Gate-4 closed-loop metrics straight from a stepped S10/S10n/S10p .qraw (numpy; QPOST is too slow on the
~0.5 GB files). Step labels come from the "k of n steps: .step ..." lines of results/<stage>.sim.txt.

    python s10_metrics.py S10            -> table + results/S10.summary.json (+ .md table)

Windows (s): a = 1.5..2.0 settled, Vref2 +2 V step at 2.0, b = 2.6..3.0 settled, module-3 shade at 3.0,
c = 3.6..4.0 settled. Averages/RMS are time-weighted (trapezoid). Pass criteria (plan, Gate 4):
98 % time < 5 ms (< 1 ms window here = 'settles'), overshoot < 25 %, duty std < 0.002 (0.003 with noise),
|ic| < 0.5 A, peak phase current < 8 A, settled v_diff errors < 0.1 V.
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TA, TSTEP, TB, TSHADE, TC, TEND = 1.5e-3, 2e-3, 2.6e-3, 3e-3, 3.6e-3, 4e-3
VSTEP = 2.0


def read(path):
    with open(path, "rb") as f:
        head = f.read(20000)
    i = head.find(b"Binary:")
    hdr = head[:i].decode("cp1252", "replace")
    nv = int(re.search(r"No\. Variables:\s*(\d+)", hdr).group(1))
    npt = int(re.search(r"No\. Points:\s*(\d+)", hdr).group(1))
    names = [m.group(2) for m in re.finditer(r"^\t(\d+)\t(\S+)\t(\S+)", hdr, re.M)]
    data = np.memmap(path, dtype="<f8", mode="r", offset=i + len(b"Binary:\n"), shape=(npt, nv))
    return names, data


def wavg(t, y, a, b):
    m = (t >= a) & (t <= b)
    tt, yy = t[m], y[m]
    if len(tt) < 2:
        return float("nan"), float("nan")
    T = tt[-1] - tt[0]
    av = np.trapz(yy, tt) / T
    rms = np.sqrt(np.trapz(yy * yy, tt) / T)
    return float(av), float(np.sqrt(max(rms * rms - av * av, 0.0)))


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "S10"
    names, D = read(os.path.join(HERE, "stages", stage + ".qraw"))
    col = {n.lower(): k for k, n in enumerate(names)}
    t_all = np.asarray(D[:, 0])
    starts = [0] + list(np.nonzero(np.diff(t_all) < 0)[0] + 1) + [len(t_all)]
    log = open(os.path.join(HERE, "results", stage + ".sim.txt"), encoding="utf-8", errors="replace").read()
    labels = [m.group(1).strip() for m in re.finditer(r"\d+ of \d+ steps:\s*\.step\s*(.*)", log)]
    noise = stage == "S10n"
    rows = []
    for s in range(len(starts) - 1):
        a, b = starts[s], starts[s + 1]
        t = t_all[a:b]
        g = lambda n: np.asarray(D[a:b, col[n]])
        vd1 = g("v(pv1p)") - 2 * g("v(pv2p)") + g("v(pv3p)")
        vd2 = g("v(pv2p)") - 2 * g("v(pv3p)")
        ia1, ib1, ia2, ib2 = g("i(vsa1)"), g("i(vsb1)"), g("i(vsa2)"), g("i(vsb2)")
        ic1, ic2 = ia1 - ib1, ia2 - ib2
        da2 = g("v(da2)")
        r = {"step": labels[s] if s < len(labels) else f"step {s + 1}"}
        r["vd1a"], _ = wavg(t, vd1, TA, TSTEP)
        r["vd2a"], _ = wavg(t, vd2, TA, TSTEP)
        vd2b, _ = wavg(t, vd2, TB, TSHADE)
        r["vd2b_err"] = vd2b - VSTEP
        r["vd1b"], _ = wavg(t, vd1, TB, TSHADE)
        r["vd1c"], _ = wavg(t, vd1, TC, TEND)
        vd2c, _ = wavg(t, vd2, TC, TEND)
        r["vd2c_err"] = vd2c - VSTEP
        ics = [wavg(t, x, w0, w1)[0] for x in (ic1, ic2) for (w0, w1) in ((TA, TSTEP), (TB, TSHADE), (TC, TEND))]
        r["ic_max"] = max(abs(v) for v in ics)
        # steady-state jitter / limit cycle: 100 us (one control tick) bin means, std over the settled
        # pre-step window a and the late window c2 (3.7..4.0 ms), worst of the two
        def tick_std(y, w0, w1):
            edges = np.arange(w0, w1 + 1e-12, 1e-4)
            means = [wavg(t, y, edges[j], edges[j + 1])[0] for j in range(len(edges) - 1)]
            return float(np.std(means))
        r["std_vd2"] = max(tick_std(vd2, TA, TSTEP), tick_std(vd2, 3.7e-3, TEND))
        r["std_ic2"] = max(tick_std(ic2, TA, TSTEP), tick_std(ic2, 3.7e-3, TEND))
        r["std_da2"] = max(tick_std(da2, TA, TSTEP), tick_std(da2, 3.7e-3, TEND))
        r["vd2_at_shade_%"] = 100 * wavg(t, vd2, TSHADE - 1e-4, TSHADE)[0] / VSTEP
        m = (t >= TSTEP) & (t <= TSHADE)
        r["overshoot_%"] = 100 * (float(vd2[m].max()) - VSTEP) / VSTEP
        k = np.nonzero(m & (vd2 >= 0.98 * VSTEP))[0]
        r["t98_ms"] = (float(t[k[0]]) - TSTEP) * 1e3 if len(k) else float("nan")
        m = (t >= 0.5e-3) & (t <= TEND)
        r["ipk"] = float(max(np.abs(x[m]).max() for x in (ia1, ib1, ia2, ib2)))
        r["d_range"] = f"{min(g(n)[m].min() for n in ('v(da1)', 'v(db1)', 'v(da2)', 'v(db2)')):.3f}-" \
                       f"{max(g(n)[m].max() for n in ('v(da1)', 'v(db1)', 'v(da2)', 'v(db2)')):.3f}"
        r["beta_max"] = float(g("v(beta)")[m].max())
        r["pout_c"], _ = wavg(t, g("v(pv1p)") * g("i(bload)"), TC, TEND)
        lim_d = 0.003 if noise else 0.002
        ok = (r["overshoot_%"] < 25 and 0 < r["t98_ms"] < 1.0 and r["std_da2"] < lim_d and r["ic_max"] < 0.5
              and r["ipk"] < 8 and abs(r["vd2b_err"]) < 0.1 and abs(r["vd2c_err"]) < 0.1)
        r["PASS"] = "PASS" if ok else "fail"
        rows.append(r)
    keys = list(rows[0].keys())
    w = max(len(k) for k in keys) + 1
    lines = []
    for k in keys:
        cells = [(f"{r[k]:.4g}" if isinstance(r[k], float) else str(r[k])) for r in rows]
        lines.append(f"{k:<{w}}" + "".join(f"{c:>24}" for c in cells))
    print("\n".join(lines))
    json.dump(rows, open(os.path.join(HERE, "results", stage + ".summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
