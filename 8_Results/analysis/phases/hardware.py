"""Hardware phase: cases (engagements, shade events, settled segments) cut from the pulled windows."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import config                     # noqa: E402
import events                     # noqa: E402
import tidy                       # noqa: E402

SETUP_OF = {"Bench_Closed_Loop_200kHz": "BENCH", "Solar_Closed_Loop": "PV80"}
_cache = {}


def window(name):
    if name not in _cache:
        w = events.load_window(name)
        ev_path = os.path.join(events.EV_DIR, name + ".events.csv")
        seg_path = os.path.join(events.EV_DIR, name + ".segments.csv")
        if not (os.path.exists(ev_path) and os.path.exists(seg_path)):
            w, ev, seg = events.build(name)
        else:
            ev, seg = pd.read_csv(ev_path), pd.read_csv(seg_path)
        ev["time_utc"] = pd.to_datetime(ev["time_utc"], utc=True, format="ISO8601")
        w["events"], w["segments"] = ev, seg
        _cache[name] = w
    return _cache[name]


def cut(w, t_event, pre_s, post_s, **attrs):
    tel = w["tel"]
    m = (tel["t_utc"] >= t_event - pd.Timedelta(seconds=pre_s)) & (tel["t_utc"] <= t_event + pd.Timedelta(seconds=post_s))
    g = tel[m]
    data = {"t": (g["t_utc"] - t_event).dt.total_seconds().to_numpy()}
    for c in ("VM1", "VM2", "VM3", "ILA1", "ILB1", "ILA2", "ILB2", "dA1", "dB1", "dA2", "dB2", "rv1", "rv2", "beta", "stress",
              "kscale", "Vstr", "Istr", "Pstr", "state"):
        if c in g:
            data[c] = g[c].to_numpy()
    if "IM1r" in g:
        data["IM1"], data["IM2"] = g["IM1r"].to_numpy(), g["IM2r"].to_numpy()
    f = tidy.frame(data, phase="hardware", setup=SETUP_OF[w["folder"]], rate_hz=config.TELEMETRY_HZ, source=w["name"],
                   event_utc=t_event.isoformat(), vm1_quality="e-load via Pi, 2.2 Hz (vm1_src=2)", **attrs)
    return f


def close_cases(name, min_run_s=2.0, post_s=5.0):
    """One case per OL/SOFTSTART -> RUN_CL transition that lasted at least min_run_s: the loop closing on the mismatch."""
    w = window(name)
    tel, ev, seg = w["tel"], w["events"], w["segments"]
    cases = []
    for _, e in ev[ev["kind"] == "close"].iterrows():
        t0 = e["time_utc"]
        s = seg[(pd.to_datetime(seg["start_utc"], utc=True, format="ISO8601") >= t0 - pd.Timedelta(seconds=0.5)) & seg["state"].str.startswith("RUN_CL")]
        if s.empty or s.iloc[0]["duration_s"] < min_run_s:
            continue
        run = s.iloc[0]
        # the IDLE level before the soft start = the natural mismatch of the string
        idle = tel[(tel["t_utc"] < t0 - pd.Timedelta(seconds=0.1)) & (tel["t_utc"] >= t0 - pd.Timedelta(seconds=3)) & (tel["state"] == "IDLE")]
        f = cut(w, t0, pre_s=3.0, post_s=min(post_s, run["duration_s"]), scenario="S1", kscale=float(run["kscale"]),
                run_duration_s=float(run["duration_s"]), ended_by=run["ended_by"], pver=run["pver"],
                idle_levels={c: float(idle[c].median()) for c in ("vd1", "vd2", "ic1", "ic2", "id1", "id2") if len(idle)})
        cases.append(f)
    return cases


def shade_cases(name, pre_s=10.0, post_s=40.0):
    """One case per shade_on / transient_on candidate inside a run segment (user confirmation pending)."""
    w = window(name)
    ev = w["events"]
    cases = []
    cand = ev[ev["kind"].isin(("shade_on", "transient_on"))]
    times = cand["time_utc"].tolist()
    for i, (_, e) in enumerate(cand.iterrows()):
        state = str(e["detail"]).split("]")[0].strip("[") if str(e["detail"]).startswith("[") else ""
        if not state.startswith("RUN"):
            continue
        t0 = e["time_utc"]
        nxt = [t for t in ev["time_utc"] if t > t0 + pd.Timedelta(seconds=3)]
        until = min(post_s, (nxt[0] - t0).total_seconds()) if nxt else post_s
        ks = w["tel"].loc[(w["tel"]["t_utc"] - t0).abs().idxmin(), "kscale"]
        f = cut(w, t0, pre_s=pre_s, post_s=until, scenario="S3", kscale=float(ks), state=state, detail=e["detail"],
                candidate=True, label=e.get("label", ""))
        cases.append(f)
    return cases


def segment_stats(name):
    """S2: settled statistics of every run segment (from events.segments)."""
    w = window(name)
    seg = w["segments"]
    runs = seg[seg["state"].isin(events.RUN_STATES) & (seg["duration_s"] > 5)].copy()
    runs["phase"] = "hardware"
    runs["setup"] = SETUP_OF[w["folder"]]
    runs["window"] = name
    return runs


def all_windows(folder=None):
    return [n for n, (f, *_r) in config.WINDOWS.items() if folder is None or f == folder]
