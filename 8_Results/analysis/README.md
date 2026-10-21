# Results synthesis (`8_Results/analysis`)

One pipeline that turns every phase of the project into the same control metrics on matched scenarios and writes
`REPORT.md`: the analytical N-module model, the Simulink models (4-module MIL, 3-module carpark), the QSPICE switching
model with the firmware DLL, the 16 Oct bench and the 20 Oct PV day.

| step | command | what |
|---|---|---|
| pull | `make pull` | closed-loop windows from the Pi's InfluxDB (telemetry in all states, e-load, command / parameter / fault / status / note logs) into `8_Results/Bench_Closed_Loop_200kHz` and `Solar_Closed_Loop`; windows in `config.py` |
| events | `make events` | `out/events/<window>.events.csv` (state transitions, commands, kscale changes, shade candidates), `.segments.csv` (runs with settled statistics), `.png` overview |
| qspice | `make qspice` | `2_Qspice/Claude's outputs/run_scenarios.py`: bench and PV80 stage netlists patched per scenario, run in parallel, converted to `out/qspice/<case>.csv` (100 us bin means) |
| simulink | `make simulink` | `4_Simulink/3_Carpark_3mod/run_scenarios.m` headless (`matlab.exe -batch`): `out/sim/carpark/*.csv`, `out/sim/mil/*.csv` |
| notebook | `make notebook` | builds and executes `3_Analytical/shuffler_notebooks/shuffler_nstring.ipynb` from `nstring.py` |
| compare | `make compare` | `compare.py`: one metric definition (`stepmetrics.py`) on every phase -> `out/tables/S1..S4*.md/.csv`, `G_compare.md`, overlays in `out/figures/` |
| report | `make report` | `REPORT.md` |
| test | `make test` | unit tests of the metric definition (synthetic first / second-order steps at 10 kHz and 50 Hz) |

`python3 run_all.py` runs pull -> events -> compare -> report (add `--with qspice,simulink` for the long stages).
Hand annotations of the detected shade events go in `out/events/<window>.annot.csv` (`time_local,kind,label`) and are merged on the next `make events`.

Phase loaders live in `phases/` (`hardware.py`, `qspice.py`, `simulink.py`, `simulink_mil.py`, `analytical.py`); all produce the tidy format of
`tidy.py` (`t, VM1..3, vd1, vd2, ILA/ILB, ic, id, duties, rv, beta, stress, kscale, Vstr, Istr, Pstr, IM1..3, state` + attrs).
