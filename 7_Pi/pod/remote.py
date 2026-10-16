"""Elegoo IR remote -> LCD menu + Nucleo commands (used by pod.py).

Receiver: gpio-ir overlay on GPIO 17, NEC protocol enabled with the Elegoo keymap (deploy/setup.sh). Keys
are read as raw NEC scancodes (EV_MSC/MSC_SCAN), so the mapping here works with or without the keymap.

    POWER         E-STOP at once (C,ESTOP)              FUNC/STOP   stop switching at once (C,EN,0)
    UP / |<<      previous menu item                    DOWN / >>|  next menu item
    PLAY (>||)    run the highlighted item              0..9        jump to that preset (actions.py)
    VOL+ / VOL-   gain scale +/- 0.1 (SET + APPLY)      EQ          next status page
    ST/REPT       leave the menu, back to status

Nothing starts switching (or turns the e-load on) without PLAY: a digit only moves the cursor. Presets
3..6 drive the DL3021 through the eload service (E,... commands, podlink.EloadLink); they do not need the
Nucleo link. Status page 4 shows the e-load.
"""
from __future__ import annotations

import logging
import math
import queue
import socket
import threading
import time

from actions import ACTIONS, BY_DIGIT, ESTOP, KSCALE_STEP, STOP, kscale_cmds

log = logging.getLogger("remote")

# Elegoo kit remote, NEC address 0x00: Linux scancode = command byte (the kit's 0xFFA25D style codes are
# the same commands bit-reversed: 0xA2 -> 0x45)
ELEGOO = {
    0x45: "POWER", 0x46: "VOL+", 0x47: "FUNC",
    0x44: "PREV", 0x40: "PLAY", 0x43: "NEXT",
    0x07: "DOWN", 0x15: "VOL-", 0x09: "UP",
    0x16: "0", 0x19: "EQ", 0x0D: "ST",
    0x0C: "1", 0x18: "2", 0x5E: "3",
    0x08: "4", 0x1C: "5", 0x5A: "6",
    0x42: "7", 0x52: "8", 0x4A: "9",
}
REPEATABLE = {"UP", "DOWN", "PREV", "NEXT", "VOL+", "VOL-"}
MENU_TIMEOUT_S = 15.0
MSG_S = 4.0
STATUS_PAGES = 5          # 0 mode + checkboxes, 1 module voltages, 2 state / gains, 3 network, 4 e-load


def pi_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "no network"


class Remote:
    """Menu state + command executor. key() runs on the IR thread, lines() on the pod main loop."""

    def __init__(self, nucleo, st, link_ok, eload=None, record=None):
        self.nucleo = nucleo          # pod.Nucleo: .send(cmd)
        self.st = st                  # pod.PodState: .kscale, .switching ...
        self.link_ok = link_ok        # callable -> bool
        self.eload = eload            # podlink.EloadLink or None: E,... commands
        self.record = record          # callable(dir, line) -> Influx "cmd" measurement (key presses), or None
        self.answers: queue.Queue = queue.Queue()
        self.cursor = 0
        self.view = "status"          # "status" | "menu" | "msg"
        self.t_key = 0.0
        self.msg = ("", "")
        self.t_msg = 0.0
        self.page: int | None = None  # None = auto-alternate pages 0/1 as before
        self.busy = threading.Lock()
        self._last = (None, 0.0)

    # ------------------------------------------------------------ input ---
    def scancode(self, sc: int):
        name = ELEGOO.get(sc & 0xFF) if (sc >> 8) & 0xFF in (0x00, 0xFF) else None
        if name is None:
            log.debug("IR scancode 0x%x not mapped", sc)
            return
        now = time.time()
        last, t = self._last
        # NEC repeats the code ~every 110 ms while held: arrows/volume auto-repeat at 4 Hz, everything else once
        if name == last and now - t < (0.25 if name in REPEATABLE else 0.6):
            return
        self._last = (name, now)
        self.key(name)

    def key(self, name: str):
        log.info("IR %s", name)
        if self.record is not None:
            self.record("ir", name)
        self.t_key = time.time()
        if name == "POWER":
            self._run("E-STOP", ESTOP)
        elif name == "FUNC":
            self._run("STOP", STOP)
        elif name in ("UP", "PREV"):
            self._menu(self.cursor - 1 if self.view == "menu" else self.cursor)
        elif name in ("DOWN", "NEXT"):
            self._menu(self.cursor + 1 if self.view == "menu" else self.cursor)
        elif name.isdigit():
            a = BY_DIGIT.get(int(name))
            if a:
                self._menu(ACTIONS.index(a))
        elif name == "PLAY":
            if self.view == "menu":
                a = ACTIONS[self.cursor]
                self._run(a.lcd.strip()[2:] if a.lcd[0].isdigit() else a.lcd.strip(), a.cmds)
            else:
                self._menu(self.cursor)
        elif name in ("VOL+", "VOL-"):
            k = self.st.kscale if self.st.kscale == self.st.kscale else 0.3
            k += KSCALE_STEP if name == "VOL+" else -KSCALE_STEP
            cmds = kscale_cmds(k)
            self._run(f"GAINS {float(cmds[0].split(',')[-1]) * 100:.0f}%", cmds)
        elif name == "EQ":
            self.page = 0 if self.page is None else (self.page + 1) % STATUS_PAGES
            self.view = "status"
        elif name == "ST":
            self.view, self.page = "status", None

    def on_answer(self, line: str):
        """pod rx thread: every A,<cmd>,OK|ERR,... line"""
        self.answers.put(line)

    # --------------------------------------------------------- actions ---
    def _menu(self, idx: int):
        self.cursor = idx % len(ACTIONS)
        self.view = "menu"

    def _show(self, l1: str, l2: str):
        self.msg, self.t_msg, self.view = (l1, l2), time.time(), "msg"

    def _run(self, title: str, cmds: list[str]):
        if any(c.startswith("C,") for c in cmds) and not self.link_ok():
            # nothing is queued for later: a command sent minutes after the key press would surprise everyone
            self._show(title[:16], "NO LINK:NOT SENT")
            log.warning("IR %s: no Nucleo link, %s not sent", title, cmds)
            return
        if not self.busy.acquire(blocking=False):
            if cmds in (ESTOP, STOP):        # safety keys never wait behind a running sequence
                for c in cmds:
                    self.nucleo.send(c)
                self._show(title[:16], "SENT")
            return
        threading.Thread(target=self._seq, args=(title, cmds), daemon=True).start()

    def _seq(self, title: str, cmds: list[str]):
        try:
            while not self.answers.empty():
                self.answers.get_nowait()
            self._show(title[:16], "SENDING...")
            for c in cmds:
                name = c.split(",")[1]
                if c.startswith("E,"):
                    ans = self.eload.request(c) if self.eload is not None else None
                    if ans is None:
                        self._show(title[:16], "NO ELOAD SERVICE")
                        log.warning("IR %s: eload service not reachable, %s not sent", title, c)
                        return
                else:
                    self.nucleo.send(c)
                    ans = self._wait(name, 2.0)
                if ans is None:
                    self._show(title[:16], f"NO ANSWER {name}"[:16])
                    return
                if not ans.startswith(f"A,{name},OK"):
                    reason = ans.split(",", 3)[3] if ans.count(",") >= 3 else "refused"
                    self._show(f"ERR {title}"[:16], reason[:16])
                    log.warning("IR %s refused: %s", title, ans)
                    return
            self._show(title[:16], "OK")
        finally:
            self.busy.release()

    def _wait(self, name: str, timeout: float) -> str | None:
        t_end = time.time() + timeout
        while time.time() < t_end:
            try:
                a = self.answers.get(timeout=0.1)
            except queue.Empty:
                continue
            if a.startswith(f"A,{name},"):
                return a
        return None

    # ----------------------------------------------------------- display ---
    def lines(self) -> tuple[str, str] | None:
        """LCD override for the menu / message views, None = the pod's status pages"""
        now = time.time()
        if self.view == "msg":
            if now - self.t_msg < MSG_S:
                return self.msg
            self.view = "menu" if now - self.t_key < MENU_TIMEOUT_S else "status"
        if self.view == "menu":
            if now - self.t_key > MENU_TIMEOUT_S:
                self.view = "status"
                return None
            a = ACTIONS[self.cursor]
            return ">" + a.lcd[:15], ("PLAY=START" if a.starts else "PLAY=RUN  ") + "  ^v"
        return None

    def status_page(self, auto: int) -> int:
        return auto if self.page is None else self.page


def page_lines(st, page: int) -> tuple[str, str] | None:
    """Status pages 1..3 (page 0 is the pod's mode/checkbox view)."""
    if page == 1:
        v = ["--.-" if not (x == x) else f"{x:4.1f}" for x in st.vm]
        return f"V1 {v[0]} V2 {v[1]}", f"V3 {v[2]}"
    if page == 2:
        k = "?" if not (st.kscale == st.kscale) else f"{st.kscale:.2f}"
        return f"{st.state[:10]:<10} F{st.fault:03x}", f"GAIN {k} {st.mode[:6]}"
    if page == 3:
        return "WEB:8080 GRF3000", pi_ip()[:16]
    if page == 4:
        e = st.eload
        if e is None:
            return "LOAD: NO SERVICE", "systemctl eload"
        if not e.get("link_ok"):
            return "LOAD: NO USB", "check DL3021 USB"
        l1 = f"LOAD {e.get('mode') or '?':<2} {'ON ' if e.get('input_on') else 'OFF'} {'LOC' if e.get('paused') else 'REM'}"
        v, i, p = (e.get(k) for k in ("v", "i", "p"))
        if v is None or i is None or p is None:
            return l1, "no readings yet"
        return l1, f"{v:4.1f}V {i:4.2f}A {p:3.0f}W"
    return None


def ir_loop(remote: Remote):
    """gpio-ir overlay (dtoverlay=gpio-ir,gpio_pin=17), NEC enabled by deploy/setup.sh."""
    try:
        import evdev
    except ImportError:
        log.warning("evdev missing: IR disabled")
        return
    while True:
        dev = None
        for path in evdev.list_devices():
            d = evdev.InputDevice(path)
            if "gpio_ir" in d.name.lower():
                dev = d
                break
        if dev is None:
            log.warning("no gpio_ir_recv input device, retrying in 10 s")
            time.sleep(10)
            continue
        log.info("IR: %s (%s)", dev.name, dev.path)
        try:
            for ev in dev.read_loop():
                if ev.type == evdev.ecodes.EV_MSC and ev.code == evdev.ecodes.MSC_SCAN:
                    remote.scancode(ev.value)
        except OSError as e:
            log.warning("IR device lost (%s)", e)
            time.sleep(2)
