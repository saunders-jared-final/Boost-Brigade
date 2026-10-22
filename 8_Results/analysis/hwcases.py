#!/usr/bin/env python3
"""Hardware test cases of the presentation: clean RUN-only frames, segments and the inventory table.

    python3 hwcases.py [--only B06] [--figures]

Writes out/hw/<cid>_<label>.csv (RUN rows only, stale values removed, derived signals, KCL module currents, powers),
out/hw/segments.csv (every RUN segment with settled statistics) and out/tables/T1_inventory.{csv,md}.
"""
import argparse
import os

import pandas as pd

import config
import events
from phases import hardware as hw

HW_DIR = os.path.join(config.OUT, "hw")
TAB = os.path.join(config.OUT, "tables")
KEEP = ["t_utc", "t_local", "t_s", "state", "kscale", "pver", "VM1", "VM2", "VM3", "Vstr", "vd1", "vd2", "ILA1", "ILB1", "ILA2", "ILB2",
        "ic1", "ic2", "id1", "id2", "dA1", "dB1", "dA2", "dB2", "uc1", "ud1", "uc2", "ud2", "rv1", "rv2", "beta", "stress", "IM1r", "IM2r",
        "IM1r_calc", "IM2r_calc", "IM1", "IM2", "IM3", "IM1_chk", "Imean_chk", "Vel", "Istr", "Pstr", "Vel_i", "Istr_i", "Pstr_i",
        "el_mode", "el_setpoint", "P_M1", "P_M2", "P_M3", "P_mod", "P_sh1", "P_sh2", "P_sh", "P_ret", "eff", "T1", "T2", "T3", "fault", "VM1_est", "VM1_tel"]


def inventory_row(cid):
    w = hw.case(cid)
    spec = w["spec"]
    run = hw.run_frame(cid)
    info = w["run_info"]
    seg = hw.run_segments(cid)
    ev = w["events"]
    kinds = ev["kind"].value_counts().to_dict()
    imean = (run["Istr_i"] - run["Imean_chk"]).abs().median() if "Imean_chk" in run else float("nan")
    return {"cid": cid, "slide": spec["slide"] or "", "day": spec["day"], "setup": spec["setup"], "f_khz": spec["f_khz"], "loop": spec["loop"],
            "kscale_spec": spec["kscale"] if spec["kscale"] is not None else "", "kscale_seen": ("/".join(f"{k:g}" for k in info["kscale_seen"]) if spec["loop"] == "CL" else "-"),
            "pver": "; ".join(p.replace("sps-params-2.", "") for p in info["pver_seen"]),
            "window_local": f"{spec['start'][11:]}-{spec['stop'][11:]}", "states": "/".join(info["states_seen"]),
            "run_segments": len(seg), "run_seconds": round(info["run_seconds"], 1), "frames": info["n_run_rows"],
            "rate_hz": round(info["rate_hz"], 1), "frozen_dropped": info["n_frozen_rows"], "vm1_source": info["vm1_source"],
            "vm1_dev_V": round(info.get("vm1_dev_median_V", float("nan")), 2),
            "eload_rows": int(w["eload"]["p"].notna().sum()) if len(w["eload"]) and "p" in w["eload"] else 0,
            "events": ", ".join(f"{k} x{v}" for k, v in sorted(kinds.items()) if k in ("close", "kscale_apply", "duty_step", "load_step", "mismatch_on", "mismatch_off", "irradiance_up", "irradiance_down", "fault")),
            "collapse_dropped": info["n_collapse_rows"], "mean_identity_A": round(float(imean), 3), "note": spec["note"]}


def inventory_md(df):
    cols = ["cid", "slide", "setup", "f_khz", "loop", "kscale_seen", "window_local", "run_segments", "run_seconds", "frames", "rate_hz", "frozen_dropped",
            "vm1_source", "events", "note"]
    head = {"cid": "case", "slide": "slide", "setup": "setup", "f_khz": "f_sw [kHz]", "loop": "loop", "kscale_seen": "kscale (telemetry)", "window_local": "window (local)",
            "run_segments": "RUN segs", "run_seconds": "RUN [s]", "frames": "frames", "rate_hz": "rate [Hz]", "frozen_dropped": "frozen dropped",
            "vm1_source": "VM1 source", "events": "events in window", "note": "note"}
    lines = ["| " + " | ".join(head[c] for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only")
    ap.add_argument("--figures", action="store_true")
    a = ap.parse_args()
    os.makedirs(HW_DIR, exist_ok=True)
    os.makedirs(TAB, exist_ok=True)
    rows, segs = [], []
    for cid in config.TEST_CASES:
        if a.only and a.only not in cid:
            continue
        run = hw.run_frame(cid)
        run[[c for c in KEEP if c in run]].to_csv(os.path.join(HW_DIR, config.case_name(cid) + ".csv"), index=False, float_format="%.5g")
        rows.append(inventory_row(cid))
        segs.append(hw.run_segments(cid))
        r = rows[-1]
        print(f"{cid}: {r['run_segments']} RUN seg, {r['run_seconds']} s, {r['frames']} frames @ {r['rate_hz']} Hz, frozen {r['frozen_dropped']}, "
              f"collapse {r['collapse_dropped']}, VM1 {r['vm1_source']}, events: {r['events']}")
        if a.figures:
            import figures
            figures.hardware_overview(cid)
    inv = pd.DataFrame(rows)
    if not a.only:
        inv.to_csv(os.path.join(TAB, "T1_inventory.csv"), index=False)
        open(os.path.join(TAB, "T1_inventory.md"), "w").write(inventory_md(inv))
        pd.concat(segs, ignore_index=True).to_csv(os.path.join(HW_DIR, "segments.csv"), index=False)


if __name__ == "__main__":
    main()
