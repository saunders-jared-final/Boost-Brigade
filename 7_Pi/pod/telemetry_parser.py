"""Parser for the Nucleo ASCII link (0_Documentation/telemetry.md). Shared by the
pod service, the bench tools and the plotting scripts - the only place the field
order is written down in Python."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

N_MOD = 3
N_LEG = 4
N_SHUF = 2

T_FIELDS_V1 = (["ms", "state", "fault"]
               + [f"VM{k}" for k in range(1, N_MOD + 1)]
               + ["ILA1", "ILB1", "ILA2", "ILB2"]
               + ["dA1", "dB1", "dA2", "dB2"]
               + [f"rv{k}" for k in range(1, N_SHUF + 1)]
               + ["beta", "stress"]
               + [f"IM{k}r" for k in range(1, N_MOD)]
               + ["T1", "T2", "T3", "pver"])
# protocol 2 (fw 0.3.0): active gain scale and gain-set counter before pver
T_FIELDS_V2 = T_FIELDS_V1[:-1] + ["kscale", "pset", "pver"]
T_FIELDS = T_FIELDS_V2
_T_BY_LEN = {len(T_FIELDS_V1) + 1: T_FIELDS_V1, len(T_FIELDS_V2) + 1: T_FIELDS_V2}

STATE_CODES = {"BOOT": 0, "SELFTEST": 1, "IDLE": 2, "SOFTSTART": 3, "RUN_OL": 10, "RUN_CL": 11,
               "RUN_OL1": 12, "RUN_CL1": 13, "RUN_OL2": 14, "RUN_CL2": 15, "STOP": 4, "FAULT": 9}


@dataclass
class Frame:
    kind: str
    ms: int = 0
    state: str = ""
    fault: int = 0
    values: dict = field(default_factory=dict)
    raw: str = ""


def _f(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return math.nan


def parse_line(line: str) -> Frame | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split(",")
    kind = parts[0]
    if kind == "T":
        fields = _T_BY_LEN.get(len(parts))
        if fields is None:
            return None
        fr = Frame("T", raw=line)
        vals = parts[1:]
        fr.ms = int(vals[0])
        fr.state = vals[1]
        fr.fault = int(vals[2], 16)
        for name, v in zip(fields[3:-1], vals[3:-1]):
            fr.values[name] = _f(v)
        fr.values["pver"] = vals[-1]
        fr.values["state_code"] = float(STATE_CODES.get(fr.state, -1))
        fr.values["Vstr"] = sum(fr.values.get(f"VM{k}", math.nan) for k in range(1, N_MOD + 1))
        return fr
    if kind == "S" and len(parts) >= 7:
        return Frame("S", ms=int(parts[1]), state=parts[2], fault=int(parts[3], 16),
                     values={"mode": parts[4], "fw": parts[5], "pver": parts[6]}, raw=line)
    if kind == "F" and len(parts) >= 6:
        return Frame("F", ms=int(parts[1]), fault=int(parts[2], 16),
                     values={"channel": parts[3], "value": _f(parts[4]), "raw_code": _f(parts[5])}, raw=line)
    if kind == "P" and len(parts) >= 3:
        # C,GET -> P,<name>,<value>; C,LIST -> P,<name>,<value>,<min>,<max>,<LIVE|IDLE|STAGED>
        v = {"name": parts[1], "value": _f(parts[2])}
        if len(parts) >= 6:
            v.update({"min": _f(parts[3]), "max": _f(parts[4]), "class": parts[5]})
        return Frame("P", values=v, raw=line)
    if kind == "A" and len(parts) >= 4:
        return Frame("A", values={"cmd": parts[1], "ok": parts[2] == "OK", "why": ",".join(parts[3:])}, raw=line)
    return None
