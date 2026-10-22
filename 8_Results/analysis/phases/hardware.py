"""Hardware phase: cases (engagements, shade events, settled segments) cut from the pulled windows."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import config                     # noqa: E402
import events                     # noqa: E402
import tidy                       # noqa: E402

SETUP_OF = {"Bench_Closed_Loop_200kHz": "BENCH", "Solar_Closed_Loop": "PV80"}
_cache = {}


def window(name):
    if name not in _cache:
        w = events.load_window(name)
        ev_path = os.path.join(events.EV_DIR, name + ".events.csv")
        seg_path = os.path.join(events.EV_DIR, name + ".segments.csv")
        if not (os.path.exists(ev_path) and os.path.exists(seg_path)):
            w, ev, seg = events.build(name)
        else:
            ev, seg = pd.read_csv(ev_path), pd.read_csv(seg_path)
        ev["time_utc"] = pd.to_datetime(ev["time_utc"], utc=True, format="ISO8601")
        w["events"], w["segments"] = ev, seg
        _cache[name] = w
    return _cache[name]


def cut(w, t_event, pre_s, post_s, **attrs):
    tel = w["tel"]
    m = (tel["t_utc"] >= t_event - pd.Timedelta(seconds=pre_s)) & (tel["t_utc"] <= t_event + pd.Timedelta(seconds=post_s))
    g = tel[m]
    data = {"t": (g["t_utc"] - t_event).dt.total_seconds().to_numpy()}
    for c in ("VM1", "VM2", "VM3", "ILA1", "ILB1", "ILA2", "ILB2", "dA1", "dB1", "dA2", "dB2", "rv1", "rv2", "beta", "stress",
              "kscale", "Vstr", "Istr", "Pstr", "state"):
        if c in g:
            data[c] = g[c].to_numpy()
    if "IM1r" in g:
        data["IM1"], data["IM2"] = g["IM1r"].to_numpy(), g["IM2r"].to_numpy()
    f = tidy.frame(data, phase="hardware", setup=SETUP_OF[w["folder"]], rate_hz=config.TELEMETRY_HZ, source=w["name"],
                   event_utc=t_event.isoformat(), vm1_quality="e-load via Pi, 2.2 Hz (vm1_src=2)", **attrs)
    return f


def close_cases(name, min_run_s=2.0, post_s=5.0):
    """One case per OL/SOFTSTART -> RUN_CL transition that lasted at least min_run_s: the loop closing on the mismatch."""
    w = window(name)
    tel, ev, seg = w["tel"], w["events"], w["segments"]
    cases = []
    for _, e in ev[ev["kind"] == "close"].iterrows():
        t0 = e["time_utc"]
        s = seg[(pd.to_datetime(seg["start_utc"], utc=True, format="ISO8601") >= t0 - pd.Timedelta(seconds=0.5)) & seg["state"].str.startswith("RUN_CL")]
        if s.empty or s.iloc[0]["duration_s"] < min_run_s:
            continue
        run = s.iloc[0]
        # the IDLE level before the soft start = the natural mismatch of the string
        idle = tel[(tel["t_utc"] < t0 - pd.Timedelta(seconds=0.1)) & (tel["t_utc"] >= t0 - pd.Timedelta(seconds=3)) & (tel["state"] == "IDLE")]
        f = cut(w, t0, pre_s=3.0, post_s=min(post_s, run["duration_s"]), scenario="S1", kscale=float(run["kscale"]),
                run_duration_s=float(run["duration_s"]), ended_by=run["ended_by"], pver=run["pver"],
                idle_levels={c: float(idle[c].median()) for c in ("vd1", "vd2", "ic1", "ic2", "id1", "id2") if len(idle)})
        cases.append(f)
    return cases


def shade_cases(name, pre_s=10.0, post_s=40.0):
    """One case per shade_on / transient_on candidate inside a run segment (user confirmation pending)."""
    w = window(name)
    ev = w["events"]
    cases = []
    cand = ev[ev["kind"].isin(("shade_on", "transient_on"))]
    times = cand["time_utc"].tolist()
    for i, (_, e) in enumerate(cand.iterrows()):
        state = str(e["detail"]).split("]")[0].strip("[") if str(e["detail"]).startswith("[") else ""
        if not state.startswith("RUN"):
            continue
        t0 = e["time_utc"]
        nxt = [t for t in ev["time_utc"] if t > t0 + pd.Timedelta(seconds=3)]
        until = min(post_s, (nxt[0] - t0).total_seconds()) if nxt else post_s
        ks = w["tel"].loc[(w["tel"]["t_utc"] - t0).abs().idxmin(), "kscale"]
        f = cut(w, t0, pre_s=pre_s, post_s=until, scenario="S3", kscale=float(ks), state=state, detail=e["detail"],
                candidate=True, label=e.get("label", ""))
        cases.append(f)
    return cases


def segment_stats(name):
    """S2: settled statistics of every run segment (from events.segments)."""
    w = window(name)
    seg = w["segments"]
    runs = seg[seg["state"].isin(events.RUN_STATES) & (seg["duration_s"] > 5)].copy()
    runs["phase"] = "hardware"
    runs["setup"] = SETUP_OF[w["folder"]]
    runs["window"] = name
    return runs


def all_windows(folder=None):
    return [n for n, (f, *_r) in config.WINDOWS.items() if folder is None or f == folder]


# ============================================================================ presentation test cases (config.TEST_CASES)
RUN_ONLY_FIELDS = ["VM2", "VM3", "ILA1", "ILB1", "ILA2", "ILB2", "dA1", "dB1", "dA2", "dB2"]   # frozen-frame test
CL_ONLY_FIELDS = ["rv1", "rv2", "beta", "stress", "IM1r", "IM2r"]                            # updated by the firmware in RUN_CL only
VM1_TOL_V = 2.0
_case_cache = {}


def case(cid):
    """Events + segments (every state) of a test case, built once; PV shade candidates come from the current mismatch."""
    if cid not in _case_cache:
        w, ev, seg = events.build_case(cid)
        ev["time_utc"] = pd.to_datetime(ev["time_utc"], utc=True, format="ISO8601")
        w["run"], w["run_info"] = clean_run(w)
        if w["spec"]["setup"] == "PV80":
            ev = ev[~ev["kind"].isin(("shade_on", "shade_off", "transient_on", "transient_off"))]
            extra = pd.DataFrame(mismatch_events(w["run"]))
            if len(extra):
                extra["t_s"] = (extra["time_utc"] - w["tel"]["t_utc"].iat[0]).dt.total_seconds().round(3)
                ev = pd.concat([ev, extra], ignore_index=True).sort_values("time_utc").reset_index(drop=True)
            ev.to_csv(os.path.join(events.EV_DIR, w["name"] + ".events.csv"), index=False)
        w["events"], w["segments"] = ev, seg
        _case_cache[cid] = w
    return _case_cache[cid]


def kcl_module_currents(df):
    """Module currents from the winding currents, duties and the string current (6_RTOS/ctrl_core/shuffler_recon.c):
    itop_k = dA_k ILA_k - dB_k ILB_k (drawn from the top rail), im_k = ILA_k - ILB_k (into the midpoint),
    ibot_k = im_k - itop_k; module 3 is the reference: IM2r = im_2 - ibot_1, IM1r = IM2r + im_1 - itop_2.
    Absolute values by KCL at the string terminals: I1 = Istr + itop_1, I3 = Istr - ibot_2, I2 = I3 + IM2r."""
    for k in (1, 2):
        df[f"itop{k}"] = df[f"dA{k}"] * df[f"ILA{k}"] - df[f"dB{k}"] * df[f"ILB{k}"]
        df[f"im{k}"] = df[f"ILA{k}"] - df[f"ILB{k}"]
        df[f"ibot{k}"] = df[f"im{k}"] - df[f"itop{k}"]
    df["IM2r_calc"] = df["im2"] - df["ibot1"]
    df["IM1r_calc"] = df["IM2r_calc"] + df["im1"] - df["itop2"]
    istr = df["Istr_i"] if "Istr_i" in df else df.get("Istr")
    if istr is not None:
        df["IM3"] = istr - df["ibot2"]
        df["IM2"] = df["IM3"] + df["IM2r_calc"]
        df["IM1"] = istr + df["itop1"]
        df["IM1_chk"] = df["IM3"] + df["IM1r_calc"]            # must equal IM1 (same KCL walked from the other end)
        df["Imean_chk"] = (df["IM1"] + df["IM2"] + df["IM3"]) / 3   # averaged-model identity Istr = mean(Ik) at D = 1/2
    return df


def powers(df):
    """Module, string, shuffled and 'returned' power (W) from the cleaned frame."""
    if "IM1" in df:
        for k in (1, 2, 3):
            df[f"P_M{k}"] = df[f"VM{k}"] * df[f"IM{k}"]
        df["P_mod"] = df["P_M1"] + df["P_M2"] + df["P_M3"]
        vstr = df["Vel_i"] if "Vel_i" in df else df["Vstr"]
        df["P_ret"] = (df["Istr_i"] - df[["IM1", "IM2", "IM3"]].min(axis=1)) * vstr
        df["eff"] = df["Pstr_i"] / df["P_mod"]
    df["P_sh1"] = df["id1"].abs() * (df["VM1"] + df["VM2"]) / 2
    df["P_sh2"] = df["id2"].abs() * (df["VM2"] + df["VM3"]) / 2
    df["P_sh"] = df["P_sh1"] + df["P_sh2"]
    return df


COLLAPSE_V = 2.0        # a module voltage this far from its segment median at the start / end of a run = shutdown or start-up frames
COLLAPSE_MAX_S = 10.0


def trim_collapse(run):
    """Drop the leading / trailing frames of every RUN segment in which VM2 or VM3 has left the segment median by more
    than COLLAPSE_V (the e-load / PSU being switched off before the FAULT, still tagged RUN). Returns (frame, n_dropped)."""
    if run.empty:
        return run, 0
    gap = run["t_utc"].diff().dt.total_seconds().fillna(0) > events.GAP_S
    sid = (gap | run["state"].ne(run["state"].shift())).cumsum()
    keep = np.ones(len(run), bool)
    pos = 0
    for _, g in run.groupby(sid, sort=False):
        n = len(g)
        med2, med3 = g["VM2"].median(), g["VM3"].median()
        ok = ((g["VM2"] - med2).abs() < COLLAPSE_V) & ((g["VM3"] - med3).abs() < COLLAPSE_V)
        okv = ok.to_numpy()
        t = g["t_utc"].to_numpy()
        if okv.any():
            first, last = int(np.argmax(okv)), int(len(okv) - 1 - np.argmax(okv[::-1]))
            if first > 0 and (t[first] - t[0]) / np.timedelta64(1, "s") <= COLLAPSE_MAX_S:
                keep[pos:pos + first] = False
            if last < n - 1 and (t[-1] - t[last]) / np.timedelta64(1, "s") <= COLLAPSE_MAX_S:
                keep[pos + last + 1:pos + n] = False
        pos += n
    return run[keep].copy(), int((~keep).sum())


def level_shifts(series, floor, span=2, merge_s=5.0, mask_times=(), mask_s=6.0):
    """Change points of a 1 s-median series: |x(t+span) - x(t-span)| above max(3 MAD, floor), merged within merge_s."""
    s = series.interpolate(limit=3)
    d = s.shift(-span) - s.shift(span)
    for tt in mask_times:
        d[np.abs((d.index - tt).total_seconds()) <= mask_s] = np.nan
    mad = np.nanmedian(np.abs(d - np.nanmedian(d))) * 1.4826 if d.notna().any() else np.nan
    thr = max(3 * (mad if np.isfinite(mad) else 0), floor)
    hits = d[np.abs(d) > thr]
    group, last = [], None
    for t, v in hits.items():
        if last is None or (t - last).total_seconds() > merge_s:
            group.append([t, float(v)])
        elif abs(v) > abs(group[-1][1]):
            group[-1] = [t, float(v)]
        last = t
    return group, thr


def mismatch_events(run):
    """PV cases: in closed loop the module voltages stay equal, so a shade shows in the module-current mismatch
    (max_k |I_k - I_str|, reconstructed by KCL) and in the string power. Returns event dicts: mismatch_on / mismatch_off
    (mismatch grows / shrinks) and irradiance_up / irradiance_down (string power), each with the 4 s change in detail."""
    ev = []
    if "IM1" not in run or run["Istr_i"].isna().all():
        return ev
    s = run.set_index("t_utc")
    mis = pd.concat([(s[f"IM{k}"] - s["Istr_i"]).abs() for k in (1, 2, 3)], axis=1).max(axis=1)
    m = pd.DataFrame({"mis": mis, "act": s["id1"].abs() + s["id2"].abs(), "P": s["Pstr_i"], "id1": s["id1"], "id2": s["id2"]}).resample("1s").median()
    gaps = run.loc[run["t_utc"].diff().dt.total_seconds() > events.GAP_S, "t_utc"].tolist()
    starts = [run["t_utc"].iat[0]]
    # shuffling activity |i_sh1| + |i_sh2| (direct, low noise) over 6 s; the KCL mismatch is quoted beside it
    for t, v in level_shifts(m["act"], floor=0.3, span=3, mask_times=gaps + starts)[0]:
        dm = float(m["mis"].shift(-3).get(t, np.nan) - m["mis"].shift(3).get(t, np.nan))
        ev.append(events._ev(t, "mismatch_on" if v > 0 else "mismatch_off",
                             f"|i_sh1|+|i_sh2| {v:+.2f} A over 6 s; max|I_k - I_str| {dm:+.2f} A", v, "detector"))
    for t, v in level_shifts(m["P"], floor=4.0, mask_times=gaps + starts)[0]:
        ev.append(events._ev(t, "irradiance_up" if v > 0 else "irradiance_down", f"P_string {v:+.1f} W over 4 s", v, "detector"))
    return ev


def clean_run(w):
    """RUN_OL / RUN_CL rows of a loaded case with the stale-value rules applied. Returns (frame, info dict)."""
    tel = w["tel"]
    spec = w["spec"]
    run = tel[tel["state"].fillna("").str.startswith("RUN")].copy()
    n_run = len(run)
    run = run[~run["t_utc"].duplicated(keep="first")]
    n_dup = n_run - len(run)
    frozen = (run[RUN_ONLY_FIELDS].diff().abs().sum(axis=1) == 0) & run[RUN_ONLY_FIELDS].notna().all(axis=1)
    frozen.iloc[0] = False
    run = run[~frozen].copy()
    n_frozen = int(frozen.sum())
    run, n_collapse = trim_collapse(run)
    # the controller's supervisory outputs are written only while closed: elsewhere the frame repeats the last RUN_CL value
    ol = ~run["state"].str.startswith("RUN_CL")
    for c in CL_ONLY_FIELDS:
        if c in run:
            run.loc[ol, c] = np.nan
    # VM1: the firmware's VM1 is the e-load voltage pushed at 2 Hz minus U11; take the 5 Hz e-load directly when they disagree
    info = {"n_run_rows": n_run, "n_duplicate_rows": n_dup, "n_frozen_rows": n_frozen, "n_collapse_rows": n_collapse}
    if "Vel_i" in run and run["Vel_i"].notna().any():
        run["VM1_est"] = run["Vel_i"] - run["VM2"] - run["VM3"]
        dev = (run["VM1"] - run["VM1_est"]).abs().median()
        info["vm1_dev_median_V"] = float(dev)
        if not np.isfinite(dev) or dev > VM1_TOL_V:
            run["VM1_tel"] = run["VM1"]
            run["VM1"] = run["VM1_est"]
            info["vm1_source"] = "e-load V - VM2 - VM3 (telemetry VM1 invalid)"
        else:
            info["vm1_source"] = "telemetry (e-load V via Pi, 2 Hz)"
        run["Vstr"] = run["VM1"] + run["VM2"] + run["VM3"]
        run["vd1"] = run["VM1"] - run["VM2"]
    else:
        info["vm1_source"] = "telemetry (no e-load log)"
    for k in (1, 2):
        run[f"uc{k}"] = run[f"dA{k}"] + run[f"dB{k}"] - 1
        run[f"ud{k}"] = run[f"dA{k}"] - run[f"dB{k}"]
    run = kcl_module_currents(run)
    run = powers(run)
    t0 = pd.Timestamp(spec["start"]).tz_localize(config.LOCAL_TZ)
    run["t_s"] = (run["t_utc"] - t0).dt.total_seconds()
    run["t_local"] = run["t_utc"].dt.tz_convert(config.LOCAL_TZ)
    dt = run["t_utc"].diff().dt.total_seconds()
    info["dt_median_ms"] = float(dt.median() * 1e3)
    info["rate_hz"] = float(1 / dt.median()) if dt.median() > 0 else np.nan
    info["run_seconds"] = float(dt[dt < events.GAP_S].sum())
    info["kscale_seen"] = sorted(set(run["kscale"].dropna().round(3)))
    info["pver_seen"] = sorted(set(run["pver"].dropna()))
    info["states_seen"] = sorted(set(run["state"]))
    run.attrs.update(cid=w["cid"], phase="hardware", setup=spec["setup"], f_khz=spec["f_khz"], loop=spec["loop"],
                     kscale=spec["kscale"], **info)
    return run.reset_index(drop=True), info


def run_frame(cid):
    """Cleaned RUN-only frame of a test case (cached)."""
    w = case(cid)
    if "run" not in w:
        w["run"], w["run_info"] = clean_run(w)
    return w["run"]


def run_segments(cid):
    """Contiguous RUN segments (state, kscale, pver; gaps > 2 s) of the cleaned frame with settled statistics."""
    seg = events.segments(run_frame(cid))
    seg = seg[seg["state"].isin(events.RUN_STATES)].copy()
    seg["cid"] = cid
    return seg
