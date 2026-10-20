#!/usr/bin/env python3
"""Export pod telemetry (and the e-load log) from the Pi's InfluxDB as CSV, one file per time window.

    python3 influx_export.py --out ../../8_Results/Solar_Open_Loop \
        --window "Open Loop 1410" 1792469425055 1792469446432 \
        --window "Full sun #2 1504-1507" 2026-10-20T15:04:36+10:00 2026-10-20T15:07:45+10:00

A window is <name> <from> <to>; from/to are epoch milliseconds (as in a Grafana URL) or ISO-8601 with offset.
Writes <name>.csv (telemetry, one row per T frame, pivoted: one column per field) and <name> eload.csv
(the DL3021 poll log, same layout). --states RUN_OL,RUN_CL keeps only those firmware states (default RUN_OL;
"all" keeps everything, with the state in a column). The time columns are UTC ISO, local ISO and t_s
(seconds since the window start) so a reconstruction can use whichever it likes. Needs only the standard library.
"""
import argparse
import csv
import datetime as dt
import io
import os
import sys
import urllib.request

URL = os.environ.get("INFLUX_URL", "http://10.15.78.91:8086")
TOKEN = os.environ.get("INFLUX_TOKEN", "shuffler-pod-token")
ORG = os.environ.get("INFLUX_ORG", "boost")
BUCKET = os.environ.get("INFLUX_BUCKET", "shuffler")
LOCAL_TZ = dt.timezone(dt.timedelta(hours=10), "AEST")

# column order of the T frame (0_Documentation/telemetry.md); anything else the pod logged follows alphabetically
T_ORDER = ["VM1", "VM2", "VM3", "Vstr", "ILA1", "ILB1", "ILA2", "ILB2", "dA1", "dB1", "dA2", "dB2", "rv1", "rv2",
           "beta", "stress", "IM1r", "IM2r", "T1", "T2", "T3", "kscale", "pset", "fault"]
E_ORDER = ["v", "i", "p", "r", "mode", "input_on", "setpoint", "set_cc", "set_cv", "set_cr", "set_cp"]


def parse_time(s: str) -> dt.datetime:
    if s.isdigit():
        return dt.datetime.fromtimestamp(int(s) / 1000, dt.timezone.utc)
    t = dt.datetime.fromisoformat(s)
    if t.tzinfo is None:
        t = t.replace(tzinfo=LOCAL_TZ)
    return t.astimezone(dt.timezone.utc)


def influx_time(s: str) -> dt.datetime:
    """RFC3339 with up to 9 fractional digits (Python's fromisoformat stops at 6)."""
    s = s.rstrip("Z")
    if "." in s:
        base, frac = s.split(".", 1)
        s = f"{base}.{frac[:6].ljust(6, '0')}"
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)


def flux(query: str) -> list[dict]:
    req = urllib.request.Request(f"{URL}/api/v2/query?org={ORG}", data=query.encode(), method="POST",
                                 headers={"Authorization": f"Token {TOKEN}", "Content-Type": "application/vnd.flux",
                                          "Accept": "application/csv"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            text = r.read().decode()
    except urllib.error.HTTPError as e:
        sys.exit(f"influx {e.code}: {e.read().decode()[:500]}\nquery: {query}")
    rows: list[dict] = []
    for table in text.split("\r\n\r\n"):          # one annotated CSV table per result group
        lines = [l for l in table.splitlines() if l and not l.startswith("#")]
        if len(lines) < 2:
            continue
        rows.extend(csv.DictReader(io.StringIO("\n".join(lines))))
    return rows


def export(name: str, start: dt.datetime, stop: dt.datetime, out: str, states: set[str] | None,
           fields: list[str] | None = None, every: str | None = None, eload: bool = True,
           pver: str | None = None) -> list[str]:
    rng = f'range(start: {start.isoformat().replace("+00:00", "Z")}, stop: {stop.isoformat().replace("+00:00", "Z")})'
    written = []
    # heatsink_c comes from the Pi (source=pi, no state tag); include it only when fields are chosen explicitly
    src = "true" if fields else 'r.source == "nucleo"'
    jobs = [("", "telemetry", src, ["state", "pver"], T_ORDER)]
    if eload:
        jobs.append((" eload", "eload", "true", [], E_ORDER))
    for suffix, meas, extra, tags, order in jobs:
        fsel = ""
        if fields and meas == "telemetry":
            fsel = " and (" + " or ".join(f'r._field == "{f}"' for f in fields) + ")"
        if pver and meas == "telemetry":
            fsel += f' and r.pver =~ /{pver}/'
        agg = f' |> aggregateWindow(every: {every}, fn: mean, createEmpty: false)' if every else ""
        # series from the Pi (heatsink_c) carry no state/pver tag: give them empty ones so the pivot row key exists
        fill = (' |> map(fn: (r) => ({r with state: if exists r.state then r.state else "",'
                ' pver: if exists r.pver then r.pver else ""}))') if tags else ""
        q = (f'from(bucket: "{BUCKET}") |> {rng} |> filter(fn: (r) => r._measurement == "{meas}" and {extra}{fsel})'
             f'{agg}{fill} |> drop(columns: ["_start", "_stop", "_measurement", "source"])'
             f' |> pivot(rowKey: ["_time"{"".join(", " + repr(t).replace(chr(39), chr(34)) for t in tags)}],'
             f' columnKey: ["_field"], valueColumn: "_value") |> sort(columns: ["_time"])')
        rows = flux(q)
        if states and meas == "telemetry":
            rows = [r for r in rows if r.get("state") in states]
        rows.sort(key=lambda r: r["_time"])     # the result comes as one table per state/pver group
        if not rows:
            print(f"  {name}{suffix}: no rows", file=sys.stderr)
            continue
        seen: dict[str, None] = {}          # union of the columns of every result table, first-seen order
        for r in rows:
            seen.update(dict.fromkeys(r))
        fields = [k for k in seen if k not in ("", "result", "table", "_time", *tags)]
        fields = [f for f in order if f in fields] + sorted(f for f in fields if f not in order)
        path = os.path.join(out, f"{name}{suffix}.csv")
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["time_utc", "time_local", "t_s", *tags, *fields])
            for r in rows:
                t = influx_time(r["_time"])
                w.writerow([t.isoformat().replace("+00:00", "Z"), t.astimezone(LOCAL_TZ).isoformat(),
                            f"{(t - start).total_seconds():.3f}", *(r.get(k, "") for k in tags),
                            *(r.get(f, "") for f in fields)])
        print(f"  {os.path.basename(path)}: {len(rows)} rows, {rows[0]['_time']} .. {rows[-1]['_time']}")
        written.append(path)
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=".")
    ap.add_argument("--states", default="RUN_OL", help="comma list of firmware states to keep, or 'all'")
    ap.add_argument("--window", nargs=3, action="append", metavar=("NAME", "FROM", "TO"), required=True)
    ap.add_argument("--fields", help="comma list of telemetry fields to keep (default all; e.g. T1,T2,T3,heatsink_c)")
    ap.add_argument("--every", help="downsample with a mean over this window, e.g. 1s (default: raw 50 Hz rows)")
    ap.add_argument("--no-eload", action="store_true", help="skip the e-load CSV")
    ap.add_argument("--pver", help="keep only telemetry whose parameter version matches this regex, e.g. qspice300")
    a = ap.parse_args()
    states = None if a.states == "all" else set(a.states.split(","))
    fields = a.fields.split(",") if a.fields else None
    os.makedirs(a.out, exist_ok=True)
    for name, f, t in a.window:
        start, stop = parse_time(f), parse_time(t)
        print(f"{name}: {start.astimezone(LOCAL_TZ):%Y-%m-%d %H:%M:%S} .. {stop.astimezone(LOCAL_TZ):%Y-%m-%d %H:%M:%S} "
              f"local, states {a.states}" + (f", fields {a.fields}" if fields else "") + (f", mean every {a.every}" if a.every else ""))
        export(name, start, stop, a.out, states, fields, a.every, not a.no_eload, a.pver)


if __name__ == "__main__":
    main()
