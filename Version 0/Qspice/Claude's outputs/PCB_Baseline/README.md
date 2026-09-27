# Qspice baseline of the Version 0 shuffler PCB

Everything in this folder is generated from `gen_shuffler.py`; nothing here edits the KiCad
project. The model follows the board as built: three Aiko modules in series, two identical
two-phase converters (STD45N10F7 half-bridges, TDK ERUC23-4R1K inverse-coupled inductor,
TMCS1126 current paths, 1ED3140 drivers with 10 R / 4R7 gate paths and VSSA210 bootstrap),
open loop at 50 % duty, 200 kHz, 200 ns dead time, both legs 180 degrees apart.

## The one file to open

`Version 0/Qspice/Shuffler_PCB_Baseline.qsch` (keep `shuffler_models.lib` beside it) is the complete
model on a single sheet, laid out by block with titles: reference string, PV string with cables, board
capacitors, converter 1, converter 2, PARAMETERS, SIMULATION, MEASUREMENTS. Every parasitic and every
setting (timing, loads, gate resistors, package/ESL/cable/copper lumps, placeholder footprints) is a
`.param` in the PARAMETERS block, so the sheet is edited in one place. It is electrically identical to
stage S7 and is regenerated with `python gen_shuffler.py --report --verify`; `python run_baseline.py REPORT`
simulates it and writes `results/REPORT.meas.json`. Hand edits and the generator do not mix: keep an edited copy
under another name, or change the generator and regenerate.

## Files

| file | what |
|---|---|
| `gen_shuffler.py` | the circuit, stage by stage; writes `shuffler_models.lib` and `stages/S*.qsch` + `S*.cir` |
| `qsch_writer.py` | writer for Qspice `.qsch` files (format notes in the docstring) |
| `pcb_parasitics.py` | reads the board file and writes `parasitics.json` (copper R/L per net, ballpark) |
| `parasitics.json` | the numbers used for stage S6+; hand-editable |
| `run_baseline.py` | runs QSPICE64 on every stage, collects `.meas` results with QPOST, makes SVG plots |
| `stages/` | one runnable schematic + netlist per Lego stage |
| `results/` | `baseline_table.md`, `*.meas.json`, SVG waveforms |
| `build_book.html` | the illustrated stage-by-stage walkthrough |

## Stages

| stage | adds | what you should see |
|---|---|---|
| S1 | PV string, bypass diodes, resistor / constant-current loads, reference string | MPP at 1000 W/m2: 115 V, 14.2 A, 1633 W; shaded module bypassed (-0.4 V) |
| S2 | module capacitance, four 130 uF board capacitors | same DC numbers, caps just add settling time |
| S3 | converter 1 (ideal 12 V gate pulses) | inductor currents, midpoint pulled toward the shaded module, shuffle current into PV2+ |
| S4 | converter 2 | both midpoints balanced, string power above the reference string when a module is shaded |
| S5 | 1ED3140 drivers, gate resistors, 12 V rails, bootstrap | 12 V gate pulses with the 200 ns dead time, bootstrap ripple |
| S6 | copper / package / ESL / cable parasitics (damped), snubber & HF footprints at 1 pF | finite switch-node ringing, gate loop ringing |
| S7 | full measurement set | the baseline table |
| S8 / S8b | snubber and HF-cap sweeps on the placeholder positions | overshoot and snubber power vs C and R |

## Run

```bash
python pcb_parasitics.py          # optional: refresh parasitics.json from the .kicad_pcb
python gen_shuffler.py --verify   # regenerate all stages and check each .qsch against its .cir
python gen_shuffler.py --report --verify   # regenerate ../Shuffler_PCB_Baseline.qsch (the single-sheet file)
python run_baseline.py            # simulate everything (or: python run_baseline.py REPORT S3 S4)
```

Open any `stages/S*.qsch` in Qspice to look at or edit a stage; the `.cir` next to it is the
same circuit as a netlist (QUX.exe -Netlist on the .qsch reproduces it, which is what
`--verify` checks). `--verify` also hands each netlist to QSPICE64 for a 20 ns run with the first and then the
last value of every `.step` list, so an undefined parameter, a bad value or an operating point that cannot be
found is reported before a real run.

## Steps inside each stage

`CASE` selects the irradiance pattern (1: 1000/1000/1000, 2: 1000/600/1000, 3: 1000/1000/400 W/m2)
and `LOADSEL` the bench load (0: resistor near the 3-module MPP, 1: 10 A constant-current sink).
S8 fixes CASE=2 / LOADSEL=0 and steps the snubber (`Csn`, `Rsn`) and HF-cap (`Chf`) values instead.

## Known approximations

* STD45N10F7 is an estimated VDMOS from datasheet headline numbers; replace the `.model` line in
  `shuffler_models.lib` with the one from Qspice's MOSFET generator when you have it.
* The 1ED3140 is behavioural (delay, output resistances, interlock, UVLO), not the vendor model.
* Copper parasitics are per-net lumps from track lengths and pour bounding boxes (see
  `pcb_parasitics.py`); component ESR/ESL and cable values are typed-in ballparks.
* One bypass diode per module; the sensor's output side is not modelled.
* The PV power law is clamped at 0 V (`pvmi`); the untouched original is `pvmi_orig`. Without the clamp
  a bypassed module made Qspice crawl at picosecond timesteps.
* Every parasitic inductance has a parallel damping resistor (5 Ω board, 50 Ω cable); the snubber / HF-cap
  footprints are kept in the S6/S7 netlists at 1 pF ("not fitted"). Both are needed for the solver to get
  through the parasitic stages; neither changes the answers at the ballpark level.
* The current-sink load is 10 A: with one converter and the middle module at 600 W/m2 the string cannot
  hold 12 A (no steady state, inductor current runs away). The sink ramps up over the first 200 us; a 10 A step
  at t = 0 broke the operating point of the single-sheet file.
* Each 1ED3140 draws 0.6 mA quiescent (20 k across its supply): the real part does, and without it the bootstrap
  nodes have no DC path and the operating point is singular.
* Symbol labels follow Qspice's own conventions for rotated and mirrored parts (justification codes and offsets
  as Qspice writes them), read off the hand-drawn sheets in `Version 0/Qspice`.
