#!/usr/bin/env python3
"""Rigol DL3021 electronic load (USB-TMC) -> InfluxDB measurement "eload".

The load is the string load for both the bench and the carpark, so its readings are the
absolute string voltage / current / power the board itself cannot measure (no shunts).
Read-only: the load is set from its front panel; this service only queries it. Any USB query puts
the DL3021 into remote (front panel locked), so after connecting and after every poll the service
de-asserts REN and sends GO_TO_LOCAL (USB488 control requests), which hands the panel back.

  fast (--rate, default 5 Hz): v, i, p          (:MEAS:VOLT? / :MEAS:CURR? / :MEAS:POW?)
  slow (1 Hz):                 mode (CC/CV/CR/CP), input_on, setpoint (of the active mode), link_ok

Transport: the kernel usbtmc driver (/dev/usbtmc*), else pyvisa + pyvisa-py if installed.
The DL3021 ignores those for its own front panel: any query relocks it. To use the panel, pause the
service (no sudo needed; it closes the device and writes paused = 1 until the file is removed):
  touch ~/eload.pause      # pause  -> press Local on the load
  rm ~/eload.pause         # resume logging
Run as a systemd service (eload.service) or by hand:  python3 eload.py [-v] [--rate 5]
Without a load attached it retries every 2 s and writes link_ok = 0.

It also forwards the measured string voltage to the Nucleo as C,SET,vstr_pi,<V> (through the pod's control
socket, at most --fwd-rate per second): with C,SET,vm1_src,2 the firmware computes VM1 = vstr_pi - VM2 - VM3
when U10 (INA CS3) is not available, and trips FLT_VSTR_STALE (0x1000) if the forwarding stops for 2 s."""
from __future__ import annotations

import argparse
import fcntl
import glob
import logging
import os
import time

from pod import Influx
from podlink import PodLink

log = logging.getLogger("eload")

RIGOL_VID = 0x1AB1
MODE_NAMES = {"CC": "CC", "CURR": "CC", "CURRENT": "CC", "CV": "CV", "VOLT": "CV", "VOLTAGE": "CV",
              "CR": "CR", "RES": "CR", "RESISTANCE": "CR", "CP": "CP", "POW": "CP", "POWER": "CP"}
# linux/usb/tmc.h ioctls (USBTMC_IOC_NR = 91): REN_CONTROL = _IOW(91, 19, u8), GOTO_LOCAL = _IO(91, 20)
USBTMC488_IOCTL_REN_CONTROL = 0x40015B13
USBTMC488_IOCTL_GOTO_LOCAL = 0x5B14
PAUSE_FILE = os.path.expanduser("~/eload.pause")   # home dir: 7_Pi/data is root-owned (docker)
SETPOINT_QUERY = {"CC": ":SOUR:CURR:LEV:IMM?", "CV": ":SOUR:VOLT:LEV:IMM?",
                  "CR": ":SOUR:RES:LEV:IMM?", "CP": ":SOUR:POW:LEV:IMM?"}


class UsbTmcDev:
    """Kernel usbtmc character device: one write per command, one read per answer."""

    def __init__(self, path: str):
        self.path = path
        self.fd = os.open(path, os.O_RDWR)

    def query(self, cmd: str) -> str:
        os.write(self.fd, (cmd + "\n").encode())
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
        self.inst = rm.open_resource(res[0], timeout=2000, read_termination="\n", write_termination="\n")

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
    """First instrument that answers *IDN? with a DL30xx; None if there is none."""
    for path in sorted(glob.glob("/dev/usbtmc*")):
        try:
            dev = UsbTmcDev(path)
            idn = dev.query("*IDN?")
            if "DL30" in idn.upper():
                log.info("e-load: %s on %s", idn, path)
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
        return float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=5.0, help="v/i/p samples per second")
    ap.add_argument("--fwd-rate", type=float, default=2.0, help="C,SET,vstr_pi forwards per second (0 = off)")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.v else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    influx = Influx()
    pod = PodLink() if a.fwd_rate > 0 else None
    t_fwd = 0.0
    tags = {"source": "dl3021"}
    period = 1.0 / a.rate
    dev = None
    t_slow = 0.0
    mode = "?"
    while True:
        if os.path.exists(PAUSE_FILE):
            if dev is not None:
                log.info("paused (%s): front panel free", os.path.normpath(PAUSE_FILE))
                dev.release()
                dev.close()
                dev = None
            influx.write("eload", {"paused": True}, tags)
            time.sleep(1.0)
            continue
        if dev is None:
            dev = open_load()
            if dev is None:
                influx.write("eload", {"link_ok": False}, tags)
                time.sleep(2.0)
                continue
        t0 = time.time()
        try:
            fields = {"v": as_float(dev.query(":MEAS:VOLT?")),
                      "i": as_float(dev.query(":MEAS:CURR?")),
                      "p": as_float(dev.query(":MEAS:POW?"))}
            if t0 - t_slow >= 1.0:
                t_slow = t0
                mode = MODE_NAMES.get(dev.query(":SOUR:FUNC?").upper(), "?")
                fields["mode"] = mode
                fields["input_on"] = dev.query(":SOUR:INP:STAT?") in ("1", "ON")
                if mode in SETPOINT_QUERY:
                    fields["setpoint"] = as_float(dev.query(SETPOINT_QUERY[mode]))
                fields["link_ok"] = True
                fields["paused"] = False
            dev.release()
            influx.write("eload", fields, tags)
            v = fields["v"]
            if pod is not None and v == v and 0.0 < v < 150.0 and t0 - t_fwd >= 1.0 / a.fwd_rate:
                t_fwd = t0
                pod.send(f"C,SET,vstr_pi,{v:.3f}")
        except Exception as e:  # noqa: BLE001  (OSError from usbtmc, VisaIOError from pyvisa)
            log.warning("e-load lost (%s), reconnecting", e)
            try:
                dev.close()
            except Exception:  # noqa: BLE001
                pass
            dev = None
            continue
        time.sleep(max(0.0, period - (time.time() - t0)))


if __name__ == "__main__":
    main()
