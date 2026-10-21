"""QSPICE phase: cases sliced from the tidy runs written by 2_Qspice/Claude's outputs/run_scenarios.py."""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import config      # noqa: E402
import tidy        # noqa: E402

OUT = os.path.join(config.OUT, "qspice")
EVENT_OF = {"S1": "close", "S3": "shade_on", "S4": "vref"}


def runs():
    out = []
    for j in sorted(glob.glob(os.path.join(OUT, "*.json"))):
        meta = json.load(open(j))
        csv = j[:-5] + ".csv"
        if os.path.exists(csv) and not meta["case"].startswith("smoke"):
            out.append((meta, csv))
    return out


def slice_case(df, meta, t_event, scenario, pre=2e-3):
    ev = sorted(v for v in meta["events"].values() if v > t_event + 1e-6)
    t_end = ev[0] if ev else meta["tend"]
    g = df[(df["t"] >= t_event - pre) & (df["t"] < t_end)].copy()
    g["t"] = g["t"] - t_event
    f = tidy.frame(g.to_dict("list"), phase="qspice", setup=meta["setup"], kscale=meta["kscale"], scenario=scenario,
                   rate_hz=1 / config.TS, source=meta["case"], event=f"{EVENT_OF[scenario]} @ {t_event * 1e3:.3g} ms")
    return f


def cases(scenario):
    key = EVENT_OF.get(scenario)
    if key is None:
        return []
    out = []
    for meta, csv in runs():
        if key not in meta["events"]:
            continue
        df = pd.read_csv(csv)
        out.append(slice_case(df, meta, meta["events"][key], scenario))
    return out


def settled_stats():
    """S2 rows: standard deviation of the 100 us tick means over the last 40 % before each event (ripple removed)."""
    rows = []
    for meta, csv in runs():
        df = pd.read_csv(csv)
        bounds = sorted(meta["events"].values()) + [meta["tend"]]
        for a, b in zip(bounds[:-1], bounds[1:]):
            g = df[(df["t"] >= a + 0.6 * (b - a)) & (df["t"] < b)]
            if len(g) < 10:
                continue
            rows.append({"phase": "qspice", "setup": meta["setup"], "state": "RUN_CL", "kscale": meta["kscale"], "window": meta["case"],
                         "start_local": f"{a * 1e3:.3g}-{b * 1e3:.3g} ms", "duration_s": round(b - a, 4), "ended_by": "event",
                         **{f"{c}_mean": float(g[c].mean()) for c in ("vd1", "vd2", "ic1", "ic2", "id1", "id2", "stress", "Pstr", "Vstr") if c in g},
                         **{f"{c}_std": float(g[c].std()) for c in ("vd1", "vd2", "ic1", "ic2", "dA1", "dA2", "dB2") if c in g}})
    return rows
