# Boost Brigade — solar power shuffler (S-PPC) string

Adaptive control of serial partial-power converters ("power shufflers") for
MPPT under partial shading. QUT EGH490 capstone: control stream (this repo's
firmware/control/simulation) + hardware stream (Version 0 PCB).

**Current goal (due Fri 16 Oct 2026): carpark experiment** — 3 × 150 W panels,
2 shufflers on the Version 0 board, EcoFlow DELTA 2 Max as the string MPPT
load, closed-loop module equalisation on the Nucleo-G474RE, telemetry on
Grafana via the Raspberry Pi pod. Day-by-day plan: `0_Documentation/PLAN.md`.

## Layout

| Folder | What |
|---|---|
| `0_Documentation/` | proposals, progress reports, UI pod wiring, **`telemetry.md`** (Nucleo↔Pi contract), plan, experiment checklist |
| `1_Datasheets/` | INA239, TMCS1126, 1ED3140, EcoFlow, LM5180 calculator |
| `2_Qspice/` | switching-level models; `Claude's outputs/PCB_Baseline/` is the scripted baseline (`gen_shuffler.py` → stages S1–S8b, `run_baseline.py`); closed-loop C-block stage S9 to come |
| `3_Analytical/` | notebooks + design log (`shuffler_notebooks/DESIGN_LOG.md`) and the early MATLAB control-design lineage |
| `4_Simulink/` | test ladder: `1_MIL` (4-mod validated model), `2_SIL` (C Caller model + **host build/tests of the C core**), **`3_Carpark_3mod`** (3-module scripts + model-edit checklist) |
| `5_Kicad/` | `Version 0 project/` (schematic, PCB, gerbers) + `libs/` (all part libraries; project-relative lib tables) |
| `6_RTOS/` | STM32G474 firmware (CubeMX + CMake) and **`ctrl_core/`**, the single copy of the control-stack C shared by SIL, QSPICE and firmware; `ctrl_core/params/` holds the JSON gain file and generators |
| `7_Pi/` | Raspberry Pi pod: InfluxDB + Grafana compose, serial bridge, IR/LCD/LED service, bench tools |

## Gain flow (one source, three harnesses)

```
Simulink ident (4_Simulink/3_Carpark_3mod/shuffler_string_ident.m)
   └─> 6_RTOS/ctrl_core/params/shuffler_params.json   (M, Ts, thresholds)
         └─> gen_params.py / export_params.m  ->  6_RTOS/ctrl_core/params.h
               ├─> SIL: C Caller blocks + golden replay + unit tests (4_Simulink/2_SIL.../firmware)
               ├─> QSPICE: shuffler_ctrl.dll C-block, stage S9 (2_Qspice)
               └─> firmware: 10 kHz control ISR on the Nucleo (6_RTOS)
```

Hardware facts that shape the control configuration (verified in `5_Kicad`):
- 3 panels / 2 converters; HRTIM pins PA8-11 (S1 A/B high/low) and PB12-15 (S2); hall sensors PA0 ILA_1, PA4 ILB_1, PA1 ILA_2, PC1 ILB_2; INA239 ×3 on SPI3 (CS PA7, PB6, PC7).
- The INA239s read bus voltage only (shunt inputs shorted): module currents are **reconstructed** from the inductor currents and duties (`ctrl_core/shuffler_recon.c`); the string current is an unobservable common offset that the supervisor's deficit term cancels. String-level MPPT is the EcoFlow's job (`en_mppt = 0` in firmware).
- U10 (panel-1 voltage) sits behind a mis-wired ISO7762: rework required for closed loop on converter 1.
- 1ED3140 drivers have no fault pins and add no dead time; dead time (200 ns, HRTIM) and over-current trips are firmware.

## Quick starts

Host tests of the control core (WSL):
```sh
cd 4_Simulink/2_SIL_Software_In_The_Loop/firmware && cmake -B build && cmake --build build && ctest --test-dir build --output-on-failure
```
Regenerate gains after an identification: `python3 6_RTOS/ctrl_core/params/gen_params.py`
(or `export_params` in MATLAB). Preset `params/mil4_params.json` reproduces the validated 4-module constants.

Firmware build (Windows ST bundle, callable from WSL; paths in `6_RTOS/.vscode/tasks.json`):
```sh
cd 6_RTOS && cmake.exe --preset Debug && cmake.exe --build --preset Debug
STM32_Programmer_CLI.exe -c port=SWD -w build/Debug/Shuffler_1_Open_Loop.elf -rst
```

## Panel reference (150 W hard-frame, 22 V model)

Pm 150 W ±3 %, Vmp 18.28 V, Imp 8.207 A, Voc 22.407 V, Isc 8.721 A, NOCT 45 ±2 °C,
max series fuse 15 A, 1160 × 670 × 30 mm, 9.32 kg, IP67.
