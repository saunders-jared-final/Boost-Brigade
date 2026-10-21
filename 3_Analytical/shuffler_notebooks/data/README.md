# data/ — QSPICE and switching-twin evidence behind `shuffler_nstring.ipynb` section 8

| file | produced by | content |
|---|---|---|
| `qspice_ud_sweep.json` / `.npz` | `../qspice_ud_sweep.py` (QSPICE, bench S10i / S10i4 netlists, 2 ms open loop) | settled `ic1`, `im1`, `vd1`, ripple pp of the winding currents for `u_d` steps 0.0025 … 0.08 on shuffler 1 at 200 and 400 kHz, the RUN 1 baselines and a `u_c` step; the `.npz` holds two switching periods of `iA1`/`iB1` and the first millisecond of `vd1`, `vd2`, `ic1`, `im1` per case |
| `qspice_ideal_switch.json` | `../qspice_ideal_switch.py` | the same baseline and `u_d = 0.01` runs with the STD45N10F7 model idealised in the case-local library: `norr` (no body-diode reverse recovery), `nocap` (no device capacitances either) |
| `nswitch_static.json` | notebook section 8.3 / `nswitch.static_characteristic` | the switching twin's settled `ic`, `im`, `vd` for the same `u_d` steps, ideal switches and with a 2.2 nF pole capacitance, 200 and 400 kHz |
| `work_*/` (git-ignored) | the two QSPICE scripts | per-case `.cir`, library and DLL copies and the QSPICE log; `.qraw` files are deleted after extraction |

Rerun order: `python3 qspice_ud_sweep.py --parallel 4` (about 8 min), `python3 qspice_ideal_switch.py` (about 5 min),
then `python3 build_nstring_notebook.py`.
