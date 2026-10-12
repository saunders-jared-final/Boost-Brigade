#!/usr/bin/env bash
# One-shot Pi setup (Raspberry Pi OS 64-bit, run as the normal user, not root):  bash 7_Pi/deploy/setup.sh
# Idempotent. Installs docker + compose, python deps in a venv, OpenOCD (to flash the Nucleo),
# enables the I2C / 1-wire / IR overlays, installs + starts the pod service, starts InfluxDB + Grafana.
set -euo pipefail

PI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
U="$(id -un)"
[ "$U" != root ] || { echo "run as your normal user (it uses sudo where needed)"; exit 1; }

echo "== apt packages"
sudo apt-get update
sudo apt-get install -y git rsync openocd docker.io ir-keytable python3-venv python3-pip \
  python3-gpiozero python3-lgpio python3-serial python3-smbus2 python3-evdev
# compose: the package name differs between Raspberry Pi OS releases
for p in docker-compose-v2 docker-compose-plugin docker-compose; do
  if apt-cache show "$p" >/dev/null 2>&1 && sudo apt-get install -y "$p"; then break; fi
done
if docker compose version >/dev/null 2>&1; then COMPOSE="docker compose"
elif command -v docker-compose >/dev/null; then COMPOSE="docker-compose"
else echo "no docker compose available"; exit 1; fi

echo "== groups (serial, GPIO, I2C, IR, docker)"
sudo usermod -aG docker,dialout,input,gpio,i2c,plugdev "$U" || true

echo "== python venv"
python3 -m venv --system-site-packages "$PI_DIR/.venv"
"$PI_DIR/.venv/bin/pip" install -r "$PI_DIR/pod/requirements.txt"

echo "== ST-LINK udev rule (flash without sudo)"
sudo tee /etc/udev/rules.d/49-stlink.rules >/dev/null <<'RULE'
SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="374[8-9a-f]|375[0-9a-f]", MODE="0666", TAG+="uaccess"
RULE
sudo udevadm control --reload-rules && sudo udevadm trigger

echo "== boot overlays (I2C LCD, DS18B20, IR receiver)"
CFG=/boot/firmware/config.txt; [ -f "$CFG" ] || CFG=/boot/config.txt
for l in "dtparam=i2c_arm=on" "dtoverlay=w1-gpio,gpiopin=4" "dtoverlay=gpio-ir,gpio_pin=17"; do
  grep -qxF "$l" "$CFG" || echo "$l" | sudo tee -a "$CFG" >/dev/null
done

echo "== pod service (user $U, $PI_DIR)"
sed -e "s|@USER@|$U|g" -e "s|@PI_DIR@|$PI_DIR|g" "$PI_DIR/pod/pod.service" | sudo tee /etc/systemd/system/pod.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now pod

echo "== InfluxDB + Grafana"
cd "$PI_DIR"
# Grafana runs as uid 472; a bind-mount dir docker creates is root-owned and Grafana restart-loops on it
mkdir -p data/grafana data/influxdb
sudo chown -R 472:0 data/grafana
sudo $COMPOSE up -d

cat <<MSG

Done. Log out and back in once (new groups), and reboot if the overlays were just added.
  Grafana  http://$(hostname -I | awk '{print $1}'):3000   (admin / shuffler, anonymous viewer on)
  Logs     journalctl -u pod -f
  Flash    $PI_DIR/tools/flash_nucleo.sh
MSG
