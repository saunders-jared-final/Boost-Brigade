#!/usr/bin/env bash
# Build the firmware from WSL with the Windows STM32Cube bundle (no WSL toolchain needed).
#   bash 6_RTOS/build_wsl.sh            -> build/$PRESET/Shuffler_1_Open_Loop.elf (+ size report); PRESET=Release (default, -O2) or Debug (-O0: ISR too slow for 300 kHz)
# Override the bundle location with STM32CUBE_BUNDLES=/mnt/c/Users/<you>/AppData/Local/stm32cube/bundles
set -euo pipefail
B="${STM32CUBE_BUNDLES:-/mnt/c/Users/jazsa/AppData/Local/stm32cube/bundles}"
pick() { ls -d "$B/$1"/*/bin 2>/dev/null | sort -V | tail -1; }
export PATH="$(pick gnu-tools-for-stm32):$(pick ninja):$(pick cmake):$PATH"
export WSLENV="${WSLENV:-}:PATH/l"      # cmake.exe resolves the ARM compiler through the Windows PATH
cd "$(dirname "${BASH_SOURCE[0]}")"
PRESET="${PRESET:-Release}"
cmake.exe --preset "$PRESET" > /dev/null 2>&1 || cmake.exe --preset "$PRESET"
cmake.exe --build --preset "$PRESET" 2>&1 | tail -"${1:-25}"
arm-none-eabi-size.exe "build/$PRESET/Shuffler_1_Open_Loop.elf"
