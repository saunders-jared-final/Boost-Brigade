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
  shuffler_hw.c/.h    HRTIM: master timer @200 kHz, four legs (A legs reset on master period,
                      B legs on master CMP2 -> 180 deg), 200 ns dead time, duty = CMP1 preload,
                      control tick = master repetition IRQ @10 kHz (every 20 periods), outputs-off /
                      gates-low paths; ADC trigger 1 = timer A/B CMP3/CMP4 (4 per period, PER/8 + k*PER/4)
  params_rt.c/.h      run-time parameter table: C,SET/SETM/GET/LIST/APPLY/REVERT, gain set in RAM
                      (CTRL_RUNTIME_GAINS), kscale (boot 0.3), MCU 4x4 inverse, bumpless swap
  app.c/.h            state machine BOOT->SELFTEST->IDLE->SOFTSTART->RUN->STOP, FAULT latch,
                      10 kHz control ISR (sensors -> stack_step -> duties), 1 kHz INA task,
                      100 Hz safety task (envelopes, IWDG, E-stop), requests from the parser
  comms.c/.h          T/S/F/A frames + C commands (0_Documentation/telemetry.md), LPUART1 921600
Core/Src/sensors.c    TMCS1126 hall sensing: HRTIM-triggered regular ADC1/ADC2 + circular DMA, 80 samples
                      per channel per tick = mean over exactly 20 PWM periods (comb, nulls at k*fsw);
                      over-current latch (oc_a, default 12 A, for 2 ms, a railed code, or stalled DMA)
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

`C,MODE,<OL|CL|OL1|CL1|OL2|CL2>` then `C,EN,1` → SOFTSTART → RUN. Soft start: while idle every
shuffler's legs are held at the pre-bias d0 = Vbot/(Vtop+Vbot) (0.5 if a module voltage is unknown), the
outputs switch on at a quarter PWM period (centred first pulse), then the duties ramp linearly to the
mode's duty (OL duties, 0.5 for CL) over 150 ms; RUN starts when the ramp ends. Without this a 1 V module
mismatch rails the hall sensors at enable. `*1` = converter 1 (legs 0–1), `*2` = converter 2 (legs 2–3).
`CL` modes need the module voltages of the legs involved (U10 for converter 1).
In single-converter closed-loop modes the controller is blinded to the inactive
shuffler (its channels read zero error).

Any of these forces outputs off and FAULT (cleared with `C,CLEAR`, outputs stay
off until re-enabled): over-current latch (ISR), E-stop button (EXTI, priority 0),
`C,ESTOP`, per-module OV/UV envelope, INA die over-temperature, INA bus lost in a
closed-loop mode, implausible zero calibration or isolator conflict at boot.
IWDG 2 s, kicked by the safety task; a watchdog reset is reported as fault 0x100.

## Open-loop test cases (no Pi needed)

Terminal on the ST-LINK VCP (921600 8N1, send `\n`); the `T` stream is just noise to ignore.

| Command | Does |
|---|---|
| `C,TEST,0` | IC init check, gates off: SPI3 bus, INA239 ×3 (re-probe, config read-back, VBUS, die temp), TMCS1126 ×4 (zero-cal, rest reading), E-stop, fault word. Prints `# INIT ...` lines + `# INIT RESULT`; answer `A,TEST,OK/ERR`. Refused while switching. |
| `C,TEST,1` | bottom shuffler only (S2, legs 2–3, `OL2`) |
| `C,TEST,2` | top shuffler only (S1, legs 0–1, `OL1`) |
| `C,TEST,3` | both shufflers (`OL`) |

1–3 only select the mode; `C,EN,1` (or B1) starts SOFTSTART (150 ms ramp) → RUN at 0.5 duty, `C,DUTY,<leg>,<d>` / `C,DUTYS,...` set duties, `C,EN,0` stops. Unselected legs stay off.

## Bring-up order (bench, PSUs + resistors)

1. Flash, open the VCP at 921600: banner, `S` lines, `T` frames at 50 Hz.
2. `C,MODE,OL2` `C,EN,1`: scope PB12/PB13 — 200 kHz, 200 ns dead time; `C,DUTY,2,0.6` moves leg 2.
3. `C,MODE,OL1` likewise on PA8..PA11, then `C,MODE,OL` for all four; confirm 180° between A and B.
4. Hall calibration: known DC current per phase, `C,SET,hall_mva<ch>,<mV/A>` until `T` reads right
   (B phases: 25 vs 100 mV/A is open); save to `7_Pi/pod/params.yaml`, later into `sensors.c`.
   Over-current test with `C,SET,oc_a,2` and a 3 A PSU current.
5. `VM1..3` vs DMM after the U10 isolator rework.
6. `C,MODE,CL2` `C,EN,1` at the boot `kscale` 0.3 (telemetry field `kscale`); `C,VREF,0,1` steps;
   raise kscale with `C,SET,kscale,<k>` + `C,APPLY` (or the page on :8080) only while steps settle
   cleanly; then `CL1`, `CL`. Without U10: `C,SET,vm1_src,1` + `C,SET,vstr_param,<DL3021 CV V>`.

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
