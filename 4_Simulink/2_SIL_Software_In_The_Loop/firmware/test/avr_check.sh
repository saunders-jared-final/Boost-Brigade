#!/bin/sh
# Compile-only check of core/ + sil/ under avr-gcc for the ATmega328P (PIL
# target). No linking, no upload - just proof the code is AVR-clean:
# 16-bit int, 32-bit double, no hosted-library dependencies.
#
# Usage: test/avr_check.sh [path-to-avr-gcc]   (run from firmware/)
# Exit codes: 0 pass, 1 compile failure, 2 toolchain missing (ctest SKIP).
set -e
AVR_GCC="${1:-avr-gcc}"
command -v "$AVR_GCC" >/dev/null 2>&1 || {
    echo "avr_check: SKIP - $AVR_GCC not found (install gcc-avr or pass its path)" >&2
    exit 2
}
# avr-gcc >= 10 can be configured with 64-bit double; pin the ATmega-native
# 32-bit double when the flag exists so this check matches the PIL target.
DBLFLAG=""
if "$AVR_GCC" -mmcu=atmega328p -mdouble=32 -E -x c /dev/null >/dev/null 2>&1; then
    DBLFLAG="-mdouble=32"
fi
TMPDIR="${TMPDIR:-/tmp}/shuf_avr_check.$$"
mkdir -p "$TMPDIR"
trap 'rm -rf "$TMPDIR"' EXIT
CORE=../../../6_RTOS/ctrl_core
for f in $CORE/shuffler_ctrl.c $CORE/shuffler_supervisor.c $CORE/shuffler_mppt.c $CORE/shuffler_recon.c \
         $CORE/stack.c sil/sil_wrappers.c; do
    echo "avr-gcc $DBLFLAG -c $f"
    "$AVR_GCC" -mmcu=atmega328p $DBLFLAG -Os -std=c99 -Wall -Wextra -Werror \
        -I$CORE -Isil -c "$f" -o "$TMPDIR/$(basename "$f").o" || exit 1
done
echo "avr_check: PASS (compile-only, atmega328p)"
