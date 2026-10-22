"""Energy of the solar (and bench) RUN segments from the cleaned hardware frames.

Definitions (all from 1 s means of the cleaned RUN frame, so the noisy 45 Hz current samples average out; the e-load
power is logged at 5 Hz):
  E_load      = sum P_string dt            energy delivered to the DL3021 (its own v*i)
  E_mod       = sum (sum_k VM_k I_k) dt    energy produced by the modules, I_k rebuilt by KCL from the winding currents,
                                           duties and the string current (phases/hardware.kcl_module_currents)
  E_shuffled  = sum (sum_j |i_sh,j| Vbar_j/2) dt   energy processed through the shufflers
  E_returned  = sum (I_str - max(min_k I_k, 0)) V_str dt   energy the load received above a string limited to its
                                           weakest module (what series modules without shufflers would deliver at
                                           the same string voltage; never above E_load) = the DPP benefit
  efficiency  = E_load / E_mod
"""
import numpy as np
import pandas as pd

import config
from phases import hardware as hw

COLS_1S = ["VM1", "VM2", "VM3", "ILA1", "ILB1", "ILA2", "ILB2", "id1", "id2", "ic1", "ic2", "IM1", "IM2", "IM3", "Istr_i", "Vel_i", "Pstr_i",
           "P_mod", "P_sh1", "P_sh2", "P_sh"]


def means_1s(run):
    s = run.set_index("t_utc")[[c for c in COLS_1S if c in run]].astype(float)
    m = s.resample("1s").mean()
    m["n"] = s["VM2"].resample("1s").count()
    m = m[m["n"] >= 3]                                  # bins with real RUN data only
    return m


def integrate(m):
    """Energies [J] and mean powers [W] of a 1 s-mean table."""
    dt = 1.0
    P_load = m["Pstr_i"]
    P_mod = m["VM1"] * m["IM1"] + m["VM2"] * m["IM2"] + m["VM3"] * m["IM3"]
    imin = m[["IM1", "IM2", "IM3"]].min(axis=1).clip(lower=0)     # a series string cannot carry less than zero
    P_ret = ((m["Istr_i"] - imin) * m["Vel_i"]).clip(lower=0)
    P_sh = m["id1"].abs() * (m["VM1"] + m["VM2"]) / 2 + m["id2"].abs() * (m["VM2"] + m["VM3"]) / 2
    ok = P_load.notna() & P_mod.notna()
    n = int(ok.sum())
    if n == 0:
        return {}
    out = {"seconds": n * dt, "E_load_J": float(P_load[ok].sum() * dt), "E_mod_J": float(P_mod[ok].sum() * dt),
           "E_shuffled_J": float(P_sh[ok].sum() * dt), "E_returned_J": float(P_ret[ok].clip(lower=0).sum() * dt),
           "P_load_W": float(P_load[ok].mean()), "P_mod_W": float(P_mod[ok].mean()), "P_shuffled_W": float(P_sh[ok].mean()),
           "P_returned_W": float(P_ret[ok].clip(lower=0).mean()), "P_returned_max_W": float(P_ret[ok].max()),
           "I_str_A": float(m["Istr_i"][ok].mean()), "V_str_V": float(m["Vel_i"][ok].mean()),
           "I_M1_A": float(m["IM1"][ok].mean()), "I_M2_A": float(m["IM2"][ok].mean()), "I_M3_A": float(m["IM3"][ok].mean()),
           "I_min_A": float(imin[ok].mean()), "i_sh1_A": float(m["id1"][ok].mean()), "i_sh2_A": float(m["id2"][ok].mean())}
    out["efficiency"] = out["E_load_J"] / out["E_mod_J"] if out["E_mod_J"] > 0 else np.nan
    out["returned_frac"] = out["E_returned_J"] / out["E_load_J"] if out["E_load_J"] > 0 else np.nan
    out["E_load_Wh"] = out["E_load_J"] / 3600
    out["E_returned_Wh"] = out["E_returned_J"] / 3600
    out["E_shuffled_Wh"] = out["E_shuffled_J"] / 3600
    return out


def case_energy(cid, per_segment=True):
    """Rows: one per RUN segment (> 10 s) and one for the whole case."""
    spec = config.TEST_CASES[cid]
    run = hw.run_frame(cid)
    rows = []
    segs = hw.run_segments(cid) if per_segment else pd.DataFrame()
    for _, s in segs.iterrows():
        if s["duration_s"] < 10:
            continue
        g = run[(run["t_utc"] >= pd.Timestamp(s["start_utc"])) & (run["t_utc"] <= pd.Timestamp(s["end_utc"]))]
        e = integrate(means_1s(g))
        if e:
            rows.append({"cid": cid, "setup": spec["setup"], "f_khz": spec["f_khz"], "loop": spec["loop"], "state": s["state"], "kscale": s["kscale"],
                         "start_local": s["start_local"][11:19], "scope": "segment", **e})
    e = integrate(means_1s(run))
    if e:
        rows.append({"cid": cid, "setup": spec["setup"], "f_khz": spec["f_khz"], "loop": spec["loop"], "state": "/".join(sorted(set(run["state"]))),
                     "kscale": spec["kscale"], "start_local": spec["start"][11:], "scope": "case", **e})
    return rows


def window_energy(cid, t0, t1):
    """Energies between two UTC timestamps of one case (e.g. a shade event)."""
    run = hw.run_frame(cid)
    g = run[(run["t_utc"] >= t0) & (run["t_utc"] <= t1)]
    return integrate(means_1s(g))
