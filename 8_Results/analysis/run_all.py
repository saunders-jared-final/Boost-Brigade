#!/usr/bin/env python3
"""Pipeline: pull-cases -> hw -> events -> metrics -> ripple -> figures -> compare -> report (see the Makefile).

    python3 run_all.py [--skip pull,...] [--only hw,compare] [--with mil-validate,...]

Long stages (qspice, simulink, carpark-validate, mil-validate, simulink-extra: MATLAB / QSPICE runs of minutes to
hours) are skipped unless named with --with or --only; they log to out/logs/<stage>.log.
"""
import argparse
import os
import subprocess
import sys

import config

STAGES = ["pull", "pull-cases", "hw", "events", "metrics", "ripple", "qspice", "simulink", "carpark-validate", "mil-validate", "simulink-extra", "notebook", "figures", "compare", "report"]
LONG = {"qspice", "simulink", "carpark-validate", "mil-validate", "simulink-extra"}


def sh(cmd, cwd=None, log=None):
    print("$", " ".join(cmd), flush=True)
    if log:
        os.makedirs(os.path.join(config.OUT, "logs"), exist_ok=True)
        with open(os.path.join(config.OUT, "logs", log), "w") as fh:
            rc = subprocess.run(cmd, cwd=cwd or config.HERE, stdout=fh, stderr=subprocess.STDOUT).returncode
            fh.write(f"\nexit {rc}\n")
        print(f"  -> out/logs/{log} (exit {rc})")
        return rc
    return subprocess.run(cmd, cwd=cwd or config.HERE).returncode


def win(path):
    return subprocess.run(["wslpath", "-w", path], capture_output=True, text=True).stdout.strip()


def matlab(folder, call, log):
    w = win(os.path.join(config.REPO, "4_Simulink", folder))
    return sh(["matlab.exe", "-batch", f"cd('{w}'); {call}"], log=log)


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
        if st in skip or (st in LONG and st not in with_ and not only):
            continue
        if st == "pull":
            sh([sys.executable, "influx_pull.py"])
        elif st == "pull-cases":
            sh([sys.executable, "influx_pull.py", "--cases"])
        elif st == "hw":
            sh([sys.executable, "hwcases.py", "--figures"])
        elif st == "events":
            sh([sys.executable, "figures.py", "--events"])
        elif st == "metrics":
            sh([sys.executable, "hwmetrics.py"])
        elif st == "ripple":
            sh([sys.executable, "ripple.py"])
        elif st == "figures":
            sh([sys.executable, "figures.py", "--sims", "analytical,qspice,simulink,validate"])
        elif st == "carpark-validate":
            o = win(os.path.join(config.OUT, "sim", "carpark_validate"))
            matlab("3_Carpark_3mod", f"shuffler_string_validate('{o}')", "carpark_validate.log")
        elif st == "mil-validate":
            o = win(os.path.join(config.OUT, "sim", "mil_validate"))
            matlab("1_MIL_Model_In_The_Loop", f"shuffler_string_validate('{o}')", "mil_validate.log")
        elif st == "simulink-extra":
            o = win(os.path.join(config.OUT, "sim"))
            matlab("3_Carpark_3mod", f"run_scenarios('carpark','{o}','', [0.2 0.5])", "simulink_extra.log")
        elif st == "qspice":
            sh([sys.executable, "run_scenarios.py", "--all", "--parallel", "4"], cwd=config.QSPICE_OUT)
        elif st == "simulink":
            o = win(os.path.join(config.OUT, "sim"))
            matlab("3_Carpark_3mod", f"run_scenarios('carpark','{o}','')", "simulink.log")
        elif st == "notebook":
            sh([sys.executable, "build_nstring_notebook.py"], cwd=config.NOTEBOOKS)
        elif st == "compare":
            sh([sys.executable, "compare.py"])
        elif st == "report":
            sh([sys.executable, "report.py"])


if __name__ == "__main__":
    main()
