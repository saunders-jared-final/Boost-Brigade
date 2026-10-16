#!/usr/bin/env python3
"""Send commands to the Nucleo through the running pod service (it owns the serial port), and to the
Rigol DL3021 through the eload service (E,... lines go to its control socket and print the answer).
Over SSH on the Pi:
    python3 podctl.py C,TEST,0              one command, print what comes back for --wait seconds
    python3 podctl.py C,MODE,OL C,EN,1      several, in order
    python3 podctl.py E,STATUS              e-load status (JSON); E,INPUT,0|1  E,MODE,CV  E,SET,CV,70  E,LOCAL  E,REMOTE
    python3 podctl.py                       interactive: type C,... / E,... lines, `q` quits
T frames are echoed once per second; --quiet-t hides them."""
import argparse
import socket
import sys
import threading
import time

CTL = ("127.0.0.1", 5017)
ELOAD = ("127.0.0.1", 5018)


def eload_cmd(line: str):
    try:
        with socket.create_connection(ELOAD, timeout=10) as e:
            e.sendall((line + "\n").encode())
            print(e.makefile().readline().rstrip(), flush=True)
    except OSError as err:
        print(f"eload service not reachable on {ELOAD[0]}:{ELOAD[1]} ({err}); systemctl status eload", flush=True)


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
            if c.startswith("E,"):
                eload_cmd(c)
                continue
            s.sendall((c + "\n").encode())
            time.sleep(0.3)
        time.sleep(a.wait)
        return
    for line in sys.stdin:
        line = line.strip()
        if line == "q":
            break
        if line.startswith("E,"):
            eload_cmd(line)
        elif line:
            s.sendall((line + "\n").encode())


if __name__ == "__main__":
    main()
