#!/usr/bin/env python3
"""QSPICE closed-loop scenario runs for the results synthesis (8_Results/analysis).

    python3 run_scenarios.py --smoke                  # pv80, kscale 1, 1.5 ms: proves the chain in about a minute
    python3 run_scenarios.py --all [--parallel 4]     # bench + pv80 x kscale {0.1, 0.3, 1}
    python3 run_scenarios.py --tidy                   # (re)convert every finished .qraw to tidy CSV + meta JSON
    python3 run_scenarios.py --case pv80_k0.3 ...

Each run patches a PCB_Baseline stage netlist (S10.cir = bench: NGE PSU channels with the 16 Oct current limits
into the DL3021 at 70 V; S10p.cir = carpark: 3 x KAUSSP80 into the DL3021 at 61.5 V) so that one transient holds
the three matched events: open loop at 0.5 duty until TEN (loop closes), a +1 V step on the VM2-VM3 reference at
TSTEP, and (pv80) module 3 to 2/3 irradiance at TSHADE. Settling time between events scales with 1/kscale.
Outputs: 8_Results/analysis/out/qspice/work/<case>/ (netlist, log, .qraw) and out/qspice/<case>.csv (100 us bin
means of every saved signal in the tidy names) + <case>.json (events, parameters).
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
PB = os.path.join(HERE, "PCB_Baseline")
sys.path.insert(0, PB)
sys.path.insert(0, os.path.join(HERE, "..", "..", "8_Results", "analysis"))
from s10_metrics import read as read_qraw     # noqa: E402
import config                                  # noqa: E402
import tidy                                    # noqa: E402

QSPICE = "/mnt/c/Program Files/QSPICE"
OUT = os.path.join(config.OUT, "qspice")
WORK = os.path.join(OUT, "work")
BASES = {"bench": "S10.cir", "pv80": "S10p.cir"}
SETUP = {"bench": "BENCH", "pv80": "PV80"}
SUPPORT = [os.path.join(PB, "shuffler_models.lib"), os.path.join(PB, "stages", "shuffler_ctrl_dll2.DLL"),
           os.path.join(PB, "stages", "ctrl_M2.txt")]
KSCALES = [0.1, 0.3, 1.0]
VSTEP2 = 1.0
SHADE = 0.667


def settle(k):
    """Time left between events: about eight voltage-loop time constants, at least 3 ms, at most 40 ms (kscale 0.1
    then gets 3.8 time constants; the fitted model carries the rest). At about 36 s of QSPICE time per simulated ms."""
    return min(40e-3, max(3e-3, 8.0 / (k * config.KI_V)))


TEN_DEFAULT = 3e-3        # open-loop time before the loop closes: the S10 start-up transient needs about 2 ms to die out


def plan(base, k, ten=TEN_DEFAULT):
    s = settle(k)
    tstep = ten + s
    tshade = tstep + s if base == "pv80" else None
    tend = (tshade + s) if tshade else (tstep + s)
    return dict(ten=ten, tstep=tstep, tshade=tshade, tend=tend)


def patch(text, params, ten, tstep, tshade, tend):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(".step") or s.startswith(".meas"):
            continue
        if s.startswith(".param"):
            for k, v in params.items():
                line = re.sub(rf"\b{k}=\S+", f"{k}={v:g}", line)
        elif s.startswith("Ven "):
            line = f"Ven CTRL_EN 0 PWL(0 0 {ten:.9g} 0 {ten + 1e-6:.9g} 1)"
        elif s.startswith("Vref2 "):
            line = f"Vref2 VREF2 0 PWL(0 0 {tstep:.9g} 0 {tstep + 1e-6:.9g} {{VSTEP2}})"
        elif s.startswith(".tran"):
            line = f".tran 0 {tend:.9g} 0 125n uic"
        out.append(line)
    return "\r\n".join(out) + "\r\n"


def wpath(p):
    return subprocess.run(["wslpath", "-w", p], capture_output=True, text=True, check=True).stdout.strip()


def make_case(name, base, k, short=None, ten=TEN_DEFAULT):
    p = plan(base, k, ten)
    if short:
        p.update(short)
    params = {"KSCALE": k, "VSTEP2": VSTEP2, "SHADE": SHADE if base == "pv80" else 1.0,
              "TSHADE": p["tshade"] if p["tshade"] else 1.0}
    d = os.path.join(WORK, name)
    os.makedirs(d, exist_ok=True)
    text = open(os.path.join(PB, "stages", BASES[base]), "rb").read().decode("cp1252")
    cir = patch(text, params, p["ten"], p["tstep"], p["tshade"] or 1.0, p["tend"])
    open(os.path.join(d, name + ".cir"), "wb").write(cir.encode("cp1252"))
    for f in SUPPORT:
        dst = os.path.join(d, os.path.basename(f))
        if not os.path.exists(dst):
            open(dst, "wb").write(open(f, "rb").read())
    meta = dict(case=name, base=base, setup=SETUP[base], kscale=k, params=params, events={"close": p["ten"], "vref": p["tstep"]},
                tend=p["tend"], vstep2=VSTEP2, shade=SHADE if base == "pv80" else None)
    if p["tshade"]:
        meta["events"]["shade_on"] = p["tshade"]
    json.dump(meta, open(os.path.join(d, name + ".json"), "w"), indent=1)
    return d, meta


def run_case(d, name, timeout=4 * 3600, force=False):
    cir = os.path.join(d, name + ".cir")
    log = os.path.join(d, name + ".sim.txt")
    qraw = os.path.join(d, name + ".qraw")
    if not force and os.path.exists(qraw) and os.path.getsize(qraw) > 1000 and os.path.exists(log) and "Total elapsed" in open(log, errors="replace").read():
        return name, "cached", 0.0
    t0 = time.time()
    with open(log, "wb") as fh:
        r = subprocess.run([os.path.join(QSPICE, "QSPICE64.exe"), wpath(cir)], cwd=d, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout)
    txt = open(log, errors="replace").read()
    ok = r.returncode == 0 and "Total elapsed" in txt and "error" not in txt.lower()
    return name, ("ok" if ok else "FAILED: " + txt[-300:]), time.time() - t0


# ----------------------------------------------------------------------------- tidy conversion
NAMES = {"VM1": ("v(pv1p)", "v(pv2p)"), "VM2": ("v(pv2p)", "v(pv3p)"), "VM3": ("v(pv3p)", None)}


def tidy_case(d, name, dt=config.TS):
    names, D = read_qraw(os.path.join(d, name + ".qraw"))
    col = {n.lower(): i for i, n in enumerate(names)}
    t = np.asarray(D[:, 0], float)
    starts = np.nonzero(np.diff(t) < 0)[0]
    if len(starts):                                      # should not happen (no .step), keep the last run
        a = starts[-1] + 1
        t, D = t[a:], D[a:]

    def g(n):
        return np.asarray(D[:, col[n]], float)

    sig = {}
    sig["VM1"] = g("v(pv1p)") - g("v(pv2p)")
    sig["VM2"] = g("v(pv2p)") - g("v(pv3p)")
    sig["VM3"] = g("v(pv3p)")
    sig["ILA1"], sig["ILB1"] = g("i(vsa1)"), -g("i(vsb1)")      # ILB positive out of the midpoint (firmware convention)
    sig["ILA2"], sig["ILB2"] = g("i(vsa2)"), -g("i(vsb2)")
    for n in ("dA1", "dB1", "dA2", "dB2", "rv1", "rv2", "beta", "stress"):
        key = {"rv1": "v(rv1)", "rv2": "v(rv2)", "beta": "v(beta)", "stress": "v(stress)"}.get(n, f"v({n.lower()})")
        if key in col:
            sig[n] = g(key)
    sig["Vstr"] = g("v(pv1p)")
    if "i(bload)" in col:
        sig["Istr"] = g("i(bload)")
        sig["Pstr"] = g("v(pv1p)") * g("i(bload)")
    for k in (1, 2, 3):
        if f"i(vi{k})" in col:
            sig[f"IM{k}"] = g(f"i(vi{k})")
    data = {}
    tc = None
    for n, y in sig.items():
        tc, data[n] = tidy.bin_mean(t, y, dt)
    data["t"] = tc
    meta = json.load(open(os.path.join(d, name + ".json")))
    f = tidy.frame(data, phase="qspice", setup=meta["setup"], kscale=meta["kscale"], rate_hz=1 / dt, source=name, events=meta["events"])
    f.to_csv(os.path.join(OUT, name + ".csv"), index=False)
    json.dump(meta, open(os.path.join(OUT, name + ".json"), "w"), indent=1)
    return len(f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--case", action="append", help="base_kK, e.g. pv80_k0.3")
    ap.add_argument("--tidy", action="store_true", help="only convert finished runs")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--keep-qraw", action="store_true", help="keep the raw waveform files (about 48 MB per simulated ms)")
    ap.add_argument("--ten", type=float, default=TEN_DEFAULT, help="open-loop time before the loop closes [s]")
    ap.add_argument("--force", action="store_true", help="rerun even if a finished .qraw exists")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    jobs = []
    if a.smoke:
        jobs.append(make_case("smoke_pv80_k1", "pv80", 1.0, short=dict(ten=0.3e-3, tstep=0.8e-3, tshade=None, tend=1.5e-3)))
    if a.all:
        for base in BASES:
            for k in KSCALES:
                jobs.append(make_case(f"{base}_k{k:g}", base, k, ten=a.ten))
    for c in a.case or []:
        base, k = c.split("_k")
        jobs.append(make_case(c, base, float(k), ten=a.ten))
    if a.tidy:
        for name in sorted(os.listdir(WORK)):
            d = os.path.join(WORK, name)
            q = os.path.join(d, name + ".qraw")
            if os.path.exists(q) and "Total elapsed" in open(os.path.join(d, name + ".sim.txt"), errors="replace").read():
                print(name, tidy_case(d, name), "rows")
                if not a.keep_qraw:
                    os.remove(q)
        return
    for d, meta in jobs:
        print(f"{meta['case']}: tend {meta['tend'] * 1e3:.1f} ms, events {meta['events']}, estimated {meta['tend'] * 1e3 * 29 / 60:.0f} min")
    with ThreadPoolExecutor(max_workers=a.parallel) as ex:
        for name, status, secs in ex.map(lambda j: run_case(j[0], j[1]["case"], force=a.force), jobs):
            print(f"{name}: {status} ({secs / 60:.1f} min)", flush=True)
            if status in ("ok", "cached"):
                print(f"  tidy: {tidy_case(os.path.join(WORK, name), name)} rows", flush=True)
                if not a.keep_qraw:
                    os.remove(os.path.join(WORK, name, name + ".qraw"))


if __name__ == "__main__":
    main()
