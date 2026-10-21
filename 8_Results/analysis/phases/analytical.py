"""Analytical phase: the N = 3 string model of 3_Analytical/shuffler_notebooks/nstring.py closed with the deployed
gain matrix (6_RTOS/ctrl_core/params/shuffler_params.json), simulated at the control tick for the matched scenarios."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import config      # noqa: E402
import tidy        # noqa: E402

sys.path.insert(0, config.NOTEBOOKS)
import nstring     # noqa: E402

KSCALES = (0.1, 0.3, 1.0)
PRE = 2e-3


def deployed_M():
    d = json.load(open(os.path.join(config.CTRL_PARAMS, "shuffler_params.json")))
    return np.array(d["ctrl"]["M"], float), d.get("version", "")


def plants():
    # switching-plant resistance R_w + R_sw(200 kHz) = 0.29 ohm in both winding modes (shuffler_nstring.ipynb section 8);
    # BENCH = the QSPICE S10 operating point (all three NGE channels in current limit, 23.3 V)
    return {"PV80": nstring.pv80(R_w=0.29), "BENCH": nstring.bench_qspice(R_w=0.29)}


def horizon(k):
    return max(0.06, 12.0 / (k * config.KI_V))


def _frame(t, Y, U, p, k, scenario, event, X=None, **extra):
    NS = p.N - 1
    data = {"t": t, "vd1": Y[:, 0], "vd2": Y[:, 1], "ic1": Y[:, NS], "ic2": Y[:, NS + 1]}
    if X is not None:                                   # shuffled currents i_m are plant states
        for j in range(NS):
            data[f"id{j + 1}"] = X[:, p.N + j]
    uc, ud = U[:, :NS], U[:, NS:]
    for j in range(NS):
        data[f"dA{j + 1}"] = 0.5 + 0.5 * (uc[:, j] + ud[:, j])
        data[f"dB{j + 1}"] = 0.5 + 0.5 * (uc[:, j] - ud[:, j])
    f = tidy.frame(data, phase="analytical", setup=p.label.split()[0], kscale=k, scenario=scenario, rate_hz=1 / config.TS,
                   source=f"nstring N={p.N} {p.label}", event=event, **extra)
    return f


def cases(scenario):
    if scenario not in ("S1", "S3", "S4"):
        return []
    M, ver = deployed_M()
    out = []
    for setup, p in plants().items():
        if scenario == "S3" and setup != "PV80":
            continue
        for k in KSCALES:
            cl = nstring.ClosedLoop(p, M=M, kscale=k)
            T = horizon(k)
            NS = p.N - 1
            npre = int(round(PRE / config.TS))
            if scenario == "S4":
                r = lambda t: np.array([0, 1.0] + [0] * NS) if t >= 0 else np.zeros(2 * NS)
                t, Y, U = cl.simulate(T, r=lambda tt: r(tt - PRE))
                ev = "Vref2 0 -> +1 V"
            elif scenario == "S3":
                w3 = np.zeros(p.N)
                w3[-1] = -3.9 / 3.0                                          # 1/3 of Imp off the bottom module
                t, Y, U = cl.simulate(T, w=lambda tt: w3 if tt >= PRE else np.zeros(p.N))
                ev = "module 3 current -1/3 Imp"
            else:
                # open loop at 0.5 duty already equalises the modules; what the loop removes is the resistive residual.
                # Scale the module-3 deficit so that residual is 0.5 V on vd2, the size seen on the hardware after soft start.
                w = np.zeros(p.N)
                w[-1] = -1.0
                y0 = cl.C @ cl.ol_fixed_point(w)
                w *= 0.5 / max(abs(y0[1]), 1e-9)
                x0 = cl.ol_fixed_point(w)
                t, Y, U = cl.simulate(T - PRE, w=lambda tt: w, x0=x0)
                X = cl.X
                y0 = cl.C @ x0
                tpre = -np.arange(npre, 0, -1) * config.TS
                t = np.concatenate([tpre, t])
                Y = np.vstack([np.tile(y0, (npre, 1)), Y])
                U = np.vstack([np.zeros((npre, U.shape[1])), U])
                X = np.vstack([np.tile(x0, (npre, 1)), X])
                ev = f"OL -> CL on vd_OL = [{y0[0]:.2f}, {y0[1]:.2f}] V ({-w[-1]:.2f} A deficit on module 3)"
                out.append(_frame(t, Y, U, p, k, scenario, ev, X=X, gain_set=ver))
                continue
            t = t - PRE
            out.append(_frame(t, Y, U, p, k, scenario, ev, X=cl.X, gain_set=ver))
    return out


def settled_stats():
    return []
