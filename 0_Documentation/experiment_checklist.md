# Carpark experiment — pre-flight checklist and procedure

Date: ______  Weather / irradiance: ______  Panels: 3 × KickAss KAUSSP80 (80 W, Voc 25.07 V, Isc 4.35 A; string Voc 75.2 V)
Load: Rigol DL3021 e-load in CV (also the bench load; no EcoFlow, no string MPPT). Firmware fw-0.4.1 (200 kHz PWM, 10 kHz control, protocol 2; a 300 kHz image is staged but not cleared for closed loop).

Controls: IR remote / LCD, web page `http://<pi>:8080`, Grafana `http://<pi>:3000`, `podctl.py` over SSH.
Presets are the same everywhere (`7_Pi/pod/actions.py`): 0 init check · 1 open loop · 2 closed loop · 3 load on ·
4 load off · 5 load remote · 6 load local · 7 gains 30 % · 8 gains 100 % · 9 clear fault. Remote: digit then PLAY;
POWER = E-stop, FUNC/STOP = stop. Both shufflers always run together (hard-wired on the Version 0 board).

## A. Hardware (tick before the string is connected)

- [ ] Init check passes (`0` + PLAY, or `C,TEST,0`): SPI bus, INA CS1/CS2(/CS3), halls zero-cal OK, E-stop released
- [ ] `VM1` source decided: U10 (`vm1_src` 0) if the ISO7762 rework is done, else `vm1_src` 1 with `vstr_param` = the DL3021 CV setpoint
- [ ] Hall gains settled by the DC check (ch.4 step 2): `hall_mva1` / `hall_mva3` 25 or 100 mV/A, signs A INTO the midpoint, B OUT, saved to `params.yaml`
- [ ] Open loop re-proved at 200 kHz on the bench (`1` + PLAY): 200 ns dead time, 180° interleave on the scope, VM2/(VM2+VM3) ≈ 1−d
- [ ] Over-current latch tested (`C,SET,oc_a,2`, then back to 12), E-stop button (0x04), `C,ESTOP` (0x200) and `C,CLEAR` tested
- [ ] Heatsink DS18B20 taped and reading in Grafana; INA die temperatures plausible
- [ ] E-load: USB to the Pi, `E,STATUS` shows link ok, CV level set (about 3 × Vmp ≈ 61 V, under the 200 W rating), input OFF, LOAD REMOTE
- [ ] 15 A fuse in the string (panel max series fuse 15 A); XT60 polarity checked twice
- [ ] Pi on battery/inverter, Grafana reachable from the laptop, `pod`, `eload`, `params_web` services running (LED blue = idle, safe)
- [ ] Firmware flashed from `7_Pi/firmware/shuffler.bin`; banner shows `fw-0.4.1 … pwm=200000Hz` and the intended `PARAMS_VERSION`; `Push params.yaml` done after the reset (values are RAM-only)

## B. Power-up order

1. Everything off, panels covered or disconnected, e-load input OFF. Pi up, Grafana open. Nucleo on USB: state `IDLE`, faults `0`.
2. Connect the string to the board (XT60_4 string output to the DL3021), uncover panels: `VM1..3` ≈ Voc/3 each, `Vstr` ≈ 75 V, e-load `v` agrees.
3. `3 LOAD ON` (+ PLAY, or second click on the web page): `Vstr` drops to the CV level, string current flows. Still `IDLE`. Record an IDLE baseline.
4. `7 GAINS 30 %`, then `1 OPEN LOOP`: SOFTSTART → RUN_OL at 0.5 duties. Watch `IL*`, temperatures. 2 minutes. `FUNC/STOP`.
5. `2 CLOSED LOOP`: watch `stress`, `beta`, duties off the rails, VM1−VM2 and VM2−VM3 → 0. Raise the gain with VOL+ one step at a time (vref step at each level).

## C. Runs (log the Influx time window of each; the command log panel in Grafana marks every preset)

| # | Condition | Mode | Window (Grafana) | Notes |
|---|---|---|---|---|
| 1 | uniform sun | IDLE (shufflers off) | | baseline |
| 2 | uniform sun | CL | | equalisation at zero mismatch |
| 3 | module 2 shaded 25 % (cardboard) | IDLE | | baseline shaded |
| 4 | module 2 shaded 25 % | CL | | shuffled current, VM equalised? |
| 5 | module 2 shaded 50 % | IDLE / CL | | |
| 6 | module 3 shaded 50 % | IDLE / CL | | end-module case |
| 7 | CL with `C,SET,vref1,1` → `0` step | CL | | step response for the report |

Export each window with `7_Pi/tools/plots.py --start <t0> --stop <t1> --out 3_Analytical/data/runN`.

## D. Shutdown

`FUNC/STOP` (STOP → IDLE), `4 LOAD OFF`, cover/disconnect panels, LED blue, then power off.
Any FAULT during a run: note the `F` line (also in the Grafana command log), `9 CLEAR FAULT` only after the cause is understood.
