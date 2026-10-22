# Results: CSV exports behind the Grafana screenshots

> **Analysis of the presentation's raw-data slides:** `TestCases/` holds a fresh export of every slide window
> (all firmware states, e-load, pod logs; `analysis/influx_pull.py --cases`), and `analysis/` turns them into the
> metrics, figures and `analysis/REPORT.md` (see `analysis/README.md`). Regenerated figures: `analysis/out/figures/`
> (one overview per slide in `hardware/`, event zooms in `events/`, simulations, comparisons, energy).


Every PNG here is a Grafana panel screenshot of the pod's InfluxDB. The CSVs next to them are the data for the
same window, exported with `7_Pi/tools/influx_export.py` (standard-library Python; it reads the Pi's InfluxDB
over the network). Times are Australia/Brisbane (AEST, UTC+10). The e-load CSVs are the DL3021 poll log for the
same window; a file that would have held no load data was not written.

Two kinds of export:

- **Telemetry, RUN_OL only** (default): one row per 50 Hz T frame while the firmware was in open loop. Columns
  `time_utc, time_local, t_s` (s since window start), `state, pver` (gain-set version), then the T-frame fields
  of `0_Documentation/telemetry.md`: `VM1..VM3`, `Vstr`, `ILA1 ILB1 ILA2 ILB2`, `dA1 dB1 dA2 dB2`, `rv1 rv2 beta
  stress IM1r IM2r` (controller outputs, zero in open loop), `T1 T2 (T3)` driver temperatures, `kscale pset fault
  state_code`. Older firmware (13 Oct) did not log `VM1`, `Vstr`, `kscale`, `pset`.
- **Temperature, all states, 1 s mean**: `T1 T2 T3` (INA die / driver temperatures from the Nucleo, tagged with
  the firmware state) and `heatsink_c` (Pi-side sensor, no state tag so it sits on its own rows with an empty
  `state`).

## 16 Oct 2026, bench (DL3021 e-load, CV 70 V)

The firmware state is tagged with the gain-set version (`pver`), which changed with the PWM frequency that day:
qspice200 until 16:21, qspice300 16:31-17:30, qspice400 18:02-18:04 (RUN_OL spans). Each folder has the
screenshot window as taken plus the whole RUN_OL span of the matching gain set; every row of a screenshot
export carries the gain set of its folder.

| Folder | File | Window | Rows |
|---|---|---|---|
| Bench_Open_Loop_200kHz | `Bench OL 200kHz 16Oct 1431-1437.csv` (+ eload) | 14:31:34-14:37:30, the screenshots | 13 491 |
| Bench_Open_Loop_200kHz | `Bench OL 16Oct all RUN_OL pver qspice200 1416-1621.csv` (+ eload) | every RUN_OL sample with the 200 kHz gain set | 106 615 |
| Bench_Open_Loop_300kHz | `Bench OL 300kHz 16Oct 1631-1636.csv` (+ eload) | 16:31:27-16:36:29, the screenshots | 10 844 |
| Bench_Open_Loop_300kHz | `Bench OL 16Oct all RUN_OL pver qspice300 1631-1730.csv` (+ eload) | every RUN_OL sample with the 300 kHz gain set | 28 407 |
| Bench_Open_Loop_400khz | `Bench OL 400kHz 16Oct 1801-1804.csv` (+ eload) | 18:01:55-18:04:40, the screenshots (the only 400 kHz open-loop run) | 6890 |
| Bench_Open_Loop_400khz | `Bench OL 16Oct all RUN_OL pver qspice400 1802-1805.csv` (+ eload) | same run, slightly wider e-load window | 6890 |
| 8_Results | `LAB INA Temp 16Oct 1420-1836.csv` | 14:20:00-18:36:05, temperatures, all states, 1 s mean | 26 926 |

## 13 Oct 2026, bench, 100 kHz (Bench_Open_Loop_100kHz)

`ol100k_a.csv` / `ol100k_b.csv` (+ `_eload`, `_oppoints`) are the earlier exports behind the `ol100k_*` plots
(12:20-14:00 and 14:55-15:07, all states). `Bench OL 100kHz 13Oct 0930-1530 RUN_OL.csv` (+ eload) is the
`*-13-10-26.png` screenshot window, 09:30-15:30, RUN_OL only, 320 457 rows; its RUN_OL segments:
09:51-09:53, 09:59-10:06, 10:07-10:09, 12:25-12:53, 12:54-14:01, 14:59-15:06.
`100khz thermal data 13-14Oct.csv` is the temperature screenshot, 13 Oct 09:09 to 14 Oct 20:30, 1 s mean.

## 20 Oct 2026, carpark solar

See `Solar_Open_Loop/README.md` for the five open-loop windows. `Solar INA Temp 20Oct 1252-1625.csv` is the
temperature screenshot, 12:52:04-16:25:54, all states, 1 s mean.

## Regenerate / add a window

```
python3 7_Pi/tools/influx_export.py --out <folder> --window "<name>" <from> <to> [...]
    <from> <to>: epoch ms copied from the Grafana URL, or ISO-8601 local time (2026-10-16T14:31:34+10:00)
    --states RUN_OL,RUN_CL | all     firmware states to keep (default RUN_OL)
    --pver qspice300                 keep only rows of that gain-set version
    --fields T1,T2,T3,heatsink_c     subset of telemetry fields
    --every 1s                       downsample with a mean
    --no-eload                       skip the e-load CSV
```
