# Boost-Brigade: 5-day plan to the carpark experiment (due Fri 16 Oct 2026)

## Context

Goal: run a live **3-panel / 2-shuffler** string (150 W panels, EcoFlow DELTA 2 Max as the
string-level MPPT load) in the carpark by Friday night, with closed-loop module equalisation,
safe start/stop, and logged telemetry, then report.

The gain-development path is **Simulink → SIL (C core) → QSPICE (switching model) → firmware**.
Simulink is where M and the loop gains are designed and validated; QSPICE shows the controller
works against the real power stage, drivers, dead time, ripple and sensor quantisation, and is where
gains get refined; the firmware runs the same C core with the resulting `params.h`. All of this
happens Mon–Wed so the bench and carpark run with simulation-backed gains.

### What the repo actually contains (verified)

| Finding | Where | Consequence |
|---|---|---|
| PCB = 3 panels / 2 converters. HRTIM pins PA8-11 (S1 A/B H/L), PB12-15 (S2); hall ADC PA0 ILA_1, PA4 ILB_1, PA1 ILA_2, PC1 ILB_2; INA on SPI3 PB3/4/5 with CS PA7/PB6/PC7 | `Version 0/Version 0 project/*.kicad_sch` | Control stack (4 panels, 6 duties) becomes N-generic with N_MOD=3; Simulink plant needs a 3-module variant |
| INA239 shunt inputs shorted: **bus voltage only**. VM3=U12, VM2=U11−U12, VM1=U10−(U11−U12). No direct module or string current | `V_Sense.kicad_sch` | **Module currents are reconstructed** from the four inductor currents and the common-mode duties by KCL at the PV2+ and PV3+ nodes (averaged: shuffler k draws d_k·ic_k at its top node, (1−d_k)·ic_k at its bottom node, injects ic_k at its midpoint). The unknown string current is a common offset that cancels in the supervisor's deficit `max(IM) − IM`, so the **full supervisor runs**. Only the string MPPT needs absolute Istr; that is the EcoFlow's job. Vstr = VM1+VM2+VM3 |
| U10 (needed for VM1) is behind the ISO7762 wired backwards; it also drives SCLK/MOSI/CS3 | `V_Sense.kicad_sch`; `ina2x9.c` detects this and disables SPI | **Rework is a hard prerequisite** for closed loop on converter 1 (user decision: rework) |
| 1ED3140: no EN/FAULT/RDY, interlock only, no dead time; TMCS OC_N tied to GND | `Gate_Drivers.kicad_sch`, `Current_Sense.kicad_sch` | Dead time + OC trip are firmware/HRTIM only (already done in existing firmware) |
| Hall variants: A-phase B4 (100 mV/A), B-phase B1 (25 mV/A), opposite polarity; BOM says all B4 | sch vs `BOM.xlsx`; `sensors.c` already encodes 100/−25 | Verify per channel with a DC current on the bench |
| Existing firmware `C:\Users\jazsa\Documents\Shuffler_1_Open_Loop` (CubeMX CMake, G474, 170 MHz): HRTIM TC/TD 100 kHz 50 % with 200 ns dead time (S2 only; S1 pins held low), injected-ADC 1 kHz 16× oversampled + OC latch (10 A/100 ms), INA239/229 driver, LPUART1 VCP printf telemetry 10 Hz, button start/stop, gates-low-at-boot constructor | `Core/Src/{main,sensors,ina2x9}.c` | **This is the firmware base.** Not in git; not FreeRTOS yet |
| Toolchain installed (Windows): `%LOCALAPPDATA%\stm32cube\bundles\{cmake 4.3.1, ninja, gnu-tools-for-stm32 14.3.1, programmer 2.23.0}`; VS Code tasks: `cmake --preset Debug`, flash `STM32_Programmer_CLI -c port=SWD -w build/Debug/*.elf -rst` | `.vscode/tasks.json`, `CMakePresets.json` | Build/flash from WSL via the `.exe` interop paths; no PlatformIO needed |
| Validated C control core only on branch `SIL_Software_In_The_Loop`: float32 C99 `core/{shuffler_ctrl,shuffler_supervisor,shuffler_mppt,stack}.c`, `params.h` from `matlab/export_params.m` / `gen_params.py`, `test/{unit_tests,replay}.c`, `sil/` C Caller wrappers + `INSTRUCTIONS.md`. Hard-coded 4 modules / 6 legs, Ts 50 µs, DECIM 20 | `git show SIL_Software_In_The_Loop:MATLAB/2_SIL_Software_In_The_Loop/firmware/...` | Merge; generalise to N_MOD; regenerate params at Ts = 100 µs |
| Control model tuned on Aiko 540 W (Vmp 38.7 V, 14.35 A, L_self 7.9 µH, 200 kHz); carpark: 150 W panels (Vmp 18.3 V, 8.2 A), ERUC23-4R1K inductors, 100 kHz PWM | `init_params.m`, QSPICE `parasitics.json` vs `README.md` | Simulink plant parameters must be updated before identification |
| QSPICE baseline is scripted: `gen_shuffler.py` writes stages S1–S8b, `run_baseline.py` drives `QSPICE64.exe`/`QPOST.exe` (Windows). Open-loop 50 % `PULSE()` gates, 1ED3140 behavioural model, no controller block | `Version 0/Qspice/Claude's outputs/PCB_Baseline/` | Add a C-block DLL stage (S9) wrapping `core/` |
| EcoFlow DELTA 2 Max solar input: **11–60 V, 15 A, 500 W/port**. 3 × 150 W: Vmp 55 V OK, **Voc 67 V > 60 V** | `Documentation/EcoFlow_PowerStation.pdf` | Experiment risk; resolve Monday (see Risks) |
| Pi pod wiring documented: IR GPIO17, RGB 12/13/19, I²C LCD 0x27/0x3F, DS18B20 on GPIO4; Nucleo link = ST-LINK VCP | `Documentation/UI Pod Wiring.html` | Pi side is Python + Docker |

### Architecture decisions

1. **One C control core, three harnesses**: SIL (C Caller + golden replay), QSPICE C-block DLL, firmware. Only `params.h` and the I/O glue differ. Gains flow Simulink → `params.h` → everywhere.
2. **Control scope on hardware** = inner decoupling loop + full supervisor (deficit + stress), with module currents reconstructed from IL and duties by a small `recon_module_currents()` in `core/` (same function dropped into Simulink as a MATLAB Function block and checked against the plant's true module currents). Firmware MPPT layer compiled out (EcoFlow is the string MPPT; `Iref` has no actuator on this hardware). Simulink/QSPICE run the same configuration so the validated thing is the deployed thing. `SUP_STRESS_ONLY` kept only as a fallback flag if the reconstruction proves too noisy on the bench.
3. **Inner loop at 10 kHz** (Ts = 100 µs, STACK_DECIM = 10), supervisor 1 kHz. Rate-dependent constants regenerated, SIL suite re-run.
4. **Firmware**: control in a TIM6 10 kHz ISR; FreeRTOS (CMSIS-RTOS2 via CubeMX) for INA polling, telemetry, commands, state machine. Time-boxed; fallback is the existing superloop with the same ISR. Safety path (OC trip → `ODISR`, E-stop EXTI, IWDG) never depends on the scheduler.
5. **PWM 100 kHz** (bench-proven; QSPICE and Simulink switching settings follow the hardware).
6. **Build/flash from WSL using the Windows ST bundle**; QSPICE and MATLAB run on Windows (you), scripts are mine.

## Day plan

### Day 0 — Sunday (today): repo, C core, scripts (mine, after approval)

1. `git merge SIL_Software_In_The_Loop` into `controller_integration` (adds files only).
2. Restructure with `git mv` (one commit, nothing deleted):
   - `0_Documentation/` ← `Documentation/` (add; PDFs tracked); `README.md` rewritten as an index + this roadmap
   - `1_Datasheets/` ← datasheet PDFs (ina239, tmcs1126, 1ED314x, EcoFlow, STD45N10F7 etc.)
   - `2_Qspice/` ← `Version 0/Qspice/`
   - `3_Analytical/` ← `shuffler_notebooks/`, `MATLAB/0_Analytical_Solution/`
   - `4_Simulink/` ← `MATLAB/1_MIL…`, `2_SIL…`, `3_PIL…`, `4_HIL…`, `5_Alpha…`
   - `5_Kicad/` ← `Version 0/Version 0 project/` and every part-library folder (Coupled Inductor, Hall effect IC, LM5180, NUCLEO-G474RE + zip, SP3T Switch, STL115N10F7AG, Transformer, XT-60 Connector, 130uF cap footprint, KiCad_WPME-FDSM, DVG0010A.stp, BOM.xlsx, LM5180 calculator); fix relative paths in `fp-lib-table` / `sym-lib-table`
   - `6_RTOS/` ← copy of `Shuffler_1_Open_Loop` (minus `build/`), with `6_RTOS/core/` = the SIL `firmware/core` moved here (SIL CMake and the QSPICE DLL build reference it by relative path: one copy)
   - `7_Pi/` ← new
   - `.gitignore`: `6_RTOS/build*/`, `7_Pi/**/data/`, `2_Qspice/**/*.qraw`
3. **C core generalisation** (`6_RTOS/core`): `N_MOD`/`N_SHUF`/`N_LEG` macros; `recon_module_currents(IL, d) → IM` (KCL, referenced to module N so IM_N = 0; unit-tested against a double-precision KCL on random inputs, and against the SIL golden module currents up to a common offset); `SUP_STRESS_ONLY` fallback flag; `CTRL_TS`, `STACK_DECIM`, `MPPT_ENABLED` from `params.h`; `gen_params.py` (numpy) and `export_params.m` take N_MOD, Ts, ratings, and an `M.json` from identification; `unit_tests.c`/`replay.c` follow the macros. `ctest` green at N_MOD=3, Ts=100 µs with a placeholder M.
4. **MATLAB scripts for the 3-module model** (you run them Monday): `init_params.m` updated for 150 W PV (Vmp 18.28, Imp 8.207, Voc 22.407, Isc 8.721), ERUC23 inductance + 61 mΩ phase R, 100 kHz, 3 modules; `shuffler_string_ident.m` / `_validate.m` / `export_golden.m` / `export_params.m` generalised to N_MOD; a checklist of the GUI edits needed on `power_shuffler_sim.slx` (drop module 4 + shuffler 3, resize controller/supervisor ports, remove the MPPT/current-sink path or keep it as the "lab load" variant). The supervisor's `IM` input is fed from the reconstruction block, not the plant's true module currents, with a scope comparing the two (this is the proof that the hardware measurement set is sufficient). Optional extras from objective 1 as switchable blocks: Gaussian sensor noise at the measured scales (INA 3.125 mV LSB, hall 12-bit), and a first-order/comb filter on y matching the C core's LPF.
5. **Telemetry/command contract** `0_Documentation/telemetry.md` (frame at 50 Hz: `T,<ms>,<state>,<fault>,VM1..3,ILA1,ILB1,ILA2,ILB2,d1..4,rv1,beta,stress,Tdie1..3,pver`; commands `C,MODE,<IDLE|OL|CL|OL1|CL1|OL2|CL2>`, `C,DUTY,<leg>,<d>`, `C,EN`, `C,ESTOP`, `C,CLEAR`, `C,GAIN,<preset>`).

### Day 1 — Monday: Simulink gains (you) + QSPICE C-block and firmware scaffold (me)

You, MATLAB: build the 3-module plant variant, run `shuffler_string_ident` → M, paste/regenerate, run `shuffler_string_validate` tests 1–5 (6–7 only with the lab-load variant). Then SIL per `sil/INSTRUCTIONS.md` (C Caller blocks, N_MOD=3 build) + `export_golden` → golden replay passes. Output: `params.h` **v2.0.0-3mod**, versioned M.

Me, QSPICE: `2_Qspice/ctrl_dll/` builds `shuffler_ctrl.dll` from `6_RTOS/core` (QSPICE C-block API; compiled with QSPICE's bundled DMC or mingw-w64; a `build.bat`/`build.sh`). The block samples its inputs internally at the control rate and holds duties between ticks. Inputs: VM1..3 via INA-style sample-and-hold at 1 kHz with 3.125 mV quantisation, IL×4 via 12-bit quantised hall model (1.65 V + S·I, 100/25 mV/A); outputs: 4 duties → PWM comparators (100 kHz ramp, 180° between legs) replacing the fixed `PULSE()` sources, through the existing S5 driver model with 200 ns dead time. `gen_shuffler.py` gets stage **S9 closed loop** (CASE uniform / 1000-600-1000 / 1000-1000-400, Vref step), `run_baseline.py S9` reports settled VM equalisation, duties, shuffled current, stress. Runs are short (≤ 50 ms sim time).

Me, firmware: CubeMX additions (FreeRTOS CMSIS_V2, TIM6 10 kHz, IWDG, E-stop EXTI on a free pin e.g. PC0, LPUART1 921600); HRTIM both converters with independent duties and a 180° leg offset (master timer CMP2 = PER/2 resets the B legs; each leg set-on-reset / reset-on-own-CMP1 = d·PER, preload, clamp [0.05, 0.95]); COMP1/COMP3 (PA1/PA0, DAC threshold) → HRTIM fault for the A phases; control ISR calling `stack_step`; soft-start ramp; state machine `BOOT → SELFTEST → IDLE → SOFTSTART → RUN_{OL,CL,OL1,CL1,OL2,CL2} → STOP; any → FAULT`; tasks `sense_v` (1 kHz INA round-robin), `safety` (100 Hz, IWDG, envelopes), `telemetry` (50 Hz), `cmd`.

Me, Pi (`7_Pi/`): `docker-compose.yml` (influxdb 2.7 + grafana 11, provisioned datasource + dashboard JSON); `pod/` service (pyserial → influxdb-client; DS18B20; IR via evdev → commands; LCD + RGB from state); `tools/ident.py` (bench cross-check of M), `tools/plots.py`.

Bench (you): isolator rework on U10; confirm Nucleo GND/3V3 provisioning; E-stop button on the pod; EcoFlow input question (see Risks).

### Day 2 — Tuesday: QSPICE closed loop + firmware bring-up

- QSPICE S9 with the Monday `params.h`: confirm no limit cycle through switching ripple and dead time, equalisation under the shade cases, supervisor stress behaviour. If gains need refining (e.g. Kp_ratio or LPF fc), change in Simulink/`init_params`, re-run validate + SIL, regenerate `params.h`; QSPICE is the arbiter, Simulink the source. Save S9 figures for the report.
- Firmware on the bench (PSUs + resistors): telemetry in Grafana; `OL` on S2, S1, both; scope dead time and leg phase; hall calibration (DC current per phase) and VM vs DMM; OC trip test.

### Day 3 — Wednesday: closed loop on the bench

- Flash firmware with the QSPICE-confirmed `params.h`. `CL1` then `CL`; Vref steps, PSU imbalance as shade; compare settle time/shape with the SIL and S9 traces. `tools/ident.py` as a cross-check that the bench G matches the Simulink G within ~20 % (if not, that's a model-parameter finding for the report, and the Simulink M gets refreshed from it).
- Pi UI: IR mode cycling, LCD/LED states, safe-to-touch indication. Tag `carpark-v1`.

### Day 4 — Thursday: carpark dry run

Checklist (`0_Documentation/experiment_checklist.md`): EcoFlow input question closed; 15 A string fuse; E-stop reachable; heatsink temperature alarm; fault-latch test with outputs live; Pi + laptop with Grafana. Run `OL → CL1 → CL` under real sun; shade one panel in steps; baseline (`IDLE`) under the same shade.

### Day 5 — Friday: experiment + data capture

Repeat with the full logging set; export Influx CSVs to `3_Analytical/data/`; `tools/plots.py` for baseline vs shuffled power, VM traces, duties, currents, alongside the SIL and S9 traces of the same scenarios.

### After Friday

Report + presentation: Simulink/SIL/QSPICE/hardware comparison of the same cases is the thesis story. PIL/HIL ladder and firmware-side string MPPT (needs a string current sensor and a controllable load) go in future work.

## Verification

- Day 0: `ctest` green in `6_RTOS/core` at N_MOD=3, Ts=100 µs; firmware builds from WSL via the Windows bundle; KiCad opens with no missing-library warnings (you).
- Day 1: validate tests 1–5 pass on the 3-module model with the supervisor fed by reconstructed module currents (reconstruction error vs true IM, after removing the common offset, well inside the governor thresholds); golden replay passes with the C core; `shuffler_ctrl.dll` loads in QSPICE and S9 netlist passes `--verify`.
- Day 2: S9 settles with no oscillation and VM equalised within the Simulink prediction; bench: 200 ns dead time, 180° legs, duty tracks within 1 %, OC trip < 1 ms (COMP) / 100 ms (latch).
- Day 3: closed-loop step on the bench matches SIL/S9 shape; fault latch stops switching in every mode.
- Day 4/5: logged dataset + signed checklist.

## Risks and open items

- **Time**: three simulation rungs plus hardware in five days. If Monday's Simulink work overruns, Tuesday's QSPICE S9 runs with the Monday M as-is and gain refinement is skipped; if both overrun, Wednesday's bench ident supplies M and the sims are re-run post-hoc for the report.
- **EcoFlow 60 V limit vs 67 V Voc.** Options: (a) confirm on the bench (PSU at 67 V, current-limited) that it refuses rather than breaks, and connect only after loading; (b) 2 panels + 1 shuffler on the EcoFlow; (c) resistor bank. Decide Monday with the supervisor.
- **Isolator rework** on the critical path for VM1; fallback is `CL1` (converter 2) only.
- **FreeRTOS time-box** Monday; fallback superloop with the same ISR control and safety.
- **Simulink `.slx` edits are GUI work** I cannot do from here; I supply scripts, parameters and a step-by-step checklist.
- **Nucleo GND pads have no net on the PCB**: confirm the bodge used for the power test.


---

## Status log

**Sun 11 Oct (Day 0, done):** repo restructured and SIL branch merged; control core generalised to
3 modules at 10 kHz with module-current reconstruction (host tests green); 3-module Simulink scripts
and model-edit checklist; telemetry contract; firmware for both converters (HRTIM 4 legs, 10 kHz
control ISR running the C core, state machine, telemetry, E-stop, IWDG) building; Pi stack
(InfluxDB + Grafana + bridge + tools); **QSPICE closed loop done ahead of plan**: stage S9i identified
the Version 0 plant (`2_Qspice/ctrl_dll/README.md`), stage S9 closes the loop on the switching model
with the firmware control stack in a DLL and tracks a 1 V reference step cleanly.

Findings that change Monday's work:
1. **Sign of `u_diff → i_comm` is positive on the PCB/QSPICE wiring, negative in the 4-module Simulink
   identification.** The 3-module Simulink ident must be compared with `results/S9i.meas.json`; if
   its sign differs, the Simulink model's leg/ILB convention is flipped relative to the hardware and
   the QSPICE M is the one to flash.
2. INA239 conversion time: firmware now sets 84 µs (default 1 ms rang the voltage loop).
3. Control-stack IL convention: ILA into the midpoint, ILB out (raw PCB sensor signs). Bench-verify
   with the open-loop 0.52/0.48 probe before closed loop.
