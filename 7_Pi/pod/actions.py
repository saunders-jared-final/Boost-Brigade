"""Operator presets shared by the IR remote / LCD menu (pod.py, remote.py), the web page (params_web.py) and the
cheat sheet, so a preset means the same thing everywhere. Each action is a list of commands sent in order; the
sequence stops at the first refusal (A,<cmd>,ERR,...).

  C,...  Nucleo (through the pod)        E,...  Rigol DL3021 e-load (eload.py's control socket, podlink.EloadLink)

Firmware semantics (6_RTOS/App/app.c): C,MODE only selects a mode; C,EN,1 starts switching through SOFTSTART;
C,EN,0 stops; C,ESTOP latches a fault (outputs off) until C,CLEAR. The two shufflers are hard-wired to each
other on the Version 0 board, so only the both-shuffler modes (OL, CL) are presets; the single-shuffler modes
(OL1/OL2/CL1/CL2) stay reachable from the terminal.
E-load semantics (eload.py): E,INPUT,1 turns the load input on (power flows); E,LOCAL hands the front panel to
the operator and pauses logging; E,REMOTE resumes logging and control from the pod.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Action:
    key: str
    lcd: str                 # LCD menu text, 15 characters max (the menu adds a ">" cursor)
    label: str               # web button / cheat sheet text
    cmds: list[str] = field(default_factory=list)
    digit: int | None = None
    starts: bool = False     # starts switching or power flow: the web page asks for a second click, LCD says START

    @property
    def needs_nucleo(self) -> bool:
        return any(c.startswith("C,") for c in self.cmds)


ACTIONS: list[Action] = [
    Action("init", "0 INIT CHECK", "Init check (ICs, sensors, E-stop)", ["C,TEST,0"], 0),
    Action("ol", "1 OPEN LOOP", "Open loop, both shufflers (0.5 duties)", ["C,MODE,OL", "C,EN,1"], 1, True),
    Action("cl", "2 CLOSED LOOP", "Closed loop, both shufflers", ["C,MODE,CL", "C,EN,1"], 2, True),
    Action("lon", "3 LOAD ON", "E-load input ON (DL3021)", ["E,INPUT,1"], 3, True),
    Action("loff", "4 LOAD OFF", "E-load input OFF", ["E,INPUT,0"], 4),
    Action("lrem", "5 LOAD REMOTE", "E-load remote: logging + control from the pod", ["E,REMOTE"], 5),
    Action("lloc", "6 LOAD LOCAL", "E-load local: front panel free, logging paused", ["E,LOCAL"], 6),
    Action("k03", "7 GAINS 30%", "Gain scale 0.3 (safe start)", ["C,SET,kscale,0.3", "C,APPLY"], 7),
    Action("k10", "8 GAINS 100%", "Gain scale 1.0 (full)", ["C,SET,kscale,1", "C,APPLY"], 8),
    Action("clear", "9 CLEAR FAULT", "Clear a latched fault", ["C,CLEAR"], 9),
    Action("stop", "  STOP", "Stop switching", ["C,EN,0"]),
    Action("idle", "  MODE IDLE", "Stop and deselect the mode", ["C,EN,0", "C,MODE,IDLE"]),
]
BY_KEY = {a.key: a for a in ACTIONS}
BY_DIGIT = {a.digit: a for a in ACTIONS if a.digit is not None}
ESTOP = ["C,ESTOP"]
STOP = ["C,EN,0"]

KSCALE_STEP = 0.1
KSCALE_MIN, KSCALE_MAX = 0.1, 1.0


def kscale_cmds(k: float) -> list[str]:
    k = round(min(max(k, KSCALE_MIN), KSCALE_MAX), 2)
    return [f"C,SET,kscale,{k:g}", "C,APPLY"]
