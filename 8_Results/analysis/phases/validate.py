"""Simulink validate-suite phase: the per-test CSV/JSON exported by 4_Simulink/*/shuffler_string_validate.m
(out/sim/carpark_validate -> phase 'simulink', out/sim/mil_validate -> phase 'simulink_mil'). Every test starts cold
(module capacitors at 0 V, references and irradiance constant from t = 0), so the reference-step metrics are
'cold-start' responses: the first ~1 ms is the plant charging, then the loop pulls v_d onto its reference."""
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
WHICH = {"carpark": ("carpark_validate", "simulink", "BENCH"), "mil": ("mil_validate", "simulink_mil", "MIL4")}


def runs(which):
    folder, phase, setup = WHICH[which]
    out = []
    for j in sorted(glob.glob(os.path.join(SIM, folder, "*.json"))):
        meta = json.load(open(j))
        csv = j[:-5] + ".csv"
        if os.path.exists(csv):
            out.append((meta, csv))
    return out


def to_frame(meta, csv, which):
    folder, phase, setup = WHICH[which]
    d = pd.read_csv(csv)
    n = int(meta.get("N") or sum(1 for c in d.columns if c.startswith("VM") and not c.startswith("VMm")))
    data = {"t": d["t"]}
    for c in d.columns:
        if c != "t":
            data[c] = d[c]
    data["Vstr"], data["Istr"] = d.get("V_String"), d.get("I_String")
    if "V_String" in d and "I_String" in d:
        data["Pstr"] = d["V_String"] * d["I_String"]
    for j in range(1, n):                       # modal signals for every shuffler (tidy covers 1-2; keep 3 for MIL)
        data[f"vd{j}"] = d[f"VM{j}"] - d[f"VM{j + 1}"]
        if f"ILA{j}" in d:
            data[f"ic{j}"] = d[f"ILA{j}"] + d[f"ILB{j}"]
            data[f"id{j}"] = d[f"ILA{j}"] - d[f"ILB{j}"]
    f = tidy.frame({k: v for k, v in data.items() if v is not None and k in tidy.COLS},
                   phase=phase, setup=setup, kscale=1.0, scenario="V" + str(meta["k"]), rate_hz=1.0 / meta["dt"], source=meta["id"],
                   test=meta["name"], mode=meta["mode"], rv=meta["rv"], irrN=meta["irrN"], Tstop=meta["Tstop"], n_mod=n,
                   passed=bool(meta.get("pass")), stats=meta.get("stats", {}), event="cold start t = 0")
    for extra in ("vd3", "ic3", "id3", "VM4", "IM4", "ILA3", "ILB3", "dA3", "dB3", "rv3", "Pav", "Iref", "mppt_state", "IMr1", "IMr2", "IMr3", "VMm1", "VMm2", "VMm3"):
        if extra in data and data[extra] is not None:
            f[extra] = data[extra].to_numpy()
    return f


def tests(which):
    return [to_frame(meta, csv, which) for meta, csv in runs(which)]


def cases(scenario):
    return []


def settled_stats():
    rows = []
    for which in ("carpark", "mil"):
        folder, phase, setup = WHICH[which]
        for meta, csv in runs(which):
            f = to_frame(meta, csv, which)
            g = f[f["t"] >= f["t"].iat[-1] - 0.01]
            rows.append({"phase": phase, "setup": setup, "state": "RUN_CL", "kscale": 1.0, "window": meta["id"], "start_local": "last 10 ms",
                         "duration_s": 0.01, "ended_by": "end", **{f"{c}_mean": float(g[c].mean()) for c in ("vd1", "vd2", "ic1", "ic2", "id1", "id2", "stress", "Pstr", "Vstr") if c in g},
                         **{f"{c}_std": float(g[c].std()) for c in ("vd1", "vd2", "ic1", "ic2", "dA1", "dA2", "dB2") if c in g}})
    return rows
