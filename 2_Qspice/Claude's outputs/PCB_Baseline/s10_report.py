#!/usr/bin/env python3
"""Gate-4 closed-loop summary for the S10 / S10n / S10p stages (results/<stage>.meas.json).

    python s10_report.py S10 [--labels "MSEL=0 K=0.3" ...]

Per step: settled v_diff errors before the step (a), after the Vref2 +2 V step (b) and after the
module-3 shade step (c); circulating current |ic|; steady-state std of v_diff2 / duty dA2 / ic2 from
RMS and AVG (limit cycle and noise); overshoot and 98 % time of the step; peak phase current; governor.
Pass criteria (plan, Gate 4): settle < 5 ms (98 % time used), overshoot < 25 %, duty std < 0.002 (0.003
with noise), |ic| < 0.5 A, peak phase current < 8 A.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
T_STEP = 2e-3
VSTEP = 2.0


def std(rms, avg):
    return math.sqrt(max(rms * rms - avg * avg, 0.0))


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "S10"
    labels = sys.argv[sys.argv.index("--labels") + 1:] if "--labels" in sys.argv else []
    m = json.load(open(os.path.join(HERE, "results", stage + ".meas.json")))
    n = max(len(v) for v in m.values())
    g = lambda k, i: (m.get(k) or [float("nan")] * n)[i] if i < len(m.get(k) or []) else float("nan")
    noise = stage == "S10n"
    rows = []
    for i in range(n):
        r = {"step": labels[i] if i < len(labels) else f"step {i + 1}"}
        r["vd1a"], r["vd2a"] = g("vd1a", i), g("vd2a", i)
        r["vd2b_err"] = g("vd2b", i) - VSTEP
        r["vd1b"] = g("vd1b", i)
        r["vd1c"], r["vd2c_err"] = g("vd1c", i), g("vd2c", i) - VSTEP
        r["ic_max"] = max(abs(g(f"ic{k}{w}", i)) for k in (1, 2) for w in "abc")
        r["std_vd2"] = std(g("vd2br", i), g("vd2b", i))
        r["std_da2"] = max(std(g(f"da2{w}r", i), g(f"da2{w}", i)) for w in "bc")
        r["std_ic2"] = std(g("ic2br", i), g("ic2b", i))
        r["overshoot_%"] = 100 * (g("vd2max", i) - VSTEP) / VSTEP
        r["t98_ms"] = (g("t98", i) - T_STEP) * 1e3
        r["ipk"] = max(max(abs(g(f"vs{p}{k}max", i)), abs(g(f"vs{p}{k}min", i))) for p in "ab" for k in (1, 2))
        r["beta_max"] = g("betamax", i)
        lim_d = 0.003 if noise else 0.002
        ok = (r["overshoot_%"] < 25 and 0 < r["t98_ms"] < 5 and r["std_da2"] < lim_d and r["ic_max"] < 0.5
              and r["ipk"] < 8 and abs(r["vd2b_err"]) < 0.1 and abs(r["vd2c_err"]) < 0.1)
        r["PASS"] = "PASS" if ok else "fail"
        rows.append(r)
    keys = list(rows[0].keys())
    w = max(len(k) for k in keys) + 1
    print(f"{stage}: {n} steps")
    for k in keys:
        cells = []
        for r in rows:
            v = r[k]
            cells.append(f"{v:>12.4g}" if isinstance(v, float) else f"{v:>12}")
        print(f"{k:<{w}}" + "".join(cells))
    json.dump(rows, open(os.path.join(HERE, "results", stage + ".summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
