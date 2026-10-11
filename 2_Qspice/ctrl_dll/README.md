# ctrl_dll — the firmware control stack as a QSPICE C-block

`shuffler_ctrl_dll.cpp` wraps `6_RTOS/ctrl_core` (unchanged sources, `params.h` from the
same JSON as the firmware) into a QSPICE `Ø(.DLL)` block with the firmware's sampling and
quantisation (INA239 1 kHz hold, 3.125 mV LSB; 12-bit hall ADC; 10 kHz control tick forced
through `Trunc()`; one-level state rollback for rejected solver steps). Stages **S9i / S9**
of `../Claude's outputs/PCB_Baseline/gen_shuffler.py` put it around the S5 switching model
(150 W panels `pvmi_150w`, 1ED3140 drivers, 100 kHz PWM, 200 ns dead time) with HRTIM-style
comparators turning the held duties into gate pulses.

## Workflow (all from `..\Claude's outputs\PCB_Baseline`, Windows Python; ~2 min per S9 run)

```
..\..\ctrl_dll\build_dll.bat               # Digital Mars C++ bundled with QSPICE -> shuffler_ctrl_dll.dll (copied to stages/)
python gen_shuffler.py S9i S9              # stages/S9i.* (identification) and stages/S9.* (closed loop)
python run_baseline.py S9i                 # 5 runs (RUN 1 baseline, 2-3 u_comm, 4-5 u_diff), 4 ms each, ~4 min
"C:\Program Files\QSPICE\QPOST.exe" stages\S9i.cir > stages\qpost_S9i.txt    # windowed .meas with .step: use QPOST, not --remeasure
python -c "import run_baseline as rb,json; json.dump(rb.parse_qpost(open('stages/qpost_S9i.txt','rb').read().decode('cp1252')),open('results/S9i.meas.json','w'))"
python qspice_ident.py --write             # G -> M -> 6_RTOS/ctrl_core/params/shuffler_params.json (version ...-qspice)
python ..\..\..\6_RTOS\ctrl_core\params\gen_params.py   # -> params.h
..\..\ctrl_dll\build_dll.bat               # DLL with the new gains
python run_baseline.py S9                  # closed loop: results/S9.meas.json + results/S9_*.svg
```

## What S9 shows (11 Oct 2026, CASE 2 = module 2 at 600 W/m², 6.5 A current-sink load)

- With the **4-module Simulink M** (placeholder) the loop diverged: the switching model's
  `u_diff -> i_comm` gain is **+256 / +216 A per unit duty** (positive), the averaged 4-module
  identification had it negative. Same magnitude class, opposite sign: a leg/sign convention
  difference between the Simulink plant and the PCB/QSPICE wiring. **Monday's 3-module Simulink
  identification must be checked against `results/S9i.meas.json` (signs of `G`) before any M
  goes to the hardware.**
- With the **QSPICE-identified M** (`sps-params-2.20261011-1634-3mod-qspice`, now in
  `shuffler_params.json`) the loop is stable: `vd1`/`vd2` settle to 0.00 / −0.01 V, circulating
  currents nulled (`idf*` ≈ 0), the 1 V `Vref1` step settles in ~1.5 ms with ~9 % overshoot,
  `stressmax` ≈ 0.24, string power 377 W vs 262 W for the reference string without shufflers.
- Two sampling details mattered and are now mirrored in the firmware: (1) the hall inputs must be
  the **average over a PWM period** (a point sample phase-locked to the PWM aliased the phase ripple
  into a 6.8 A bias that the controller then "nulled"); the firmware's 4× oversampling across one
  period does this. (2) The INA239's power-on 1.05 ms conversion plus the 1 kHz poll is ~1.5 ms of
  lag — ~80° at 150 Hz — and made the voltage loop ring with 50 % overshoot; the firmware now writes
  `ADC_CONFIG` for an 84 µs bus conversion (`ina2x9.c`), the DLL models the same.
- Load: the resistor-type load (`LOADSEL=0`, a behavioural current source) stalls the solver at
  t = 0 in this stage; use the current sink (`LOADSEL=1`, `Icc` below what the shaded string can
  carry, 8 A collapsed it).
- `.meas ... FROM/TO` with `.step`: the saved window is time-rebased, and `run_baseline.py
  --remeasure` does not parse FROM/TO; QPOST does.

Sign convention of the stack (see `0_Documentation/telemetry.md`): `IL = {ILA, ILB}` with ILA
positive into the converter midpoint and ILB positive out of it, so `ILA+ILB` is the circulating
current the controller nulls and `ILA−ILB` the shuffled current. The S9 hall-sensor sources carry
the PCB's reversed B-phase mounting, exactly like the real sensors.
