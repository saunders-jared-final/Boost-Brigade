"""Analytical phase: the N = 3 string model of 3_Analytical/shuffler_notebooks/nstring.py closed with the gain set the
hardware ran (6_RTOS/ctrl_core/params/shuffler_params.<pver>.json, one per switching frequency), simulated at the
control tick for the matched scenarios:
  S1  loop close on a 0.5 V residual (what the hardware loop sees at RUN_CL entry after the soft-start ramp)
  S3  module 3 loses 1/3 of its current from a settled closed loop (PV80)
  S4  +1 V step on the VM2-VM3 reference
  S5  open-loop common-duty steps as sent on the bench on 16 Oct (uc2 +0.04; uc1 = uc2 = -0.02; uc1 +0.04)
The plant resistance per frequency is the identified switching resistance R_w + R_sw(f_sw) (DESIGN_LOG 6.7):
0.29 / 0.80 / 1.70 ohm at 200 / 300 / 400 kHz."""
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

KSCALES = (0.1, 0.2, 0.3, 0.4, 0.5, 1.0)
PRE = 2e-3
GAIN_SET = {200: "sps-params-2.20261015-1950-3mod-qspice200-bench",
            300: "sps-params-2.20261016-1628-3mod-qspice300-bench",
            400: "sps-params-2.20261016-1751-3mod-qspice400-bench"}
R_SW = {200: 0.29, 300: 0.80, 400: 1.70}        # ohm, identified effective winding-path resistance of the switching plant
DUTY_STEPS = [("uc2 +0.04", np.array([0.0, 0.04, 0.0, 0.0])),
              ("uc1 = uc2 = -0.02", np.array([-0.02, -0.02, 0.0, 0.0])),
              ("uc1 +0.04", np.array([0.04, 0.0, 0.0, 0.0]))]


def gain_set(f_khz):
    pver = GAIN_SET[f_khz]
    d = json.load(open(os.path.join(config.CTRL_PARAMS, f"shuffler_params.{pver}.json")))
    return np.array(d["ctrl"]["M"], float), d.get("version", pver)


def deployed_M():
    return gain_set(200)


def plants(f_khz=200):
    """PV80: three KAUSSP80 at Vmp into the DL3021 in CV. BENCH: the 16 Oct operating point seen in the telemetry - the
    e-load holds 70 V, so the three NGE103 channels sit at 23.3 V each, below their 25 V set point, i.e. all three in
    current limit (g = 0, the QSPICE S10i point); only in IDLE do channels 1 and 3 reach 25 V with channel 2 at 20 V."""
    R = R_SW[f_khz]
    return {"PV80": nstring.pv80(R_w=R), "BENCH": nstring.bench_qspice(V=23.3, R_w=R)}


def horizon(k):
    return max(0.06, 12.0 / (k * config.KI_V))


def _frame(t, Y, U, p, k, scenario, event, X=None, **extra):
    NS = p.N - 1
    data = {"t": t, "vd1": Y[:, 0], "vd2": Y[:, 1], "ic1": Y[:, NS], "ic2": Y[:, NS + 1]}
    if X is not None:                                   # shuffled currents i_m are plant states; potentials give VM
        for j in range(NS):
            data[f"id{j + 1}"] = X[:, p.N + j]
        phi = X[:, :p.N]
        for m in range(p.N):
            data[f"VM{m + 1}"] = phi[:, m] - (phi[:, m + 1] if m + 1 < p.N else 0.0)
    uc, ud = U[:, :NS], U[:, NS:]
    for j in range(NS):
        data[f"dA{j + 1}"] = 0.5 + 0.5 * (uc[:, j] + ud[:, j])
        data[f"dB{j + 1}"] = 0.5 + 0.5 * (uc[:, j] - ud[:, j])
    f = tidy.frame(data, phase="analytical", setup=p.label.split()[0], kscale=k, scenario=scenario, rate_hz=1 / config.TS,
                   source=f"nstring N={p.N} {p.label}", event=event, **extra)
    return f


def simulate_ol(p, T, u_step, w=None, t_step=PRE):
    """Open loop at the fixed point of duties 0.5 under PV deficit w, then the modal duty step u_step at t_step."""
    A, B, Bw, C, D = nstring.build_ss(p)
    Ad, Bd = nstring.discretise(A, np.hstack([B, Bw]), config.TS)
    nb = B.shape[1]
    w = np.zeros(p.N) if w is None else w
    x = -np.linalg.solve(A, Bw @ w)                     # open-loop fixed point
    n = int(round(T / config.TS))
    X, U, t = np.zeros((n, len(x))), np.zeros((n, nb)), np.arange(n) * config.TS - t_step
    for i in range(n):
        u = u_step if t[i] >= 0 else np.zeros(nb)
        X[i], U[i] = x, u
        x = Ad @ x + Bd @ np.concatenate([u, w])
    Y = X @ C.T
    return t, Y, U, X


def cases(scenario, f_khz=(200,)):
    if scenario not in ("S1", "S3", "S4", "S5"):
        return []
    out = []
    for f in f_khz:
        M, ver = gain_set(f)
        for setup, p in plants(f).items():
            if scenario == "S3" and setup != "PV80":
                continue
            if scenario == "S5":
                if setup != "BENCH":
                    continue
                for name, u in DUTY_STEPS:
                    w = np.zeros(p.N)
                    t, Y, U, X = simulate_ol(p, 0.06, u, w)
                    f_ = _frame(t, Y, U, p, None, scenario, f"open loop: {name}", X=X, gain_set="", f_khz=f, R_ohm=R_SW[f], ustep=u.tolist())
                    f_.attrs["kscale"] = 0.0
                    out.append(f_)
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
                    out.append(_frame(t, Y, U, p, k, scenario, ev, X=X, gain_set=ver, f_khz=f, R_ohm=R_SW[f]))
                    continue
                t = t - PRE
                out.append(_frame(t, Y, U, p, k, scenario, ev, X=cl.X, gain_set=ver, f_khz=f, R_ohm=R_SW[f]))
    return out


def design_tau(k):
    """First-order design time constants of the two loop types at gain scale k."""
    return {"vd": 1 / (k * config.KI_V), "ic": 1 / (k * config.KI_I)}


def settled_stats():
    return []
