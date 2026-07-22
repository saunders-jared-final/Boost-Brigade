# Wiring the C Callers into `SIL_power_shuffler_sim` (SIL step)

Replace the three MATLAB Function blocks with C Caller blocks calling the
entry points in `sil_wrappers.h`. **Everything else stays**: the plant, the
telemetry, the three rv 1 ms Unit Delays, the Vref1..3 sum, and the Iref 1 ms
Unit Delay (IC = IREF0). The wrappers implement only the algorithm blocks —
the delays/sums are NOT inside the C (they are replicated only in
`core/stack.c`, which Simulink never uses).

Anything I could not verify from outside Simulink is marked **TODO** — check
it rather than trusting a guess.

## 1. Model-wide custom code settings

Model Settings (Ctrl+E) → **Simulation Target**:

| Field | Value (paths relative to the model's folder, i.e. `2_SIL_Software_In_The_Loop/`) |
|---|---|
| Include headers | `#include "sil_wrappers.h"` |
| Include directories | `firmware/sil`  and  `firmware/core` (one per line) |
| Source files | `firmware/sil/sil_wrappers.c`  `firmware/core/shuffler_ctrl.c`  `firmware/core/shuffler_supervisor.c`  `firmware/core/shuffler_mppt.c` (one per line; do NOT add `stack.c` — its scheduling must stay in the model for SIL) |
| Deterministic functions (Advanced parameters) | leave at default **None** — the wrappers hold static state; marking them deterministic would let Simulink cache/reorder calls and corrupt it |

**TODO**: if MATLAB refuses relative paths on your setup, use
`$pwd`-anchored or absolute paths.

## 2. Block replacements

For each block: note its exact wiring (or copy the block, then replace),
delete the MATLAB Function block, drop in a **C Caller**
(Simulink → User-Defined Functions), set **Function name**, and reconnect
identically. After setting the function name, open the block's **Port
specification** table and verify scope/size per the tables below (C Caller
usually infers them from the prototypes in `sil_wrappers.h`; fix by hand if
not).

The three MATLAB Function blocks (paths read out of the .slx archive, so
verify they still match your current save):

| Block to replace | Sample time | Notes |
|---|---|---|
| `SIL_power_shuffler_sim/Controller/Controller` | `50e-6` (explicit, atomic) | inputs: VM and IL vectors from the Bus Selector, rv from the `Vref` inport |
| `SIL_power_shuffler_sim/Supervisor/Supervisor` | `1e-3` (explicit, atomic) | inputs 1–3: VM/IM/IL vectors; inputs 4–9: the six duty scalars from `Bus Selector1`; input 10: the `Enable` constant |
| `SIL_power_shuffler_sim/MPPT/P&O` | `1e-3` (explicit, atomic) | inputs: Vstr/Istr from the Bus Selector, beta inport, `Enable` constant; Iref output feeds `Delay` (Unit Delay, IC = 12, Ts = 1e-3) |

The original blocks carry **explicit** sample times (`SystemSampleTime` 50e-6
/ 1e-3) and `TreatAsAtomicUnit on` — the duty path into the Supervisor is a
direct connection with no rate-transition delay, which is exactly the
same-tick sampling the port assumes (`STACK_SUP_DUTY_SAME_TICK=1`).

### 2a. Inner controller → `sil_ctrl_step`

| C argument | Scope | Size | Connects to |
|---|---|---|---|
| `VM` | Input | 4 | module-voltage vector (same signal the MATLAB block used) |
| `IL` | Input | 6 | inductor-current vector, order {ILA1, ILB1, ILA2, ILB2, ILA3, ILB3} |
| `rv` | Input | 3 | output of the Vref1..3 + delayed-rv sum |
| `dA1 dB1 dA2 dB2 dA3 dB3` | Output | 1 each | the six duty lines to the shufflers + telemetry + supervisor |

Wiring (from the .slx): VM and IL arrive as vectors from the subsystem's Bus
Selector; rv arrives as a 3-vector on the `Vref` inport (the Mux of the three
delay+Vref sums inside the Supervisor subsystem). No Mux changes needed.

### 2b. Supervisor → `sil_supervisor_step`

| C argument | Scope | Size | Connects to |
|---|---|---|---|
| `VM` | Input | 4 | module-voltage vector (unused by the algorithm — reference quirk — but wire it anyway) |
| `IM` | Input | 4 | module-current vector |
| `IL` | Input | 6 | inductor-current vector, same order as above |
| `dA1..dB3` | Input | 1 each | the six duties from the controller |
| `en` | Input | 1 | `Supervisor/Enable` constant |
| `rv1 rv2 rv3` | Output | 1 each | into the three 1 ms Unit Delays (unchanged) |
| `beta` | Output | 1 | to the MPPT beta input (same-tick, no delay) |
| `stress` | Output | 1 | telemetry |

### 2c. MPPT → `sil_mppt_step`

| C argument | Scope | Size | Connects to |
|---|---|---|---|
| `Vstr` | Input | 1 | string voltage |
| `Istr` | Input | 1 | string current |
| `beta` | Input | 1 | supervisor beta (fresh, same 1 ms tick) |
| `en` | Input | 1 | `MPPT/Enable` constant |
| `Iref` | Output | 1 | into the 1 ms Unit Delay with **IC = IREF0 = 12** (unchanged) |
| `Pav`, `state` | Output | 1 each | telemetry |

## 3. Data types (single-precision boundary)

The C ports are `float`, model signals are `double`. If Simulink reports a
data type mismatch at any C Caller port, insert **Data Type Conversion**
blocks: to `single` on every input, back to `double` on every output. This
cast IS the SIL fidelity boundary (float32 in, float32 out — identical to
what the AVR/STM32 will compute), not an approximation to avoid.

**TODO**: on recent MATLAB versions C Caller inserts these casts implicitly;
only add conversion blocks if you actually get the mismatch error, and then
add them at every C Caller port for uniformity.

## 4. Sample times

The original blocks do NOT inherit — they carry explicit sample times
(Controller `50e-6`, Supervisor and P&O `1e-3`, all atomic). Replicate that:
set each C Caller's Sample time parameter to the same value (the C Caller
block dialog exposes one; if your MATLAB version's dialog does not, wrap the
block in an Atomic Subsystem with that sample time). Then enable Sample Time
colors/annotations and confirm the three rates — this matters especially for
the Supervisor, whose 1 ms rate is what decimates the directly-connected
50 µs duty signals.

## 5. State reset between runs (IMPORTANT — Fast Restart!)

MATLAB Function persistents reset at every simulation start; the C wrappers'
static state does NOT — it lives in the loaded simulation target across
runs, and *especially* across Fast Restart runs of the validate suite. Without
a reset, test N+1 starts with test N's integrator/MPPT state and the
MIL-equivalence comparison is invalid.

Primary fix — runs automatically every simulation start, including Fast
Restart:
1. Add an **Initialize Function** block (subsystem) at the model top level.
2. Inside it, place a C Caller with Function name `sil_reset_pass`, feed its
   `u` input from a Constant (0), send its output to a Terminator.
   (`sil_reset_pass` resets all three blocks and passes `u` through; it
   exists because a void/void C Caller has no ports to sit on a wire.)

Fallbacks if the Initialize Function route fights you:
- Model callback `InitFcn`: `clear mex` (forces the sim target to reload;
  slower, and **TODO**: verify it actually clears state on your MATLAB
  version — check with two consecutive runs giving identical traces).
- Manual `clear mex` in the command window before each run (not viable for
  the multi-test validate suite).

Acceptance check for the reset: run any test twice back-to-back (Fast
Restart on); the two traces must be identical to the last bit.

## 6. Verify

1. `matlab/export_golden.m` first, on the **MIL** variant (MATLAB blocks
   still active — see that file's header for the To Workspace blocks to add).
2. Host: `cd firmware && cmake -B build && cmake --build build && ctest
   --test-dir build --output-on-failure`, then
   `./build/test/replay test/golden/golden_inputs.csv test/golden/golden_expected.csv`.
3. Swap in the C Callers per this file and run `shuffler_string_validate` —
   the 7-test suite is the SIL acceptance gate.
