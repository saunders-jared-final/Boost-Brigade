PY := python3
.PHONY: all pull events compare report notebook qspice simulink hw test

all: events compare report
pull:
	$(PY) influx_pull.py
events:
	$(PY) events.py --plot
compare:
	$(PY) compare.py
hw:
	$(PY) compare.py --phases hardware --scenarios S1,S2,S3
report:
	$(PY) report.py
notebook:
	cd ../../3_Analytical/shuffler_notebooks && $(PY) build_nstring_notebook.py
qspice:
	cd "../../2_Qspice/Claude's outputs" && $(PY) run_scenarios.py --all --parallel 4
simulink:
	$(PY) run_all.py --only simulink
test:
	$(PY) -c "import importlib.util,sys; s=importlib.util.spec_from_file_location('t','tests/test_stepmetrics.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); [getattr(m,n)() for n in dir(m) if n.startswith('test_')]; print('tests ok')"
