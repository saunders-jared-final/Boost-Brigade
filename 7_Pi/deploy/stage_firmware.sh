#!/usr/bin/env bash
# DEV MACHINE (WSL): build the firmware and stage it where the Pi can flash it from.
#   bash 7_Pi/deploy/stage_firmware.sh   then commit 7_Pi/firmware/ (or run sync.sh)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
B="${LOCALAPPDATA_WSL:-/mnt/c/Users/$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r')/AppData/Local}/stm32cube/bundles"
OBJCOPY="$(ls "$B"/gnu-tools-for-stm32/*/bin/arm-none-eabi-objcopy.exe | tail -1)"
GNU="$(dirname "$OBJCOPY")"; NINJA="$(ls -d "$B"/ninja/*/bin | tail -1)"
export PATH="$PATH:$GNU:$NINJA"            # cmake.exe resolves the ARM compiler through the Windows PATH
export WSLENV="${WSLENV:-}:PATH/l"
cd "$ROOT/6_RTOS"
cmake.exe --preset Debug >/dev/null
cmake.exe --build --preset Debug
"$OBJCOPY" -O binary build/Debug/Shuffler_1_Open_Loop.elf "$(wslpath -w "$ROOT/7_Pi/firmware")\\shuffler.bin"
{
  echo "firmware: $(grep -o 'shuffler-fw-[0-9.]*' App/comms.h | head -1)  built $(date -u +%Y-%m-%dT%H:%MZ)"
  echo "git: $(git -C "$ROOT" rev-parse --short HEAD)$(git -C "$ROOT" diff --quiet -- 6_RTOS || echo '+dirty')"
  echo "sha256: $(sha256sum "$ROOT/7_Pi/firmware/shuffler.bin" | cut -d' ' -f1)"
} > "$ROOT/7_Pi/firmware/VERSION.txt"
cat "$ROOT/7_Pi/firmware/VERSION.txt"
