# Results synthesis: control behaviour across analysis, Simulink, QSPICE, bench and PV

_Generated 2026-10-21 22:18 by `8_Results/analysis/report.py`; rerun `make report` after any change._

## 0 · Findings of the 21 Oct 2026 run

- **Reference step (S4, `vd2`, time constant of the fitted first-order response):** at kscale 0.1 the analytical model
  (12.2 ms PV80), the Simulink carpark model (11.6 / 10.1 ms) and the QSPICE switching model with the firmware DLL
  (12.4 / 9.7 ms) agree with the pure-integral design value (10.6 ms) within 20 %. At kscale 0.3 the same holds
  (3.5-4.0 ms against 3.5 ms design). At kscale 1 the switching model (0.77 / 0.55 ms) and Simulink (0.56 / 0.40 ms)
  are about twice as fast as the design value (1.06 ms) and the analytical closed loop (1.08 ms), and the first
  overshoot appears (QSPICE 4 %, Simulink bench 9 %): the proportional term and a plant gain above the one the
  deployed decoupler assumes become visible at full gain. No reference step was sent on hardware.
- **Loop closing (S1):** on the bench the soft start ramps the duties to 0.5 in about 200 ms and removes most of the
  5 V module mismatch by itself; the controller then takes the 0.5 V residual to zero within one 50 Hz sample
  (<= 23-25 ms) at every kscale from 0.1 to 0.6, consistent with the 4-41 ms settling the simulations predict.
  On the solar day the panels were matched (residual 0.1 V), except the 13:04 run under the shirt (3.7 V idle
  mismatch), where the supervisor then held `vd2` at its own reference.
- **Shade (S3):** all three simulations move the shuffled current by 1.5-1.9 A within a millisecond of a one-third
  irradiance loss on module 3 (analytical 1.7 A, Simulink 1.9 A, QSPICE 1.5 A); on hardware the shade events are
  10-34 W power dips with multi-second recoveries set by the shirt / hand motion and the e-load, not by the loop.
- **Settled statistics (S2):** bench `vd2` noise fell from 0.08 V (early runs) to 0.013-0.017 V after the
  ADC phase-B change at 16:02; on the solar sweep the circulating-current noise grows with gain
  (0.22 A at kscale 0.1 to 0.31 A at 0.8) while `vd2` stays at 0.09-0.17 V.
- **Gain matrices (section 5):** the averaged model reproduces the identified voltage-mode gains (-Vbar: -41 PV80,
  -46.5 at the QSPICE bench point, against -37 to -47 V per unit identified) and the circulating-mode gain is Vbar / R
  with R the plant's effective winding resistance: 61 mOhm in the averaged Simulink model (742 identified) and
  0.27 / 0.79 / 1.66 ohm in the switching plant at 200 / 300 / 400 kHz (142 / 58 / 23 A per unit). That resistance is
  the pole-capacitance commutation during the dead time, R_sw = 64 C_p f_sw^3 (L+M)^2 = 0.21 / 0.72 / 1.70 ohm for
  C_p = 2.2 nF (derived and checked against a QSPICE u_d sweep in `3_Analytical/shuffler_notebooks/shuffler_nstring.ipynb`,
  section 8). The switching plant also carries a -10 to -25 V per unit coupling from differential duty to voltage
  difference that the averaged model does not contain.

## 1 · Method

One metric definition (`stepmetrics.step_metrics`) is applied to every phase and signal. Levels are medians (pre-event window,
last 20 % of the post-event window); the response is normalised by the measured change `delta`; **rise time** is 10-90 % with
interpolated crossings; **overshoot** is against the measured final value; **settling** is the last excursion outside a 2 % (5 %)
band, never narrower than three times the pre-event noise; **steady-state error** is against the reference. Changes smaller than
a floor (0.1 V, 0.3 A, 3 W) are treated as disturbances: peak deviation and time back inside the band. A first-order or
second-order model with delay is fitted by least squares; its time constant (with a 1-sigma interval) is the quantity that
makes 50 Hz telemetry comparable with 10 kHz simulations. When fewer than four samples fall inside the transient the time
metrics are reported as upper bounds (`<=` one sample).

Scenarios: **S1** the loop closing on the string mismatch (hardware: every SOFTSTART -> RUN_CL; QSPICE: the true open-loop ->
closed-loop switch; Simulink and analytical: a reference step of `-vd_OL` from a settled loop, equivalent to first order
because the firmware's bumpless rebase starts the integrators at zero; the analytical row simulates the true initial-condition
response); **S2** settled statistics per kscale; **S3** module 3 shaded to about two thirds from a settled loop (hardware:
candidate events detected in the data, to be confirmed); **S4** a +1 V step on the VM2-VM3 reference (simulations only; no
reference step was sent on hardware).

Design reference (pure-integral loop, `kI_v = 2*pi*150`, `kI_i = 2*pi*400`, scaled by kscale): voltage-difference loop
tau 10.6 / 3.5 / 1.06 ms, 10-90 rise 23 / 7.8 / 2.3 ms, 2 % settling 41 / 14 / 4.1 ms at kscale 0.1 / 0.3 / 1;
circulating-current loop tau 4.0 / 1.3 / 0.40 ms.

Conventions: `vd1 = VM1-VM2`, `vd2 = VM2-VM3`, `ic = ILA+ILB` (circulating, nulled by the controller), `id = ILA-ILB` (shuffled).
Hardware telemetry is 50 Hz; VM1 comes from the e-load through the Pi at 2.2 Hz, so hardware step metrics use `vd2`;
the inductor-current frames are point samples of the switching ripple, so currents enter only through the S2 statistics.

## 2 · Hardware data inventory

Exports: `8_Results/Bench_Closed_Loop_200kHz/`, `8_Results/Solar_Closed_Loop/` (READMEs there). Events and segments: `out/events/`.

| window | RUN_CL segments (kscale) | FAULT ends | shade candidates in runs | note |
|---|---|---|---|---|
| `Bench CL 16Oct qspice200 1525-1609` | 9 (0.3, 0.1, 0.1, 0.1, 0.3, 0.2, 0.3, 0.3, 0.3) | 7 | 10 | every 200 kHz closed-loop attempt (gains 10-30 %), several end in FAULT |
| `Bench CL 16Oct run 1550-1553` | 1 (0.3) | 0 | 1 | good run, gain 20 % |
| `Bench CL 16Oct run 1602-1605` | 1 (0.3) | 0 | 3 | good run, gain 20 % with the ADC phase-B reduction |
| `Bench CL 16Oct qspice300 1716-1742` | 9 (0.3, 0.3, 0.4, 0.4, 0.4, 0.5, 0.6, 0.4, 0.3) | 10 | 3 | 300 kHz image, gains 30 / 50 % |
| `Bench CL 16Oct qspice400 1804-1819` | 5 (0.3, 0.3, 0.3, 0.3, 0.3) | 2 | 2 | 400 kHz image, gain 30 % |
| `Solar OL+CL 20Oct 1252-1313` | 2 (0.2, 0.2) | 5 | 12 | first closed-loop runs; shirt on module 3 and a person walking round the panels |
| `Solar CL 20Oct 1508-1513` | 1 (0.1) | 0 | 4 | peak sun, kscale 0.1 |
| `Solar CL 20Oct 1515-1518` | 1 (0.2) | 0 | 0 | short run after a kscale step up |
| `Solar CL 20Oct kscale sweep 1551-1626` | 8 (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8) | 0 | 0 | kscale 0.1 .. 0.8, each level a fresh OL -> CL engagement |

Overview plots per window (state bands, 1 s medians of module voltages, string power, currents, duties, detected events):

- [Bench CL 16Oct qspice200 1525-1609.png](out/events/Bench CL 16Oct qspice200 1525-1609.png)
- [Bench CL 16Oct qspice300 1716-1742.png](out/events/Bench CL 16Oct qspice300 1716-1742.png)
- [Bench CL 16Oct qspice400 1804-1819.png](out/events/Bench CL 16Oct qspice400 1804-1819.png)
- [Bench CL 16Oct run 1550-1553.png](out/events/Bench CL 16Oct run 1550-1553.png)
- [Bench CL 16Oct run 1602-1605.png](out/events/Bench CL 16Oct run 1602-1605.png)
- [Solar CL 20Oct 1508-1513.png](out/events/Solar CL 20Oct 1508-1513.png)
- [Solar CL 20Oct 1515-1518.png](out/events/Solar CL 20Oct 1515-1518.png)
- [Solar CL 20Oct kscale sweep 1551-1626.png](out/events/Solar CL 20Oct kscale sweep 1551-1626.png)
- [Solar OL+CL 20Oct 1252-1313.png](out/events/Solar OL+CL 20Oct 1252-1313.png)

### Shade / walking candidates for confirmation (solar day, inside runs)

Mark the real ones in `out/events/<window>.annot.csv` (columns `time_local,kind,label`), then `make events compare report`.

- `Solar OL+CL 20Oct 1252-1313`: 12:53:41 shade_on [RUN_OL] VM1 +4.40, VM2 -2.19, VM3 -2.19, Pstr +173.52
- `Solar OL+CL 20Oct 1252-1313`: 12:54:01 shade_on [RUN_OL] VM3 -1.86, Pstr +138.59
- `Solar OL+CL 20Oct 1252-1313`: 12:54:31 transient_on [RUN_OL] VM1 -2.05, VM2 +3.95, VM3 -1.89, Pstr +144.48
- `Solar OL+CL 20Oct 1252-1313`: 12:55:40 shade_on [RUN_CL] Pstr -10.22
- `Solar OL+CL 20Oct 1252-1313`: 13:02:47 shade_on [RUN_OL] VM3 -1.33, VM2 -1.61, id2 -0.85
- `Solar OL+CL 20Oct 1252-1313`: 13:04:48 shade_on [RUN_CL] Pstr -43.20, id2 +0.44
- `Solar OL+CL 20Oct 1252-1313`: 13:05:07 shade_on [RUN_CL] id2 -0.42
- `Solar OL+CL 20Oct 1252-1313`: 13:07:59 shade_on [RUN_CL] Pstr -50.79, IM2r +5.13, id2 +5.05
- `Solar OL+CL 20Oct 1252-1313`: 13:08:40 shade_on [RUN_CL] id2 -1.60, Pstr -40.71
- `Solar OL+CL 20Oct 1252-1313`: 13:08:52 shade_on [RUN_CL] Pstr -18.44
- `Solar OL+CL 20Oct 1252-1313`: 13:09:23 shade_on [RUN_CL] Pstr -4.85
- `Solar OL+CL 20Oct 1252-1313`: 13:09:33 shade_on [RUN_CL] Pstr -4.72
- `Solar CL 20Oct 1508-1513`: 15:07:31 shade_on [RUN_OL] id2 +0.41, Pstr -19.39
- `Solar CL 20Oct 1508-1513`: 15:09:48 shade_on [RUN_CL] Pstr -5.03
- `Solar CL 20Oct 1508-1513`: 15:10:29 shade_on [RUN_CL] id2 +0.41, Pstr -24.40
- `Solar CL 20Oct 1508-1513`: 15:11:08 shade_on [RUN_CL] Pstr -4.34

## 3 · S1 · Loop closing on the mismatch

Condensed (medians over cases; full table: [S1_loop_close.md](out/tables/S1_loop_close.md), CSV alongside).

| phase | setup | kscale | signal | cases | |delta| | rise 10-90 [ms] | overshoot [%] | t settle 2 % [ms] | ss error | tau [ms] (fit) | resolved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Analytical N=3 (nstring, deployed M) | BENCH | 0.1 | id2 | 1 | 0.0036 | - | - | - | - | - | 0/1 |
| Analytical N=3 (nstring, deployed M) | BENCH | 0.3 | id2 | 1 | 0.0036 | - | - | - | - | - | 0/1 |
| Analytical N=3 (nstring, deployed M) | BENCH | 1.0 | id2 | 1 | 0.0036 | - | - | - | - | - | 0/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 0.1 | id2 | 1 | 0.16 | - | - | - | - | - | 0/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 0.3 | id2 | 1 | 0.16 | - | - | - | - | - | 0/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 1.0 | id2 | 1 | 0.16 | - | - | - | - | - | 0/1 |
| Simulink carpark 3-module | BENCH | 0.1 | id2 | 1 | 2.9e-05 | - | - | - | - | - | 0/1 |
| Simulink carpark 3-module | BENCH | 0.3 | id2 | 1 | 5e-06 | - | - | - | - | - | 0/1 |
| Simulink carpark 3-module | BENCH | 1.0 | id2 | 1 | 0.00027 | - | - | - | - | - | 0/1 |
| Simulink carpark 3-module | PV80 | 0.1 | id2 | 1 | 2.3e-09 | - | - | - | - | - | 0/1 |
| Simulink carpark 3-module | PV80 | 0.3 | id2 | 1 | 2.6e-09 | - | - | - | - | - | 0/1 |
| Simulink carpark 3-module | PV80 | 1.0 | id2 | 1 | 4.1e-09 | - | - | - | - | - | 0/1 |
| QSPICE switching + firmware DLL | BENCH | 0.1 | id2 | 1 | 0.3 | 0 | 11 | 0 | - | 0.0139 | 0/1 |
| QSPICE switching + firmware DLL | BENCH | 0.3 | id2 | 1 | 0.31 | 0 | 11 | 0 | - | 0.282 | 0/1 |
| QSPICE switching + firmware DLL | BENCH | 1.0 | id2 | 1 | 0.012 | - | - | - | - | - | 0/1 |
| QSPICE switching + firmware DLL | PV80 | 0.1 | id2 | 1 | 0.07 | - | - | - | - | - | 0/1 |
| QSPICE switching + firmware DLL | PV80 | 0.3 | id2 | 1 | 0.071 | - | - | - | - | - | 0/1 |
| QSPICE switching + firmware DLL | PV80 | 1.0 | id2 | 1 | 0.0057 | - | - | - | - | - | 0/1 |
| Analytical N=3 (nstring, deployed M) | BENCH | 0.1 | vd2 | 1 | 0.5 | 23.2 | 0.0016 | 41.4 | 1.2e-05 | 10.6 | 1/1 |
| Analytical N=3 (nstring, deployed M) | BENCH | 0.3 | vd2 | 1 | 0.5 | 7.59 | 2.3e-05 | 13.6 | 1.4e-07 | 3.45 | 1/1 |
| Analytical N=3 (nstring, deployed M) | BENCH | 1.0 | vd2 | 1 | 0.5 | 2.08 | 2.2e-14 | 3.9 | 3.3e-16 | 0.929 | 1/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 0.1 | vd2 | 1 | 0.5 | 28.9 | 0.012 | 51.5 | 9.7e-05 | 13.2 | 1/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 0.3 | vd2 | 1 | 0.5 | 9.51 | 0.00044 | 17 | 3e-06 | 4.32 | 1/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 1.0 | vd2 | 1 | 0.5 | 2.67 | 2.2e-14 | 4.9 | 3.9e-16 | 1.2 | 1/1 |
| Simulink carpark 3-module | BENCH | 0.1 | vd2 | 1 | 0.036 | - | - | - | 0.034 | - | 0/1 |
| Simulink carpark 3-module | BENCH | 0.3 | vd2 | 1 | 0.035 | - | - | - | 0.033 | - | 0/1 |
| Simulink carpark 3-module | BENCH | 1.0 | vd2 | 1 | 0.031 | - | - | - | 0.033 | - | 0/1 |
| Simulink carpark 3-module | PV80 | 0.1 | vd2 | 1 | 0 | - | - | - | 6.9e-05 | - | 0/1 |
| Simulink carpark 3-module | PV80 | 0.3 | vd2 | 1 | 0 | - | - | - | 0.00021 | - | 0/1 |
| Simulink carpark 3-module | PV80 | 1.0 | vd2 | 1 | 1e-07 | - | - | - | -1e-07 | - | 0/1 |
| QSPICE switching + firmware DLL | BENCH | 0.1 | vd2 | 1 | 0.24 | 10.2 | 4 | 0 | -0.0026 | 0.941 | 0/1 |
| QSPICE switching + firmware DLL | BENCH | 0.3 | vd2 | 1 | 0.24 | 0.272 | 45 | 0 | -0.00059 | 0.137 | 0/1 |
| QSPICE switching + firmware DLL | BENCH | 1.0 | vd2 | 1 | 0.16 | 0.758 | 7.8 | 8.45 | 0.0022 | - | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 0.1 | vd2 | 1 | 0.028 | - | - | - | 3.5e-05 | - | 0/1 |
| QSPICE switching + firmware DLL | PV80 | 0.3 | vd2 | 1 | 0.029 | - | - | - | 0.00099 | - | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 1.0 | vd2 | 1 | 0.019 | - | - | - | 0.0067 | - | 0/1 |
| Hardware | BENCH | 0.1 | vd2 | 2 | 2.4 | <= 25 | 4 | <= 25 | -0.005 | 13 | 0/2 |
| Hardware | BENCH | 0.3 | vd2 | 11 | 2.6 | <= 23 | 1.8 | <= 23 | 0 | 0.665 | 0/11 |
| Hardware | BENCH | 0.4 | vd2 | 4 | 2.3 | <= 23 | 2.4 | <= 23 | 0 | 0.247 | 0/4 |
| Hardware | BENCH | 0.5 | vd2 | 1 | 2.3 | <= 23 | 6.2 | <= 23 | 0 | 0.00111 | 0/1 |
| Hardware | BENCH | 0.6 | vd2 | 1 | 2.3 | <= 23 | 50 | <= 23 | 0.06 | 0.00393 | 0/1 |
| Hardware | PV80 | 0.1 | vd2 | 2 | 0.12 | 47.7 | 1.4e+02 | 4.99e+03 | 0.015 | 14.8 | 2/2 |
| Hardware | PV80 | 0.2 | vd2 | 4 | 0.093 | <= 1213 | 47 | <= 2491 | -0.013 | 0.014 | 2/4 |
| Hardware | PV80 | 0.3 | vd2 | 1 | 0.09 | - | - | - | 0.03 | - | 1/1 |
| Hardware | PV80 | 0.4 | vd2 | 1 | 0.11 | 6.03 | 1.4e+02 | 4.76e+03 | 0 | 1.18 | 1/1 |
| Hardware | PV80 | 0.5 | vd2 | 1 | 0.1 | - | - | - | 0.03 | - | 1/1 |
| Hardware | PV80 | 0.6 | vd2 | 1 | 0.07 | - | - | - | 0 | - | 1/1 |
| Hardware | PV80 | 0.7 | vd2 | 1 | 0.02 | - | - | - | -0.01 | - | 1/1 |
| Hardware | PV80 | 0.8 | vd2 | 1 | 0.06 | - | - | - | 0.02 | - | 1/1 |

## 3 · S4 · +1 V reference step (simulations and analysis)

Condensed (medians over cases; full table: [S4_vref2_step.md](out/tables/S4_vref2_step.md), CSV alongside).

| phase | setup | kscale | signal | cases | |delta| | rise 10-90 [ms] | overshoot [%] | t settle 2 % [ms] | ss error | tau [ms] (fit) | resolved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Analytical N=3 (nstring, deployed M) | BENCH | 0.1 | vd2 | 1 | 1 | 23.2 | 0.0016 | 41.3 | -2.3e-05 | 10.5 | 1/1 |
| Analytical N=3 (nstring, deployed M) | BENCH | 0.3 | vd2 | 1 | 1 | 7.61 | 2.3e-05 | 13.6 | -2.8e-07 | 3.42 | 1/1 |
| Analytical N=3 (nstring, deployed M) | BENCH | 1.0 | vd2 | 1 | 1 | 2.04 | 4.4e-14 | 3.8 | -8.9e-16 | 0.909 | 1/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 0.1 | vd2 | 1 | 1 | 28.4 | 0.01 | 50.6 | -0.00017 | 12.9 | 1/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 0.3 | vd2 | 1 | 1 | 9.35 | 0.00037 | 16.7 | -5e-06 | 4.21 | 1/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 1.0 | vd2 | 1 | 1 | 2.59 | 2.2e-14 | 4.8 | -5.6e-16 | 1.16 | 1/1 |
| Simulink carpark 3-module | BENCH | 0.1 | vd2 | 1 | 1 | 22.9 | 0.017 | 41.4 | 0.0014 | 10.1 | 1/1 |
| Simulink carpark 3-module | BENCH | 0.3 | vd2 | 1 | 1 | 6.89 | 0.056 | 12.4 | 0.001 | 2.97 | 1/1 |
| Simulink carpark 3-module | BENCH | 1.0 | vd2 | 1 | 1 | 0.759 | 8.8 | 2.7 | -0.00012 | 0.404 | 1/1 |
| Simulink carpark 3-module | PV80 | 0.1 | vd2 | 1 | 1 | 26 | 0.0031 | 45.5 | -0.0011 | 11.6 | 1/1 |
| Simulink carpark 3-module | PV80 | 0.3 | vd2 | 1 | 1 | 8.06 | 0.0048 | 14.2 | -4.9e-05 | 3.47 | 1/1 |
| Simulink carpark 3-module | PV80 | 1.0 | vd2 | 1 | 1 | 0.894 | 0.16 | 3 | 0.00051 | 0.562 | 1/1 |
| QSPICE switching + firmware DLL | BENCH | 0.1 | vd2 | 1 | 0.97 | 19.8 | 1.2 | 30.7 | -0.027 | 9.72 | 1/1 |
| QSPICE switching + firmware DLL | BENCH | 0.3 | vd2 | 1 | 1 | 6.55 | 0.28 | 11.9 | -0.00016 | 2.84 | 1/1 |
| QSPICE switching + firmware DLL | BENCH | 1.0 | vd2 | 1 | 1 | 1.27 | 0.68 | 2.16 | -0.0027 | 0.549 | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 0.1 | vd2 | 1 | 0.95 | 22.5 | 1.2 | 32.1 | -0.051 | 12.4 | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 0.3 | vd2 | 1 | 1 | 8.7 | 1.7 | 15.2 | -0.002 | 3.71 | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 1.0 | vd2 | 1 | 0.99 | 1.91 | 4.2 | 8.46 | 0.0009 | 0.77 | 1/1 |

## 3 · S3 · Module 3 shade

Condensed (medians over cases; full table: [S3_shade_m3.md](out/tables/S3_shade_m3.md), CSV alongside).

| phase | setup | kscale | signal | cases | |delta| | rise 10-90 [ms] | overshoot [%] | t settle 2 % [ms] | ss error | tau [ms] (fit) | resolved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Simulink carpark 3-module | PV80 | 0.1 | Pstr | 1 | 30 | 0 | 1.7 | 0.1 | - | 0.001 | 0/1 |
| Simulink carpark 3-module | PV80 | 0.3 | Pstr | 1 | 30 | 0 | 1.7 | 0.1 | - | 0.001 | 0/1 |
| Simulink carpark 3-module | PV80 | 1.0 | Pstr | 1 | 30 | 0 | 1.7 | 0.1 | - | 0.001 | 0/1 |
| QSPICE switching + firmware DLL | PV80 | 0.1 | Pstr | 1 | 27 | 0 | 6.2 | 6.35 | - | 0.0013 | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 0.3 | Pstr | 1 | 27 | 0 | 7.4 | 3.26 | - | 0.001 | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 1.0 | Pstr | 1 | 27 | 0 | 6.1 | 0.673 | - | 0.00101 | 1/1 |
| Hardware | PV80 | 0.1 | Pstr | 3 | 10 | 2.42e+04 | 6.4 | 2.64e+04 | - | 1.16e+04 | 3/3 |
| Hardware | PV80 | 0.2 | Pstr | 9 | 15 | <= 1811 | 10 | <= 11271 | - | 847 | 8/9 |
| Hardware | PV80 | 0.3 | Pstr | 3 | 34 | 855 | 13 | 1.8e+04 | - | - | 3/3 |
| Simulink carpark 3-module | PV80 | 0.1 | VM3 | 1 | 0.0038 | - | - | - | - | - | 0/1 |
| Simulink carpark 3-module | PV80 | 0.3 | VM3 | 1 | 0.0037 | - | - | - | - | - | 0/1 |
| Simulink carpark 3-module | PV80 | 1.0 | VM3 | 1 | 0.0031 | - | - | - | - | - | 0/1 |
| QSPICE switching + firmware DLL | PV80 | 0.1 | VM3 | 1 | 0.065 | - | - | - | - | - | 0/1 |
| QSPICE switching + firmware DLL | PV80 | 0.3 | VM3 | 1 | 0.0078 | - | - | - | - | - | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 1.0 | VM3 | 1 | 0.013 | - | - | - | - | - | 1/1 |
| Hardware | PV80 | 0.1 | VM3 | 3 | 0 | <= 23 | - | <= 23 | - | - | 0/3 |
| Hardware | PV80 | 0.2 | VM3 | 10 | 0 | <= 23 | 1.5 | <= 2226 | - | - | 1/10 |
| Hardware | PV80 | 0.3 | VM3 | 3 | 0.34 | 269 | 2.7e+02 | 1.1e+04 | - | 706 | 3/3 |
| Analytical N=3 (nstring, deployed M) | PV80 | 0.1 | id2 | 1 | 1.7 | 0.235 | 0.001 | 18.9 | - | 0.0781 | 1/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 0.3 | id2 | 1 | 1.7 | 0.228 | 3.8e-05 | 6.1 | - | 0.0786 | 1/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 1.0 | id2 | 1 | 1.7 | 0.213 | 0 | 1.6 | - | 0.0786 | 1/1 |
| Simulink carpark 3-module | PV80 | 0.1 | id2 | 1 | 1.9 | 0.0719 | 11 | 0.2 | - | 0.00111 | 0/1 |
| Simulink carpark 3-module | PV80 | 0.3 | id2 | 1 | 1.9 | 0.0719 | 11 | 0.2 | - | 0.00111 | 0/1 |
| Simulink carpark 3-module | PV80 | 1.0 | id2 | 1 | 1.9 | 0.0719 | 11 | 0.2 | - | 0.00112 | 0/1 |
| QSPICE switching + firmware DLL | PV80 | 0.1 | id2 | 1 | 1.8 | 0.137 | 0.54 | 15.6 | - | 0.0659 | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 0.3 | id2 | 1 | 1.8 | 0.14 | 0.47 | 7.46 | - | 0.0663 | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 1.0 | id2 | 1 | 1.8 | 0.0896 | 1.2 | 0.873 | - | 0.0639 | 1/1 |
| Hardware | PV80 | 0.1 | id2 | 3 | 0.17 | <= 2762 | 71 | <= 27145 | - | 1.13e+04 | 2/3 |
| Hardware | PV80 | 0.2 | id2 | 10 | 0.14 | <= 90 | 27 | <= 16333 | - | 2.45e+03 | 7/10 |
| Hardware | PV80 | 0.3 | id2 | 3 | 0.005 | <= 23 | - | <= 23 | - | - | 0/3 |
| Analytical N=3 (nstring, deployed M) | PV80 | 0.1 | vd2 | 1 | 9.1e-05 | - | - | - | - | - | 1/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 0.3 | vd2 | 1 | 2.9e-06 | - | - | - | - | - | 1/1 |
| Analytical N=3 (nstring, deployed M) | PV80 | 1.0 | vd2 | 1 | 2.2e-16 | - | - | - | - | - | 1/1 |
| Simulink carpark 3-module | PV80 | 0.1 | vd2 | 1 | 0.0014 | - | - | - | - | - | 1/1 |
| Simulink carpark 3-module | PV80 | 0.3 | vd2 | 1 | 0.00095 | - | - | - | - | - | 1/1 |
| Simulink carpark 3-module | PV80 | 1.0 | vd2 | 1 | 0.0021 | - | - | - | - | - | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 0.1 | vd2 | 1 | 0.077 | - | - | - | - | - | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 0.3 | vd2 | 1 | 0.00028 | - | - | - | - | - | 1/1 |
| QSPICE switching + firmware DLL | PV80 | 1.0 | vd2 | 1 | 0.0022 | - | - | - | - | - | 1/1 |
| Hardware | PV80 | 0.1 | vd2 | 3 | 0.01 | <= 23 | - | <= 23 | - | - | 0/3 |
| Hardware | PV80 | 0.2 | vd2 | 10 | 0.0075 | <= 2538 | 21 | <= 12069 | - | 4.61e+03 | 4/10 |
| Hardware | PV80 | 0.3 | vd2 | 3 | 0.07 | 466 | 0.51 | 1.96e+03 | - | - | 3/3 |

## 4 · S2 · Settled statistics per kscale

| phase | setup | state | kscale | duration_s | ended_by | vd2_mean | vd2_std | ic2_mean | ic2_std | id1_mean | id2_mean | dA2_std | stress_mean | Pstr_mean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hardware | BENCH | RUN_CL | 0.1 | 36.7 | FAULT | 0.004 | 0.0374 | 0.0044 | 1.39 | 0.228 | -0.767 | 0.0043 | 0.128 | 57.6 |
| hardware | BENCH | RUN_CL | 0.1 | 156 | IDLE | 0.005 | 0.0402 | -0.0189 | 1.35 | 0.324 | -0.104 | 0.0003 | 0.0482 | 44.5 |
| hardware | BENCH | RUN_CL | 0.2 | 17.6 | FAULT | 0.0029 | 0.137 | 0.18 | 1.49 | 0.162 | -0.775 | 0.007 | 0.113 | 58 |
| hardware | BENCH | RUN_CL | 0.3 | 9.21 | FAULT | 0.144 | 0.622 | 0.387 | 2.32 | -0.598 | -0.477 | 0.105 | 0.155 | 39.1 |
| hardware | BENCH | RUN_CL | 0.3 | 138 | IDLE | 0.0095 | 0.0837 | 0.138 | 1.83 | 0.469 | -0.0098 | 0.0008 | 0.0562 | 42.9 |
| hardware | BENCH | RUN_CL | 0.3 | 143 | IDLE | 0.0054 | 0.0757 | 0.0462 | 0.395 | 0.0909 | -0.0383 | 0.0007 | 0.0221 | 40.2 |
| hardware | BENCH | RUN_CL | 0.3 | 47.1 | RUN_CL | 0.0082 | 0.0786 | 0.0588 | 0.4 | 0.185 | 0.0535 | 0.0007 | 0.0321 | 40.5 |
| hardware | BENCH | RUN_CL | 0.3 | 360 | STOP | 0.0004 | 0.016 | -0.0001 | 0.055 | 0.295 | -0.281 | 0.0019 | 0.0348 | 35.9 |
| hardware | BENCH | RUN_CL | 0.3 | 151 | IDLE | 0.0008 | 0.0158 | 0.0007 | 0.0537 | 0.733 | -0.662 | 0.0018 | 0.0733 | 62.9 |
| hardware | BENCH | RUN_CL | 0.3 | 93.8 | IDLE | 0.0001 | 0.0128 | -0.001 | 0.0532 | 0.246 | -0.179 | 0.0001 | 0.0248 | 44.7 |
| hardware | BENCH | RUN_CL | 0.3 | 98.5 | STOP | 0.0014 | 0.0153 | 0.0598 | 0.0915 | 0.212 | -0.0893 | 0.0005 | 0.0209 | 49.8 |
| hardware | BENCH | RUN_CL | 0.3 | 39.7 | STOP | 0.0006 | 0.0167 | 0.0557 | 0.0788 | 0.343 | -0.281 | 0.0008 | 0.0354 | 63.3 |
| hardware | BENCH | RUN_CL | 0.3 | 196 | IDLE | 0.0002 | 0.0173 | 0.0613 | 0.0847 | 0.363 | -0.265 | 0.0005 | 0.036 | 63.7 |
| hardware | BENCH | RUN_CL | 0.3 | 57.9 | IDLE | -0.0023 | 0.0358 | 0.0626 | 0.0857 | 0.357 | -0.277 | 0.0006 | 0.0352 | 63.7 |
| hardware | BENCH | RUN_CL | 0.3 | 156 | IDLE | -0.0054 | 0.0452 | 0.0566 | 0.0794 | 0.483 | -0.356 | 0.0013 | 0.0479 | 66 |
| hardware | BENCH | RUN_CL | 0.4 | 8.47 | IDLE | -0.0015 | 0.0346 | -0.0026 | 0.0555 | 0.261 | -0.182 | 0.0006 | 0.0264 | 45.5 |
| hardware | BENCH | RUN_CL | 0.4 | 148 | STOP | -0.0019 | 0.0732 | -0.0015 | 0.0542 | 0.388 | -0.502 | 0.002 | 0.0571 | 61.1 |
| hardware | BENCH | RUN_CL | 0.4 | 21 | RUN_CL | -0.0035 | 0.0418 | 0.0011 | 0.0553 | 0.27 | -0.129 | 0.0006 | 0.0272 | 45.7 |
| hardware | BENCH | RUN_CL | 0.5 | 36 | RUN_CL | -0.0035 | 0.0939 | -0.0025 | 0.0537 | 0.354 | -0.0703 | 0.0017 | 0.0366 | 45.5 |
| hardware | BENCH | RUN_CL | 0.6 | 8.61 | STOP | 0.0559 | 1.48 | 0.0055 | 0.0563 | 0.303 | -0.0171 | 0.0201 | 0.0705 | 43.1 |
| hardware | BENCH | RUN_OL | 0.2 | 82.2 | IDLE | -0.111 | 0.0652 | 2.84 | 1.01 | -0.0003 | -2.15 | 0 | 0 | 49.6 |
| hardware | BENCH | RUN_OL | 0.3 | 5.86 | STOP | -0.908 | 0.293 | 0.0295 | 0.0527 | 0.866 | -0.857 | 0 | 0.085 | 56.8 |
| hardware | BENCH | RUN_OL | 0.3 | 96.3 | RUN_OL | -0.484 | 0.188 | 0.148 | 0.0479 | 0.182 | -0.092 | 0 | 0 | 50.7 |
| hardware | BENCH | RUN_OL | 0.5 | 47.3 | end of window | -0.142 | 0.0785 | 0.963 | 0.265 | 0.27 | -0.386 | 0 | 0.383 | 53.9 |
| hardware | PV80 | RUN_CL | 0.1 | 237 | IDLE | 0.0008 | 0.0316 | -0.0328 | 0.225 | -0.827 | -0.232 | 0.0009 | 0.0823 | 23.8 |
| hardware | PV80 | RUN_CL | 0.1 | 265 | STOP | 0.0049 | 0.138 | -0.0233 | 0.257 | -0.35 | -0.0607 | 0.0005 | 0.0369 | 8.45 |
| hardware | PV80 | RUN_CL | 0.2 | 12.7 | IDLE | -0.0408 | 0.11 | 0.585 | 0.0935 | 0.016 | 0.154 | 0 | 0.933 | 14.8 |
| hardware | PV80 | RUN_CL | 0.2 | 421 | STOP | -0.0001 | 0.0313 | -0.0172 | 0.2 | -3.19 | -1.44 | 0.0037 | 0.328 | 116 |
| hardware | PV80 | RUN_CL | 0.2 | 23.9 | STOP | 0.0004 | 0.0324 | -0.0139 | 0.242 | -0.865 | -0.243 | 0.0005 | 0.0809 | 23.2 |
| hardware | PV80 | RUN_CL | 0.2 | 229 | IDLE | 0.0009 | 0.0991 | -0.035 | 0.265 | -0.469 | -0.0916 | 0.0007 | 0.0452 | 11.8 |
| hardware | PV80 | RUN_CL | 0.3 | 189 | IDLE | 0.0012 | 0.0906 | -0.042 | 0.272 | -0.507 | -0.112 | 0.0005 | 0.0515 | 13.7 |
| hardware | PV80 | RUN_CL | 0.4 | 156 | STOP | -0.0041 | 0.0904 | -0.0462 | 0.285 | -0.5 | -0.12 | 0.0005 | 0.0499 | 13.2 |
| hardware | PV80 | RUN_CL | 0.5 | 150 | IDLE | -0.0018 | 0.124 | -0.0323 | 0.288 | -0.396 | -0.0864 | 0.0009 | 0.0405 | 10 |
| hardware | PV80 | RUN_CL | 0.6 | 278 | STOP | -0.0012 | 0.167 | -0.0522 | 0.305 | -0.305 | -0.0093 | 0.0008 | 0.0307 | 6.87 |
| hardware | PV80 | RUN_CL | 0.7 | 178 | IDLE | -0.0042 | 0.131 | -0.0365 | 0.313 | -0.247 | -0.0092 | 0.0009 | 0.0249 | 4.58 |
| hardware | PV80 | RUN_CL | 0.8 | 90.5 | STOP | -0.0008 | 0.0947 | -0.054 | 0.309 | -0.187 | 0.0161 | 0.0007 | 0.0211 | 1.88 |
| hardware | PV80 | RUN_OL | 0.2 | 60 | STOP | -0.135 | 0.138 | 1.01 | 0.164 | -1.27 | -0.384 | 0 | 0.933 | - |
| hardware | PV80 | RUN_OL | 0.2 | 44.6 | IDLE | -0.178 | 0.0685 | 0.983 | 0.224 | -1.16 | -0.429 | 0 | 0 | 35.5 |
| hardware | PV80 | RUN_OL | 0.2 | 78.4 | IDLE | -0.0744 | 0.117 | 1 | 0.237 | -0.374 | -0.0564 | 0 | 0.07 | 8.54 |
| hardware | PV80 | RUN_OL | 0.3 | 99.7 | RUN_OL | -3.21 | 2.84 | 0.978 | 0.0644 | 0.0188 | 0.133 | 0 | 0 | 73.1 |
| qspice | BENCH | RUN_CL | 0.1 | 0.04 | event | -0.00327 | 0.00328 | -0.00288 | 0.00935 | -0.462 | -0.539 | 9.7e-06 | 0.0541 | 71.8 |
| qspice | BENCH | RUN_CL | 0.1 | 0.04 | event | 0.955 | 0.0204 | 0.00376 | 0.00436 | -0.455 | -0.536 | 0.000214 | 0.0512 | 71.5 |
| qspice | BENCH | RUN_CL | 0.3 | 0.0283 | event | 3.58e-05 | 0.00338 | -0.0015 | 0.0109 | -0.462 | -0.539 | 7.37e-06 | 0.0543 | 71.8 |
| qspice | BENCH | RUN_CL | 0.3 | 0.0283 | event | 0.999 | 0.00139 | 0.0052 | 0.00426 | -0.454 | -0.535 | 1.16e-05 | 0.0504 | 71.4 |
| qspice | BENCH | RUN_CL | 1 | 0.0085 | event | 1 | 0.00278 | 0.0047 | 0.00517 | -0.454 | -0.535 | 2.51e-05 | 0.0526 | 71.5 |
| qspice | BENCH | RUN_CL | 1 | 0.0085 | event | -5.36e-05 | 0.00552 | -0.000852 | 0.0108 | -0.461 | -0.539 | 2.04e-05 | 0.0548 | 71.7 |
| qspice | PV80 | RUN_CL | 0.1 | 0.04 | event | 0.00376 | 0.00412 | 0.0561 | 0.0161 | 0.00195 | -0.00684 | 3.41e-05 | 0.0143 | 238 |
| qspice | PV80 | RUN_CL | 0.1 | 0.04 | event | 0.922 | 0.0306 | 0.0617 | 0.0119 | -0.137 | -0.302 | 0.000388 | 0.0272 | 237 |
| qspice | PV80 | RUN_CL | 0.1 | 0.04 | event | 1.05 | 0.0145 | 0.0516 | 0.00939 | 0.711 | 1.46 | 0.000227 | 0.161 | 210 |
| qspice | PV80 | RUN_CL | 0.3 | 0.0283 | event | 0.00192 | 0.00306 | 0.0583 | 0.0227 | 0.00494 | -0.00502 | 5.14e-05 | 0.0107 | 238 |
| qspice | PV80 | RUN_CL | 0.3 | 0.0283 | event | 0.994 | 0.00572 | 0.037 | 0.0219 | -0.151 | -0.324 | 5.77e-05 | 0.0292 | 237 |
| qspice | PV80 | RUN_CL | 0.3 | 0.0283 | event | 1.01 | 0.00659 | 0.0495 | 0.0178 | 0.724 | 1.47 | 5.09e-05 | 0.158 | 210 |
| qspice | PV80 | RUN_CL | 1 | 0.0085 | event | 1 | 0.0125 | 0.0423 | 0.0395 | -0.152 | -0.325 | 0.000137 | 0.0295 | 237 |
| qspice | PV80 | RUN_CL | 1 | 0.0085 | event | 1 | 0.00432 | 0.0428 | 0.0353 | 0.723 | 1.47 | 0.000117 | 0.124 | 210 |
| qspice | PV80 | RUN_CL | 1 | 0.0085 | event | 0.00378 | 0.00794 | 0.0374 | 0.0347 | 0.00687 | -0.00584 | 4.94e-05 | 0.0067 | 238 |
| simulink | BENCH | RUN_CL | 0.1 | 0.01 | event | -0.00134 | 0 | 0.0104 | 1.74e-18 | -0.467 | -0.533 | 5.58e-17 | 0.0516 | 72.3 |
| simulink | BENCH | RUN_CL | 0.1 | 0.01 | event | -0.00134 | 0 | 0.0104 | 1.74e-18 | -0.467 | -0.533 | 5.58e-17 | 0.0516 | 72.3 |
| simulink | BENCH | RUN_CL | 0.3 | 0.01 | event | -0.0016 | 0 | 0.0114 | 5.23e-18 | -0.467 | -0.533 | 5.58e-17 | 0.0513 | 72.3 |
| simulink | BENCH | RUN_CL | 0.3 | 0.01 | event | -0.0016 | 0 | 0.0114 | 5.23e-18 | -0.467 | -0.533 | 5.58e-17 | 0.0513 | 72.3 |
| simulink | BENCH | RUN_CL | 1 | 0.01 | event | 0.00175 | 0.000754 | 0.00645 | 0.00711 | -0.466 | -0.533 | 5.28e-06 | 0.0529 | 72.3 |
| simulink | BENCH | RUN_CL | 1 | 0.01 | event | 0.00175 | 0.000754 | 0.00645 | 0.00711 | -0.466 | -0.533 | 5.28e-06 | 0.0529 | 72.3 |
| simulink | PV80 | RUN_CL | 0.1 | 0.01 | event | 6.95e-05 | 0 | 0.0019 | 6.54e-19 | -2.13e-07 | -3.83e-06 | 1.12e-16 | 5.12e-06 | 265 |
| simulink | PV80 | RUN_CL | 0.1 | 0.01 | event | 6.95e-05 | 0 | 0.0019 | 6.54e-19 | -2.13e-07 | -3.83e-06 | 1.12e-16 | 5.12e-06 | 265 |
| simulink | PV80 | RUN_CL | 0.1 | 0.01 | event | 6.95e-05 | 0 | 0.0019 | 6.54e-19 | -2.13e-07 | -3.83e-06 | 1.12e-16 | 5.12e-06 | 265 |
| simulink | PV80 | RUN_CL | 0.3 | 0.01 | event | 0.000209 | 0 | 0.00571 | 8.72e-19 | -6.19e-07 | -1.15e-05 | 1.12e-16 | 1.54e-05 | 265 |
| simulink | PV80 | RUN_CL | 0.3 | 0.01 | event | 0.000209 | 0 | 0.00571 | 8.72e-19 | -6.19e-07 | -1.15e-05 | 1.12e-16 | 1.54e-05 | 265 |
| simulink | PV80 | RUN_CL | 0.3 | 0.01 | event | 0.000209 | 0 | 0.00571 | 8.72e-19 | -6.19e-07 | -1.15e-05 | 1.12e-16 | 1.54e-05 | 265 |
| simulink | PV80 | RUN_CL | 1 | 0.01 | event | 0 | 0 | 1.29e-08 | 3.33e-24 | 6.33e-12 | 1.58e-12 | 0 | 1.85e-15 | 265 |
| simulink | PV80 | RUN_CL | 1 | 0.01 | event | 0 | 0 | 1.29e-08 | 3.33e-24 | 6.33e-12 | 1.58e-12 | 0 | 1.85e-15 | 265 |
| simulink | PV80 | RUN_CL | 1 | 0.01 | event | 0 | 0 | 1.29e-08 | 3.33e-24 | 6.33e-12 | 1.58e-12 | 0 | 1.85e-15 | 265 |

## 5 · Identified gain matrices against the N-module model

| source | vd1/uc1 | vd2/uc2 | ic1/ud1 | ic2/ud2 | vd1/ud1 (cross) | cond(G) | note |
|---|---|---|---|---|---|---|---|
| analytical PV80, averaged R 61 mOhm (Simulink) | -40.4 | -40.4 | 672.1 | 672.1 | 0.0 | 16.8 | modes [('6973 Hz', 'z 0.36'), ('9296 Hz', 'z 0.27')] |
| analytical PV80, switching R 0.29 ohm (200 kHz) | -38.2 | -38.2 | 141.4 | 141.4 | 0.0 | 3.8 | modes [] |
| analytical PV80, switching R 1.72 ohm (400 kHz) | -29.2 | -29.2 | 23.8 | 23.8 | 0.0 | 1.4 | modes [] |
| analytical BENCH QSPICE point (all CC), R 0.29 ohm | -46.6 | -46.7 | 160.7 | 160.7 | 0.0 | 3.5 | modes [] |
| analytical BENCH ch1 CC / ch2,3 CV, R 0.29 ohm | -15.2 | -7.2 | 155.2 | 172.4 | 0.0 | 26.3 | modes [('20889 Hz', 'z 0.93')] |
| identified sps-params-2.20261015-1950-3mod-qspice200-bench | -46.3 | -46.9 | 142.5 | 139.0 | -24.7 | 3.2 | diag(kI) M^-1 of the gain set |
| identified sps-params-2.20261011-1634-3mod-qspice | -37.4 | -37.7 | 256.0 | 215.8 | 7.3 | 7.4 | diag(kI) M^-1 of the gain set |
| identified sps-params-2.20261015-1754-3mod-simulink-bench | -46.0 | -47.4 | 741.5 | 742.5 | -0.6 | 16.1 | diag(kI) M^-1 of the gain set |
| identified sps-params-2.20261016-1628-3mod-qspice300-bench | -45.3 | -45.7 | 58.8 | 56.8 | -17.0 | 1.6 | diag(kI) M^-1 of the gain set |
| identified sps-params-2.20261016-1751-3mod-qspice400-bench | -41.6 | -42.9 | 23.5 | 23.0 | -14.4 | 2.3 | diag(kI) M^-1 of the gain set |
| identified sps-params-2.20261016-1804-3mod-qspice400d1-bench | -42.7 | -43.8 | 26.2 | 26.0 | -10.3 | 1.9 | diag(kI) M^-1 of the gain set |

Rows [vd1 vd2 ic1 ic2], columns [uc1 uc2 ud1 ud2]; V per unit modal duty, A per unit modal duty.

The derivation, the N = 2 check against the retrospective, cond(G(N)) and the closed-loop poles are in `3_Analytical/shuffler_notebooks/shuffler_nstring.ipynb` (`nstring.py`).

## 6 · Overlay figures

![S1_k0.1_ic2.png](out/figures/S1_k0.1_ic2.png)
![S1_k0.1_ic2_hw.png](out/figures/S1_k0.1_ic2_hw.png)
![S1_k0.1_id2.png](out/figures/S1_k0.1_id2.png)
![S1_k0.1_id2_hw.png](out/figures/S1_k0.1_id2_hw.png)
![S1_k0.1_vd2.png](out/figures/S1_k0.1_vd2.png)
![S1_k0.1_vd2_hw.png](out/figures/S1_k0.1_vd2_hw.png)
![S1_k0.2_ic2_hw.png](out/figures/S1_k0.2_ic2_hw.png)
![S1_k0.2_id2_hw.png](out/figures/S1_k0.2_id2_hw.png)
![S1_k0.2_vd2_hw.png](out/figures/S1_k0.2_vd2_hw.png)
![S1_k0.3_ic2_hw.png](out/figures/S1_k0.3_ic2_hw.png)
![S1_k0.3_id2_hw.png](out/figures/S1_k0.3_id2_hw.png)
![S1_k0.3_vd2_hw.png](out/figures/S1_k0.3_vd2_hw.png)
![S1_k0.4_ic2_hw.png](out/figures/S1_k0.4_ic2_hw.png)
![S1_k0.4_id2_hw.png](out/figures/S1_k0.4_id2_hw.png)
![S1_k0.4_vd2_hw.png](out/figures/S1_k0.4_vd2_hw.png)
![S1_k0.5_ic2_hw.png](out/figures/S1_k0.5_ic2_hw.png)
![S1_k0.5_id2_hw.png](out/figures/S1_k0.5_id2_hw.png)
![S1_k0.5_vd2_hw.png](out/figures/S1_k0.5_vd2_hw.png)
![S1_k0.6_ic2_hw.png](out/figures/S1_k0.6_ic2_hw.png)
![S1_k0.6_id2_hw.png](out/figures/S1_k0.6_id2_hw.png)
![S1_k0.6_vd2_hw.png](out/figures/S1_k0.6_vd2_hw.png)
![S1_k0.7_ic2_hw.png](out/figures/S1_k0.7_ic2_hw.png)
![S1_k0.7_id2_hw.png](out/figures/S1_k0.7_id2_hw.png)
![S1_k0.7_vd2_hw.png](out/figures/S1_k0.7_vd2_hw.png)
![S1_k0.8_ic2_hw.png](out/figures/S1_k0.8_ic2_hw.png)
![S1_k0.8_id2_hw.png](out/figures/S1_k0.8_id2_hw.png)
![S1_k0.8_vd2_hw.png](out/figures/S1_k0.8_vd2_hw.png)
![S1_k1_ic2.png](out/figures/S1_k1_ic2.png)
![S1_k1_id2.png](out/figures/S1_k1_id2.png)
![S1_k1_vd2.png](out/figures/S1_k1_vd2.png)
![S3_k0.1_VM3.png](out/figures/S3_k0.1_VM3.png)
![S3_k0.1_VM3_hw.png](out/figures/S3_k0.1_VM3_hw.png)
![S3_k0.1_id2.png](out/figures/S3_k0.1_id2.png)
![S3_k0.1_id2_hw.png](out/figures/S3_k0.1_id2_hw.png)
![S3_k0.1_vd2.png](out/figures/S3_k0.1_vd2.png)
![S3_k0.1_vd2_hw.png](out/figures/S3_k0.1_vd2_hw.png)
![S3_k0.2_VM3_hw.png](out/figures/S3_k0.2_VM3_hw.png)
![S3_k0.2_id2_hw.png](out/figures/S3_k0.2_id2_hw.png)
![S3_k0.2_vd2_hw.png](out/figures/S3_k0.2_vd2_hw.png)
![S3_k0.3_VM3.png](out/figures/S3_k0.3_VM3.png)
![S3_k0.3_VM3_hw.png](out/figures/S3_k0.3_VM3_hw.png)
![S3_k0.3_id2.png](out/figures/S3_k0.3_id2.png)
![S3_k0.3_id2_hw.png](out/figures/S3_k0.3_id2_hw.png)
![S3_k0.3_vd2.png](out/figures/S3_k0.3_vd2.png)
![S3_k0.3_vd2_hw.png](out/figures/S3_k0.3_vd2_hw.png)
![S3_k1_VM3.png](out/figures/S3_k1_VM3.png)
![S3_k1_id2.png](out/figures/S3_k1_id2.png)
![S3_k1_vd2.png](out/figures/S3_k1_vd2.png)
![S4_k0.1_ic2.png](out/figures/S4_k0.1_ic2.png)
![S4_k0.1_vd2.png](out/figures/S4_k0.1_vd2.png)
![S4_k0.3_ic2.png](out/figures/S4_k0.3_ic2.png)
![S4_k0.3_vd2.png](out/figures/S4_k0.3_vd2.png)
![S4_k1_ic2.png](out/figures/S4_k1_ic2.png)
![S4_k1_vd2.png](out/figures/S4_k1_vd2.png)

## 7 · Screenshots to take (Grafana, local time)

- Bench 16 Oct, good closed-loop runs: 15:50:30-15:53:00 and 16:02:00-16:04:40 (module voltages, inductor currents, duties, supervisor).
- Bench 16 Oct, the loop-closing instant at 15:50:33 with a 10 s window (shows IDLE -> SOFTSTART -> RUN_CL).
- Solar 20 Oct, the kscale sweep 15:51-16:26 as one window and each level on its own (15:52:05 k0.1, 15:56:54 k0.2, 16:01:08 k0.3, 16:05:37 k0.4, 16:09:44 k0.5, 16:13:19 k0.6, 16:19:11 k0.7, 16:23:11 k0.8).
- Solar 20 Oct, 13:04:18-13:11:19 closed loop with the shade events (string power + shuffled currents), and 12:53:17-12:55:00 open loop for the same panel.
- Solar 20 Oct, 13:00:30-13:01:40 (the person walking round the panels while idle: module 3 voltage dip).
- QSPICE: `Power_Shuffler_Integrated.qsch` and the S10 / S10p stage waveforms if the native look is wanted; the matched runs are in `out/qspice/`.

## 8 · Caveats

- 50 Hz telemetry against 150 / 400 Hz loops: hardware step metrics are upper bounds except at low kscale; the fitted time constant is the comparable number.
- The hardware engagement runs through a 150 ms soft start that ramps the duties to 0.5; that ramp alone removes most of the module mismatch (the half bridge at 0.5 duty forces VM2 = VM3), so the loop's own step is the residual (about 0.5 V on the bench) and completes within one telemetry sample.
- VM1 on hardware is the e-load reading through the Pi (2.2 Hz): vd1 / ic1 hardware metrics are flagged, comparisons use vd2 / ic2 / id2.
- FAULT-terminated bench runs are listed but only segments longer than 2 s after the event contribute.
- The solar kscale sweep ran at 8-14 W of string power (late afternoon); PV irradiance drifts across runs; the shirt shading is not repeatable, so S3 hardware rows carry magnitudes, not matched steps.
- Shade is a bypassed substring in reality (voltage step) but an irradiance scale in the simulations (current step).
- The QSPICE bench model has channel 1 in current limit (ILIM 0.8 / 1.0 / 1.3 A); the 16 Oct bench had the middle module at 20 V. Confirm the PSU settings before matching the bench rows.
- The analytical model is linear: amplitudes are illustrative, time constants are the comparison.
- QSPICE S1 at kscale 0.1 and 0.3 closes the loop 0.5 ms after a cold start (the S10 netlists start from `.ic` voltages), so the
  pre-event level is a still-moving start-up; the kscale 1 cases were rerun with a 3 ms open-loop period (`run_scenarios.py --ten`).
  S3 and S4 are unaffected (the loop is settled long before those events).
- Simulink MIL (4-module ideal model): not in the tables. Its references enter through a bus into the Supervisor subsystem,
  so the in-memory Constant -> Step swap of `run_scenarios.m` breaks the bus; the MIL record remains the validate figures
  (`4_Simulink/1_MIL_Model_In_The_Loop/figs`, reference set at t = 0) until the model gets a Step input of its own.
- On the solar day the supervisor was active: after a shaded engagement the loop regulates `vd2` to the supervisor's `rv2`, not to 0,
  so the hardware S1 steady-state "error" there is the supervisor reference, not a controller offset.
