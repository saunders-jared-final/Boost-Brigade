#!/usr/bin/env python3
"""Shuffler pod service: Nucleo serial <-> InfluxDB, DS18B20 heatsink probe,
IR remote -> commands, LCD + RGB LED status. Run as a systemd service
(pod.service) or by hand: python3 pod.py --port /dev/ttyACM0

The pod owns the Nucleo's serial port, so other tools talk to the Nucleo through
it: a line-based TCP socket on 127.0.0.1:5017 (tools/podctl.py). Every line a
client sends is forwarded as a command; every non-T line from the Nucleo (plus
one T frame per second) is copied back to all clients.

Everything optional degrades gracefully: no Influx -> log to stdout, no LCD ->
skip, no IR device -> skip. Nothing here is in the control loop (Pi = telemetry
+ UI only, by design)."""
from __future__ import annotations

import argparse
import glob
import logging
import math
import os
import queue
import re
import socket
import struct
import threading
import time

import serial

from telemetry_parser import parse_line

log = logging.getLogger("pod")

INFLUX_URL = os.environ.get("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "shuffler-pod-token")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "boost")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "shuffler")
CTL_PORT = 5017
TX_CHAR_GAP_S = 0.002   # the firmware drops bytes of a back-to-back line at 921600 (one RX IRQ per byte)

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

# LCD line 1 per requested mode (16 chars max, fault code is appended in cols 13-16)
MODE_TEXT = {"IDLE": "IDLE", "OL": "BOTH OL", "CL": "BOTH CL", "OL1": "S1 TOP OL", "CL1": "S1 TOP CL",
             "OL2": "S2 BOTTOM OL", "CL2": "S2 BOTTOM CL"}
S1_MODES = {"OL", "CL", "OL1", "CL1"}
S2_MODES = {"OL", "CL", "OL2", "CL2"}
# init-check items the bottom shuffler (S2, modules 2-3) needs; U10 (INA CS3) and the S1 halls are not among them
S2_NEEDS = ["SPI3 bus", "INA CS1", "INA CS2", "ILA_2", "ILB_2", "E-stop", "firmware"]
INIT_RE = re.compile(r"^# INIT (.+?)\s+(PASS|FAIL)\s+(.*)$")
INIT_RESULT_RE = re.compile(r"^# INIT RESULT: (PASS|FAIL) \((\d+) failing\)")


class Influx:
    def __init__(self):
        self.api = None
        try:
            from influxdb_client import InfluxDBClient, Point, WriteOptions
            self._Point = Point
            self.client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
            # batched + background flush: a slow Influx never stalls the serial reader
            self.api = self.client.write_api(write_options=WriteOptions(batch_size=200, flush_interval=500))
            log.info("influx: %s bucket %s", INFLUX_URL, INFLUX_BUCKET)
        except Exception as e:  # noqa: BLE001
            log.warning("influx unavailable (%s): logging to stdout", e)

    def write(self, measurement: str, fields: dict, tags: dict | None = None):
        if self.api is None:
            log.debug("%s %s %s", measurement, tags, fields)
            return
        # stamp at receive time: batched points without a time all get the flush time and overwrite each other
        p = self._Point(measurement).time(time.time_ns())
        for k, v in (tags or {}).items():
            p = p.tag(k, v)
        n = 0
        for k, v in fields.items():
            if isinstance(v, bool):
                p, n = p.field(k, float(v)), n + 1
            elif isinstance(v, (int, float)) and v == v:  # drop NaN
                p, n = p.field(k, float(v)), n + 1
            elif isinstance(v, str):
                p, n = p.field(k, v), n + 1
        if n == 0:
            return
        try:
            self.api.write(bucket=INFLUX_BUCKET, record=p)
        except Exception as e:  # noqa: BLE001
            log.warning("influx write failed: %s", e)


class CtlServer:
    """127.0.0.1:CTL_PORT, one line per command in, Nucleo lines out (tools/podctl.py)."""

    def __init__(self, nucleo: "Nucleo"):
        self.nucleo = nucleo
        self.clients: list[socket.socket] = []
        self.lock = threading.Lock()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", CTL_PORT))
        srv.listen(4)
        log.info("control socket: 127.0.0.1:%d", CTL_PORT)
        while True:
            c, _ = srv.accept()
            # a client that stops reading must not stall the serial rx thread: 1 s send timeout, then dropped
            c.setsockopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO, struct.pack("ll", 1, 0))
            with self.lock:
                self.clients.append(c)
            threading.Thread(target=self._client, args=(c,), daemon=True).start()

    def _client(self, c: socket.socket):
        buf = b""
        try:
            while True:
                chunk = c.recv(256)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    cmd = line.decode(errors="replace").strip()
                    if cmd:
                        self.nucleo.send(cmd)
        except OSError:
            pass
        with self.lock:
            if c in self.clients:
                self.clients.remove(c)
        c.close()

    def broadcast(self, line: str):
        data = (line + "\n").encode()
        with self.lock:
            for c in list(self.clients):
                try:
                    c.sendall(data)
                except OSError:
                    self.clients.remove(c)


class Nucleo:
    """Serial link; every line goes to on_line, commands are queued and answered."""

    def __init__(self, port: str, baud: int, on_line):
        self.port, self.baud = port, baud
        self.ser = None  # opened (and re-opened) by _rx so the pod runs without a Nucleo
        self.on_line = on_line
        self.tx = queue.Queue()
        self.alive = 0.0
        self.connects = 0
        threading.Thread(target=self._rx, daemon=True).start()
        threading.Thread(target=self._txloop, daemon=True).start()

    def send(self, cmd: str, quiet: bool = False):
        self.tx.put((cmd, quiet))

    def _txloop(self):
        while True:
            cmd, quiet = self.tx.get()
            if self.ser is None:
                if not quiet:
                    log.warning("-> %s dropped: no Nucleo link", cmd)
                continue
            try:
                for b in (cmd.strip() + "\n").encode():
                    self.ser.write(bytes((b,)))
                    self.ser.flush()
                    time.sleep(TX_CHAR_GAP_S)
                (log.debug if quiet else log.info)("-> %s", cmd)
            except (serial.SerialException, OSError) as e:
                log.warning("-> %s failed: %s", cmd, e)

    def _open(self):
        while self.ser is None:
            try:
                self.ser = serial.Serial(self.port, self.baud, timeout=0.2)
                self.connects += 1
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
                s = line.decode(errors="replace").strip()
                if s:
                    self.alive = time.time()
                    self.on_line(s)


class PodState:
    """What the LCD, LED and dashboard show; fed from Nucleo lines (rx thread), read by the main loop."""

    def __init__(self):
        self.state = "?"
        self.fault = 0
        self.mode = "IDLE"
        self.vm = [math.nan] * 3
        self.view = "mode"          # "init" while/after an init check, "mode" once a run mode is selected
        self.init_items: dict[str, bool] = {}
        self.init_detail: dict[str, str] = {}
        self.init_running = False
        self.init_result: str | None = None   # "PASS" / "FAIL"
        self.init_fails = 0

    @property
    def switching(self) -> bool:
        return self.state.startswith("RUN") or self.state == "SOFTSTART"

    @property
    def s2_ready(self) -> bool:
        return all(self.init_items.get(k, False) for k in S2_NEEDS)

    def init_ok(self, *names: str) -> bool:
        return all(self.init_items.get(n, False) for n in names)

    def flags(self) -> dict:
        return {"s1_active": self.mode in S1_MODES, "s2_active": self.mode in S2_MODES,
                "switching": self.switching, "fault_active": self.fault != 0 or self.state == "FAULT"}


def read_ds18b20() -> float | None:
    for path in glob.glob("/sys/bus/w1/devices/28-*/temperature"):
        try:
            with open(path) as f:
                return int(f.read().strip()) / 1000.0
        except (OSError, ValueError):
            pass
    return None


class Ui:
    """RGB LED (GPIO 12/13/19) + I2C LCD (0x27 / 0x3F). LED colour = safety state, LCD = mode + checkboxes."""

    def __init__(self):
        self.led = None
        self.lcd = None
        try:
            from gpiozero import RGBLED
            self.led = RGBLED(12, 13, 19)
        except Exception as e:  # noqa: BLE001
            log.warning("no RGB LED: %s", e)
        try:
            from lcd import Lcd, BOX_OFF, BOX_ON
            self.lcd = Lcd()
            self._box = {False: BOX_OFF, True: BOX_ON}
        except Exception as e:  # noqa: BLE001
            log.warning("no LCD: %s", e)

    def _led(self, st: PodState, link_ok: bool):
        known = [v for v in st.vm if v == v]
        v_live = max(known) if known else math.nan
        if not link_ok:
            self.led.color = (1, 0, 1)        # magenta: no Nucleo link
        elif st.state == "FAULT" or st.fault:
            self.led.color = (1, 0, 0)        # red: faulted / not safe
        elif st.switching:
            self.led.color = (0, 1, 0)        # green: switching
        elif not known or v_live > 10.0 or sum(known) > 10.0:
            self.led.color = (1, 0.4, 0)      # amber: idle but live, or voltages unreadable (not proven safe)
        else:
            self.led.color = (0, 0, 1)        # blue: idle, safe to touch (every readable module < 10 V)

    def _lines(self, st: PodState, link_ok: bool, page: int) -> tuple[str, str]:
        b = self._box
        if not link_ok:
            return "NO NUCLEO LINK", "check USB cable"
        if st.view == "init":
            if st.init_running:
                l1 = "INIT RUNNING..."
            elif st.init_result == "PASS":
                l1 = "INIT PASS"
            else:
                l1 = f"INIT FAIL{st.init_fails}" + (" S2 OK" if st.s2_ready else " S2 NO")
            # boxes = what the bottom shuffler needs: SPI bus, U11+U12, S2 halls, E-stop released
            l2 = (f"SPI{b[st.init_ok('SPI3 bus')]}INA{b[st.init_ok('INA CS1', 'INA CS2')]}"
                  f"HAL{b[st.init_ok('ILA_2', 'ILB_2')]}ES{b[st.init_ok('E-stop')]}")
            return l1, l2
        f = st.flags()
        l1 = MODE_TEXT.get(st.mode, st.mode)
        if f["fault_active"]:
            l1 = f"{l1[:12]:<12}F{st.fault:03x}"
        if page == 0:
            l2 = f"S1{b[f['s1_active']]} S2{b[f['s2_active']]} SW{b[f['switching']]} FL{b[f['fault_active']]}"
        else:
            l2 = f"V2 {st.vm[1]:4.1f} V3 {st.vm[2]:4.1f}"
        return l1, l2

    def show(self, st: PodState, link_ok: bool):
        if self.led:
            self._led(st, link_ok)
        if self.lcd:
            page = int(time.time() / 3) % 2      # mode view alternates checkboxes / S2 module voltages
            l1, l2 = self._lines(st, link_ok, page)
            try:
                self.lcd.write(l1[:16], l2[:16])
            except OSError as e:
                log.warning("LCD write failed: %s", e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--no-ir", action="store_true")
    ap.add_argument("--no-init", action="store_true", help="do not run C,TEST,0 when the Nucleo link comes up")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.v else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    influx = Influx()
    ui = Ui()
    st = PodState()
    ctl: CtlServer | None = None
    t_echo = [0.0]

    def on_note(s: str):
        m = INIT_RE.match(s)
        r = INIT_RESULT_RE.match(s)       # checked first: the RESULT line also fits INIT_RE
        if s.startswith("# INIT check start"):
            st.view, st.init_running = "init", True
            st.init_items, st.init_detail = {}, {}
        elif r:
            st.init_running, st.init_result, st.init_fails = False, r.group(1), int(r.group(2))
            fields = {re.sub(r"\W+", "_", k): v for k, v in st.init_items.items()}
            fields.update(result_pass=st.init_result == "PASS", fails=st.init_fails, s2_ready=st.s2_ready)
            influx.write("init", fields, {"source": "nucleo"})
            log.info("init check %s (%d failing), S2 ready: %s", st.init_result, st.init_fails, st.s2_ready)
        elif m:
            st.init_items[m.group(1)] = m.group(2) == "PASS"
            st.init_detail[m.group(1)] = m.group(3)
        if s.startswith("# INIT") or s.startswith("# INA") or s.startswith("# hall"):
            log.info("%s", s)

    def on_line(s: str):
        if ctl and (not s.startswith("T,") or time.time() - t_echo[0] >= 1.0):
            if s.startswith("T,"):
                t_echo[0] = time.time()
            ctl.broadcast(s)
        if s.startswith("#"):
            on_note(s)
            return
        fr = parse_line(s)
        if fr is None:
            return
        if fr.kind == "T":
            st.state, st.fault = fr.state, fr.fault
            st.vm = [fr.values.get(f"VM{k}", math.nan) for k in (1, 2, 3)]
            if st.switching:
                st.view = "mode"
            fields = {k: v for k, v in fr.values.items() if k != "pver"}
            fields["fault"] = float(fr.fault)
            influx.write("telemetry", fields, {"source": "nucleo", "state": fr.state, "pver": fr.values.get("pver", "")})
        elif fr.kind == "S":
            st.state, st.fault = fr.state, fr.fault
            mode = fr.values.get("mode", "")
            if mode and mode != st.mode and mode != "IDLE":
                st.view = "mode"
            st.mode = mode or st.mode
            influx.write("status", {"fault": float(fr.fault)},
                         {"source": "nucleo", "state": fr.state, "mode": st.mode})
        elif fr.kind == "F":
            influx.write("fault", {"code": float(fr.fault), "value": fr.values["value"]},
                         {"source": "nucleo", "channel": fr.values["channel"]})
            log.error("FAULT %s", fr.raw)
        elif fr.kind == "A":
            # heartbeat and e-load forwarding answers are routine; refusals are not
            if not fr.values["ok"]:
                log.warning("<- %s", fr.raw)
            elif fr.values["cmd"] in ("PING", "SET", "GET", "LIST"):
                log.debug("<- %s", fr.raw)
            else:
                log.info("<- %s", fr.raw)

    nucleo = Nucleo(a.port, a.baud, on_line)
    ctl = CtlServer(nucleo)

    if not a.no_ir:
        threading.Thread(target=ir_loop, args=(nucleo,), daemon=True).start()

    t_last = 0.0
    temp = None
    seen_connects = 0
    t_link = 0.0
    while True:
        now = time.time()
        link_ok = (now - nucleo.alive) < 2.0
        # fresh link (pod start or USB re-plug): ping, then run the IC init check once frames flow
        if nucleo.connects != seen_connects:
            seen_connects, t_link = nucleo.connects, now
            nucleo.send("C,PING")
        if t_link and link_ok and now - t_link > 1.5:
            t_link = 0.0
            if not a.no_init:
                nucleo.send("C,TEST,0")
        if now - t_last >= 1.0:
            t_last = now
            # heartbeat for the firmware's closed-loop comms watchdog (C,SET,wdg_s; FLT_COMMS_WDG 0x800)
            if link_ok:
                nucleo.send("C,PING", quiet=True)
            temp = read_ds18b20()
            if temp is not None:
                influx.write("telemetry", {"heatsink_c": temp}, {"source": "pi"})
                if temp > 80.0:
                    nucleo.send("C,ESTOP")
                    log.error("heatsink %.1f C: E-stop sent", temp)
            pod_fields = dict(st.flags(), mode=st.mode, view=st.view, link_ok=link_ok)
            influx.write("pod", pod_fields, {"source": "pi"})
        ui.show(st, link_ok)
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
