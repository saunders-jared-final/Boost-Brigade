| case | slide | setup | f_sw [kHz] | loop | kscale (telemetry) | window (local) | RUN segs | RUN [s] | frames | rate [Hz] | frozen dropped | VM1 source | events in window | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B01 | 48 | BENCH | 200 | OL | - | 14:32:00-14:44:56 | 2 | 706.5 | 29592 | 39.8 | 0 | e-load V - VM2 - VM3 (telemetry VM1 invalid) | fault x1, load_step x9 | duties 0.5; e-load CV set-point steps 125 <-> 60 V; VM1 from the e-load |
| B01s |  | BENCH | 200 | OL | - | 15:09:00-15:16:00 | 1 | 412.1 | 17112 | 39.8 | 0 | e-load V - VM2 - VM3 (telemetry VM1 invalid) | duty_step x4, fault x1, load_step x4 | not on a slide: the only open-loop duty steps (15:11:42 S2 +0.02/leg, 15:13:00 S1 & S2 -0.01/leg, 15:15:15 S1 +0.02/leg); ends in FAULT |
| B02 | 42 | BENCH | 200 | CL | 0.1 | 15:31:34-15:34:25 | 2 | 160.6 | 1867 | 11.3 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x2 | before the ADC fix; PSU unstable |
| B03 | 43 | BENCH | 200 | CL | 0.3 | 16:02:05-16:04:33 | 1 | 143.1 | 2107 | 14.1 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x1, load_step x2 | slide says kscale 20 %, telemetry says 0.3 with pset 0 (boot default after the re-flash for the ADC phase-B fix; no SET/APPLY sent) |
| B04 | 44 | BENCH | 200 | CL | 0.3/0.4 | 16:07:00-16:07:49 | 2 | 47.1 | 701 | 14.1 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x1, fault x1, kscale_apply x1 | kscale 0.4 applied at 16:07:50 -> OC fault within 1 s |
| B05 | 49 | BENCH | 300 | OL | - | 16:31:36-16:37:04 | 2 | 303.8 | 11633 | 36.4 | 0 | telemetry (e-load V via Pi, 2 Hz) |  |  |
| B06 | 45 | BENCH | 300 | CL | 0.3 | 17:17:00-17:25:49 | 2 | 511.5 | 23223 | 44.1 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x2, fault x1, load_step x7 | PSU / e-load set-point steps 17:22:30-17:25:30 while closed |
| B07 | 46 | BENCH | 300 | CL | 0.3/0.4/0.5/0.6 | 17:34:08-17:41:47 | 7 | 294.6 | 13384 | 44.1 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x4, fault x2, kscale_apply x15, load_step x2 |  |
| B08 | 50 | BENCH | 400 | OL | - | 18:02:03-18:04:38 | 2 | 151.7 | 6890 | 44.1 | 0 | telemetry (e-load V via Pi, 2 Hz) | fault x1, kscale_apply x1, load_step x1 | PSU change at 18:03:40 |
| B09 | 47 | BENCH | 400 | CL | 0.3 | 18:05:11-18:13:40 | 4 | 391.8 | 17769 | 43.9 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x4, fault x1, kscale_apply x2, load_step x2 |  |
| S01 | 24 | PV80 | 200 | OL | - | 15:04:35-15:07:47 | 1 | 187.0 | 8489 | 44.4 | 0 | telemetry (e-load V via Pi, 2 Hz) | irradiance_down x1, mismatch_off x1 | peak sun |
| S02 | 25 | PV80 | 200 | CL | 0.1 | 15:08:40-15:12:44 | 1 | 236.8 | 10748 | 44.2 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x1, irradiance_down x1, irradiance_up x1, mismatch_off x2, mismatch_on x2 | peak sun; shade event about 15:09:20-15:10:40 |
| S03 | 26 | PV80 | 200 | OL | - | 15:48:22-15:51:20 | 1 | 174.3 | 7906 | 44.4 | 0 | telemetry (e-load V via Pi, 2 Hz) | mismatch_off x2, mismatch_on x1 | minimal sun |
| S04 | 27 | PV80 | 200 | CL | 0.1 | 15:52:03-15:56:31 | 1 | 265.1 | 12028 | 44.2 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x1 | minimal sun |
| S05 | 37 | PV80 | 200 | CL | 0.2 | 15:56:51-16:00:47 | 1 | 229.1 | 10402 | 44.2 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x1, kscale_apply x1, mismatch_on x1 | minimal sun |
| S06 | 38 | PV80 | 200 | CL | 0.3 | 16:01:07-16:04:19 | 1 | 188.6 | 8559 | 44.2 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x1 | minimal sun |
| S07 | 39 | PV80 | 200 | CL | 0.4 | 16:05:30-16:08:17 | 1 | 155.7 | 7071 | 44.2 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x1 | minimal sun |
| S08 | 40 | PV80 | 200 | CL | 0.5 | 16:09:42-16:12:16 | 1 | 150.3 | 6829 | 44.2 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x1, kscale_apply x1, mismatch_on x1 | minimal sun |
| S09 |  | PV80 | 200 | CL | 0.6 | 16:13:15-16:18:00 | 1 | 278.3 | 12633 | 44.2 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x1, kscale_apply x2 | not on a slide (closed_loop_timeslots.pdf) |
| S10 |  | PV80 | 200 | CL | 0.7 | 16:19:05-16:22:12 | 1 | 178.4 | 8101 | 44.2 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x1, kscale_apply x2 | not on a slide (closed_loop_timeslots.pdf) |
| S11 |  | PV80 | 200 | CL | 0.8 | 16:23:05-16:24:45 | 1 | 90.5 | 4111 | 44.2 | 0 | telemetry (e-load V via Pi, 2 Hz) | close x1 | not on a slide (closed_loop_timeslots.pdf) |
