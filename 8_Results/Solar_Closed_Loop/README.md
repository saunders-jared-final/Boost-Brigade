# Carpark solar closed loop, 20 Oct 2026 (3 x KAUSSP80, DL3021 e-load in CV)

Exports from the pod's InfluxDB made by `8_Results/analysis/influx_pull.py` (windows in `analysis/config.py`,
each widened by 60 s so the open-loop baseline and the kscale command before a run are inside).
Times are Australia/Brisbane (AEST, UTC+10). Unlike the open-loop folders these exports keep **every firmware
state** (`state` column: IDLE, SOFTSTART, RUN_OL, RUN_CL, STOP, FAULT ...), so a closed-loop run can be cut
from its open-loop baseline to its end.

Per window: `<name>.csv` telemetry (50 Hz T frames, columns as in `Solar_Open_Loop/README.md`), `<name> eload.csv`
(DL3021 log), and the pod's records: `<name> cmd.csv` (every command sent, `dir=tx`; answers that were not routine,
`dir=rx`; IR keys, `dir=ir`; e-load commands with their `answer`), `<name> params.csv` (the full parameter set after
every APPLY), `<name> fault.csv`, `<name> status.csv`, `<name> note.csv`. `<day> cmd.csv` etc. are the whole day.

| Window (local, before widening) | Telemetry rows | E-load rows | cmd rows | Note |
|---|---|---|---|---|
| `Solar OL+CL 20Oct 1252-1313` (12:52:00-13:13:00) | 64241 | 5210 | 109 | first closed-loop runs; shirt on module 3 and a person walking round the panels |
| `Solar CL 20Oct 1508-1513` (15:08:00-15:13:30) | 20456 | 2624 | 26 | peak sun, kscale 0.1 |
| `Solar CL 20Oct 1515-1518` (15:15:00-15:18:00) | 13627 | 1763 | 14 | short run after a kscale step up |
| `Solar CL 20Oct kscale sweep 1551-1626` (15:51:00-16:26:00) | 96111 | 12364 | 141 | kscale 0.1 .. 0.8, each level a fresh OL -> CL engagement |

Closed-loop segments and events per window: `8_Results/analysis/out/events/` (made by `analysis/events.py`).
Regenerate: `python3 8_Results/analysis/influx_pull.py --force` (needs the Pi's InfluxDB reachable).
