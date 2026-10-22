PY := python3
.PHONY: all pull pull-cases hw events metrics ripple sims figures compare report test clean-out \
        carpark-validate mil-validate simulink-extra qspice-extra qspice simulink notebook

# everything short, in order (long MATLAB / QSPICE runs are separate targets whose outputs are picked up when present)
all: hw events metrics ripple figures compare report

pull:              # the older closed-loop windows (config.WINDOWS)
	$(PY) influx_pull.py
pull-cases:        # the presentation test cases (config.TEST_CASES) -> 8_Results/TestCases
	$(PY) influx_pull.py --cases
hw:                # clean RUN-only frames, inventory T1, overview figure per case
	$(PY) hwcases.py --figures
events:            # event zoom figures (events + segments are built by hw)
	$(PY) figures.py --events
metrics:           # T2 steady state, T3 events, T7 energy
	$(PY) hwmetrics.py
ripple:            # T6 switching ripple (analytical, QSPICE incl. one raw read per frequency, hardware noise)
	$(PY) ripple.py
figures:           # per-run simulation figures (analytical, QSPICE, carpark scenarios, validate suites)
	$(PY) figures.py --sims analytical,qspice,simulink,validate
compare:           # T4 simulation metrics, T5 cross-phase, G matrices, comparison + energy figures
	$(PY) compare.py
report:
	$(PY) report.py
test:
	$(PY) -c "import importlib.util,sys,glob; [ (lambda s: (lambda m: (s.loader.exec_module(m), [getattr(m,n)() for n in dir(m) if n.startswith('test_')]))(importlib.util.module_from_spec(s)))(importlib.util.spec_from_file_location('t', f)) for f in sorted(glob.glob('tests/test_*.py'))]; print('tests ok')"

# ---- long runs (MATLAB R2025b via matlab.exe -batch, QSPICE64.exe); each logs to out/logs/<name>.log
carpark-validate:  # 3-module validate suite: CSV/JSON per test -> out/sim/carpark_validate, PDF figures -> 4_Simulink/3_Carpark_3mod/figs
	$(PY) run_all.py --only carpark-validate
mil-validate:      # 4-module MIL validate suite (25-65 min) -> out/sim/mil_validate, 4_Simulink/1_MIL_Model_In_The_Loop/figs
	$(PY) run_all.py --only mil-validate
simulink-extra:    # carpark scenario runs at kscale 0.2 / 0.5 (about 25 min)
	$(PY) run_all.py --only simulink-extra
qspice-extra:      # QSPICE closed-loop cases at kscale 0.2 / 0.5 (about an hour)
	cd "../../2_Qspice/Claude's outputs" && $(PY) run_scenarios.py --case bench_k0.2 --case bench_k0.5 --case pv80_k0.2 --case pv80_k0.5 --parallel 4
qspice:            # the original kscale 0.1 / 0.3 / 1 QSPICE cases (hours)
	cd "../../2_Qspice/Claude's outputs" && $(PY) run_scenarios.py --all --parallel 4
simulink:          # the original carpark scenario runs (kscale 0.1 / 0.3 / 1)
	$(PY) run_all.py --only simulink
notebook:
	cd ../../3_Analytical/shuffler_notebooks && $(PY) build_nstring_notebook.py
clean-out:
	rm -rf out/hw out/events out/figures out/tables REPORT.md
