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

## Setup (Raspberry Pi OS 64-bit)

```sh
sudo apt install -y docker.io docker-compose-plugin python3-pip ir-keytable
sudo usermod -aG docker,dialout,input,gpio,i2c pi
pip3 install -r pod/requirements.txt
# /boot/firmware/config.txt: dtoverlay=gpio-ir,gpio_pin=17   dtoverlay=w1-gpio,gpiopin=4   dtparam=i2c_arm=on
cd 7_Pi && docker compose up -d           # Grafana at http://<pi>:3000 (admin / shuffler)
python3 pod/pod.py --port /dev/ttyACM0 -v # first run by hand; then: sudo cp pod/pod.service /etc/systemd/system && sudo systemctl enable --now pod
```
First milestone: `heatsink_c` on the dashboard within a minute of boot (no Nucleo needed).
Then plug the Nucleo (ST-LINK VCP = `/dev/ttyACM0`): `T` frames at 50 Hz appear as `telemetry` fields.

IR: run `sudo ir-keytable -t` once, press the remote's buttons, map the key names in `IR_MAP`
(pod.py). Defaults: POWER = disable, PLAY = enable, STOP = E-stop, OK = clear fault, 1–6 = modes,
LEFT/RIGHT = cycle modes.

LED: blue = idle and string < 10 V (safe to touch), amber = idle but live, green = switching,
red = fault, magenta = no Nucleo link. The pod sends `C,ESTOP` itself if the heatsink passes 80 °C.
