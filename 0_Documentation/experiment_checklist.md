# Carpark experiment — pre-flight checklist and procedure

Date: ______  Weather / irradiance: ______  Panels: 3 × 150 W (Voc 22.4 V each, 67 V string)

## A. Hardware (tick before the string is connected)

- [ ] U10 isolator (ISO7762) reworked; `VM1` reads correctly on the bench vs DMM (`T` frames, `vm_valid` = 7)
- [ ] Nucleo GND / 3V3 provisioning to the PCB confirmed (schematic note: Nucleo GND pads had no net)
- [ ] Hall calibration done (`C,CAL`) and values in `sensors.c`; signs verified with a DC current:
      A phase positive INTO the midpoint, B phase positive OUT of it
- [ ] Open-loop sign probe (DESIGN_LOG 3.6): `C,MODE,OL1`, `C,DUTYS,0.52,0.48,0.5,0.5` → ILA1+ILB1 strongly negative (circulating), small change in VM1−VM2
- [ ] Dead time 200 ns and 180° interleave seen on the scope at the gates, all four legs
- [ ] Over-current latch tested (lowered `SENSE_OC_LIMIT_A`), E-stop button (PC0) tested, `C,ESTOP` and `C,CLEAR` tested
- [ ] Heatsink DS18B20 taped and reading in Grafana; INA die temperatures plausible
- [ ] **EcoFlow input:** solar port spec 11–60 V, 15 A. 3-panel Voc = 67 V. Decision recorded: ______
      (options: bench-verified it refuses >60 V safely; 2 panels + 1 shuffler; resistor/electronic load)
- [ ] 15 A fuse in the string (panel max series fuse rating 15 A); XT60 polarity checked twice
- [ ] Pi on battery/inverter, Grafana reachable from the laptop, `pod` service running (LED blue = idle, safe)
- [ ] Firmware tag `carpark-v1` flashed; banner shows the intended `PARAMS_VERSION`

## B. Power-up order

1. Everything off, panels covered or disconnected. Pi up, Grafana open. Nucleo powered from USB: state `IDLE`, faults `0`.
2. Connect the string to the board (XT60_4 string output open), uncover panels: `VM1..3` ≈ Voc/3 each, `Vstr` ≈ 67 V.
3. Connect the load (EcoFlow / resistor). `Vstr` drops toward the MPP (~55 V), string current flows. Still `IDLE`.
4. `C,MODE,OL` `C,EN,1`: SOFTSTART → RUN_OL at 0.5 duties. Watch `IL*`, temperatures. 2 minutes.
5. `C,MODE,CL2` (converter 2 only) `C,EN,1`; then `C,MODE,CL`. Watch `stress`, `beta`, duties off the rails.

## C. Runs (log the Influx time window of each)

| # | Condition | Mode | Window (Grafana) | Notes |
|---|---|---|---|---|
| 1 | uniform sun | IDLE (shufflers off) | | baseline |
| 2 | uniform sun | CL | | equalisation at zero mismatch |
| 3 | module 2 shaded 25 % (cardboard) | IDLE | | baseline shaded |
| 4 | module 2 shaded 25 % | CL | | shuffled current, VM equalised? |
| 5 | module 2 shaded 50 % | IDLE / CL | | |
| 6 | module 3 shaded 50 % | IDLE / CL | | end-module case |
| 7 | CL with `C,VREF,1,0` step | CL | | step response for the report |

Export each window with `7_Pi/tools/plots.py --start <t0> --stop <t1> --out 3_Analytical/data/runN`.

## D. Shutdown

`C,EN,0` (STOP → IDLE), cover/disconnect panels, disconnect load, LED blue, then power off.
Any FAULT during a run: note the `F` line, `C,CLEAR` only after the cause is understood.
