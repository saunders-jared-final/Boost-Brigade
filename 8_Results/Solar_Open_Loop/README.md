# Solar open loop, 20 Oct 2026 (carpark, 3 x KAUSSP80, DL3021 e-load in CV)

Firmware shuffler-fw-0.4.1, 200 kHz PWM, gain set sps-params-2.20261015-1950-3mod-qspice200-bench (open loop:
all four duties fixed at 0.5). Times are Australia/Brisbane (AEST, UTC+10). The PNGs are Grafana panel
screenshots; each CSV is the InfluxDB data behind the same window, exported with `7_Pi/tools/influx_export.py`.

## Files

| Window (local) | Telemetry CSV (state RUN_OL only) | E-load CSV | Screenshots |
|---|---|---|---|
| 12:53:39 - 12:53:52 | `Full sun max output 1253-1254.csv` (575 rows) | `... eload.csv` (74 rows) | Full sun max output 1253-1254 {Current, Power, Voltage} |
| 13:01:56 - 13:03:12 | `Full sun #1 1301-1303 (no eload).csv` (2854 rows, OL from 13:02:07) | none: load paused / in local mode | Full sun #1 1301-1303 (no eload) |
| 14:10:25 - 14:10:46 | `Open Loop 1410.csv` (828 rows, OL 14:10:26 - 14:10:44) | `... eload.csv` (122 rows) | Open Loop {Eload Current, Inductor Current, Module Power, Module Voltage} 1410 |
| 14:11:29 - 15:53:54 | `Open Loop Data (Long Term Load) 1411-1553.csv` (112 895 rows) | `... eload.csv` (35 777 rows) | Open Loop Data {, Current, Power} (Long Term Load) |
| 15:04:36 - 15:07:45 | `Full sun #2 1504-1507.csv` (8489 rows) | `... eload.csv` (1103 rows) | Full sun #2 {Current, Power, Voltage} 1504-1507 |

The long-term window also contains closed-loop, idle and stop periods; those rows are not in the CSV. Its
RUN_OL segments (gaps > 2 s split them):

```
14:11:29-14:12:40  14:15:26-14:29:00  14:29:22-14:32:00  14:32:37-14:38:35  14:42:33-14:44:02
14:58:09-14:59:27  15:04:37-15:07:44  15:20:53-15:22:09  15:39:02-15:46:57  15:48:24-15:51:18
```
(`Full sun #2 1504-1507` is the 15:04:37-15:07:44 segment on its own.)

## Columns

Telemetry (one row per T frame, 50 Hz): `time_utc`, `time_local`, `t_s` (seconds since the window start),
`state`, `pver`, then the T-frame fields of `0_Documentation/telemetry.md`: `VM1..VM3` module voltages (V),
`Vstr` string voltage from the e-load (V), `ILA1 ILB1 ILA2 ILB2` inductor currents (A), `dA1 dB1 dA2 dB2`
duties, `rv1 rv2 beta stress IM1r IM2r` (controller outputs, zero in open loop), `T1 T2` driver temperatures
(degC), `kscale`, `pset`, `fault` (bit mask), `state_code`. The hall sensor on ILA1 was not functional in the
12:53 run (see the screenshot title).

E-load (DL3021 poll log): fast rows at ~5 Hz carry `v` (V), `i` (A), `p` (W); the 1 Hz rows carry `mode`,
`input_on`, `setpoint` (active mode), `set_cc/cv/cr/cp`, `r`, `range_i`, `range_v`, `ques`, `link_ok`, `paused`.
Fields a row did not report are empty; forward-fill the slow ones if you need them per sample.

## Regenerate / add a window

```
python3 7_Pi/tools/influx_export.py --out 8_Results/Solar_Open_Loop \
    --window "<name>" <from> <to>          # epoch ms from the Grafana URL, or ISO-8601 local time
    [--states all | RUN_OL,RUN_CL]         # default RUN_OL
```
Needs the Pi's InfluxDB reachable (default http://10.15.78.91:8086, token in the script's environment defaults).
