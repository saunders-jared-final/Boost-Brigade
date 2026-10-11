# ctrl_dll — the firmware control stack as a QSPICE C-block

`shuffler_ctrl_dll.cpp` wraps `6_RTOS/ctrl_core` (unchanged sources, `params.h` from the
same JSON as the firmware) into a QSPICE `Ø(.DLL)` block with the firmware's sampling
and quantisation. Stage **S9** of `../Claude's outputs/PCB_Baseline/gen_shuffler.py`
places it around the S5 switching model (150 W panels, 1ED3140 drivers, 100 kHz PWM,
200 ns dead time) with HRTIM-style comparators turning the held duties into gate pulses.

```
build_dll.bat                                  # Digital Mars C++ bundled with QSPICE -> shuffler_ctrl_dll.dll (copied to stages/)
cd "..\Claude's outputs\PCB_Baseline"
python gen_shuffler.py S9                      # stages/S9.qsch + S9.cir (.param CASE=2 VSTEP=1: module 2 at 600 W/m2, 1 V step on Vref1 at 8 ms)
python run_baseline.py S9                      # QSPICE64 run (~12 ms of switching), results/S9.meas.json + SVGs
```
What to look at: `vd1`/`vd2` settle to 0 after 1 ms (equalisation), `vd1s` ≈ VSTEP after the
8 ms step with no oscillation on `da*`/`ish*`, `stressmax` below S_HI = 0.9 for the 600 W/m²
case, `pout` above `pref` (reference string, no shufflers). Rebuild the DLL whenever
`shuffler_params.json` changes (it carries `PARAMS_VERSION`).
