# 3_Carpark_3mod — Simulink model for the Version 0 board (3 panels / 2 shufflers)

Scripts here are generic in the module count (`P.N` in `init_params.m`) and
drive a model `carpark_shuffler_sim.slx` that you create from
`../2_SIL_Software_In_The_Loop/SIL_power_shuffler_sim.slx`. The gains flow
**Simulink ident → `6_RTOS/ctrl_core/params/shuffler_params.json` → `params.h`
→ SIL C Callers / QSPICE DLL / firmware**, so the thing validated here is the
thing deployed.

## 1. Model edits (GUI, once) — checklist

Start: copy `SIL_power_shuffler_sim.slx` → `carpark_shuffler_sim.slx` in this
folder (keep the MIL variant with the MATLAB Function blocks; the C Caller
variant comes after the goldens).

Power Circuit
- [ ] Delete `Irradiance 4`, PV module 4 and `Power Shuffler3`; the string is PV1–PV3 in series, Shuffler1 across PV1/PV2 (midpoint = PV2+), Shuffler2 across PV2/PV3 (midpoint = PV3+). Match the PCB: top of shuffler 1 at PV1+, bottom at PV3+; top of shuffler 2 at PV2+, bottom at string negative.
- [ ] PV block parameters → 150 W panel: Vmp 18.28 V, Imp 8.207 A, Voc 22.407 V, Isc 8.721 A (`init_params.m` `P.pv`).
- [ ] Per converter: bus capacitors 130 µF from top terminal to midpoint and 130 µF from midpoint to bottom (two TDK B40910A0137M000); ESR ≈ 28 mΩ each (QSPICE `parasitics.json`).
- [ ] Inductors unchanged (TDK ERUC23-4R1K already: L_self 7.9 µH, L_m 5.85 µH, R_w 1.85 mΩ). Keep the 61 mΩ per-phase damping resistance for now (re-identification absorbs it).
- [ ] Averaged model: no switching frequency to change. (Switching variant: 100 kHz, 200 ns dead time.)
- [ ] Load: keep the controlled current sink with `Iref` from the MPPT for the **lab-load variant** (tests 6–7). For the carpark the EcoFlow is the MPPT; the firmware runs with `en_mppt = 0`.

Controller block (`Controller/Controller`)
- [ ] Replace the function body with `shuffler_string_ctrl.m`. Ports: `VM` [3], `IL` [4] = {ILA1, ILB1, ILA2, ILB2}, `rv` [2]; output `d` [4] → Demux to dA1, dB1, dA2, dB2. Sample time **100e-6**, atomic.
- [ ] After `shuffler_string_ident` paste the printed `M` (4×4) into the block.

Supervisor block (`Supervisor/Supervisor`)
- [ ] Body ← `shuffler_string_supervisor.m`. Ports: `VM` [3], `IM` [3], `IL` [4], `d` [4] (Mux of the four duties), `en`; outputs `rv` [2] → Demux → the two 1 ms Unit Delays (IC 0), `beta`, `stress`. Sample time 1e-3, atomic.
- [ ] **New block** `Supervisor/Recon` (MATLAB Function, body ← `shuffler_string_recon.m`): inputs `IL` [4], `d` [4]; output `IM` [3]. Sample time 1e-3. Feed **its** output into the Supervisor's `IM` port (NOT the plant's true module currents) — this proves the hardware measurement set is sufficient.
- [ ] Log the Recon output as `IMr1..IMr3` (To Workspace, Timeseries) next to the true `IM1..IM3`; `shuffler_string_validate` prints `IM_true − IM_recon` per module — the spread must be ≈ 0 (the common value is the string current).
- [ ] Vref constants: keep `Vref1`, `Vref2`; delete `Vref3` and the third delay/sum.

MPPT block (`MPPT/P&O`)
- [ ] Body ← `shuffler_string_mppt.m` (IREF0 8, IMIN 2, IMAX 8.5 for the 150 W panels). The `Delay` IC must be **8** (= IREF0).

Telemetry
- [ ] To Workspace set: VM1..3, IM1..3, IMr1..3, ILA1, ILB1, ILA2, ILB2, dA1, dB1, dA2, dB2, V_String, I_String, plus rv1, rv2 (before their delays), beta, stress, Iref (before its delay), Pav, mppt_state. All Timeseries, inherited sample time.
- [ ] Identification variant: `CTRL_MODE` Variant Source with Constant blocks `Power Shuffler1/dA1_const`, `dB1_const`, `Power Shuffler2/dA2_const`, `dB2_const` (paths in `init_params.m`).

Optional (objective 1 extras, switchable with a Manual Switch / variant)
- [ ] Sensor noise at the measured scales: INA239 bus voltage 3.125 mV LSB + ~2 mV rms, hall 12-bit on 3.3 V (0.8 mV LSB → 8 mA at 100 mV/A, 32 mA at 25 mV/A) + ~20 mA rms; sample-and-hold VM at 1 kHz (INA conversion) and IL at 10 kHz.
- [ ] A comb / moving-average on IL over one PWM period (10 µs) in the switching variant only.

## 2. Workflow (Monday)

```matlab
cd 4_Simulink/3_Carpark_3mod
P = init_params();                 % sanity: paths resolve, N = 3
shuffler_string_ident              % CTRL_MODE 0, 1 + 4 modal runs -> G, M; writes shuffler_params.json
% paste M into the Controller block
shuffler_string_validate           % tests 1-5 (+6-7 with the lab load)
export_golden(0.5)                 % MIL goldens for the C replay
```
Host (WSL):
```sh
python3 6_RTOS/ctrl_core/params/gen_params.py          # JSON -> 6_RTOS/ctrl_core/params.h (or export_params.m)
cd 4_Simulink/2_SIL_Software_In_The_Loop/firmware && cmake -B build && cmake --build build
ctest --test-dir build --output-on-failure
./build/test/replay test/golden/golden_inputs.csv test/golden/golden_expected.csv
```
Then the C Caller variant per `../2_SIL_Software_In_The_Loop/firmware/sil/INSTRUCTIONS.md`
(array ports now: `d[4]`, `rv[2]`, plus `sil_recon_step`) and re-run validate = SIL gate.

## 3. What changes vs the 4-module work

| | 4-mod (validated) | 3-mod carpark |
|---|---|---|
| Modules / shufflers / duties | 4 / 3 / 6 | 3 / 2 / 4 |
| PV | Aiko 540 W (Vmp 38.7 V, 14.35 A) | 150 W (Vmp 18.3 V, 8.2 A) |
| Controller tick | 50 µs | 100 µs (10 kHz on the G474) |
| Module currents into the supervisor | plant (true) | reconstructed from IL + duties |
| MPPT clamps | 12 / 5 / 14.5 A | 8 / 2 / 8.5 A (lab load only; EcoFlow in the carpark) |
| PWM (switching variant / QSPICE / hardware) | 200 kHz | 100 kHz |
