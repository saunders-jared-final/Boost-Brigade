# Nucleo ↔ Pi telemetry and command contract

One ASCII line per message over the ST-LINK virtual COM port (LPUART1, PA2/PA3),
**921600 baud, 8N1**, `\n` terminated. Fields are comma separated, no spaces.
The same parser is used by the Pi bridge (`7_Pi/pod`), the bench identification
script (`7_Pi/tools/ident.py`) and the plotting tools, so this file is the only
place the format is defined. Firmware constant: `TELEMETRY_PROTOCOL_VERSION 1`.

## Telemetry frame `T` — Nucleo → Pi, 50 Hz

```
T,<ms>,<state>,<fault>,<VM1>,<VM2>,<VM3>,<ILA1>,<ILB1>,<ILA2>,<ILB2>,<dA1>,<dB1>,<dA2>,<dB2>,<rv1>,<rv2>,<beta>,<stress>,<IM1r>,<IM2r>,<T1>,<T2>,<T3>,<pver>
```

| Field | Unit | Meaning |
|---|---|---|
| `ms` | ms | firmware uptime (HAL tick) |
| `state` | enum | `BOOT, SELFTEST, IDLE, SOFTSTART, RUN_OL, RUN_CL, RUN_OL1, RUN_CL1, RUN_OL2, RUN_CL2, STOP, FAULT` (string) |
| `fault` | hex | fault bitmask, `0` when none: 0x01 OC latch, 0x02 OC hardware (COMP), 0x04 E-stop, 0x08 bus OV, 0x10 bus UV, 0x20 sensor zero-cal, 0x40 INA bus blocked / absent, 0x80 over-temperature (Pi-reported), 0x100 watchdog reset |
| `VM1..VM3` | V | module voltages (VM3 = U12, VM2 = U11−U12, VM1 = U10−(U11−U12)); `nan` when not readable |
| `ILA1,ILB1,ILA2,ILB2` | A | phase inductor currents, positive INTO the converter midpoint |
| `dA1..dB2` | – | applied duties |
| `rv1,rv2` | V | supervisor relaxation references |
| `beta`, `stress` | – | supervisor governor gain and stress index |
| `IM1r,IM2r` | A | reconstructed module currents relative to module 3 |
| `T1..T3` | °C | INA239 die temperatures |
| `pver` | str | `PARAMS_VERSION` of the gains in flash |

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
C,EN,<0|1>                               enable / disable switching (1 = SOFTSTART into the requested mode)
C,DUTY,<leg 0..3>,<d 0.05..0.95>         open-loop duty for one leg (OL modes only)
C,DUTYS,<dA1>,<dB1>,<dA2>,<dB2>          all four duties at once (OL modes only)
C,VREF,<rv1>,<rv2>                       manual Vref offsets for the controller (CL modes)
C,GAIN,<preset 0..3>                     select a gain preset if the firmware carries several
C,ESTOP                                  software E-stop: outputs off, FAULT latched
C,CLEAR                                  clear a latched fault (only from FAULT, outputs stay off)
C,PING                                   answered with S line
```

The Nucleo answers every command with `A,<cmd>,<OK|ERR>,<reason>`.

Leg numbering: 0 = S1 A (PA8/PA9, HRTIM TA), 1 = S1 B (PA10/PA11, TB),
2 = S2 A (PB12/PB13, TC), 3 = S2 B (PB14/PB15, TD). Modes `*1` run converter 1
only (S1, legs 0–1), `*2` converter 2 only (S2, legs 2–3).

## Pi-side measurements (not from the Nucleo)

`pod` adds `heatsink_c` (DS18B20 on GPIO4) and writes everything to InfluxDB
bucket `shuffler`, measurement `telemetry`, tags `source=nucleo|pi`, `mode`.
