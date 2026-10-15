#!/usr/bin/env python3
"""Plant identification from stage S9i: results/S9i.meas.json holds, per RUN (1 baseline,
2 u_comm_1, 3 u_comm_2, 4 u_diff_1, 5 u_diff_2), the settled y = [VM1-VM2, VM2-VM3, ic1, ic2]
in the control stack's conventions. G = dy/du, M = G \\ diag(kI) exactly as
4_Simulink/3_Carpark_3mod/shuffler_string_ident.m does on the averaged model.

    python qspice_ident.py [--du 0.04] [--write]     # --write: M -> 6_RTOS/ctrl_core/params/shuffler_params.json
then: python3 6_RTOS/ctrl_core/params/gen_params.py && 2_Qspice/ctrl_dll/build_dll.bat && run S9
"""
import argparse
import json
import os
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(HERE, "..", "..", "..", "6_RTOS", "ctrl_core", "params", "shuffler_params.json")
KI_V = 2 * np.pi * 150.0
KI_I = 2 * np.pi * 400.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--du", type=float, default=0.04)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--mfile", help="also write M (16 numbers, row-major) for shuffler_ctrl_dll2 MSEL=2, e.g. stages/ctrl_M2.txt")
    ap.add_argument("--simulink", action="store_true", help="compare with the M in shuffler_params.json (Simulink ident)")
    ap.add_argument("--meas", default=os.path.join(HERE, "results", "S9i.meas.json"))
    a = ap.parse_args()
    d = json.load(open(a.meas))
    Y = np.array([d[f"y{k}"] for k in (1, 2, 3, 4)], dtype=float).T   # runs x 4
    assert Y.shape[0] == 5, f"expected 5 runs, got {Y.shape[0]}"
    print("settled y per run (vd1 vd2 ic1 ic2):")
    for r in range(5):
        print(f"  RUN {r+1}: " + " ".join(f"{v:9.4f}" for v in Y[r]))
    G = (Y[1:] - Y[0]).T / a.du
    print("\nG (y per unit duty; columns u_comm_1 u_comm_2 u_diff_1 u_diff_2):\n", np.array2string(G, precision=3, suppress_small=True))
    print(f"cond(G) = {np.linalg.cond(G):.1f}")
    dg = np.diag(G[2:, 2:])
    print("u_diff -> ic diagonals:", dg, "(sign must match the firmware/hardware; Simulink 4-mod ident had negative)")
    M = np.linalg.solve(G, np.diag([KI_V, KI_V, KI_I, KI_I]))
    print("\nM = G \\ diag(kI):\n", np.array2string(M, precision=6, suppress_small=True))
    if a.simulink:
        Ms = np.array(json.load(open(JSON_PATH))["ctrl"]["M"], dtype=float)
        Gs = np.diag([KI_V, KI_V, KI_I, KI_I]) @ np.linalg.inv(Ms)
        print("\nG of the JSON M (G = diag(kI) M^-1):\n", np.array2string(Gs, precision=3, suppress_small=True))
        print("diag ratio G_qspice / G_json:", np.round(np.diag(G) / np.diag(Gs), 3))
    if a.mfile:
        with open(a.mfile, "w") as f:
            for r in M:
                f.write(" ".join(f"{x:.9g}" for x in r) + "\n")
        print("wrote", a.mfile)
    if a.write:
        J = json.load(open(JSON_PATH))
        J["ctrl"]["M"] = M.tolist()
        J["version"] = time.strftime("sps-params-2.%Y%m%d-%H%M-3mod-qspice")
        json.dump(J, open(JSON_PATH, "w"), indent=2)
        open(JSON_PATH, "a").write("\n")
        print("\nwrote", os.path.normpath(JSON_PATH), J["version"])


if __name__ == "__main__":
    main()
