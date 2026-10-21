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
