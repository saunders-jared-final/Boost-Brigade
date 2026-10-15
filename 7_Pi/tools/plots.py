#!/usr/bin/env python3
"""Pull a time window from InfluxDB and plot the carpark traces (VM, IL, duties,
supervisor, string power estimate) for the report.
    python3 plots.py --start -2h --out ../../3_Analytical/data/run1   (writes CSV + PNGs)
    python3 plots.py --start 2026-10-13T12:20:00+10:00 --stop 2026-10-13T14:00:00+10:00 --out ../../3_Analytical/data/ol100k_a
Absolute times are RFC3339 with an offset (Influx stores UTC). Writes <out>.csv (telemetry, 50 Hz) and
<out>_eload.csv (DL3021, 5 Hz) separately because the two streams are not on a common time base.
"""
import argparse
import os

import pandas as pd
from influxdb_client import InfluxDBClient

URL, TOKEN, ORG, BUCKET = "http://localhost:8086", "shuffler-pod-token", "boost", "shuffler"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="-1h")
    ap.add_argument("--stop", default="now()")
    ap.add_argument("--url", default=URL)
    ap.add_argument("--out", default="run")
    ap.add_argument("--chunk", type=float, default=10, help="minutes per query for absolute windows")
    ap.add_argument("--timeout", type=float, default=120, help="seconds per query")
    a = ap.parse_args()
    api = InfluxDBClient(url=a.url, token=TOKEN, org=ORG, timeout=int(a.timeout * 1000)).query_api()

    # Absolute windows are split into chunks: a pivot over 100 min of 50 Hz data outruns the Pi.
    def absolute(t):
        return t[:4].isdigit() and "T" in t   # RFC3339; pandas would read "-2h" as year 0001

    if absolute(a.start) and absolute(a.stop):
        t0, t1 = pd.Timestamp(a.start), pd.Timestamp(a.stop)
        edges = list(pd.date_range(t0, t1, freq=f"{a.chunk}min"))
        if edges[-1] < t1:
            edges.append(t1)
        spans = [(s.isoformat(), e.isoformat()) for s, e in zip(edges[:-1], edges[1:])]
    else:
        spans = [(a.start, a.stop)]   # relative (-2h) or now(): one query

    def pull(measurement):
        parts = []
        for s, e in spans:
            q = (f'from(bucket:"{BUCKET}") |> range(start: {s}, stop: {e}) '
                 f'|> filter(fn: (r) => r["_measurement"] == "{measurement}") '
                 f'|> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")')
            d = api.query_data_frame(q)
            if isinstance(d, list):
                d = pd.concat(d) if d else pd.DataFrame()
            if not d.empty:
                parts.append(d)
            if len(spans) > 1:
                print(f"  {measurement} {s} -> {e}: {len(d)} rows")
        if not parts:
            return pd.DataFrame()
        d = pd.concat(parts)
        d = d.drop(columns=[c for c in ("result", "table", "_start", "_stop", "_measurement") if c in d.columns])
        return d.set_index("_time").sort_index()

    df = pull("telemetry")
    el = pull("eload")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    df.to_csv(a.out + ".csv")
    if not el.empty:
        el.to_csv(a.out + "_eload.csv")
    print(f"telemetry rows {len(df)}, eload rows {len(el)}")
    if df.empty:
        print("no telemetry in that window (check the time zone offset)")
        return
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib missing; CSV written only")
        return
    groups = {"module_voltages": ["VM1", "VM2", "VM3"], "inductor_currents": ["ILA1", "ILB1", "ILA2", "ILB2"],
              "duties": ["dA1", "dB1", "dA2", "dB2"], "supervisor": ["rv1", "rv2", "beta", "stress"],
              "temperature": ["heatsink_c", "T1", "T2", "T3"]}
    for name, cols in groups.items():
        cols = [c for c in cols if c in df.columns]
        if not cols:
            continue
        ax = df[cols].plot(figsize=(10, 4), title=name)
        ax.grid(True)
        ax.figure.savefig(f"{a.out}_{name}.png", dpi=150, bbox_inches="tight")
    ecols = [c for c in ("v", "i", "p") if c in el.columns]
    if ecols:
        ax = el[ecols].plot(figsize=(10, 4), title="eload", subplots=True)[0]
        ax.figure.savefig(f"{a.out}_eload.png", dpi=150, bbox_inches="tight")
    print("wrote", a.out + ".csv and PNGs")


if __name__ == "__main__":
    main()
