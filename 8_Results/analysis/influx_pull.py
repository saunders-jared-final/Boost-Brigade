#!/usr/bin/env python3
"""Pull the closed-loop hardware windows from the Pi's InfluxDB into 8_Results (telemetry in every state, the
e-load log, and the command / parameter / fault / status / note records that influx_export.py does not export).

    python3 influx_pull.py [--only NAME] [--force] [--list]

Windows are defined in config.WINDOWS (local AEST). Each window is widened by config.MARGIN_S. Existing CSVs
are kept unless --force. Writes <name>.csv, <name> eload.csv, <name> <measurement>.csv and a README.md per folder.
"""
import argparse
import csv
import datetime as dt
import os
import sys

import config

sys.path.insert(0, config.TOOLS)
import influx_export as ie     # noqa: E402  (flux, export, parse_time, influx_time, LOCAL_TZ)


def export_aux(name, meas, tags, start, stop, out):
    rng = f'range(start: {start.isoformat().replace("+00:00", "Z")}, stop: {stop.isoformat().replace("+00:00", "Z")})'
    keys = "".join(f', "{t}"' for t in tags)
    q = (f'from(bucket: "{ie.BUCKET}") |> {rng} |> filter(fn: (r) => r._measurement == "{meas}")'
         f' |> drop(columns: ["_start", "_stop", "_measurement"])'
         f' |> pivot(rowKey: ["_time"{keys}], columnKey: ["_field"], valueColumn: "_value") |> sort(columns: ["_time"])')
    rows = ie.flux(q)
    rows.sort(key=lambda r: r["_time"])
    path = os.path.join(out, f"{name} {meas}.csv")
    if not rows:
        print(f"  {os.path.basename(path)}: no rows")
        return path, 0
    seen = {}
    for r in rows:
        seen.update(dict.fromkeys(r))
    fields = sorted(k for k in seen if k not in ("", "result", "table", "_time", *tags))
    if "line" in fields:                       # the text first
        fields = ["line"] + [f for f in fields if f != "line"]
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time_utc", "time_local", "t_s", *tags, *fields])
        for r in rows:
            t = ie.influx_time(r["_time"])
            w.writerow([t.isoformat().replace("+00:00", "Z"), t.astimezone(ie.LOCAL_TZ).isoformat(),
                        f"{(t - start).total_seconds():.3f}", *(r.get(k, "") for k in tags), *(r.get(f, "") for f in fields)])
    print(f"  {os.path.basename(path)}: {len(rows)} rows")
    return path, len(rows)


def count_rows(path):
    with open(path, newline="") as fh:
        return max(0, sum(1 for _ in fh) - 1)


def pull_window(name, folder, start_s, stop_s, force=False):
    out = os.path.join(config.RESULTS, folder)
    os.makedirs(out, exist_ok=True)
    start = ie.parse_time(start_s) - dt.timedelta(seconds=config.MARGIN_S)
    stop = ie.parse_time(stop_s) + dt.timedelta(seconds=config.MARGIN_S)
    main_csv = os.path.join(out, name + ".csv")
    info = {"name": name, "folder": folder, "start": start, "stop": stop, "rows": {}}
    if os.path.exists(main_csv) and not force:
        print(f"{name}: exists, skipped (use --force)")
        info["rows"]["telemetry"] = count_rows(main_csv)
        return info
    print(f"{name}: {start.astimezone(ie.LOCAL_TZ):%H:%M:%S} .. {stop.astimezone(ie.LOCAL_TZ):%H:%M:%S} local, all states")
    written = ie.export(name, start, stop, out, states=None, eload=True)
    for p in written:
        key = "eload" if p.endswith(" eload.csv") else "telemetry"
        info["rows"][key] = count_rows(p)
    for meas, tags in config.AUX.items():
        _p, n = export_aux(name, meas, tags, start, stop, out)
        info["rows"][meas] = n
    return info


def pull_day_log(name, folder, start_s, stop_s, force=False):
    out = os.path.join(config.RESULTS, folder)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{name} cmd.csv")
    if os.path.exists(path) and not force:
        print(f"{name} cmd: exists, skipped")
        return
    print(f"{name}: whole-day command / fault / status log")
    start, stop = ie.parse_time(start_s), ie.parse_time(stop_s)
    for meas in ("cmd", "fault", "status", "params", "note"):
        export_aux(name, meas, config.AUX[meas], start, stop, out)


def write_readme(folder, infos):
    out = os.path.join(config.RESULTS, folder)
    title = {"Bench_Closed_Loop_200kHz": "Bench closed loop, 16 Oct 2026 (NGE103 PSUs with unbalanced limits into the DL3021 in CV; 200 / 300 / 400 kHz images)",
             "Solar_Closed_Loop": "Carpark solar closed loop, 20 Oct 2026 (3 x KAUSSP80, DL3021 e-load in CV)"}[folder]
    lines = [f"# {title}", "",
             "Exports from the pod's InfluxDB made by `8_Results/analysis/influx_pull.py` (windows in `analysis/config.py`,",
             f"each widened by {config.MARGIN_S} s so the open-loop baseline and the kscale command before a run are inside).",
             "Times are Australia/Brisbane (AEST, UTC+10). Unlike the open-loop folders these exports keep **every firmware",
             "state** (`state` column: IDLE, SOFTSTART, RUN_OL, RUN_CL, STOP, FAULT ...), so a closed-loop run can be cut",
             "from its open-loop baseline to its end.", "",
             "Per window: `<name>.csv` telemetry (50 Hz T frames, columns as in `Solar_Open_Loop/README.md`), `<name> eload.csv`",
             "(DL3021 log), and the pod's records: `<name> cmd.csv` (every command sent, `dir=tx`; answers that were not routine,",
             "`dir=rx`; IR keys, `dir=ir`; e-load commands with their `answer`), `<name> params.csv` (the full parameter set after",
             "every APPLY), `<name> fault.csv`, `<name> status.csv`, `<name> note.csv`. `<day> cmd.csv` etc. are the whole day.", "",
             "| Window (local, before widening) | Telemetry rows | E-load rows | cmd rows | Note |", "|---|---|---|---|---|"]
    for i in infos:
        note = config.WINDOWS[i["name"]][3]
        s = (i["start"] + dt.timedelta(seconds=config.MARGIN_S)).astimezone(ie.LOCAL_TZ)
        e = (i["stop"] - dt.timedelta(seconds=config.MARGIN_S)).astimezone(ie.LOCAL_TZ)
        lines.append(f"| `{i['name']}` ({s:%H:%M:%S}-{e:%H:%M:%S}) | {i['rows'].get('telemetry', '?')} | {i['rows'].get('eload', '?')} | {i['rows'].get('cmd', '?')} | {note} |")
    lines += ["", "Closed-loop segments and events per window: `8_Results/analysis/out/events/` (made by `analysis/events.py`).",
              "Regenerate: `python3 8_Results/analysis/influx_pull.py --force` (needs the Pi's InfluxDB reachable).", ""]
    with open(os.path.join(out, "README.md"), "w") as fh:
        fh.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="substring of the window names to pull")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for n, (f, s, e, note) in config.WINDOWS.items():
            print(f"{n:45s} {f:26s} {s[11:]}..{e[11:]}  {note}")
        return
    infos = {}
    for name, (folder, s, e, _note) in config.WINDOWS.items():
        if a.only and a.only not in name:
            continue
        infos.setdefault(folder, []).append(pull_window(name, folder, s, e, a.force))
    for name, (folder, s, e) in config.DAY_LOGS.items():
        if a.only and a.only not in name:
            continue
        pull_day_log(name, folder, s, e, a.force)
    for folder, lst in infos.items():
        if not a.only:
            write_readme(folder, lst)
    print("done")


if __name__ == "__main__":
    main()
