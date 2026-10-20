# Quasi-MPPT Curve Tracer: High-Level Overview

**Purpose:** use the Rigol DL3021 electronic load as a sweep-based "quasi-MPPT" to record PV power curves and show that the shuffler (DPP converter) works.

**Audience:** control / monitoring lead (implementation in Claude Code).

---

## 1. Goal
Record the **P-V (and I-V) curve** of a real series PV string under these conditions:

| ID | Condition | Shuffler | What it shows |
|---|---|---|---|
| A | Unshaded | Off | Baseline string performance |
| B | Partially shaded | **Off** | Mismatch loss: reduced Pmax, **multiple peaks** (bypass diodes) |
| C | Partially shaded | **On** | Recovery: **single peak**, Pmax close to what's achievable |
| D (optional) | Unshaded | On | Shuffler overhead when no mismatch exists |

**Headline figure:** P-V curves for A, B and C overlaid on one plot.

---

## 2. Hardware setup
- **PV string:** 2 or 3 panels in series (e.g. 80 W panels, Voc ≈ 25 V each), with the shuffler between panels.
- **Load:** Rigol DL3021 in **CV mode** (stable at every point on a PV curve).
- **Controller / logger:** Raspberry Pi (or PC) → **rear USB DEVICE port** on the DL3021 (USB-TMC), using Python + PyVISA (`pyvisa`, `pyvisa-py`, `pyusb`).
- **Connections:** Input + / Input − on the load. Use spade lugs if possible (about 4 A).
- **Shuffler state:** log ON/OFF (and its own telemetry if available) with the same timestamps.

---

## 3. Safety limits (must be enforced)
- DL3021 limits: **200 W, 150 V, 40 A**. Exceeding the power limit **trips the input off**; it does not clamp.
- **Software power ceiling:** stop or back off at **~180 W** (headroom for clouds clearing).
- **Hardware backstop:** set the load's over-power protection to **~190 W**.
- **Vlimit / OVP:** set comfortably **above Voc** (e.g. ~60 V for 2 panels, ~90 V for 3 panels), or the load will trip early.
- **Never use CC mode** on PV for this (power = V × I_set can jump past 200 W).
- **Avoid CP mode** with real PV (it can jump to the low-voltage side of the curve).
- **Always turn the input OFF** on exit, error, or Ctrl-C (try/finally).

---

## 4. Algorithm

### Phase 1: Measure Voc
1. Input OFF.
2. Read `:MEAS:VOLT?` → `Voc`.

### Phase 2: Sweep (curve trace)
1. Set CV mode, `V = Voc − 1 V`, input ON.
2. Loop:
   - Set `V`, wait **0.3–0.5 s** to settle.
   - Read V, I, P. Log a row.
   - **Stop if** `P > P_ceiling (180 W)` **or** `V < V_min` (e.g. 5 V).
   - **Early stop (A, C, D only):** if `P < 0.95 × best_P`, the MPP has been passed.
   - **No early stop for condition B.** Run the full sweep (still power-capped) to capture **all local peaks**.
   - `V -= ΔV` (0.25–0.5 V).
3. Input OFF.

A typical sweep (2 panels) is about 100 steps × 0.4 s ≈ **40 s**. Keep each run short, because the sun and shadows move.

### Phase 3 (optional): Track (perturb and observe)
- Start at the best V from the sweep.
- Every ~1 s: `V ± 0.2 V`. If P increased, keep the direction; otherwise reverse.
- Enforce the 180 W ceiling (if exceeded, step V **up**, towards Voc).
- Log P over time. This shows sustained harvest with vs without the shuffler.

### Pseudocode
```python
voc = measure_voc()
set_mode_cv(); set_voltage(voc - 1.0); input_on()
best, v = 0.0, voc - 1.0
try:
    while v > V_MIN:
        set_voltage(v); sleep(0.4)
        V, I, P = read_vip()
        log(run_id, condition, shuffler_on, v, V, I, P)
        if P > P_CEIL: break
        if early_stop and P < 0.95 * best: break
        best = max(best, P)
        v -= DV
finally:
    input_off()
```

### SCPI commands (verify against the DL3000 programming guide)
| Purpose | Command |
|---|---|
| Identify | `*IDN?` |
| CV mode | `:FUNC VOLT` |
| Set voltage | `:VOLT <value>` |
| Input on/off | `:INP ON` / `:INP OFF` |
| Measure | `:MEAS:VOLT?` `:MEAS:CURR?` `:MEAS:POW?` |

---

## 5. Test protocol
- Use the **same shading object and position** for B and C (e.g. cardboard over part of one panel).
- Run conditions **back-to-back within minutes**, in an alternating order to cancel irradiance drift: **A → B → C → C → B → A**.
- Repeat the set **3 times**. Note the time, sky conditions, and panel temperature if available.
- **Irradiance reference:** re-run A before and after, or log a small reference panel's short-circuit current, to normalise between runs.
- Avoid peak midday sun with 3 panels in series (the string can exceed 200 W).

---

## 6. Data format (CSV)
`timestamp, run_id, condition, shuffler_on, v_set, v_meas, i_meas, p_meas, notes`

---

## 7. Outputs and metrics
**Plots**
1. **P-V overlay: A vs B vs C** (headline figure)
2. I-V overlay of the same runs
3. Bar chart of Pmax per condition (mean ± spread across repeats)
4. (Optional) P vs time from tracking mode, B vs C

**Metrics**
- `Pmax` per condition
- **Recovery:** `(Pmax_C − Pmax_B) / Pmax_B`
- **Fraction of unshaded recovered:** `Pmax_C / Pmax_A`
- **Number of local peaks:** B should show more than one, C should show one
- (Optional) Shuffler overhead: `Pmax_A − Pmax_D`

**Expected result:** B has a lower Pmax with multiple peaks. C has a single clean peak and recovers most of the mismatch loss (bench result: 43 W → 62 W, +44%).

---

## 8. Notes
- The e-load dissipates the power as heat. Check the fan is clear, and allow cool-down between runs.
- A capped sweep may stop before the true MPP in strong sun. Record that it hit the ceiling (log a flag).
- This setup mimics the downstream MPPT (power station), so the measured gains reflect real-world harvest with the shuffler.
