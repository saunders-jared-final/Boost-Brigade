#!/usr/bin/env python3
"""Discriminator for the switching-plant 'effective resistance' (section 9 of shuffler_nstring.ipynb): the same
open-loop runs as qspice_ud_sweep.py (bench S10i / S10i4, RUN 1 baseline and RUN 4 u_d = 0.01) with the
STD45N10F7 model progressively idealised in the case-local copy of shuffler_models.lib:
   full      the hand-built model (reference, from qspice_ud_sweep)
   norr      body-diode transit time tt = 0 (no reverse recovery), capacitances kept
   nocap     no reverse recovery and no device capacitances (Cgs, Cgd, Cjo -> 1 pF): an ideal switch with dead time
Writes data/qspice_ideal_switch.json.
"""
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qspice_ud_sweep as q  # noqa: E402

VARIANTS = {
    "norr": {"tt": "0"},
    "nocap": {"tt": "0", "Cgs": "1p", "Cgdmin": "1p", "Cgdmax": "1p", "Cjo": "1p"},
}
q.WORK = os.path.join(q.HERE, "data", "work_ideal_switch")


def patch_lib(path, subs):
    txt = open(path, "rb").read().decode("cp1252")
    out = []
    for ln in txt.splitlines():
        if ln.startswith(".model STD45N10F7 "):
            for k, v in subs.items():
                ln = re.sub(rf"\b{k}=\S+", f"{k}={v}", ln)
        out.append(ln)
    open(path, "wb").write("\n".join(out).encode("cp1252"))


def main():
    cs = []
    for var in VARIANTS:
        for f in (200, 400):
            cs.append((f"{var}_f{f}_run1_du0", f, 1, 0.0, var))
            cs.append((f"{var}_f{f}_run4_du0.01", f, 4, 0.01, var))
    dirs = {}
    for name, f, run, du, var in cs:
        d = q.make(name, f, run, du)
        patch_lib(os.path.join(d, "shuffler_models.lib"), VARIANTS[var])
        dirs[name] = d
    print(f"{len(cs)} cases", flush=True)
    with ThreadPoolExecutor(4) as ex:
        for name, status, dt in ex.map(lambda c: q.run(dirs[c[0]], c[0]), cs):
            print(f"  {name:26s} {status:10s} {dt:6.0f} s", flush=True)
    rows = []
    for name, f, run, du, var in cs:
        try:
            r, _tr = q.extract(dirs[name], name, f, run, du, keep=False)
            r["variant"] = var
            rows.append(r)
        except Exception as e:  # noqa: BLE001
            print("  extract failed", name, e)
    json.dump(rows, open(os.path.join(q.HERE, "data", "qspice_ideal_switch.json"), "w"), indent=1)
    for r in rows:
        print(f"  {r['case']:26s} ic1 {r['ic1']:8.3f} A  im1 {r['im1']:7.3f}  vd1 {r['vd1']:7.3f}  ic1pp {r['ic1_pp']:5.2f}")


if __name__ == "__main__":
    main()
