#!/usr/bin/env python3
"""Bench identification of the 2-shuffler plant through the firmware (open loop):
baseline + 4 modal duty steps (u_comm_k, u_diff_k) -> settled means of
y = [VM1-VM2, VM2-VM3, ic1, ic2] -> G (4x4) -> M = G \\ diag(kI).
Mirrors 4_Simulink/3_Carpark_3mod/shuffler_string_ident.m; used as the
Wednesday cross-check of the Simulink identification (not the primary source).

    python3 ident.py --port /dev/ttyACM0 --du 0.04 --settle 0.5 --avg 0.5 [--write-json]
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import serial

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pod"))
from telemetry_parser import parse_line  # noqa: E402

KI_V = 2 * np.pi * 150.0
KI_I = 2 * np.pi * 400.0
JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "6_RTOS", "ctrl_core", "params", "shuffler_params.json")


class Link:
    def __init__(self, port, baud):
        self.ser = serial.Serial(port, baud, timeout=0.2)
        self.buf = b""

    def cmd(self, c, timeout=1.0):
        self.ser.write((c + "\n").encode())
        t0 = time.time()
        while time.time() - t0 < timeout:
            fr = self.frame()
            if fr and fr.kind == "A":
                if not fr.values["ok"]:
                    raise RuntimeError(f"{c}: {fr.values['why']}")
                return fr
        raise TimeoutError(c)

    def frame(self):
        self.buf += self.ser.read(256)
        if b"\n" not in self.buf:
            return None
        line, self.buf = self.buf.split(b"\n", 1)
        return parse_line(line.decode(errors="replace"))

    def collect(self, seconds):
        rows = []
        t0 = time.time()
        while time.time() - t0 < seconds:
            fr = self.frame()
            if fr and fr.kind == "T":
                if fr.state == "FAULT":
                    raise RuntimeError("firmware FAULT during identification")
                rows.append(fr.values)
        return rows


def y_of(rows):
    v = {k: np.mean([r[k] for r in rows]) for k in ("VM1", "VM2", "VM3", "ILA1", "ILB1", "ILA2", "ILB2")}
    return np.array([v["VM1"] - v["VM2"], v["VM2"] - v["VM3"], v["ILA1"] + v["ILB1"], v["ILA2"] + v["ILB2"]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--du", type=float, default=0.04)
    ap.add_argument("--settle", type=float, default=0.5)
    ap.add_argument("--avg", type=float, default=0.5)
    ap.add_argument("--write-json", action="store_true", help="store M into shuffler_params.json (ctrl.M)")
    a = ap.parse_args()
    L = Link(a.port, a.baud)
    d0 = 0.5
    runs = [[d0] * 4 for _ in range(5)]
    runs[1][0] = runs[1][1] = d0 + a.du / 2                      # u_comm_1
    runs[2][2] = runs[2][3] = d0 + a.du / 2                      # u_comm_2
    runs[3][0], runs[3][1] = d0 + a.du / 2, d0 - a.du / 2        # u_diff_1
    runs[4][2], runs[4][3] = d0 + a.du / 2, d0 - a.du / 2        # u_diff_2

    L.cmd("C,MODE,OL")
    L.cmd("C,DUTYS,0.5,0.5,0.5,0.5")
    L.cmd("C,EN,1")
    time.sleep(0.5)
    Y = []
    for k, d in enumerate(runs):
        L.cmd("C,DUTYS," + ",".join(f"{x:.4f}" for x in d))
        time.sleep(a.settle)
        rows = L.collect(a.avg)
        y = y_of(rows)
        Y.append(y)
        print(f"run {k}: d={d}  vd=[{y[0]:+.3f} {y[1]:+.3f}]  ic=[{y[2]:+.2f} {y[3]:+.2f}]  ({len(rows)} frames)")
    L.cmd("C,DUTYS,0.5,0.5,0.5,0.5")
    L.cmd("C,EN,0")
    Y = np.array(Y)
    G = (Y[1:] - Y[0]).T / a.du
    print("\nG =\n", np.array2string(G, precision=4, suppress_small=True))
    print(f"cond(G) = {np.linalg.cond(G):.1f}")
    M = np.linalg.solve(G, np.diag([KI_V, KI_V, KI_I, KI_I]))
    print("\nM =\n", np.array2string(M, precision=6, suppress_small=True))
    if a.write_json:
        J = json.load(open(JSON_PATH))
        J["ctrl"]["M"] = M.tolist()
        J["version"] = time.strftime("sps-params-2.%Y%m%d-%H%M-3mod-bench")
        json.dump(J, open(JSON_PATH, "w"), indent=2)
        print("wrote", JSON_PATH, J["version"], "-> run gen_params.py and rebuild the firmware")


if __name__ == "__main__":
    main()
