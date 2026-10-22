# Test cases of the presentation (raw-data slides), exported from the pod's InfluxDB

Each raw-data slide of `0_Documentation/n11034459_CapstoneDelivery_V2.pdf` shows four Grafana panels over one time
range; those ranges (read off the panel headers, local AEST) are the test cases in `8_Results/analysis/config.py`
(`TEST_CASES`). Exports are widened by 5 s and keep **every firmware state** (`state` column) so the
RUN_OL / RUN_CL rows can be cut out exactly (`8_Results/analysis/phases/hardware.py`). Per case: `<id>_<label>.csv`
telemetry (T frames, ~45 Hz), `<id>_<label> eload.csv` (DL3021, 5 Hz), `... cmd/params/fault/status/note.csv` (pod records).

| id | slide | day | f_sw | loop | kscale | window (local) | telemetry rows | e-load rows | note |
|---|---|---|---|---|---|---|---|---|---|
| B01 | p48 | 2026-10-16 | 200 kHz | OL | - | 14:32:00-14:44:56 | 32097 | 4573 | duties 0.5; e-load CV set-point steps 125 <-> 60 V; VM1 from the e-load |
| B01s | - | 2026-10-16 | 200 kHz | OL | - | 15:09:00-15:16:00 | 17854 | 2505 | not on a slide: the only open-loop duty steps (15:11:42 S2 +0.02/leg, 15:13:00 S1 & S2 -0.01/leg, 15:15:15 S1 +0.02/leg); ends in FAULT |
| B02 | p42 | 2026-10-16 | 200 kHz | CL | 0.1 | 15:31:34-15:34:25 | 2700 | 1064 | before the ADC fix; PSU unstable |
| B03 | p43 | 2026-10-16 | 200 kHz | CL | 0.3 | 16:02:05-16:04:33 | 2722 | 913 | slide says kscale 20 %, telemetry says 0.3 with pset 0 (boot default after the re-flash for the ADC phase-B fix; no SET/APPLY sent) |
| B04 | p44 | 2026-10-16 | 200 kHz | CL | 0.3 | 16:07:00-16:07:49 | 1157 | 344 | kscale 0.4 applied at 16:07:50 -> OC fault within 1 s |
| B05 | p49 | 2026-10-16 | 300 kHz | OL | - | 16:31:36-16:37:04 | 12934 | 1984 |  |
| B06 | p45 | 2026-10-16 | 300 kHz | CL | 0.3 | 17:17:00-17:25:49 | 24471 | 3133 | PSU / e-load set-point steps 17:22:30-17:25:30 while closed |
| B07 | p46 | 2026-10-16 | 300 kHz | CL | 0.5 | 17:34:08-17:41:47 | 21276 | 2721 |  |
| B08 | p50 | 2026-10-16 | 400 kHz | OL | - | 18:02:03-18:04:38 | 7490 | 961 | PSU change at 18:03:40 |
| B09 | p47 | 2026-10-16 | 400 kHz | CL | 0.3 | 18:05:11-18:13:40 | 23533 | 3026 |  |
| S01 | p24 | 2026-10-20 | 200 kHz | OL | - | 15:04:35-15:07:47 | 9175 | 1180 | peak sun |
| S02 | p25 | 2026-10-20 | 200 kHz | CL | 0.1 | 15:08:40-15:12:44 | 11534 | 1479 | peak sun; shade event about 15:09:20-15:10:40 |
| S03 | p26 | 2026-10-20 | 200 kHz | OL | - | 15:48:22-15:51:20 | 8528 | 1093 | minimal sun |
| S04 | p27 | 2026-10-20 | 200 kHz | CL | 0.1 | 15:52:03-15:56:31 | 12615 | 1620 | minimal sun |
| S05 | p37 | 2026-10-20 | 200 kHz | CL | 0.2 | 15:56:51-16:00:47 | 11166 | 1436 | minimal sun |
| S06 | p38 | 2026-10-20 | 200 kHz | CL | 0.3 | 16:01:07-16:04:19 | 9168 | 1171 | minimal sun |
| S07 | p39 | 2026-10-20 | 200 kHz | CL | 0.4 | 16:05:30-16:08:17 | 8040 | 1037 | minimal sun |
| S08 | p40 | 2026-10-20 | 200 kHz | CL | 0.5 | 16:09:42-16:12:16 | 7451 | 952 | minimal sun |
| S09 | - | 2026-10-20 | 200 kHz | CL | 0.6 | 16:13:15-16:18:00 | 13387 | 1718 | not on a slide (closed_loop_timeslots.pdf) |
| S10 | - | 2026-10-20 | 200 kHz | CL | 0.7 | 16:19:05-16:22:12 | 8944 | 1152 | not on a slide (closed_loop_timeslots.pdf) |
| S11 | - | 2026-10-20 | 200 kHz | CL | 0.8 | 16:23:05-16:24:45 | 4997 | 646 | not on a slide (closed_loop_timeslots.pdf) |

Regenerate: `python3 8_Results/analysis/influx_pull.py --cases --force` (needs the Pi's InfluxDB reachable).
