# Nucleo ↔ Pi telemetry and command contract

One ASCII line per message over the ST-LINK virtual COM port (LPUART1, PA2/PA3),
**921600 baud, 8N1**, `\n` terminated. Fields are comma separated, no spaces.
The same parser is used by the Pi bridge (`7_Pi/pod`), the bench identification
script (`7_Pi/tools/ident.py`) and the plotting tools, so this file is the only
place the format is defined. Firmware constant: `COMMS_PROTOCOL_VERSION 2` (fw 0.3.0; protocol 1
frames, without `kscale,pset`, are still accepted by `telemetry_parser.py`).

## Telemetry frame `T` — Nucleo → Pi, 50 Hz

```
T,<ms>,<state>,<fault>,<VM1>,<VM2>,<VM3>,<ILA1>,<ILB1>,<ILA2>,<ILB2>,<dA1>,<dB1>,<dA2>,<dB2>,<rv1>,<rv2>,<beta>,<stress>,<IM1r>,<IM2r>,<T1>,<T2>,<T3>,<kscale>,<pset>,<pver>
```

| Field | Unit | Meaning |
|---|---|---|
| `ms` | ms | firmware uptime (HAL tick) |
| `state` | enum | `BOOT, SELFTEST, IDLE, SOFTSTART, RUN_OL, RUN_CL, RUN_OL1, RUN_CL1, RUN_OL2, RUN_CL2, STOP, FAULT` (string) |
| `fault` | hex | fault bitmask, `0` when none: 0x01 OC latch (hall tick average > `oc_a` for 2 ms, ADC rail, or hall sampling DMA stalled), 0x02 OC hardware (COMP, not implemented yet), 0x04 E-stop, 0x08 module OV (`vm_ov`), 0x10 module UV (`vm_uv`, closed loop), 0x20 sensor zero-cal, 0x40 INA bus blocked / VM not readable for the mode, 0x80 over-temperature (INA die > 85 °C; the Pi sends `C,ESTOP` for the heatsink), 0x100 watchdog reset, 0x200 software E-stop, 0x400 string OV (`vstr_ov`), 0x800 comms watchdog (closed loop, no command for `wdg_s`), 0x1000 VM1 source stale (`vm1_src`=2 and no `vstr_pi` for 2 s) |
| `VM1..VM3` | V | module voltages (VM3 = U12, VM2 = U11−U12; VM1 = U10−(U11−U12) for `vm1_src`=0, `vstr_param`−U11 for 1, `vstr_pi`−U11 for 2); `nan` when not readable |
| `ILA1,ILB1,ILA2,ILB2` | A | phase inductor currents in the control-stack convention: A positive INTO the converter midpoint, B positive OUT of it (ILA+ILB = circulating, ILA−ILB = shuffled) |
| `dA1..dB2` | – | applied duties |
| `rv1,rv2` | V | supervisor relaxation references |
| `beta`, `stress` | – | supervisor governor gain and stress index |
| `IM1r,IM2r` | A | reconstructed module currents relative to module 3 |
| `T1..T3` | °C | INA239 die temperatures |
| `kscale` | – | gain scale of the active controller gain set (boot default 0.3) |
| `pset` | – | gain-set counter: +1 on every `C,APPLY` swap (0 = the boot set) |
| `pver` | str | `PARAMS_VERSION` of the gains compiled into flash (the base M before `kscale` / `C,SETM`) |

Values are `%.4g` floats. Field count is fixed for a protocol version; a Pi
parser should match on the header count and ignore trailing extras.

## Status line `S` — Nucleo → Pi, on every state change and every 1 s

```
S,<ms>,<state>,<fault>,<mode_requested>,<fw_version>,<pver>
```

## Fault detail `F` — Nucleo → Pi, once when a fault latches

```
F,<ms>,<code>,<channel>,<value>,<raw>
```

## Commands `C` — Pi → Nucleo

```
C,MODE,<IDLE|OL|CL|OL1|CL1|OL2|CL2>     request a run mode (goes through SOFTSTART)
C,TEST,<0..3>                            bench test case: 0 = IC init check (no switching, prints `# INIT` lines, ERR if any IC fails),
                                         1 = bottom shuffler S2 (OL2), 2 = top shuffler S1 (OL1), 3 = both (OL); 1..3 select only, then C,EN,1
C,EN,<0|1>                               enable / disable switching (1 = SOFTSTART into the requested mode)
C,DUTY,<leg 0..3>,<d 0.05..0.95>         open-loop duty for one leg (OL modes only)
C,DUTYS,<dA1>,<dB1>,<dA2>,<dB2>          all four duties at once (OL modes only)
C,VREF,<rv1>,<rv2>                       manual Vref offsets for the controller (CL modes)
C,SUP,<0|1>                              supervisor (feasibility governor) on / off (= C,SET,sup_en)
C,CAL,<ch 0..3>,<mV/A>,<zero code|0>     hall calibration (= C,SET,hall_mva<ch> [+ hall_zero<ch>])
C,SET,<name>,<value>                     set one run-time parameter (bounds and class: C,LIST)
C,SETM,<m00>,<m01>,...,<m33>             the 16 entries of the base M, row-major (STAGED)
C,GET,<name>                             -> P,<name>,<value>
C,LIST                                   -> one P,<name>,<value>,<min>,<max>,<LIVE|IDLE|STAGED> line per parameter
C,APPLY                                  validate the staged gain set and swap it in at the next control tick (bumpless)
C,REVERT                                 every parameter back to its boot default + APPLY (refused while switching)
C,GAIN                                   retired: answers ERR, use SET/SETM/APPLY
C,ESTOP                                  software E-stop: outputs off, FAULT latched
C,CLEAR                                  clear a latched fault (only from FAULT, outputs stay off)
C,PING                                   answered with S line; the pod sends it every 1 s (comms watchdog heartbeat)
```

Any well-formed `C,...` line feeds the closed-loop comms watchdog. Lines are at most 255 characters.

### Run-time parameters (`6_RTOS/App/params_rt.c`, `7_Pi/pod/params.yaml`, page `http://<pi>:8080`)

Classes: **LIVE** takes effect at once; **IDLE** is refused while switching; **STAGED** is collected and swapped
by `C,APPLY` at a control-tick boundary, integrators rebased on the applied duties (`xi = Minv·u_act`) so the
duties do not jump. Effective gains: `M_eff = kscale·M`, `Mp = M_eff·diag(kp_v,kp_v,kp_i,kp_i)`,
`Minv = inv(M_eff)` (MCU Gauss-Jordan, rejected if singular or |M·Minv−I| > 1e-3), `a = 2πfcTs/(1+2πfcTs)`.

| Name | Default | Bounds | Class | Meaning |
|---|---|---|---|---|
| `kscale` | 0.3 | 0.05–1 | STAGED | scales the whole PI (closed-loop bandwidth) |
| `kp_v`, `kp_i` | 1.58e-4, 1.08e-4 s | 0–0.01 | STAGED | P/I ratios, voltage / current channels |
| `fc_lpf` | 2000 Hz | 100–4000 | STAGED | controller measurement LPF corner |
| `dmin`, `dmax` | 0.05, 0.95 | 0.05–0.45, 0.55–0.95 | STAGED | controller duty clamp |
| `m00`..`m33` | params.h | ±1000 | STAGED | base M (also `C,SETM`) |
| `sup_en` | 1 | 0–1 | LIVE | governor on |
| `sup_i_rated`, `sup_s_hi`, `sup_s_lo` | 10 A, 0.9, 0.7 | 1–12, 0.3–1, 0.1–0.95 | LIVE | governor stress scale and thresholds |
| `vref1`, `vref2` | 0 | ±30 V | LIVE | manual offsets (= `C,VREF`) |
| `hall_mva0..3` | 100, 25, 100, 25 | ±400, \|x\| ≥ 10 | LIVE | hall gain mV/A (sign = orientation) |
| `hall_zero0..3` | boot zero-cal | 1800–2300 | IDLE | ADC zero code |
| `oc_a` | 12 A | 0.5–12 | LIVE | OC latch threshold (tick average, 2 ms) |
| `vm_ov`, `vm_uv` | 30 V, 3 V | 5–32, 0–20 | LIVE | per-module envelope (UV in closed loop only) |
| `vstr_ov` | 85 V | 10–96 | LIVE | string OV (sum of readable VMs, and `vstr_pi` when `vm1_src`=2) |
| `vm1_src` | 0 | 0–2 | IDLE | VM1 from U10 (0), `vstr_param` (1), `vstr_pi` (2) |
| `vstr_param` | 70 V | 0–150 | LIVE | string voltage for `vm1_src`=1 (the DL3021 CV setpoint) |
| `vstr_pi` | – | 0–150 | LIVE | pushed by `eload.py` at 2 Hz (DL3021 readback); stale after 2 s |
| `slew` | 0.01 | 0.0005–0.2 | LIVE | closed-loop duty slew limit per 100 µs tick |
| `wdg_s` | 5 s | 0–60 | LIVE | closed-loop comms watchdog (0 = off; needs the pod's 1 Hz `C,PING`) |

The Nucleo answers every command with `A,<cmd>,<OK|ERR>,<reason>`.

Leg numbering: 0 = S1 A (PA8/PA9, HRTIM TA), 1 = S1 B (PA10/PA11, TB),
2 = S2 A (PB12/PB13, TC), 3 = S2 B (PB14/PB15, TD). Modes `*1` run converter 1
only (S1, legs 0–1), `*2` converter 2 only (S2, legs 2–3).

## Pi-side measurements (not from the Nucleo)

`pod` adds `heatsink_c` (DS18B20 on GPIO4) and writes everything to InfluxDB
bucket `shuffler`, measurement `telemetry`, tags `source=nucleo|pi`, `mode`.
Also: measurement `eload` (`eload` service, tag `source=dl3021`: `v`, `i`, `p` at 5 Hz = absolute
string voltage / current / power at the Rigol DL3021; at 1 Hz `mode` (CC/CV/CR/CP), `input_on`,
`setpoint` of the active mode, `link_ok`), measurement `pod` (1 Hz: `mode`, `view`, `s1_active`, `s2_active`, `switching`, `fault_active`,
`link_ok`) and measurement `init` (one point per `# INIT RESULT`: one 0/1 field per `# INIT` item,
`result_pass`, `fails`, `s2_ready`). Commands from other Pi tools go through the pod's control socket
127.0.0.1:5017 (`7_Pi/tools/podctl.py`); the pod sends them one byte every 2 ms.
