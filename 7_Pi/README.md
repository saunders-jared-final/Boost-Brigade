# 7_Pi — Raspberry Pi 4B pod

Telemetry and UI only; the Pi is never in the control loop.

```
docker-compose.yml        InfluxDB 2.7 (:8086) + Grafana 11 (:3000, anonymous viewer) with a provisioned
                          datasource and the "Shuffler pod" dashboard (grafana/dashboards/shuffler.json)
pod/pod.py                serial bridge (Nucleo T/S/F frames -> Influx), DS18B20 heatsink probe,
                          IR remote -> commands, LCD + RGB status; pod.service for systemd
pod/telemetry_parser.py   the frame parser (field order from 0_Documentation/telemetry.md)
tools/nucleo_cli.py       interactive console for the bench (type C,... commands)
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
(admin / shuffler), logs `journalctl -u pod -f`. Without a Nucleo or sensors the pod still runs.

## Reflashing the Nucleo from the Pi

The Pi flashes over the Nucleo's own ST-LINK (USB, SWD) with OpenOCD; the same cable carries the telemetry.
```sh
~/Boost-Brigade/7_Pi/tools/flash_nucleo.sh --probe      # does the target answer? (no write)
~/Boost-Brigade/7_Pi/tools/flash_nucleo.sh              # flash firmware/shuffler.bin (version in firmware/VERSION.txt)
~/Boost-Brigade/7_Pi/tools/flash_nucleo.sh other.bin    # any other image
```
It stops `pod` during the flash and restarts it after. New firmware: `stage_firmware.sh` on the dev machine, sync, flash.
Open-loop test cases (`C,TEST,0..3`) can be typed with `python3 tools/nucleo_cli.py --port /dev/ttyACM0`.

First milestone: `heatsink_c` on the dashboard within a minute of boot (no Nucleo needed).
Then plug the Nucleo (ST-LINK VCP = `/dev/ttyACM0`): `T` frames at 50 Hz appear as `telemetry` fields.

IR: run `sudo ir-keytable -t` once, press the remote's buttons, map the key names in `IR_MAP`
(pod.py). Defaults: POWER = disable, PLAY = enable, STOP = E-stop, OK = clear fault, 1–6 = modes,
LEFT/RIGHT = cycle modes.

LED: blue = idle and string < 10 V (safe to touch), amber = idle but live, green = switching,
red = fault, magenta = no Nucleo link. The pod sends `C,ESTOP` itself if the heatsink passes 80 °C.
