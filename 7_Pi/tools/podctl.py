#!/usr/bin/env python3
"""Send commands to the Nucleo through the running pod service (it owns the serial port).
Over SSH on the Pi:
    python3 podctl.py C,TEST,0              one command, print what comes back for --wait seconds
    python3 podctl.py C,TEST,1 C,EN,1       several, in order
    python3 podctl.py                       interactive: type C,... lines, `q` quits
T frames are echoed once per second; --quiet-t hides them."""
import argparse
import socket
import sys
import threading
import time

CTL = ("127.0.0.1", 5017)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmds", nargs="*")
    ap.add_argument("--wait", type=float, default=3.0, help="seconds to listen after the last command")
    ap.add_argument("--quiet-t", action="store_true")
    a = ap.parse_args()
    try:
        s = socket.create_connection(CTL, timeout=3)
    except OSError as e:
        sys.exit(f"pod not reachable on {CTL[0]}:{CTL[1]} ({e}); is it running? systemctl status pod")
    s.settimeout(None)

    def rx():
        buf = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                t = line.decode(errors="replace").rstrip()
                if a.quiet_t and t.startswith("T,"):
                    continue
                print(t, flush=True)

    threading.Thread(target=rx, daemon=True).start()
    if a.cmds:
        for c in a.cmds:
            s.sendall((c + "\n").encode())
            time.sleep(0.3)
        time.sleep(a.wait)
        return
    for line in sys.stdin:
        line = line.strip()
        if line == "q":
            break
        if line:
            s.sendall((line + "\n").encode())


if __name__ == "__main__":
    main()
