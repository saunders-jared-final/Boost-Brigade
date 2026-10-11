#!/usr/bin/env python3
"""Talk to the Nucleo by hand from a laptop or the Pi:
    python3 nucleo_cli.py --port COM5            (Windows)   or /dev/ttyACM0
Type commands (C,MODE,OL ...); frames print as they arrive. `q` quits."""
import argparse
import sys
import threading

import serial

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "pod"))
from telemetry_parser import parse_line  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--all", action="store_true", help="print every T frame (default: 1 per second)")
    a = ap.parse_args()
    ser = serial.Serial(a.port, a.baud, timeout=0.2)

    def rx():
        n = 0
        buf = b""
        while True:
            buf += ser.read(256)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                s = line.decode(errors="replace").strip()
                fr = parse_line(s)
                if fr is None or fr.kind != "T":
                    print(s)
                else:
                    n += 1
                    if a.all or n % 50 == 0:
                        v = fr.values
                        print(f"T {fr.ms/1000:8.2f}s {fr.state:9s} F{fr.fault:03x} VM={v['VM1']:.2f},{v['VM2']:.2f},{v['VM3']:.2f} "
                              f"IL={v['ILA1']:+.2f},{v['ILB1']:+.2f},{v['ILA2']:+.2f},{v['ILB2']:+.2f} "
                              f"d={v['dA1']:.3f},{v['dB1']:.3f},{v['dA2']:.3f},{v['dB2']:.3f} beta={v['beta']:.2f} stress={v['stress']:.2f}")

    threading.Thread(target=rx, daemon=True).start()
    for line in sys.stdin:
        line = line.strip()
        if line == "q":
            break
        if line:
            ser.write((line + "\n").encode())


if __name__ == "__main__":
    main()
