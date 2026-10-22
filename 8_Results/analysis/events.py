#!/usr/bin/env python3
"""Events and segments of the hardware windows pulled by influx_pull.py.

    python3 events.py [--window SUBSTR] [--plot] [--print]

For every window in config.WINDOWS this writes to out/events/:
  <window>.events.csv    state transitions (close = SOFTSTART/RUN_OL -> RUN_CL, fault, idle, stop ...), commands sent
                         (kscale_apply with the value, vref, dutys, mode, en, e-load), kscale changes seen in the
                         telemetry, and shade candidates found in the data (change points of the 1 s medians of
                         VM3, VM2, string power and the shuffled current). Hand annotations in <window>.annot.csv
                         (columns time_local,kind,label) are merged in.
  <window>.segments.csv  contiguous runs of one (state, kscale, pver) split at gaps > 2 s: start, end, duration,
                         what ended it (next state / fault code), and settled means / standard deviations of the
                         controlled quantities over the second half of the segment.
  <window>.png           (--plot) overview: states, module voltages, string power, currents, duties, events.
Conventions: vd1 = VM1-VM2, vd2 = VM2-VM3, ic = ILA+ILB (circulating), id = ILA-ILB (shuffled).
"""
import argparse
import os
import re

import numpy as np
import pandas as pd

import config

EV_DIR = os.path.join(config.OUT, "events")
GAP_S = 2.0
RUN_STATES = ("RUN_OL", "RUN_CL", "RUN_OL1", "RUN_CL1", "RUN_OL2", "RUN_CL2")
SETTLED_COLS = ["vd1", "vd2", "ic1", "ic2", "id1", "id2", "dA1", "dB1", "dA2", "dB2", "VM1", "VM2", "VM3", "Vstr",
                "IM1r", "IM2r", "stress", "beta", "rv1", "rv2", "Pstr", "Istr"]
FAULT_BITS = {0x1: "OC latch", 0x2: "OC hw", 0x4: "E-stop", 0x8: "module OV", 0x10: "module UV", 0x20: "zero-cal", 0x40: "INA bus",
              0x80: "over-temp", 0x100: "watchdog reset", 0x200: "soft E-stop", 0x400: "string OV", 0x800: "comms watchdog",
              0x1000: "VM1 source stale", 0x2000: "main loop stall"}      # 6_RTOS/App/app.h FLT_*


def derive(tel):
    for a, b, n in (("VM1", "VM2", "vd1"), ("VM2", "VM3", "vd2")):
        tel[n] = tel[a] - tel[b]
    for k in (1, 2):
        tel[f"ic{k}"] = tel[f"ILA{k}"] + tel[f"ILB{k}"]
        tel[f"id{k}"] = tel[f"ILA{k}"] - tel[f"ILB{k}"]
    return tel


def _load(folder, name, start_s=None):
    """Telemetry (every state) + e-load + pod records of one export. Adds vd/ic/id, the e-load's v/i/p joined within
    300 ms (Vel/Istr/Pstr), the same linearly interpolated onto the telemetry clock (Vel_i/Istr_i/Pstr_i, NaN outside
    the e-load's coverage) and its forward-filled settings (el_mode, el_setpoint, el_set_cv, el_set_cc, el_input_on)."""
    d = os.path.join(config.RESULTS, folder)
    tel = pd.read_csv(os.path.join(d, name + ".csv"), low_memory=False)
    tel["t_utc"] = pd.to_datetime(tel["time_utc"], utc=True, format="ISO8601")
    tel = tel.sort_values("t_utc").reset_index(drop=True)
    tel = derive(tel)
    out = {"name": name, "folder": folder, "tel": tel}
    for key, suffix in (("eload", " eload"), ("cmd", " cmd"), ("params", " params"), ("fault", " fault"), ("status", " status"), ("note", " note")):
        p = os.path.join(d, name + suffix + ".csv")
        df = pd.read_csv(p, low_memory=False) if os.path.exists(p) and os.path.getsize(p) > 0 else pd.DataFrame()
        if len(df):
            df["t_utc"] = pd.to_datetime(df["time_utc"], utc=True, format="ISO8601")
            df = df.sort_values("t_utc").reset_index(drop=True)
        out[key] = df
    el = out["eload"]
    if len(el) and "p" in el:
        fast = el.dropna(subset=["p"])[["t_utc", "v", "i", "p"]].rename(columns={"v": "Vel", "i": "Istr", "p": "Pstr"})
        tel = pd.merge_asof(tel.sort_values("t_utc"), fast.sort_values("t_utc"), on="t_utc", tolerance=pd.Timedelta("300ms"))
        ti = tel["t_utc"].astype("int64").to_numpy()
        te = fast["t_utc"].astype("int64").to_numpy()
        for c, src in (("Vel_i", "Vel"), ("Istr_i", "Istr"), ("Pstr_i", "Pstr")):
            tel[c] = np.interp(ti, te, fast[src].astype(float).to_numpy(), left=np.nan, right=np.nan)
        sets = [c for c in ("mode", "setpoint", "set_cv", "set_cc", "input_on") if c in el]
        if sets:
            slow = el.dropna(subset=["setpoint"] if "setpoint" in el else sets[:1])[["t_utc", *sets]]
            slow = slow.rename(columns={c: "el_" + c for c in sets})
            tel = pd.merge_asof(tel, slow.sort_values("t_utc"), on="t_utc", direction="backward")
        out["tel"] = tel
    return out


def load_window(name):
    folder, start_s, _e, _n = config.WINDOWS[name]
    return _load(folder, name, start_s)


def load_case(cid):
    """One presentation test case (config.TEST_CASES) exported by influx_pull.py --cases."""
    spec = config.TEST_CASES[cid]
    out = _load(config.CASES_FOLDER, config.case_name(cid), spec["start"])
    out["cid"], out["spec"] = cid, spec
    return out


def _ev(t, kind, detail="", value=np.nan, source="telemetry"):
    return {"time_utc": t, "time_local": t.tz_convert(config.LOCAL_TZ).isoformat(), "kind": kind, "detail": detail,
            "value": value, "source": source}


def state_transitions(tel):
    ev = []
    st = tel["state"].fillna("")
    idx = tel.index[st.ne(st.shift())][1:]
    for i in idx:
        prev, new = st.iat[tel.index.get_loc(i) - 1], st.at[i]
        if new == "RUN_CL" or new in ("RUN_CL1", "RUN_CL2"):
            kind = "close"
        elif new.startswith("RUN_OL"):
            kind = "ol_start"
        elif new == "SOFTSTART":
            kind = "softstart"
        elif new == "FAULT":
            kind = "fault"
        elif new == "STOP":
            kind = "stop"
        elif new == "IDLE":
            kind = "idle"
        else:
            kind = "state"
        detail = f"{prev}->{new}"
        if kind == "fault":
            code = int(tel.loc[i:, "fault"].head(5).max())
            bits = [n for b, n in FAULT_BITS.items() if code & b]
            detail += f" code {code} ({', '.join(bits) or '?'})"
        ev.append(_ev(tel.at[i, "t_utc"], kind, detail, tel.at[i, "kscale"]))
    return ev


def cmd_events(cmd):
    ev = []
    if not len(cmd):
        return ev
    pending = None
    for _, r in cmd.iterrows():
        line = str(r.get("line", ""))
        if r.get("dir") == "ir":
            continue
        if r.get("source") == "eload":
            if line.startswith("E,") and not line.startswith(("E,STATUS", "E,PING")):
                ev.append(_ev(r["t_utc"], "eload_cmd", line + (f" -> {r['answer']}" if isinstance(r.get("answer"), str) else ""), source="cmd"))
            continue
        if r.get("dir") != "tx":
            continue
        m = re.match(r"C,SET,kscale,([\d.]+)", line)
        if m:
            pending = float(m.group(1))
        elif line.startswith("C,APPLY"):
            ev.append(_ev(r["t_utc"], "kscale_apply", f"kscale {pending}", pending if pending is not None else np.nan, "cmd"))
        elif line.startswith("C,VREF") or re.match(r"C,SET,vref", line):
            ev.append(_ev(r["t_utc"], "vref", line, source="cmd"))
        elif line.startswith("C,DUTYS") or line.startswith("C,DUTY,"):
            vals = [float(v) for v in re.findall(r"[-+]?\d*\.\d+|\d+", line.split(",", 1)[1])] if "," in line else []
            ev.append(_ev(r["t_utc"], "duty_step", line, vals[0] if vals else np.nan, "cmd"))
        elif line.startswith("C,MODE"):
            ev.append(_ev(r["t_utc"], "mode", line, source="cmd"))
        elif line.startswith("C,EN"):
            ev.append(_ev(r["t_utc"], "en", line, source="cmd"))
        elif line.startswith(("C,SET,", "C,SUP", "C,SETM", "C,ESTOP", "C,CLEAR")):
            ev.append(_ev(r["t_utc"], "cmd", line, source="cmd"))
    return ev


def eload_setting_events(el):
    """Changes of the DL3021 set-point / mode / input while logging: a load step for the string (1 Hz rows)."""
    ev = []
    if not len(el) or "setpoint" not in el:
        return ev
    slow = el.dropna(subset=["setpoint"]).reset_index(drop=True)
    for c in ("setpoint", "mode", "input_on"):
        if c not in slow:
            continue
        v = slow[c]
        idx = slow.index[v.ne(v.shift()) & v.notna()][1:]
        for i in idx:
            prev, new = v.iat[i - 1], v.iat[i]
            if c == "setpoint" and isinstance(new, (int, float)) and isinstance(prev, (int, float)) and abs(float(new) - float(prev)) < 1e-6:
                continue
            ev.append(_ev(slow.at[i, "t_utc"], "load_step", f"e-load {c} {prev} -> {new}" + (f" ({slow.at[i, 'mode']})" if "mode" in slow else ""),
                          float(new) if c == "setpoint" else np.nan, "eload"))
    return ev


def kscale_changes(tel):
    ks = tel["kscale"]
    idx = tel.index[ks.ne(ks.shift()) & ks.notna()][1:]
    return [_ev(tel.at[i, "t_utc"], "kscale_change", f"{ks.iat[tel.index.get_loc(i) - 1]} -> {ks.at[i]}", ks.at[i]) for i in idx]


def medians_1s(tel, cols):
    s = tel.set_index("t_utc")[cols].astype(float)
    return s.resample("1s").median()


def shade_events(tel, mask_s=6.0):
    """Change points of the 1 s medians, ignoring +-mask_s around every state transition (the engagement itself
    moves the module voltages by the shuffler's equalisation) and anything outside run / idle segments > 10 s."""
    cols = [c for c in ("VM3", "VM2", "VM1", "Pstr", "id2", "IM2r") if c in tel]
    m = medians_1s(tel, cols)
    st = tel["state"].fillna("")
    trans = tel.loc[st.ne(st.shift()), "t_utc"].tolist()
    gaps = tel.loc[tel["t_utc"].diff().dt.total_seconds() > GAP_S, "t_utc"].tolist()
    masked = np.zeros(len(m), dtype=bool)
    for tt in trans + gaps:
        masked |= (np.abs((m.index - tt).total_seconds()) <= mask_s)
    state_at = tel.set_index("t_utc")["state"].reindex(m.index, method="ffill")
    floors = {"VM3": 0.6, "VM2": 0.6, "VM1": 0.8, "Pstr": 4.0, "id2": 0.4, "IM2r": 0.4}
    found = []
    for c in cols:
        s = m[c].interpolate(limit=3)
        d = s.shift(-2) - s.shift(2)                      # 4 s span
        d[masked] = np.nan                                # the engagement / disengagement steps are not shade
        mad = np.nanmedian(np.abs(d - np.nanmedian(d))) * 1.4826
        thr = max(3 * mad, floors[c])
        hits = d[np.abs(d) > thr]
        if hits.empty:
            continue
        # merge hits within 5 s, keep the largest
        group, last = [], None
        for t, v in hits.items():
            if last is None or (t - last).total_seconds() > 5:
                group.append([t, v])
            elif abs(v) > abs(group[-1][1]):
                group[-1] = [t, v]
            last = t
        for t, v in group:
            found.append((t, c, float(v), thr, str(state_at.get(t, ""))))
    # cluster across columns within 5 s
    found.sort()
    ev, cluster = [], []

    def flush():
        if not cluster:
            return
        t0 = cluster[0][0]
        parts = ", ".join(f"{c} {v:+.2f}" for _t, c, v, _thr, _s in cluster)
        vm3 = [v for _t, c, v, _, _s in cluster if c == "VM3"]
        p = [v for _t, c, v, _, _s in cluster if c == "Pstr"]
        sign = (vm3[0] if vm3 else (p[0] if p else cluster[0][2]))
        ev.append(_ev(t0, "shade_on" if sign < 0 else "shade_off", f"[{cluster[0][4]}] " + parts, sign, "detector"))

    for item in found:
        if cluster and (item[0] - cluster[-1][0]).total_seconds() > 5:
            flush()
            cluster = []
        cluster.append(item)
    flush()
    # short dips: an on followed by an off within 12 s
    for a, b in zip(ev, ev[1:]):
        if a["kind"] == "shade_on" and b["kind"] == "shade_off" and (b["time_utc"] - a["time_utc"]).total_seconds() < 12:
            a["kind"], b["kind"] = "transient_on", "transient_off"
    return ev


def segments(tel):
    key = tel["state"].fillna("") + "|" + tel["kscale"].astype(str) + "|" + tel["pver"].fillna("").astype(str)
    gap = tel["t_utc"].diff().dt.total_seconds().fillna(0) > GAP_S
    seg_id = (key.ne(key.shift()) | gap).cumsum()
    rows = []
    groups = list(tel.groupby(seg_id, sort=True))
    for n, (sid, g) in enumerate(groups):
        state = g["state"].iat[0]
        start, end = g["t_utc"].iat[0], g["t_utc"].iat[-1]
        nxt = groups[n + 1][1] if n + 1 < len(groups) else None
        ended = nxt["state"].iat[0] if nxt is not None else "end of window"
        code = int(nxt["fault"].head(5).max()) if nxt is not None and ended == "FAULT" else 0
        row = {"seg": int(sid), "state": state, "kscale": g["kscale"].iat[0], "pver": g["pver"].iat[0],
               "start_local": start.tz_convert(config.LOCAL_TZ).isoformat(), "end_local": end.tz_convert(config.LOCAL_TZ).isoformat(),
               "start_utc": start.isoformat(), "end_utc": end.isoformat(),
               "duration_s": round((end - start).total_seconds(), 2), "n": len(g), "ended_by": ended, "fault_code": code}
        if state in RUN_STATES and len(g) > 20:
            h = g.iloc[len(g) // 2:]
            for c in SETTLED_COLS:
                if c in h:
                    row[c + "_mean"] = round(float(h[c].mean()), 4)
                    row[c + "_std"] = round(float(h[c].std()), 4)
        rows.append(row)
    return pd.DataFrame(rows)


def annotations(name):
    p = os.path.join(EV_DIR, name + ".annot.csv")
    if not os.path.exists(p):
        return []
    a = pd.read_csv(p)
    ev = []
    for _, r in a.iterrows():
        t = pd.Timestamp(r["time_local"])
        if t.tzinfo is None:
            t = t.tz_localize(config.LOCAL_TZ)
        ev.append(_ev(t.tz_convert("UTC"), str(r["kind"]), str(r.get("label", "")), source="annotation"))
    return ev


def build(name, plot=False):
    w = load_window(name)
    tel = w["tel"]
    ev = state_transitions(tel) + cmd_events(w["cmd"]) + kscale_changes(tel) + shade_events(tel) + annotations(name)
    ev = pd.DataFrame(ev).sort_values("time_utc")
    t0 = tel["t_utc"].iat[0]
    ev["t_s"] = (ev["time_utc"] - t0).dt.total_seconds().round(3)
    seg = segments(tel)
    os.makedirs(EV_DIR, exist_ok=True)
    ev.to_csv(os.path.join(EV_DIR, name + ".events.csv"), index=False)
    seg.to_csv(os.path.join(EV_DIR, name + ".segments.csv"), index=False)
    if plot:
        overview_plot(w, ev, seg, os.path.join(EV_DIR, name + ".png"))
    return w, ev, seg


def build_case(cid, plot=False):
    """Events and segments (every state) of one presentation test case -> out/events/<cid>_<label>.{events,segments}.csv."""
    w = load_case(cid)
    tel = w["tel"]
    name = w["name"]
    ev = state_transitions(tel) + cmd_events(w["cmd"]) + kscale_changes(tel) + eload_setting_events(w["eload"]) + annotations(name)
    shade = shade_events(tel)
    if w["spec"]["setup"] == "BENCH":                       # no shading on the bench: those level shifts are PSU / load changes
        for e in shade:
            e["kind"] = "load_step"
            e["source"] = "detector"
    ev += shade
    ev = pd.DataFrame(ev).sort_values("time_utc").reset_index(drop=True)
    t0 = tel["t_utc"].iat[0]
    ev["t_s"] = (ev["time_utc"] - t0).dt.total_seconds().round(3)
    seg = segments(tel)
    os.makedirs(EV_DIR, exist_ok=True)
    ev.to_csv(os.path.join(EV_DIR, name + ".events.csv"), index=False)
    seg.to_csv(os.path.join(EV_DIR, name + ".segments.csv"), index=False)
    if plot:
        overview_plot(w, ev, seg, os.path.join(EV_DIR, name + ".png"))
    return w, ev, seg


def overview_plot(w, ev, seg, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tel = w["tel"]
    t0 = tel["t_utc"].iat[0]
    tl = (tel["t_utc"] - t0).dt.total_seconds() / 60.0
    m = medians_1s(tel, [c for c in ("VM1", "VM2", "VM3", "Vstr", "Pstr", "ic2", "id2", "ic1", "id1", "dA2", "dB2", "dA1", "dB1", "stress") if c in tel])
    tm = (m.index - t0).total_seconds() / 60.0
    fig, ax = plt.subplots(5, 1, figsize=(14, 11), sharex=True, gridspec_kw={"height_ratios": [0.6, 2, 1.5, 1.5, 1.2]})
    colours = {"IDLE": "#dddddd", "SOFTSTART": "#ffe6a8", "RUN_OL": "#cfe8ff", "RUN_CL": "#c9f0cf", "FAULT": "#f7b7b7", "STOP": "#e8d5f5"}
    for _, s in seg.iterrows():
        a = (pd.Timestamp(s["start_utc"]) - t0).total_seconds() / 60.0
        b = (pd.Timestamp(s["end_utc"]) - t0).total_seconds() / 60.0
        for axis in ax:
            axis.axvspan(a, b, color=colours.get(s["state"], "#eeeeee"), alpha=0.5, lw=0)
        if s["state"] in RUN_STATES:
            ax[0].text((a + b) / 2, 0.5, f"{s['state'][4:]}\nk={s['kscale']}", ha="center", va="center", fontsize=7)
    ax[0].set_yticks([]); ax[0].set_ylabel("state")
    for c in ("VM1", "VM2", "VM3"):
        ax[1].plot(tm, m[c], lw=1, label=c)
    ax[1].set_ylabel("module V (1 s median)"); ax[1].legend(loc="upper right", fontsize=8, ncol=3)
    if "Pstr" in m:
        ax[2].plot(tm, m["Pstr"], lw=1, color="#b5652a", label="P string (e-load)")
        ax[2].set_ylabel("W")
        ax[2].legend(loc="upper right", fontsize=8)
    for c, col in (("ic2", "#1f6b46"), ("id2", "#1b2d55"), ("ic1", "#7fbf9f"), ("id1", "#8fa0cc")):
        if c in m:
            ax[3].plot(tm, m[c], lw=1, color=col, label=c)
    ax[3].set_ylabel("A (1 s median)"); ax[3].legend(loc="upper right", fontsize=8, ncol=4)
    for c in ("dA1", "dB1", "dA2", "dB2"):
        if c in m:
            ax[4].plot(tm, m[c], lw=1, label=c)
    ax[4].set_ylabel("duty"); ax[4].legend(loc="upper right", fontsize=8, ncol=4); ax[4].set_xlabel("minutes since window start (%s local)" % t0.tz_convert(config.LOCAL_TZ).strftime("%H:%M:%S"))
    for _, e in ev.iterrows():
        if e["kind"] in ("close", "fault", "shade_on", "shade_off", "transient_on", "transient_off", "kscale_apply", "duty_step", "vref", "load_step"):
            x = e["t_s"] / 60.0
            col = {"close": "green", "fault": "red", "shade_on": "purple", "shade_off": "violet", "transient_on": "orange",
                   "transient_off": "orange", "kscale_apply": "gray", "duty_step": "brown", "vref": "black", "load_step": "#9467bd"}[e["kind"]]
            for axis in ax[1:]:
                axis.axvline(x, color=col, lw=0.8, ls="--", alpha=0.7)
            ax[1].text(x, ax[1].get_ylim()[1], e["kind"], rotation=90, fontsize=6, va="top", ha="right", color=col)
    fig.suptitle(w["name"], fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", help="substring filter")
    ap.add_argument("--plot", action="store_true")
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--cases", action="store_true", help="the presentation test cases (config.TEST_CASES) instead of config.WINDOWS")
    a = ap.parse_args()
    if a.cases:
        for cid in config.TEST_CASES:
            if a.window and a.window not in cid:
                continue
            w, ev, seg = build_case(cid, a.plot)
            runs = seg[seg["state"].isin(RUN_STATES)]
            print(f"{cid}: {len(ev)} events, {len(seg)} segments ({len(runs)} runs, {runs['duration_s'].sum():.0f} s in RUN)")
        return
    for name in config.WINDOWS:
        if a.window and a.window not in name:
            continue
        w, ev, seg = build(name, a.plot)
        runs = seg[seg["state"].isin(RUN_STATES)]
        print(f"{name}: {len(ev)} events, {len(seg)} segments ({len(runs)} runs)")
        if a.print:
            cols = ["state", "kscale", "start_local", "duration_s", "ended_by", "fault_code", "vd2_mean", "vd2_std", "ic2_mean", "ic2_std", "Pstr_mean"]
            print(runs[[c for c in cols if c in runs]].to_string(index=False))
            print(ev[ev["kind"].isin(("close", "fault", "shade_on", "shade_off", "transient_on", "transient_off", "vref", "duty_step", "load_step"))][["time_local", "kind", "detail"]].to_string(index=False, max_colwidth=70))


if __name__ == "__main__":
    main()
