# 6_RTOS — STM32G474 (Nucleo-G474RE) shuffler firmware

CubeMX + CMake project (`Shuffler_1_Open_Loop.ioc`, name kept for CubeMX's sake)
driving the Version 0 two-shuffler board. The control algorithm is **not** in
this folder's `Core/`: it is `ctrl_core/`, the single copy of the control stack
shared with the SIL model and the QSPICE DLL, compiled here with
`STACK_RECON_IM=1` (module currents reconstructed from inductor currents).

## Layout

```
ctrl_core/            control stack (ctrl / supervisor / mppt / recon / stack), params.h GENERATED
  params/             shuffler_params.json (gains, single source), gen_params.py, export_params.m
App/
  shuffler_hw.c/.h    HRTIM: master timer @100 kHz, four legs (A legs reset on master period,
                      B legs on master CMP2 -> 180 deg), 200 ns dead time, duty = CMP1 preload,
                      control tick = master repetition IRQ @10 kHz, outputs-off / gates-low paths
  app.c/.h            state machine BOOT->SELFTEST->IDLE->SOFTSTART->RUN->STOP, FAULT latch,
                      10 kHz control ISR (sensors -> stack_step -> duties), 1 kHz INA task,
                      100 Hz safety task (envelopes, IWDG, E-stop), requests from the parser
  comms.c/.h          T/S/F/A frames + C commands (0_Documentation/telemetry.md), LPUART1 921600
Core/Src/sensors.c    TMCS1126 hall sensing (injected ADC, 4x oversampled over one PWM period),
                      over-current latch (12 A for 2 ms, or a railed ADC code) -> outputs off in the ISR
Core/Src/ina2x9.c     INA239/229 bus-voltage monitors on SPI3 (3 chip selects), isolator-conflict detection
```

Pin map (schematic `5_Kicad/Version 0 project`):

| Function | Pins |
|---|---|
| S1 leg A/B high,low | PA8/PA9 (HRTIM TA1/TA2), PA10/PA11 (TB1/TB2) |
| S2 leg A/B high,low | PB12/PB13 (TC1/TC2), PB14/PB15 (TD1/TD2) |
| Hall ILA_1, ILB_1, ILA_2, ILB_2 | PA0 (ADC1_IN1), PA4 (ADC2_IN17), PA1 (ADC1_IN2), PC1 (ADC2_IN7) |
| INA239 SPI3 / CS1..3 | PB3/PB4/PB5, PA7 (U12 PV3+), PB6 (U11 PV2+), PC7 (U10 PV1+→PV3+, via U13) |
| Telemetry | LPUART1 PA2/PA3 (ST-LINK VCP) |
| E-stop (new) | PC0 (CN7-38) to GND, internal pull-up, EXTI falling |
| B1 button | toggles enable in the selected mode |

## Build and flash (Windows ST bundle, also from WSL)

```sh
cd 6_RTOS
cmake.exe --preset Debug && cmake.exe --build --preset Debug
STM32_Programmer_CLI.exe -c port=SWD -w build/Debug/Shuffler_1_Open_Loop.elf -rst
```
From WSL the same through `cmd.exe /c` with the bundle on PATH (see
`.vscode/tasks.json` for the exact paths). Alternative flash: copy a `.bin` to
the `NODE_G474RE` USB drive.

Regenerate gains: `python3 ctrl_core/params/gen_params.py` (after the Simulink
identification wrote `shuffler_params.json`), rebuild, flash; the banner and
every `T` frame carry `PARAMS_VERSION`.

## Modes and safety

`C,MODE,<OL|CL|OL1|CL1|OL2|CL2>` then `C,EN,1` → SOFTSTART (50 ms at 0.5 duty,
outputs on) → RUN. `*1` = converter 1 (legs 0–1), `*2` = converter 2 (legs 2–3).
`CL` modes need the module voltages of the legs involved (U10 for converter 1).
In single-converter closed-loop modes the controller is blinded to the inactive
shuffler (its channels read zero error).

Any of these forces outputs off and FAULT (cleared with `C,CLEAR`, outputs stay
off until re-enabled): over-current latch (ISR), E-stop button (EXTI, priority 0),
`C,ESTOP`, per-module OV/UV envelope, INA die over-temperature, INA bus lost in a
closed-loop mode, implausible zero calibration or isolator conflict at boot.
IWDG 2 s, kicked by the safety task; a watchdog reset is reported as fault 0x100.

## Bring-up order (bench, PSUs + resistors)

1. Flash, open the VCP at 921600: banner, `S` lines, `T` frames at 50 Hz.
2. `C,MODE,OL2` `C,EN,1`: scope PB12/PB13 — 100 kHz, 200 ns dead time; `C,DUTY,2,0.6` moves leg 2.
3. `C,MODE,OL1` likewise on PA8..PA11, then `C,MODE,OL` for all four; confirm 180° between A and B.
4. Hall calibration: known DC current per phase, `C,CAL,<ch>,<mV/A>,<zero>` until `T` reads right;
   put the final values into `sensors.c`. Over-current test by lowering `SENSE_OC_LIMIT_A` temporarily.
5. `VM1..3` vs DMM after the U10 isolator rework.
6. `C,MODE,CL2` `C,EN,1` with the Simulink-identified `params.h`; `C,VREF,0,1` steps; then `CL`.

## CubeMX pass (Monday) — things the GUI should own

- Pins PA8..PA11 → HRTIM1 CHA1/CHA2/CHB1/CHB2 (currently GPIO outputs; `hw_init` overrides to AF13).
- Middleware **FreeRTOS (CMSIS_V2)**: threads `sense_v` (1 ms), `safety` (10 ms), `telemetry`
  (20 ms), `cmd` (event); each calls the matching `app_task_*()`. Keep the control in the HRTIM ISR.
- **IWDG** (LSI/32, reload 2000) — replaces the register-level `iwdg_start()` in `app.c`.
- **COMP1** (INP PA1 = ILA_2) and **COMP3** (INP PA0 = ILA_1) with **DAC3** CH1/CH2 as the
  inverting references, outputs to HRTIM FLT4/FLT5 → hardware over-current trip on the A phases
  (then set `tim.FaultEnable = FAULT4|FAULT5` in `shuffler_hw.c`).
- LPUART1 global interrupt enabled; SPI3 prescaler 32 (5.3 MHz) for faster INA polling.
- `USE_HAL_*_REGISTER_CALLBACKS` not needed; keep `KeepUserCode = true`.
