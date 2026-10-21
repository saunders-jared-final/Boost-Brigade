#!/usr/bin/env python3
"""Pipeline: pull -> events -> compare (hardware + whatever simulation outputs exist) -> report.

    python3 run_all.py [--skip pull,qspice,simulink] [--only events,compare]

qspice and simulink stages launch the long runs (hours / an hour) and are skipped unless named with --with.
"""
import argparse
import os
import subprocess
import sys

import config

STAGES = ["pull", "events", "qspice", "simulink", "notebook", "compare", "report"]


def sh(cmd, cwd=None):
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd or config.HERE).returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--with", dest="with_", default="", help="long stages to include: qspice,simulink")
    a = ap.parse_args()
    skip = set(a.skip.split(",")) - {""}
    only = set(a.only.split(",")) - {""}
    with_ = set(a.with_.split(",")) - {""}
    for st in STAGES:
        if only and st not in only:
            continue
        if st in skip or (st in ("qspice", "simulink") and st not in with_ and not only):
            continue
        if st == "pull":
            sh([sys.executable, "influx_pull.py"])
        elif st == "events":
            sh([sys.executable, "events.py", "--plot"])
        elif st == "qspice":
            sh([sys.executable, "run_scenarios.py", "--all", "--parallel", "4"], cwd=config.QSPICE_OUT)
        elif st == "simulink":
            w = subprocess.run(["wslpath", "-w", os.path.join(config.REPO, "4_Simulink", "3_Carpark_3mod")], capture_output=True, text=True).stdout.strip()
            o = subprocess.run(["wslpath", "-w", os.path.join(config.OUT, "sim")], capture_output=True, text=True).stdout.strip()
            sh(["matlab.exe", "-batch", f"cd('{w}'); run_scenarios('carpark','{o}',''); run_scenarios('mil','{o}','')"])
        elif st == "notebook":
            sh([sys.executable, "build_nstring_notebook.py"], cwd=config.NOTEBOOKS)
        elif st == "compare":
            sh([sys.executable, "compare.py"])
        elif st == "report":
            sh([sys.executable, "report.py"])


if __name__ == "__main__":
    main()
