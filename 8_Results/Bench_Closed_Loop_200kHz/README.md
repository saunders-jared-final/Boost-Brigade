# Bench closed loop, 16 Oct 2026 (NGE103 PSUs with unbalanced limits into the DL3021 in CV; 200 / 300 / 400 kHz images)

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
| `Bench CL 16Oct qspice200 1525-1609` (15:25:00-16:09:00) | 81429 | 14048 | 338 | every 200 kHz closed-loop attempt (gains 10-30 %), several end in FAULT |
| `Bench CL 16Oct run 1550-1553` (15:49:30-15:53:30) | 8073 | 1666 | 12 | good run, gain 20 % |
| `Bench CL 16Oct run 1602-1605` (16:01:00-16:05:00) | 11118 | 2087 | 11 | good run, gain 20 % with the ADC phase-B reduction |
| `Bench CL 16Oct qspice300 1716-1742` (17:16:00-17:42:00) | 76308 | 9758 | 290 | 300 kHz image, gains 30 / 50 % |
| `Bench CL 16Oct qspice400 1804-1819` (18:04:00-18:19:00) | 46257 | 5952 | 143 | 400 kHz image, gain 30 % |

Closed-loop segments and events per window: `8_Results/analysis/out/events/` (made by `analysis/events.py`).
Regenerate: `python3 8_Results/analysis/influx_pull.py --force` (needs the Pi's InfluxDB reachable).
