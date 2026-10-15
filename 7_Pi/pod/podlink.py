"""Client for the pod's control socket (127.0.0.1:5017), shared by eload.py and params_web.py.

The pod forwards every line we send to the Nucleo and broadcasts every non-T Nucleo line (plus one T frame
per second) to all clients, so a client MUST keep reading or the pod's sendall() eventually blocks: a
daemon thread drains the socket continuously, keeps the last T frame, and hands lines to a waiting
request() when there is one. Reconnects on its own; never raises to the caller."""
from __future__ import annotations

import logging
import queue
import socket
import threading
import time

log = logging.getLogger("podlink")

CTL = ("127.0.0.1", 5017)


class PodLink:
    def __init__(self, addr=CTL):
        self.addr = addr
        self.sock: socket.socket | None = None
        self.lock = threading.Lock()          # one request() at a time
        self.wlock = threading.Lock()
        self.waiting: queue.Queue | None = None
        self.last_t = ""
        self.last_t_time = 0.0
        self.last_s = ""
        threading.Thread(target=self._rx, daemon=True).start()

    def _connect(self) -> socket.socket | None:
        if self.sock is None:
            try:
                s = socket.create_connection(self.addr, timeout=2)
                s.settimeout(None)
                self.sock = s
                log.info("pod control socket connected")
            except OSError as e:
                log.debug("pod not reachable (%s)", e)
                return None
        return self.sock

    def _rx(self):
        buf = b""
        while True:
            s = self._connect()
            if s is None:
                time.sleep(2.0)
                continue
            try:
                chunk = s.recv(4096)
            except OSError:
                chunk = b""
            if not chunk:
                self.sock, buf = None, b""
                time.sleep(1.0)
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                t = line.decode(errors="replace").strip()
                if not t:
                    continue
                if t.startswith("T,"):
                    self.last_t, self.last_t_time = t, time.time()
                    continue
                if t.startswith("S,"):
                    self.last_s = t
                w = self.waiting
                if w is not None:
                    w.put(t)

    def send(self, line: str) -> bool:
        s = self._connect()
        if s is None:
            return False
        try:
            with self.wlock:
                s.sendall((line.strip() + "\n").encode())
            return True
        except OSError:
            self.sock = None
            return False

    def request(self, cmd: str, timeout: float = 4.0) -> tuple[bool, list[str]]:
        """Send one C,<CMD>,... line and collect the reply lines up to its A,<CMD>,... answer.
        Returns (ok, lines). The pod paces bytes at 2 ms, so a long line takes a while to go out."""
        name = cmd.split(",")[1] if cmd.startswith("C,") and "," in cmd else cmd
        with self.lock:
            q: queue.Queue = queue.Queue()
            self.waiting = q
            try:
                if not self.send(cmd):
                    return False, ["pod not reachable"]
                lines: list[str] = []
                t_end = time.time() + timeout + 0.002 * len(cmd)
                while time.time() < t_end:
                    try:
                        t = q.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    lines.append(t)
                    if t.startswith(f"A,{name},"):
                        return t.startswith(f"A,{name},OK"), lines
                return False, lines + [f"timeout waiting for A,{name}"]
            finally:
                self.waiting = None
