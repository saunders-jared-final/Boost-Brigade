#!/usr/bin/env python3
"""Pull a time window from InfluxDB and plot the carpark traces (VM, IL, duties,
supervisor, string power estimate) for the report.
    python3 plots.py --start -2h --out ../../3_Analytical/data/run1   (writes CSV + PNGs)
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
    a = ap.parse_args()
    q = (f'from(bucket:"{BUCKET}") |> range(start: {a.start}, stop: {a.stop}) '
         f'|> filter(fn: (r) => r["_measurement"] == "telemetry") '
         f'|> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")')
    df = InfluxDBClient(url=a.url, token=TOKEN, org=ORG).query_api().query_data_frame(q)
    if isinstance(df, list):
        df = pd.concat(df)
    df = df.set_index("_time").sort_index()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    df.to_csv(a.out + ".csv")
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
    print("wrote", a.out + ".csv and PNGs")


if __name__ == "__main__":
    main()
