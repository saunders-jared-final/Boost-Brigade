#!/usr/bin/env bash
# Flash the Nucleo-G474RE from the Pi over its ST-LINK (SWD), using OpenOCD.
#   tools/flash_nucleo.sh                 flash firmware/shuffler.bin (the staged release)
#   tools/flash_nucleo.sh path/to/x.bin   flash another image (.bin at 0x08000000, or .elf)
#   tools/flash_nucleo.sh --probe         just check that the target answers (voltage, core ID)
# The pod service is stopped during the flash (it owns the ST-LINK virtual COM port) and restarted after.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG="${1:-$HERE/firmware/shuffler.bin}"

OCD=(openocd -f interface/stlink.cfg -f target/stm32g4x.cfg
     -c "reset_config srst_only srst_nogate connect_assert_srst")

restart_pod() { sudo systemctl start pod 2>/dev/null || true; }
sudo systemctl stop pod 2>/dev/null || true
trap restart_pod EXIT

if [ "$IMG" = "--probe" ]; then
  "${OCD[@]}" -c "init; targets; shutdown"
  exit
fi
[ -f "$IMG" ] || { echo "no image: $IMG"; exit 1; }
case "$IMG" in
  *.bin) PROG="program $IMG 0x08000000 verify reset exit" ;;
  *)     PROG="program $IMG verify reset exit" ;;
esac
[ -f "$HERE/firmware/VERSION.txt" ] && cat "$HERE/firmware/VERSION.txt"
"${OCD[@]}" -c "$PROG"
echo "flashed $IMG"
