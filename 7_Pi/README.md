# 7_Pi — Raspberry Pi 4B pod

Telemetry and UI only; the Pi is never in the control loop.

```
docker-compose.yml        InfluxDB 2.7 (:8086) + Grafana 11 (:3000, anonymous viewer) with a provisioned
                          datasource and the "Shuffler pod" dashboard (grafana/dashboards/shuffler.json)
pod/pod.py                serial bridge (Nucleo T/S/F/#/A/P lines -> Influx telemetry/status/fault/note/cmd/params),
                          DS18B20 heatsink probe, IR remote -> LCD menu + presets, LCD + RGB status; pod.service
pod/eload.py              Rigol DL3021 e-load over USB (USB-TMC) -> Influx measurement "eload" (v, i, p at 5 Hz; mode,
                          input, all four levels, ranges, QUES register, errors at 1 Hz) and the e-load control socket
                          127.0.0.1:5018 (E,INPUT / E,MODE / E,SET / E,LOCAL / E,REMOTE / E,STATUS); eload.service
pod/params_web.py         control + parameter web page on :8080 (presets, e-load panel, run-time parameters, params.yaml)
pod/actions.py            the operator presets (remote digits = web buttons = cheat sheet)
pod/remote.py             Elegoo IR remote -> LCD menu, status pages, preset execution
pod/podlink.py            clients for the two sockets: PodLink (Nucleo via the pod), EloadLink (e-load service)
pod/telemetry_parser.py   the frame parser (field order from 0_Documentation/telemetry.md)
tools/podctl.py           send C,... (Nucleo, through the pod) and E,... (e-load) commands over SSH
tools/nucleo_cli.py       interactive console straight on the serial port (only with the pod stopped)
tools/ident.py            bench identification cross-check -> G, M (optionally into shuffler_params.json)
tools/plots.py            Influx window -> CSV + PNG plots for the report
```

## Deploy to a fresh Pi (Raspberry Pi OS 64-bit)

Only `7_Pi/` goes on the Pi (code + the staged Nucleo firmware, ~100 kB).

```sh
# from the dev machine (WSL), no git needed on the Pi:
bash 7_Pi/deploy/stage_firmware.sh                 # optional: rebuild 6_RTOS and refresh 7_Pi/firmware/shuffler.bin
bash 7_Pi/deploy/sync.sh <user>@<pi-address>       # rsync 7_Pi -> ~/Boost-Brigade/7_Pi on the Pi
# or on the Pi: git clone --filter=blob:none --sparse <repo-url> Boost-Brigade && cd Boost-Brigade && git sparse-checkout set 7_Pi

# then on the Pi:
bash ~/Boost-Brigade/7_Pi/deploy/setup.sh          # apt deps, docker, venv, OpenOCD + udev, overlays, pod service, Influx+Grafana
```
Log out/in once (new groups) and reboot if the overlays were just added. Grafana `http://<pi>:3000`
(admin / `GRAFANA_PASSWORD` from `7_Pi/.env`; copy `.env.example` first), logs `journalctl -u pod -f`. Without a Nucleo or sensors the pod still runs.

## Reflashing the Nucleo from the Pi

The Pi flashes over the Nucleo's own ST-LINK (USB, SWD) with OpenOCD; the same cable carries the telemetry.
```sh
~/Boost-Brigade/7_Pi/tools/flash_nucleo.sh --probe      # does the target answer? (no write)
~/Boost-Brigade/7_Pi/tools/flash_nucleo.sh              # flash firmware/shuffler.bin (version in firmware/VERSION.txt)
~/Boost-Brigade/7_Pi/tools/flash_nucleo.sh other.bin    # any other image
```
It stops `pod` during the flash and restarts it after. New firmware: `stage_firmware.sh` on the dev machine, sync, flash.
Commands over SSH while the pod runs (the venv has the deps: `~/Boost-Brigade/7_Pi/.venv/bin/python`):
```sh
python3 ~/Boost-Brigade/7_Pi/tools/podctl.py C,TEST,0          # IC init check, prints the # INIT lines
python3 ~/Boost-Brigade/7_Pi/tools/podctl.py C,MODE,OL C,EN,1  # both shufflers open loop (0.5 duties), start
python3 ~/Boost-Brigade/7_Pi/tools/podctl.py C,EN,0            # stop
python3 ~/Boost-Brigade/7_Pi/tools/podctl.py E,STATUS          # e-load status (JSON)
python3 ~/Boost-Brigade/7_Pi/tools/podctl.py E,SET,CV,70 E,INPUT,1   # e-load: CV level 70 V, input on
python3 ~/Boost-Brigade/7_Pi/tools/podctl.py                   # interactive (C,... and E,... lines)
```
The pod runs `C,TEST,0` by itself whenever the Nucleo link comes up (`--no-init` turns that off).
The two shufflers are hard-wired together on the Version 0 board, so the presets only offer the both-shuffler
modes (`OL`, `CL`); `OL1/OL2/CL1/CL2` and `C,TEST,1..3` still exist in the firmware for the terminal.

First milestone: `heatsink_c` on the dashboard within a minute of boot (no Nucleo needed).
Then plug the Nucleo (ST-LINK VCP = `/dev/ttyACM0`): `T` frames at 50 Hz appear as `telemetry` fields.

E-load: plug the DL3021's rear USB (device) port into the Pi; `ls /dev/usbtmc*` should show it
(setup.sh adds the udev rule). `journalctl -u eload -f` logs the `*IDN?` on connect. The dashboard's
e-load row shows link / local-remote / mode / input / levels / V I P (power at the DL3021's 200 W rating),
the e-load voltage is overlaid on the String voltage panel as a cross-check of the INA sum, and the active
setpoint is dashed on the e-load V/I panel. Control: presets `3 LOAD ON`, `4 LOAD OFF`, `5 LOAD REMOTE`,
`6 LOAD LOCAL` (remote digits, web buttons), mode + level from the web page's e-load panel or
`podctl.py E,...`. Any USB query locks the front panel for a moment, so to work on the panel choose
`LOAD LOCAL` (logging and the `vstr_pi` forward pause, `paused = 1` in Influx) and `LOAD REMOTE` after.

IR (Elegoo NEC remote, `deploy/elegoo.toml`, `pod/remote.py`): POWER = E-stop, FUNC/STOP = stop switching,
digits = jump to a preset, arrows = move in the menu, PLAY = run the highlighted preset, VOL± = gain scale
±0.1, EQ = next status page, ST/REPT = back to status. Presets (`pod/actions.py`): 0 init check, 1 open
loop, 2 closed loop, 3 load on, 4 load off, 5 load remote, 6 load local, 7 gains 30 %, 8 gains 100 %,
9 clear fault, then STOP and MODE IDLE at the end of the list. Nothing starts without PLAY.

LCD: after an init check, `INIT PASS` or `INIT FAIL<n> S2 OK|NO` (S2 OK = everything the bottom shuffler
needs passed: SPI bus, U11/U12, ILA_2/ILB_2, E-stop, no fault) over checkboxes `SPI INA HAL ES` for those
items. Once a mode is selected: the mode (`BOTH CL`, `IDLE`, ... + fault code), alternating every 3 s
between checkboxes `S1 S2 SW FL` (shufflers selected, switching, fault) and the module voltages. EQ
cycles pages 0 mode, 1 voltages, 2 state/gain, 3 network address, 4 e-load (`LOAD CV ON  REM` / V I P).

LED: blue = idle and every readable module < 10 V (safe to touch), amber = idle but live or voltages unreadable, green = switching,
red = fault, magenta = no Nucleo link. The pod sends `C,ESTOP` itself if the heatsink passes 80 °C.
