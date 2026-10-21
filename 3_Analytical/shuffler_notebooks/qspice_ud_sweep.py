#!/usr/bin/env python3
"""Open-loop QSPICE experiment behind section 9 of shuffler_nstring.ipynb: the circulating-mode static
characteristic i_c(u_d) of the switching plant at 200 and 400 kHz (bench S10i / S10i4 netlists, RUN=4 =
u_d step on shuffler 1), the ripple of the two winding currents (which winding mode sees L+M) and the
voltage-mode ring after a u_c step (RUN=2). Writes data/qspice_ud_sweep.json (+ .npz with short traces)
so the notebook never needs QSPICE.

    python3 qspice_ud_sweep.py [--parallel 4] [--keep-qraw]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
PB = os.path.join(REPO, "2_Qspice", "Claude's outputs", "PCB_Baseline")
sys.path.insert(0, PB)
from s10_metrics import read as read_qraw  # noqa: E402

QSPICE = "/mnt/c/Program Files/QSPICE"
WORK = os.path.join(HERE, "data", "work_ud_sweep")
SUPPORT = [os.path.join(PB, "shuffler_models.lib"), os.path.join(PB, "stages", "shuffler_ctrl_dll2.DLL"),
           os.path.join(PB, "stages", "ctrl_M2.txt"), os.path.join(PB, "stages", "ctrl_M4.txt")]
BASES = {200: "S10i.cir", 400: "S10i4.cir"}
DUS = [0.0025, 0.005, 0.01, 0.02, 0.04, 0.08]
TEND = 2e-3
T_AVG = (1.5e-3, 2e-3)


def wpath(p):
    return subprocess.run(["wslpath", "-w", p], capture_output=True, text=True, check=True).stdout.strip()


def patch(text, run, du):
    out = []
    for ln in text.splitlines():
        if ln.startswith(".step"):
            continue
        if ln.startswith(".tran"):
            ln = f".tran 0 {TEND} 0 125n uic"
        if ln.startswith(".meas"):
            continue
        if ln.startswith(".param"):
            ln = re.sub(r"\bRUN=\S+", f"RUN={run}", ln)
            ln = re.sub(r"\bDU=\S+", f"DU={du}", ln)
        out.append(ln)
    return "\n".join(out) + "\n"


def cases():
    cs = [("f200_run1_du0", 200, 1, 0.0), ("f200_run2_du0.04", 200, 2, 0.04), ("f400_run1_du0", 400, 1, 0.0)]
    for f in (200, 400):
        for du in DUS:
            cs.append((f"f{f}_run4_du{du}", f, 4, du))
    return cs


def make(name, f, run, du):
    d = os.path.join(WORK, name)
    os.makedirs(d, exist_ok=True)
    text = open(os.path.join(PB, "stages", BASES[f]), "rb").read().decode("cp1252")
    open(os.path.join(d, name + ".cir"), "wb").write(patch(text, run, du).encode("cp1252"))
    for s in SUPPORT:
        dst = os.path.join(d, os.path.basename(s))
        if not os.path.exists(dst):
            open(dst, "wb").write(open(s, "rb").read())
    return d


def run(d, name):
    cir, log, qraw = (os.path.join(d, name + e) for e in (".cir", ".sim.txt", ".qraw"))
    if os.path.exists(qraw) and os.path.getsize(qraw) > 1000 and os.path.exists(log) and "Total elapsed" in open(log, errors="replace").read():
        return name, "cached", 0.0
    t0 = time.time()
    with open(log, "wb") as fh:
        r = subprocess.run([os.path.join(QSPICE, "QSPICE64.exe"), wpath(cir)], cwd=d, stdout=fh, stderr=subprocess.STDOUT, timeout=3600)
    txt = open(log, errors="replace").read()
    return name, ("ok" if r.returncode == 0 and "Total elapsed" in txt else "FAILED " + txt[-200:]), time.time() - t0


def wavg(t, y, a, b):
    m = (t >= a) & (t <= b)
    return float(np.trapz(y[m], t[m]) / (t[m][-1] - t[m][0]))


def extract(d, name, f, run, du, keep):
    names, D = read_qraw(os.path.join(d, name + ".qraw"))
    col = {n.lower(): i for i, n in enumerate(names)}
    t = np.asarray(D[:, col["time"]])
    g = lambda n: np.asarray(D[:, col[n.lower()]])
    iA1, iB1, iA2, iB2 = g("I(VsA1)"), g("I(VsB1)"), g("I(VsA2)"), g("I(VsB2)")
    v1, v2, v3 = g("V(PV1P)") - g("V(PV2P)"), g("V(PV2P)") - g("V(PV3P)"), g("V(PV3P)")
    a, b = T_AVG
    res = dict(case=name, f_khz=f, run=run, du=du,
               ic1=wavg(t, iA1 - iB1, a, b), im1=wavg(t, iA1 + iB1, a, b), ic2=wavg(t, iA2 - iB2, a, b), im2=wavg(t, iA2 + iB2, a, b),
               vd1=wavg(t, v1 - v2, a, b), vd2=wavg(t, v2 - v3, a, b), vm=[wavg(t, v, a, b) for v in (v1, v2, v3)],
               iA1_avg=wavg(t, iA1, a, b), iB1_avg=wavg(t, iB1, a, b))
    # ripple over the last 4 periods
    T = 1.0 / (f * 1e3)
    m = t >= b - 4 * T
    for nm, y in (("iA1", iA1), ("iB1", iB1), ("ic1", iA1 - iB1), ("im1", iA1 + iB1)):
        res[nm + "_pp"] = float(y[m].max() - y[m].min())
    traces = {}
    # two switching periods at full rate (ripple figure) and the first millisecond decimated to 0.5 us (ring / step figure)
    m2 = (t >= b - 2 * T) & (t <= b)
    traces["t_ripple"], traces["iA1_ripple"], traces["iB1_ripple"] = t[m2] - (b - 2 * T), iA1[m2], iB1[m2]
    tg = np.arange(0, 1.0e-3, 0.5e-6)
    for nm, y in (("vd1", v1 - v2), ("vd2", v2 - v3), ("ic1", iA1 - iB1), ("im1", iA1 + iB1)):
        traces[nm + "_step"] = np.interp(tg, t, y)
    traces["t_step"] = tg
    if not keep:
        os.remove(os.path.join(d, name + ".qraw"))
    return res, traces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--keep-qraw", action="store_true")
    a = ap.parse_args()
    cs = cases()
    dirs = {c[0]: make(*c) for c in cs}
    print(f"{len(cs)} cases, parallel {a.parallel}", flush=True)
    with ThreadPoolExecutor(a.parallel) as ex:
        for name, status, dt in ex.map(lambda c: run(dirs[c[0]], c[0]), cs):
            print(f"  {name:22s} {status:10s} {dt:6.0f} s", flush=True)
    rows, npz = [], {}
    for c in cs:
        try:
            r, tr = extract(dirs[c[0]], *c, keep=a.keep_qraw)
        except Exception as e:  # noqa: BLE001
            print("  extract failed", c[0], e)
            continue
        rows.append(r)
        for k, v in tr.items():
            npz[c[0] + "/" + k] = v
    json.dump(rows, open(os.path.join(HERE, "data", "qspice_ud_sweep.json"), "w"), indent=1)
    np.savez_compressed(os.path.join(HERE, "data", "qspice_ud_sweep.npz"), **npz)
    print("wrote data/qspice_ud_sweep.json and .npz")
    for r in rows:
        print(f"  {r['case']:22s} ic1 {r['ic1']:8.3f} A  im1 {r['im1']:7.3f}  vd1 {r['vd1']:7.3f}  iA1pp {r['iA1_pp']:5.2f}  ic1pp {r['ic1_pp']:5.2f}  im1pp {r['im1_pp']:5.2f}")


if __name__ == "__main__":
    main()
