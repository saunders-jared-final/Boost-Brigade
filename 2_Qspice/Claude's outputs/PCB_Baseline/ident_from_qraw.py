#!/usr/bin/env python3
"""S10i settled outputs straight from the .qraw (when QPOST is too slow for the parasitic model):
time-weighted means over 2..3 ms per .step run, written as results/<stage>.meas.json in the shape
qspice_ident.py reads (y1..y4 per RUN, plus ish1/ish2 and the module voltages).

    python ident_from_qraw.py S10i && python qspice_ident.py --meas results/S10i.meas.json --du 0.02
"""
import json
import os
import sys

import numpy as np

import s10_metrics as sm

HERE = os.path.dirname(os.path.abspath(__file__))
A, B = 2e-3, 3e-3


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "S10i"
    names, D = sm.read(os.path.join(HERE, "stages", stage + ".qraw"))
    col = {n.lower(): k for k, n in enumerate(names)}
    t_all = np.asarray(D[:, 0])
    starts = [0] + list(np.nonzero(np.diff(t_all) < 0)[0] + 1) + [len(t_all)]
    out = {k: [] for k in ("y1", "y2", "y3", "y4", "ish1", "ish2", "vm1", "vm2", "vm3")}
    for s in range(len(starts) - 1):
        a, b = starts[s], starts[s + 1]
        t = t_all[a:b]
        g = lambda n: np.asarray(D[a:b, col[n]])
        sig = {
            "y1": g("v(pv1p)") - 2 * g("v(pv2p)") + g("v(pv3p)"),
            "y2": g("v(pv2p)") - 2 * g("v(pv3p)"),
            "y3": g("i(vsa1)") - g("i(vsb1)"),
            "y4": g("i(vsa2)") - g("i(vsb2)"),
            "ish1": g("i(vsa1)") + g("i(vsb1)"),
            "ish2": g("i(vsa2)") + g("i(vsb2)"),
            "vm1": g("v(pv1p)") - g("v(pv2p)"),
            "vm2": g("v(pv2p)") - g("v(pv3p)"),
            "vm3": g("v(pv3p)"),
        }
        for k, y in sig.items():
            out[k].append(sm.wavg(t, y, A, B)[0])
    json.dump(out, open(os.path.join(HERE, "results", stage + ".meas.json"), "w"), indent=1)
    for k, v in out.items():
        print(f"{k:5s}", " ".join(f"{x:9.4f}" for x in v))


if __name__ == "__main__":
    main()
