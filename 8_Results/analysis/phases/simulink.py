"""Simulink phases: cases from the CSV / JSON written by 4_Simulink/3_Carpark_3mod/run_scenarios.m
(out/sim/carpark -> phase 'simulink', out/sim/mil -> phase 'simulink_mil')."""
import glob
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import config      # noqa: E402
import tidy        # noqa: E402

SIM = os.path.join(config.OUT, "sim")
SCEN_OF = {"S4_vr": "S4", "S1_cl": "S1", "S3_sh": "S3"}


def runs(which):
    out = []
    for j in sorted(glob.glob(os.path.join(SIM, which, "*.json"))):
        meta = json.load(open(j))
        csv = j[:-5] + ".csv"
        if os.path.exists(csv):
            out.append((meta, csv))
    return out


def to_frame(meta, csv, which):
    d = pd.read_csv(csv)
    data = {"t": d["t"] - meta["t0"]}
    n = sum(1 for c in d.columns if c.startswith("VM") and not c.startswith("VMm"))
    for c in d.columns:
        if c in ("t",):
            continue
        data[c] = d[c]
    data["Vstr"] = d.get("V_String")
    data["Istr"] = d.get("I_String")
    if "V_String" in d and "I_String" in d:
        data["Pstr"] = d["V_String"] * d["I_String"]
    scen = SCEN_OF.get(meta["id"][:5], "")
    f = tidy.frame({k: v for k, v in data.items() if v is not None and k in tidy.COLS},
                   phase="simulink_mil" if which == "mil" else "simulink", setup=meta.get("setup") or "MIL4",
                   kscale=meta.get("kscale", 1.0), scenario=scen, rate_hz=1.0 / meta["dt"], source=meta["id"],
                   event=meta.get("step", ""), ctrl_mode=meta.get("ctrl_mode", 1), vd_OL=meta.get("vd_OL"), n_mod=n)
    # for the mirrored engagement the sign is flipped back so the trace reads like the hardware (vd_OL -> 0)
    if scen == "S1" and meta.get("vd_OL") is not None:
        vd = meta["vd_OL"]
        if not isinstance(vd, list):
            vd = [vd]
        for j, v in enumerate(vd, 1):
            col = f"vd{j}"
            if col in f:
                f[col] = -(f[col]) if False else f[col]       # kept as simulated; the table reports delta = -vd_OL
    return f


def _cases(which, scenario):
    out = []
    for meta, csv in runs(which):
        if SCEN_OF.get(meta["id"][:5]) != scenario:
            continue
        if scenario == "S3" and meta.get("ctrl_mode", 1) == 0:
            continue                                    # the open-loop twin feeds the benefit table, not the step metrics
        out.append(to_frame(meta, csv, which))
    return out


def cases(scenario):
    return _cases("carpark", scenario)


def settled_stats():
    rows = []
    for which, phase in (("carpark", "simulink"), ("mil", "simulink_mil")):
        for meta, csv in runs(which):
            if meta.get("ctrl_mode", 1) == 0:
                continue
            f = to_frame(meta, csv, which)
            g = f[(f["t"] < 0) & (f["t"] > -0.01)]              # the settled window before the event
            if len(g) < 10:
                continue
            rows.append({"phase": phase, "setup": f.attrs["setup"], "state": "RUN_CL", "kscale": f.attrs["kscale"], "window": meta["id"],
                         "start_local": "10 ms before the event", "duration_s": 0.01, "ended_by": "event",
                         **{f"{c}_mean": float(g[c].mean()) for c in ("vd1", "vd2", "ic1", "ic2", "id1", "id2", "stress", "Pstr", "Vstr") if c in g},
                         **{f"{c}_std": float(g[c].std()) for c in ("vd1", "vd2", "ic1", "ic2", "dA1", "dA2", "dB2") if c in g}})
    return rows


class _Mil:
    @staticmethod
    def cases(scenario):
        return _cases("mil", scenario)

    settled_stats = staticmethod(lambda: [])
