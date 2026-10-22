"""Shared configuration of the results-synthesis pipeline (paths, windows, scenarios, control constants)."""
import datetime as dt
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
RESULTS = os.path.join(REPO, "8_Results")
OUT = os.path.join(HERE, "out")
TOOLS = os.path.join(REPO, "7_Pi", "tools")
PCB_BASELINE = os.path.join(REPO, "2_Qspice", "Claude's outputs", "PCB_Baseline")
QSPICE_OUT = os.path.join(REPO, "2_Qspice", "Claude's outputs")
CTRL_PARAMS = os.path.join(REPO, "6_RTOS", "ctrl_core", "params")
NOTEBOOKS = os.path.join(REPO, "3_Analytical", "shuffler_notebooks")
LOCAL_TZ = dt.timezone(dt.timedelta(hours=10), "AEST")

# ---------------------------------------------------------------- control stack constants (6_RTOS/ctrl_core)
TS = 100e-6                     # control tick
KI_V = 2 * 3.141592653589793 * 150   # integral gain of the voltage-difference loops (G M = diag(kI))
KI_I = 2 * 3.141592653589793 * 400   # integral gain of the circulating-current loops
KP_RATIO_V = 1.58e-4
KP_RATIO_I = 1.08e-4
FC_LPF = 2000.0
TELEMETRY_HZ = 50.0

# ---------------------------------------------------------------- hardware windows to pull (local AEST times)
# name -> (folder under 8_Results, from, to, note). Each window is pulled with MARGIN_S on both sides so the
# open-loop baseline and the C,SET,kscale / C,APPLY before a run are inside.
MARGIN_S = 60
WINDOWS = {
    # bench, 16 Oct 2026: NGE103 PSUs with unbalanced limits into the DL3021 (CV 70 V)
    "Bench CL 16Oct qspice200 1525-1609": ("Bench_Closed_Loop_200kHz", "2026-10-16T15:25:00", "2026-10-16T16:09:00",
                                           "every 200 kHz closed-loop attempt (gains 10-30 %), several end in FAULT"),
    "Bench CL 16Oct run 1550-1553":       ("Bench_Closed_Loop_200kHz", "2026-10-16T15:49:30", "2026-10-16T15:53:30",
                                           "good run, gain 20 %"),
    "Bench CL 16Oct run 1602-1605":       ("Bench_Closed_Loop_200kHz", "2026-10-16T16:01:00", "2026-10-16T16:05:00",
                                           "good run, gain 20 % with the ADC phase-B reduction"),
    "Bench CL 16Oct qspice300 1716-1742": ("Bench_Closed_Loop_200kHz", "2026-10-16T17:16:00", "2026-10-16T17:42:00",
                                           "300 kHz image, gains 30 / 50 %"),
    "Bench CL 16Oct qspice400 1804-1819": ("Bench_Closed_Loop_200kHz", "2026-10-16T18:04:00", "2026-10-16T18:19:00",
                                           "400 kHz image, gain 30 %"),
    # carpark solar, 20 Oct 2026: 3 x KAUSSP80 into the DL3021 (CV)
    "Solar OL+CL 20Oct 1252-1313":        ("Solar_Closed_Loop", "2026-10-20T12:52:00", "2026-10-20T13:13:00",
                                           "first closed-loop runs; shirt on module 3 and a person walking round the panels"),
    "Solar CL 20Oct 1508-1513":           ("Solar_Closed_Loop", "2026-10-20T15:08:00", "2026-10-20T15:13:30",
                                           "peak sun, kscale 0.1"),
    "Solar CL 20Oct 1515-1518":           ("Solar_Closed_Loop", "2026-10-20T15:15:00", "2026-10-20T15:18:00",
                                           "short run after a kscale step up"),
    "Solar CL 20Oct kscale sweep 1551-1626": ("Solar_Closed_Loop", "2026-10-20T15:51:00", "2026-10-20T16:26:00",
                                           "kscale 0.1 .. 0.8, each level a fresh OL -> CL engagement"),
}
# whole-day command logs (cheap, and the only complete record of what was pressed / sent)
DAY_LOGS = {
    "Bench 16Oct": ("Bench_Closed_Loop_200kHz", "2026-10-16T09:00:00", "2026-10-16T19:00:00"),
    "Solar 20Oct": ("Solar_Closed_Loop", "2026-10-20T12:00:00", "2026-10-20T17:00:00"),
}
AUX = {                      # measurement -> tags (pivot row key besides _time)
    "cmd": ["source", "dir"],
    "params": ["source", "pver"],
    "fault": ["source", "channel"],
    "status": ["source", "state", "mode"],
    "note": ["source"],
}

# ---------------------------------------------------------------- test cases = the raw-data slides of the presentation
# 0_Documentation/n11034459_CapstoneDelivery_V2.pdf: each raw-data slide is four Grafana panels over one time range
# (local AEST, read off the panel headers). The analysis is keyed to these windows; only RUN_OL / RUN_CL rows are used.
# id -> dict(slide page, day, f_khz, loop OL/CL, kscale, start, stop, label (file-name safe), note)
CASES_FOLDER = "TestCases"
CASE_MARGIN_S = 5
TEST_CASES = {
    # bench, 16 Oct 2026: NGE103 channels (25 V set, limits 0.8/1.0/1.3 A; the middle channel current-limited) into the DL3021 in CV
    "B01":  dict(slide=48, day="2026-10-16", f_khz=200, loop="OL", kscale=None, start="2026-10-16T14:32:00", stop="2026-10-16T14:44:56",
                 label="bench_200k_OL", setup="BENCH", note="duties 0.5; e-load CV set-point steps 125 <-> 60 V; VM1 from the e-load"),
    "B01s": dict(slide=None, day="2026-10-16", f_khz=200, loop="OL", kscale=None, start="2026-10-16T15:09:00", stop="2026-10-16T15:16:00",
                 label="bench_200k_OL_dutysteps", setup="BENCH",
                 note="not on a slide: the only open-loop duty steps (15:11:42 S2 +0.02/leg, 15:13:00 S1 & S2 -0.01/leg, 15:15:15 S1 +0.02/leg); ends in FAULT"),
    "B02":  dict(slide=42, day="2026-10-16", f_khz=200, loop="CL", kscale=0.1, start="2026-10-16T15:31:34", stop="2026-10-16T15:34:25",
                 label="bench_200k_CL_k0.1", setup="BENCH", note="before the ADC fix; PSU unstable"),
    "B03":  dict(slide=43, day="2026-10-16", f_khz=200, loop="CL", kscale=0.3, start="2026-10-16T16:02:05", stop="2026-10-16T16:04:33",
                 label="bench_200k_CL_k0.3b", setup="BENCH", note="slide says kscale 20 %, telemetry says 0.3 with pset 0 (boot default after the re-flash for the ADC phase-B fix; no SET/APPLY sent)"),
    "B04":  dict(slide=44, day="2026-10-16", f_khz=200, loop="CL", kscale=0.3, start="2026-10-16T16:07:00", stop="2026-10-16T16:07:49",
                 label="bench_200k_CL_k0.3", setup="BENCH", note="kscale 0.4 applied at 16:07:50 -> OC fault within 1 s"),
    "B05":  dict(slide=49, day="2026-10-16", f_khz=300, loop="OL", kscale=None, start="2026-10-16T16:31:36", stop="2026-10-16T16:37:04",
                 label="bench_300k_OL", setup="BENCH", note=""),
    "B06":  dict(slide=45, day="2026-10-16", f_khz=300, loop="CL", kscale=0.3, start="2026-10-16T17:17:00", stop="2026-10-16T17:25:49",
                 label="bench_300k_CL_k0.3", setup="BENCH", note="PSU / e-load set-point steps 17:22:30-17:25:30 while closed"),
    "B07":  dict(slide=46, day="2026-10-16", f_khz=300, loop="CL", kscale=0.5, start="2026-10-16T17:34:08", stop="2026-10-16T17:41:47",
                 label="bench_300k_CL_k0.5", setup="BENCH", note=""),
    "B08":  dict(slide=50, day="2026-10-16", f_khz=400, loop="OL", kscale=None, start="2026-10-16T18:02:03", stop="2026-10-16T18:04:38",
                 label="bench_400k_OL", setup="BENCH", note="PSU change at 18:03:40"),
    "B09":  dict(slide=47, day="2026-10-16", f_khz=400, loop="CL", kscale=0.3, start="2026-10-16T18:05:11", stop="2026-10-16T18:13:40",
                 label="bench_400k_CL_k0.3", setup="BENCH", note=""),
    # carpark solar, 20 Oct 2026: 3 x KAUSSP80 into the DL3021 in CV (about 61 V)
    "S01":  dict(slide=24, day="2026-10-20", f_khz=200, loop="OL", kscale=None, start="2026-10-20T15:04:35", stop="2026-10-20T15:07:47",
                 label="solar_200k_OL_peak", setup="PV80", note="peak sun"),
    "S02":  dict(slide=25, day="2026-10-20", f_khz=200, loop="CL", kscale=0.1, start="2026-10-20T15:08:40", stop="2026-10-20T15:12:44",
                 label="solar_200k_CL_k0.1_peak", setup="PV80", note="peak sun; shade event about 15:09:20-15:10:40"),
    "S03":  dict(slide=26, day="2026-10-20", f_khz=200, loop="OL", kscale=None, start="2026-10-20T15:48:22", stop="2026-10-20T15:51:20",
                 label="solar_200k_OL_min", setup="PV80", note="minimal sun"),
    "S04":  dict(slide=27, day="2026-10-20", f_khz=200, loop="CL", kscale=0.1, start="2026-10-20T15:52:03", stop="2026-10-20T15:56:31",
                 label="solar_200k_CL_k0.1_min", setup="PV80", note="minimal sun"),
    "S05":  dict(slide=37, day="2026-10-20", f_khz=200, loop="CL", kscale=0.2, start="2026-10-20T15:56:51", stop="2026-10-20T16:00:47",
                 label="solar_200k_CL_k0.2_min", setup="PV80", note="minimal sun"),
    "S06":  dict(slide=38, day="2026-10-20", f_khz=200, loop="CL", kscale=0.3, start="2026-10-20T16:01:07", stop="2026-10-20T16:04:19",
                 label="solar_200k_CL_k0.3_min", setup="PV80", note="minimal sun"),
    "S07":  dict(slide=39, day="2026-10-20", f_khz=200, loop="CL", kscale=0.4, start="2026-10-20T16:05:30", stop="2026-10-20T16:08:17",
                 label="solar_200k_CL_k0.4_min", setup="PV80", note="minimal sun"),
    "S08":  dict(slide=40, day="2026-10-20", f_khz=200, loop="CL", kscale=0.5, start="2026-10-20T16:09:42", stop="2026-10-20T16:12:16",
                 label="solar_200k_CL_k0.5_min", setup="PV80", note="minimal sun"),
    "S09":  dict(slide=None, day="2026-10-20", f_khz=200, loop="CL", kscale=0.6, start="2026-10-20T16:13:15", stop="2026-10-20T16:18:00",
                 label="solar_200k_CL_k0.6_min", setup="PV80", note="not on a slide (closed_loop_timeslots.pdf)"),
    "S10":  dict(slide=None, day="2026-10-20", f_khz=200, loop="CL", kscale=0.7, start="2026-10-20T16:19:05", stop="2026-10-20T16:22:12",
                 label="solar_200k_CL_k0.7_min", setup="PV80", note="not on a slide (closed_loop_timeslots.pdf)"),
    "S11":  dict(slide=None, day="2026-10-20", f_khz=200, loop="CL", kscale=0.8, start="2026-10-20T16:23:05", stop="2026-10-20T16:24:45",
                 label="solar_200k_CL_k0.8_min", setup="PV80", note="not on a slide (closed_loop_timeslots.pdf)"),
}


def case_name(cid):
    """File-name stem of a test case's exports in 8_Results/TestCases."""
    return f"{cid}_{TEST_CASES[cid]['label']}"


# ---------------------------------------------------------------- one source of phase labels / colours for tables and figures
PHASE_STYLE = {
    "analytical":   dict(label="Analytical N=3 (nstring)",          color="#6b6b6b", ls="-"),
    "simulink_mil": dict(label="Simulink MIL (4 modules)",          color="#8e6bbf", ls="-"),
    "simulink":     dict(label="Simulink carpark twin (3 modules)", color="#1f6b46", ls="-"),
    "qspice":       dict(label="QSPICE switching + firmware DLL",   color="#1b2d55", ls="-"),
    "hardware":     dict(label="Hardware",                          color="#d9822b", ls="none"),
}
SETUP_STYLE = {"BENCH": dict(label="bench (NGE103 PSUs)", color="#d9822b"), "PV80": dict(label="carpark PV (3 x 80 W)", color="#c0392b")}

# ---------------------------------------------------------------- matched scenarios
SCENARIOS = {
    "S1": dict(name="loop_close", event="close", signals=["vd2", "ic2", "id2", "vd1", "ic1"], ref=0.0,
               note="OL -> CL on the existing module mismatch at kscale k"),
    "S2": dict(name="kscale", event="segment", signals=["vd2", "ic2", "dA2"],
               note="settled statistics per kscale level"),
    "S3": dict(name="shade_m3", event="shade_on", signals=["vd2", "id2", "VM3", "Pstr"],
               note="module 3 shaded to about 2/3 from a settled closed loop"),
    "S4": dict(name="vref2_step", event="vref", signals=["vd2", "ic2"], ref=1.0,
               note="+1 V step on the VM2-VM3 reference from a settled state (simulations only)"),
}
