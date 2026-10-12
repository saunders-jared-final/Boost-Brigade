#!/usr/bin/env python3
"""Shuffler pod service: Nucleo serial <-> InfluxDB, DS18B20 heatsink probe,
IR remote -> commands, LCD + RGB LED status. Run as a systemd service
(pod.service) or by hand: python3 pod.py --port /dev/ttyACM0

Everything optional degrades gracefully: no Influx -> log to stdout, no LCD ->
skip, no IR device -> skip. Nothing here is in the control loop (Pi = telemetry
+ UI only, by design)."""
from __future__ import annotations

import argparse
import glob
import logging
import os
import queue
import threading
import time

import serial

from telemetry_parser import parse_line

log = logging.getLogger("pod")

INFLUX_URL = os.environ.get("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "shuffler-pod-token")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "boost")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "shuffler")

# IR remote key -> Nucleo command (edit after `ir-keytable -t` shows your remote's codes)
IR_MAP = {
    "KEY_POWER": ["C,EN,0"],
    "KEY_PLAY": ["C,EN,1"],
    "KEY_STOP": ["C,ESTOP"],
    "KEY_OK": ["C,CLEAR"],
    "KEY_1": ["C,MODE,OL"], "KEY_2": ["C,MODE,CL"],
    "KEY_3": ["C,MODE,OL1"], "KEY_4": ["C,MODE,CL1"],
    "KEY_5": ["C,MODE,OL2"], "KEY_6": ["C,MODE,CL2"],
    "KEY_0": ["C,MODE,IDLE"],
}
MODE_CYCLE = ["IDLE", "OL", "CL", "OL1", "CL1", "OL2", "CL2"]


class Influx:
    def __init__(self):
        self.api = None
        try:
            from influxdb_client import InfluxDBClient, Point
            from influxdb_client.client.write_api import SYNCHRONOUS
            self._Point = Point
            self.client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
            self.api = self.client.write_api(write_options=SYNCHRONOUS)
            log.info("influx: %s bucket %s", INFLUX_URL, INFLUX_BUCKET)
        except Exception as e:  # noqa: BLE001
            log.warning("influx unavailable (%s): logging to stdout", e)

    def write(self, measurement: str, fields: dict, tags: dict | None = None):
        if self.api is None:
            log.debug("%s %s %s", measurement, tags, fields)
            return
        p = self._Point(measurement)
        for k, v in (tags or {}).items():
            p = p.tag(k, v)
        for k, v in fields.items():
            if isinstance(v, (int, float)) and v == v:  # drop NaN
                p = p.field(k, float(v))
            elif isinstance(v, str):
                p = p.field(k, v)
        try:
            self.api.write(bucket=INFLUX_BUCKET, record=p)
        except Exception as e:  # noqa: BLE001
            log.warning("influx write failed: %s", e)


class Nucleo:
    """Serial link; frames go to on_frame, commands are queued and answered."""

    def __init__(self, port: str, baud: int, on_frame):
        self.port, self.baud = port, baud
        self.ser = None  # opened (and re-opened) by _rx so the pod runs without a Nucleo
        self.on_frame = on_frame
        self.tx = queue.Queue()
        self.last_state = "?"
        self.last_fault = 0
        self.alive = 0.0
        threading.Thread(target=self._rx, daemon=True).start()
        threading.Thread(target=self._txloop, daemon=True).start()

    def send(self, cmd: str):
        self.tx.put(cmd)

    def _txloop(self):
        while True:
            cmd = self.tx.get()
            if self.ser is None:
                log.warning("-> %s dropped: no Nucleo link", cmd)
                continue
            try:
                self.ser.write((cmd.strip() + "\n").encode())
                log.info("-> %s", cmd)
            except (serial.SerialException, OSError) as e:
                log.warning("-> %s failed: %s", cmd, e)

    def _open(self):
        while self.ser is None:
            try:
                self.ser = serial.Serial(self.port, self.baud, timeout=0.2)
                log.info("serial: %s open", self.port)
            except (serial.SerialException, OSError) as e:
                log.debug("serial: %s not available (%s)", self.port, e)
                time.sleep(2.0)

    def _rx(self):
        buf = b""
        self._open()
        while True:
            try:
                chunk = self.ser.read(256)
            except (serial.SerialException, OSError) as e:
                log.warning("serial: %s lost (%s), reconnecting", self.port, e)
                self.ser, buf = None, b""
                self._open()
                continue
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                fr = parse_line(line.decode(errors="replace"))
                if fr is None:
                    continue
                self.alive = time.time()
                if fr.kind in ("T", "S"):
                    self.last_state, self.last_fault = fr.state, fr.fault
                if fr.kind == "A":
                    log.info("<- %s", fr.raw)
                self.on_frame(fr)


def read_ds18b20() -> float | None:
    for path in glob.glob("/sys/bus/w1/devices/28-*/temperature"):
        try:
            with open(path) as f:
                return int(f.read().strip()) / 1000.0
        except (OSError, ValueError):
            pass
    return None


class Ui:
    """RGB LED (GPIO 12/13/19) + I2C LCD (0x27 / 0x3F). Colour = safety state."""

    def __init__(self):
        self.led = None
        self.lcd = None
        try:
            from gpiozero import RGBLED
            self.led = RGBLED(12, 13, 19)
        except Exception as e:  # noqa: BLE001
            log.warning("no RGB LED: %s", e)
        try:
            from lcd import Lcd
            self.lcd = Lcd()
        except Exception as e:  # noqa: BLE001
            log.warning("no LCD: %s", e)

    def show(self, state: str, fault: int, vstr: float, temp: float | None, link_ok: bool):
        if self.led:
            if not link_ok:
                self.led.color = (1, 0, 1)        # magenta: no Nucleo link
            elif state == "FAULT" or fault:
                self.led.color = (1, 0, 0)        # red: faulted / not safe
            elif state.startswith("RUN") or state == "SOFTSTART":
                self.led.color = (0, 1, 0)        # green: switching
            elif vstr == vstr and vstr > 10.0:
                self.led.color = (1, 0.4, 0)      # amber: idle but string live
            else:
                self.led.color = (0, 0, 1)        # blue: idle, safe to touch (string < 10 V)
        if self.lcd:
            l1 = f"{state:<9}F{fault:03x}" if link_ok else "NO LINK"
            l2 = f"{vstr:5.1f}V {temp if temp is not None else float('nan'):4.1f}C"
            self.lcd.write(l1[:16], l2[:16])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--no-ir", action="store_true")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.v else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    influx = Influx()
    ui = Ui()
    latest = {"vstr": float("nan")}

    def on_frame(fr):
        if fr.kind == "T":
            latest["vstr"] = fr.values.get("Vstr", float("nan"))
            fields = {k: v for k, v in fr.values.items() if k != "pver"}
            fields["fault"] = float(fr.fault)
            influx.write("telemetry", fields, {"source": "nucleo", "state": fr.state, "pver": fr.values.get("pver", "")})
        elif fr.kind == "S":
            influx.write("status", {"state_code": float(fr.values and 1), "fault": float(fr.fault)},
                         {"source": "nucleo", "state": fr.state, "mode": fr.values.get("mode", "")})
        elif fr.kind == "F":
            influx.write("fault", {"code": float(fr.fault), "value": fr.values["value"]},
                         {"source": "nucleo", "channel": fr.values["channel"]})
            log.error("FAULT %s", fr.raw)

    nucleo = Nucleo(a.port, a.baud, on_frame)
    nucleo.send("C,PING")

    if not a.no_ir:
        threading.Thread(target=ir_loop, args=(nucleo,), daemon=True).start()

    t_last = 0.0
    temp = None
    while True:
        now = time.time()
        if now - t_last >= 1.0:
            t_last = now
            temp = read_ds18b20()
            if temp is not None:
                influx.write("telemetry", {"heatsink_c": temp}, {"source": "pi"})
                if temp > 80.0:
                    nucleo.send("C,ESTOP")
                    log.error("heatsink %.1f C: E-stop sent", temp)
        link_ok = (now - nucleo.alive) < 2.0
        ui.show(nucleo.last_state, nucleo.last_fault, latest["vstr"], temp, link_ok)
        time.sleep(0.2)


def ir_loop(nucleo: Nucleo):
    """gpio-ir overlay (dtoverlay=gpio-ir,gpio_pin=17) + ir-keytable -> /dev/input/event*."""
    try:
        import evdev
    except ImportError:
        log.warning("evdev missing: IR disabled")
        return
    dev = None
    for path in evdev.list_devices():
        d = evdev.InputDevice(path)
        if "gpio_ir" in d.name.lower() or "ir" in d.name.lower():
            dev = d
            break
    if dev is None:
        log.warning("no IR input device")
        return
    log.info("IR: %s", dev.name)
    mode_idx = 0
    for ev in dev.read_loop():
        if ev.type != evdev.ecodes.EV_KEY or ev.value != 1:
            continue
        key = evdev.ecodes.KEY[ev.code]
        if key == "KEY_RIGHT":
            mode_idx = (mode_idx + 1) % len(MODE_CYCLE)
            nucleo.send(f"C,MODE,{MODE_CYCLE[mode_idx]}")
        elif key == "KEY_LEFT":
            mode_idx = (mode_idx - 1) % len(MODE_CYCLE)
            nucleo.send(f"C,MODE,{MODE_CYCLE[mode_idx]}")
        else:
            for cmd in IR_MAP.get(key, []):
                nucleo.send(cmd)


if __name__ == "__main__":
    main()
