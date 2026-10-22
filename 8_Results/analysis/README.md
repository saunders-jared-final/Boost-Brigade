# Results synthesis (`8_Results/analysis`)

One pipeline that takes the **raw-data slides of the presentation** as test cases (`config.TEST_CASES`: the Grafana
window of every slide, RUN_OL / RUN_CL rows only), computes the same step / disturbance / steady-state / noise /
energy metrics on them and on every simulation phase (analytical N-module model, QSPICE switching plant with the
firmware DLL, Simulink carpark twin and its validate suite, Simulink MIL validate suite), draws one consistent figure
set (vector PDF + PNG) and writes `REPORT.md` entirely from the tables.

```
make test            # unit tests of the metric definitions (stepmetrics, energy)
make pull-cases      # 8_Results/TestCases/<id>_<label>*.csv from the Pi's InfluxDB (every state + e-load + pod logs)
make all             # hw -> events -> metrics -> ripple -> figures -> compare -> report   (a few minutes)
make carpark-validate mil-validate   # MATLAB validate suites (CSV/JSON + light-theme PDF figures), 10 min / 25-65 min
make qspice-extra simulink-extra     # kscale 0.2 / 0.5 runs (an hour / 25 min); `make compare report` picks them up
```

| step | script | writes |
|---|---|---|
| `hw` | `hwcases.py --figures` | `out/hw/<case>.csv` (cleaned RUN-only frames: stale values removed, vd/ic/id/uc/ud, KCL module currents, powers), `out/hw/segments.csv`, `out/tables/T1_inventory`, `out/figures/hardware/<case>_overview` (the slide replacement), `out/events/<case>.{events,segments}.csv` |
| `events` | `figures.py --events` | `out/figures/events/<case>_e<n>_<kind>` zooms (loop close, duty step, load step, mismatch / irradiance, kscale apply) |
| `metrics` | `hwmetrics.py` | `T2_hw_steady_state` (mean/std/pk-pk/RMS/dominant frequency, SSE), `T3_hw_events` (step & disturbance metrics per event and signal), `T7_energy` |
| `ripple` | `ripple.py` | `T6_ripple` (analytical law, QSPICE incl. one raw-waveform read per frequency, hardware noise for contrast), `out/qspice/ripple_<f>k.csv` |
| `figures` | `figures.py --sims ...` | per-run figures: `out/figures/{analytical,qspice,carpark,carpark_validate,mil_validate}/` |
| `compare` | `compare.py` | `T4_sim_step_metrics`, `T5_cross_phase` (hardware column = bounds), `G_compare`, `out/figures/compare/` (step overlays with the hardware events underneath, metrics vs kscale, ripple vs f_sw, hardware steady state, S5 duty steps) and `out/figures/energy/` |
| `report` | `report.py` | `REPORT.md` (scope + metric definitions, T1-T7, computed findings, figure index keyed by slide page, caveats) |

**Data rules** (details in `REPORT.md` section 0): only RUN rows; `rv, beta, stress, IM1r, IM2r` are recomputed by KCL
(they freeze outside RUN_CL); start-up / shutdown frames still tagged RUN are trimmed; VM1 is taken from the e-load when
the telemetry VM1 is invalid; telemetry is ~45 Hz (11-14 Hz on some 200 kHz runs) so hardware rise / peak / settling
times shorter than one sample are reported as `<= 23 ms` bounds, never as measurements.

**Metric definition**: `stepmetrics.step_metrics` (robust levels, 10-90 % rise, peak value / time with an overshoot flag,
overshoot / undershoot, 2 % / 5 % and absolute-band settling, steady-state error, IAE, first / second-order fit) and
`stepmetrics.ripple_stats`; energy definitions in `energy.py` (E_load, E_modules, E_shuffled, E_returned = above a
weakest-module-limited series string).

**Conventions**: `vd1 = VM1-VM2`, `vd2 = VM2-VM3`, `ic = ILA+ILB` (circulating, reference 0), `id = i_sh = ILA-ILB`
(shuffled, into the midpoint), `uc = dA+dB-1`, `ud = dA-dB`. Phase loaders in `phases/` (`hardware.py` = test cases,
`analytical.py` = nstring with the per-frequency gain sets, `qspice.py`, `simulink.py` = carpark scenario runs,
`validate.py` = the validate suites' exports); all return the tidy format of `tidy.py`. Style and colours of every
figure: `figstyle.py` / `config.PHASE_STYLE`.

Older entry points kept for reference: `config.WINDOWS` + `events.py --plot` (the closed-loop windows of the first
synthesis), `compare_legacy.py`, `report_legacy.py`. PNG twins of the figures and `out/logs/` are git-ignored
(`make all` rebuilds them); the PDFs are tracked.
