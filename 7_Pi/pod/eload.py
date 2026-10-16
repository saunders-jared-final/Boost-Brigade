#!/usr/bin/env python3
"""Rigol DL3021 electronic load (USB-TMC): logger -> InfluxDB measurement "eload", and the pod's e-load
control socket (127.0.0.1:5018).

The load is the string load for both the bench and the carpark, so its readings are the absolute string
voltage / current / power the board itself cannot measure (no shunts). This service owns the USB link; every
other program (web page, IR remote, podctl) goes through the control socket, one line per command:

  E,STATUS                 -> A,STATUS,OK,{json}  cached readings + settings (never touches the USB)
  E,INPUT,0|1              load input off / on          (ON is the only e-load command that starts power flow)
  E,MODE,CC|CV|CR|CP       select the function          (refused while the input is on)
  E,SET,CC|CV|CR|CP,<v>    level of that function       (bounds in LIMITS; takes effect at once, input on or off)
  E,LOCAL                  front panel to the operator: polling, forwarding and control pause (paused = 1)
  E,REMOTE                 polling + control from here again
  answers: A,<CMD>,OK[,<info>] | A,<CMD>,ERR,<reason>

Logged to Influx (tag source=dl3021):
  fast (--rate, default 5 Hz): v, i, p                        (:MEAS:VOLT? / :MEAS:CURR? / :MEAS:POW?)
  slow (1 Hz): mode (CC/CV/CR/CP), input_on, setpoint (active mode), set_cc / set_cv / set_cr / set_cp,
               r (:MEAS:RES?), range_i, range_v, ques (:STAT:QUES:COND? raw register), err (last SCPI error,
               only when there is one), link_ok, paused
  every command through the socket -> measurement "cmd" (tags source=eload, dir=tx) with its answer

Any USB query puts the DL3021 into remote (front panel locked), so after every poll and command the service
de-asserts REN and sends GO_TO_LOCAL (USB488 control requests), which hands the panel back between polls. To
work on the front panel without the 5 Hz interruptions use E,LOCAL (preset 6 on the remote / web page), or:
  touch ~/eload.pause      # same as E,LOCAL           rm ~/eload.pause      # same as E,REMOTE
Transport: the kernel usbtmc driver (/dev/usbtmc*), else pyvisa + pyvisa-py if installed.
Run as a systemd service (eload.service) or by hand:  python3 eload.py [-v] [--rate 5]
Without a load attached it retries every 2 s, writes link_ok = 0 and answers ERR,no e-load link.

It also forwards the measured string voltage to the Nucleo as C,SET,vstr_pi,<V> (through the pod's control
socket, at most --fwd-rate per second): with C,SET,vm1_src,2 the firmware computes VM1 = vstr_pi - VM2 - VM3
when U10 (INA CS3) is not available, and trips FLT_VSTR_STALE (0x1000) if the forwarding stops for 2 s.
E,LOCAL stops the forwarding too: in closed loop use vm1_src 0 (U10) or 1 (vstr_param) while local."""
from __future__ import annotations

import argparse
import fcntl
import glob
import json
import logging
import math
import os
import queue
import socket
import sys
import threading
import time

from pod import Influx
from podlink import ELOAD_CTL, PodLink

log = logging.getLogger("eload")

RIGOL_VID = 0x1AB1
MODE_NAMES = {"CC": "CC", "CURR": "CC", "CURRENT": "CC", "CV": "CV", "VOLT": "CV", "VOLTAGE": "CV",
              "CR": "CR", "RES": "CR", "RESISTANCE": "CR", "CP": "CP", "POW": "CP", "POWER": "CP"}
FUNC_CMD = {"CC": "CURR", "CV": "VOLT", "CR": "RES", "CP": "POW"}   # :SOUR:FUNC argument = level subsystem
# bounds this service accepts for E,SET (the DL3021 itself allows 150 V / 40 A / 200 W):
LIMITS = {"CC": (0.0, 15.0, "A"),       # 15 A string fuse; panels Isc 4.35 A, firmware oc_a <= 12 A
          "CV": (0.0, 150.0, "V"),      # 3 x KAUSSP80 Voc = 75.2 V, firmware vstr_ov default 85 V
          "CR": (0.05, 15000.0, "ohm"),
          "CP": (0.0, 200.0, "W")}      # the DL3021 rating
# linux/usb/tmc.h ioctls (USBTMC_IOC_NR = 91): SET_TIMEOUT = _IOW(91, 14, u32) ms, REN_CONTROL = _IOW(91, 19, u8),
# GOTO_LOCAL = _IO(91, 20)
USBTMC_IOCTL_SET_TIMEOUT = 0x40045B0E
USBTMC488_IOCTL_REN_CONTROL = 0x40015B13
USBTMC488_IOCTL_GOTO_LOCAL = 0x5B14
USB_TIMEOUT_MS = 1500            # bounds the cost of a query the load's firmware does not know (default is 5 s)
PAUSE_FILE = os.path.expanduser("~/eload.pause")   # home dir: 7_Pi/data is root-owned (docker)
CMD_TIMEOUT_S = 8.0


class UsbTmcDev:
    """Kernel usbtmc character device: one write per command, one read per answer."""

    def __init__(self, path: str):
        self.path = path
        self.fd = os.open(path, os.O_RDWR)
        try:
            fcntl.ioctl(self.fd, USBTMC_IOCTL_SET_TIMEOUT, USB_TIMEOUT_MS.to_bytes(4, sys.byteorder))
        except OSError as e:
            log.debug("usbtmc timeout ioctl: %s", e)

    def write(self, cmd: str):
        os.write(self.fd, (cmd + "\n").encode())

    def query(self, cmd: str) -> str:
        self.write(cmd)
        return os.read(self.fd, 4096).decode(errors="replace").strip()

    def release(self):
        """Front panel back to the user (REN off + go to local); harmless if unsupported."""
        try:
            fcntl.ioctl(self.fd, USBTMC488_IOCTL_REN_CONTROL, bytes((0,)))
            fcntl.ioctl(self.fd, USBTMC488_IOCTL_GOTO_LOCAL)
        except OSError as e:
            log.debug("go-to-local: %s", e)

    def close(self):
        os.close(self.fd)


class VisaDev:
    """Fallback when the usbtmc module is not loaded: pyvisa over pyvisa-py (libusb)."""

    def __init__(self):
        import pyvisa
        rm = pyvisa.ResourceManager("@py")
        # resource names carry the vendor id in hex or decimal: USB0::0x1AB1::... or USB0::6833::...
        res = [r for r in rm.list_resources()
               if f"::0x{RIGOL_VID:04x}::" in r.lower() or f"::{RIGOL_VID}::" in r]
        if not res:
            raise OSError("no Rigol USB-TMC resource")
        self.path = res[0]
        self.inst = rm.open_resource(res[0], timeout=USB_TIMEOUT_MS, read_termination="\n", write_termination="\n")

    def write(self, cmd: str):
        self.inst.write(cmd)

    def query(self, cmd: str) -> str:
        return self.inst.query(cmd).strip()

    def release(self):
        try:
            from pyvisa.constants import RENLineOperation
            self.inst.control_ren(RENLineOperation.deassert_gtl)
        except Exception as e:  # noqa: BLE001
            log.debug("go-to-local: %s", e)

    def close(self):
        self.inst.close()


def open_load():
    """First instrument that answers *IDN? with a DL30xx (its idn is kept on the object); None if there is none."""
    for path in sorted(glob.glob("/dev/usbtmc*")):
        try:
            dev = UsbTmcDev(path)
            idn = dev.query("*IDN?")
            if "DL30" in idn.upper():
                log.info("e-load: %s on %s", idn, path)
                dev.idn = idn
                dev.release()
                return dev
            log.debug("%s is not a DL30xx (%s)", path, idn)
            dev.close()
        except OSError as e:
            log.debug("%s: %s", path, e)
    try:
        dev = VisaDev()
        idn = dev.query("*IDN?")
        if "DL30" in idn.upper():
            log.info("e-load: %s via pyvisa %s", idn, dev.path)
            dev.idn = idn
            dev.release()
            return dev
        dev.close()
    except Exception as e:  # noqa: BLE001  (pyvisa missing, no backend, no device)
        log.debug("pyvisa: %s", e)
    return None


def as_float(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return math.nan


def paused() -> bool:
    return os.path.exists(PAUSE_FILE)


class Load:
    """Owns the USB device. Everything that touches it runs on the main thread; the control socket's threads only
    queue (line, reply queue) pairs, which the main loop answers between polls."""

    def __init__(self, influx: Influx, pod: PodLink | None, rate: float, fwd_rate: float):
        self.influx, self.pod = influx, pod
        self.period, self.fwd_rate = 1.0 / rate, fwd_rate
        self.dev = None
        self.idn = ""
        self.unsupported: set[str] = set()   # queries this load's firmware answered with nothing (per connection)
        self.cache: dict = {}                # last readings and settings, served by E,STATUS
        self.t_fast = self.t_slow = self.t_fwd = 0.0
        self.cmds: queue.Queue = queue.Queue()
        self.tags = {"source": "dl3021"}
        self.was_paused: bool | None = None

    # ------------------------------------------------------------ device ---
    def connect(self) -> bool:
        if self.dev is not None:
            return True
        self.dev = open_load()
        if self.dev is None:
            return False
        self.idn = self.dev.idn
        self.unsupported.clear()
        self.cache.update(link_ok=True)
        self.influx.write("note", {"line": f"e-load connected: {self.idn} ({self.dev.path})"}, {"source": "eload"})
        return True

    def drop(self, why):
        log.warning("e-load lost (%s), reconnecting", why)
        try:
            self.dev.close()
        except Exception:  # noqa: BLE001
            pass
        self.dev = None
        self.cache.update(link_ok=False)
        self.influx.write("eload", {"link_ok": False}, self.tags)

    def q(self, cmd: str) -> str:
        """Required query: any failure means the link is gone (caller drops the device)."""
        return self.dev.query(cmd)

    def q_opt(self, cmd: str) -> str | None:
        """Optional query: a load firmware without the command answers nothing; skipped from then on."""
        if cmd in self.unsupported:
            return None
        try:
            return self.dev.query(cmd)
        except Exception as e:  # noqa: BLE001  (OSError timeout from usbtmc, VisaIOError from pyvisa)
            log.info("%s: no answer (%s), not asked again on this connection", cmd, e)
            self.unsupported.add(cmd)
            return None

    def q_optf(self, cmd: str) -> float:
        s = self.q_opt(cmd)
        return math.nan if s is None else as_float(s)

    # ------------------------------------------------------------- polls ---
    def poll_fast(self, now: float) -> dict:
        f = {"v": as_float(self.q(":MEAS:VOLT?")), "i": as_float(self.q(":MEAS:CURR?")),
             "p": as_float(self.q(":MEAS:POW?"))}
        self.t_fast = now
        self.cache.update(f)
        return f

    def poll_slow(self) -> dict:
        mode = MODE_NAMES.get(self.q(":SOUR:FUNC?").upper(), "?")
        f = {"mode": mode, "input_on": self.q(":SOUR:INP:STAT?").upper() in ("1", "ON"),
             "link_ok": True, "paused": False}
        for m, sub in FUNC_CMD.items():
            f[f"set_{m.lower()}"] = self.q_optf(f":SOUR:{sub}:LEV:IMM?")
        if mode in FUNC_CMD:
            f["setpoint"] = f[f"set_{mode.lower()}"]
        f["r"] = self.q_optf(":MEAS:RES?")
        f["range_i"] = self.q_optf(":SOUR:CURR:RANG?")
        f["range_v"] = self.q_optf(":SOUR:VOLT:RANG?")
        f["ques"] = self.q_optf(":STAT:QUES:COND?")
        err = self.q_opt(":SYST:ERR?")
        if err and not err.startswith("0,") and not err.startswith("+0,"):
            f["err"] = err
            log.warning("DL3021 error: %s", err)
        self.cache.update(f)
        return f

    def slow_cycle(self):
        """One settings poll now (after a command, or when the load is paused and a command changed it)."""
        self.t_slow = time.time()
        f = self.poll_slow()
        f["paused"] = paused()
        self.dev.release()
        self.influx.write("eload", f, self.tags)

    def status(self) -> dict:
        now = time.time()
        c = {k: (None if isinstance(v, float) and v != v else v) for k, v in self.cache.items()}
        c.update(link_ok=self.dev is not None, paused=paused(), idn=self.idn,
                 age=round(now - self.t_fast, 1) if self.t_fast else None,
                 limits={m: [lo, hi, u] for m, (lo, hi, u) in LIMITS.items()})
        return c

    # ---------------------------------------------------------- commands ---
    def exec(self, line: str) -> str:
        p = line.strip().split(",")
        if len(p) < 2 or p[0] != "E":
            return "A,?,ERR,expected E,<cmd>,..."
        cmd = p[1].upper()
        if cmd == "STATUS":
            return "A,STATUS,OK," + json.dumps(self.status())
        if cmd == "LOCAL":
            open(PAUSE_FILE, "a").close()
            if self.dev is not None:
                try:
                    self.dev.write(":SYST:LOC")
                    self.dev.release()
                except Exception as e:  # noqa: BLE001
                    self.drop(e)
            ans = "A,LOCAL,OK,front panel free; logging and vstr_pi forwarding paused"
        elif cmd == "REMOTE":
            try:
                os.remove(PAUSE_FILE)
            except FileNotFoundError:
                pass
            self.t_slow = 0.0
            ans = "A,REMOTE,OK,logging and control from the pod"
        elif cmd in ("INPUT", "MODE", "SET"):
            ans = self._ctl(cmd, p[2:])
        else:
            ans = f"A,{cmd},ERR,unknown command (STATUS INPUT MODE SET LOCAL REMOTE)"
        self.influx.write("cmd", {"line": line.strip(), "answer": ans[:200]}, {"source": "eload", "dir": "tx"})
        (log.info if ",OK" in ans else log.warning)("%s -> %s", line.strip(), ans)
        return ans

    def _ctl(self, cmd: str, args: list[str]) -> str:
        if not self.connect():
            return f"A,{cmd},ERR,no e-load link (USB)"
        try:
            if cmd == "INPUT":
                if len(args) < 1 or args[0] not in ("0", "1"):
                    return "A,INPUT,ERR,E,INPUT,0|1"
                self.dev.write(f":SOUR:INP:STAT {args[0]}")
                on = self.q(":SOUR:INP:STAT?").upper() in ("1", "ON")
                if on != (args[0] == "1"):
                    self.slow_cycle()
                    return "A,INPUT,ERR,input did not change (protection tripped? check the panel)"
                info = "input " + ("ON" if on else "OFF")
            elif cmd == "MODE":
                m = args[0].upper() if args else ""
                if m not in FUNC_CMD:
                    return "A,MODE,ERR,E,MODE,CC|CV|CR|CP"
                if self.q(":SOUR:INP:STAT?").upper() in ("1", "ON"):
                    return "A,MODE,ERR,turn the input off first (E,INPUT,0)"
                self.dev.write(f":SOUR:FUNC {FUNC_CMD[m]}")
                got = MODE_NAMES.get(self.q(":SOUR:FUNC?").upper(), "?")
                if got != m:
                    return f"A,MODE,ERR,mode is {got}"
                info = f"mode {m}"
            else:  # SET
                m = args[0].upper() if args else ""
                if m not in LIMITS or len(args) < 2:
                    return "A,SET,ERR,E,SET,CC|CV|CR|CP,<value>"
                v = as_float(args[1])
                lo, hi, unit = LIMITS[m]
                if not lo <= v <= hi:
                    return f"A,SET,ERR,{m} level {lo:g}..{hi:g} {unit}"
                self.dev.write(f":SOUR:{FUNC_CMD[m]}:LEV:IMM {v:.5g}")
                got = as_float(self.q(f":SOUR:{FUNC_CMD[m]}:LEV:IMM?"))
                if not abs(got - v) <= 0.01 * max(1.0, abs(v)):
                    self.slow_cycle()
                    return f"A,SET,ERR,readback {got:g} {unit} (outside the load's range?)"
                info = f"{m} {got:g} {unit}"
            self.slow_cycle()      # settings into Influx and the cache right away (also while paused)
            return f"A,{cmd},OK,{info}"
        except Exception as e:  # noqa: BLE001
            self.drop(e)
            return f"A,{cmd},ERR,e-load link lost ({e})"

    def serve(self, block_s: float):
        """Answer queued commands; waits up to block_s for the first one (this is the loop's sleep)."""
        try:
            line, reply = self.cmds.get(timeout=block_s)
        except queue.Empty:
            return
        while True:
            reply.put(self.exec(line))
            try:
                line, reply = self.cmds.get_nowait()
            except queue.Empty:
                return

    # -------------------------------------------------------------- loop ---
    def run(self):
        while True:
            self.serve(0.0)
            now = time.time()
            if paused():
                if self.was_paused is not True:
                    log.info("paused (%s): front panel free", os.path.normpath(PAUSE_FILE))
                    self.was_paused = True
                    if self.dev is not None:
                        self.dev.release()
                if now - self.t_slow >= 1.0:
                    self.t_slow = now
                    self.cache["paused"] = True
                    self.influx.write("eload", {"paused": True, "link_ok": self.dev is not None}, self.tags)
                self.serve(0.2)
                continue
            if self.was_paused is not False:
                if self.was_paused:
                    log.info("resumed: logging + control")
                self.was_paused = False
                self.cache["paused"] = False
            if not self.connect():
                if now - self.t_slow >= 2.0:
                    self.t_slow = now
                    self.influx.write("eload", {"link_ok": False, "paused": False}, self.tags)
                self.serve(2.0)
                continue
            try:
                fields = self.poll_fast(now)
                if now - self.t_slow >= 1.0:
                    self.t_slow = now
                    fields.update(self.poll_slow())
                self.dev.release()
                self.influx.write("eload", fields, self.tags)
                v = fields["v"]
                if self.pod is not None and v == v and 0.0 < v < 150.0 and now - self.t_fwd >= 1.0 / self.fwd_rate:
                    self.t_fwd = now
                    self.pod.send(f"C,SET,vstr_pi,{v:.3f}")
            except Exception as e:  # noqa: BLE001  (OSError from usbtmc, VisaIOError from pyvisa)
                self.drop(e)
                continue
            self.serve(max(0.0, self.period - (time.time() - now)))


def ctl_server(load: Load):
    """127.0.0.1:5018: one E,... line per command, one A,... line back (podlink.EloadLink is the client)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(ELOAD_CTL)
    except OSError as e:
        log.error("control socket %s:%d: %s (another eload.py running?)", ELOAD_CTL[0], ELOAD_CTL[1], e)
        os._exit(1)
    srv.listen(8)
    log.info("control socket: %s:%d", *ELOAD_CTL)

    def client(c: socket.socket):
        buf = b""
        c.settimeout(60.0)
        try:
            while True:
                chunk = c.recv(256)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    t = line.decode(errors="replace").strip()
                    if not t:
                        continue
                    reply: queue.Queue = queue.Queue()
                    load.cmds.put((t, reply))
                    try:
                        ans = reply.get(timeout=CMD_TIMEOUT_S)
                    except queue.Empty:
                        ans = "A,?,ERR,eload service busy (USB stalled?)"
                    c.sendall((ans + "\n").encode())
        except OSError:
            pass
        c.close()

    while True:
        c, _ = srv.accept()
        threading.Thread(target=client, args=(c,), daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=5.0, help="v/i/p samples per second")
    ap.add_argument("--fwd-rate", type=float, default=2.0, help="C,SET,vstr_pi forwards per second (0 = off)")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.v else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    load = Load(Influx(), PodLink() if a.fwd_rate > 0 else None, a.rate, a.fwd_rate)
    threading.Thread(target=ctl_server, args=(load,), daemon=True).start()
    load.run()


if __name__ == "__main__":
    main()
