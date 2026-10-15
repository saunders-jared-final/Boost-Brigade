#!/usr/bin/env bash
# Build the firmware from WSL with the Windows STM32Cube bundle (no WSL toolchain needed).
#   bash 6_RTOS/build_wsl.sh            -> build/Debug/Shuffler_1_Open_Loop.elf (+ size report)
# Override the bundle location with STM32CUBE_BUNDLES=/mnt/c/Users/<you>/AppData/Local/stm32cube/bundles
set -euo pipefail
B="${STM32CUBE_BUNDLES:-/mnt/c/Users/jazsa/AppData/Local/stm32cube/bundles}"
pick() { ls -d "$B/$1"/*/bin 2>/dev/null | sort -V | tail -1; }
export PATH="$(pick gnu-tools-for-stm32):$(pick ninja):$(pick cmake):$PATH"
cd "$(dirname "${BASH_SOURCE[0]}")"
cmake.exe --preset Debug > /dev/null 2>&1 || cmake.exe --preset Debug
cmake.exe --build --preset Debug 2>&1 | tail -"${1:-25}"
arm-none-eabi-size.exe build/Debug/Shuffler_1_Open_Loop.elf
