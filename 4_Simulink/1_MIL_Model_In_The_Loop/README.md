# Power Shuffler String — Simulation & Control Toolkit

MIMO control of a 4-PV-module / 3-shuffler differential-power-processing (S-PPC)
string, developed on an averaged-switch Simulink model (`power_shuffler_sim.slx`).

Validated stack (all seven acceptance tests passing):

| Layer | Block / file | Rate | Job |
|---|---|---|---|
| MPPT | `shuffler_string_mppt.m` | 1 ms tick, 20 ms perturb | adaptive-step P&O on string current |
| Supervisor | `shuffler_string_supervisor.m` | 1 ms | feasibility governor: relaxes equalisation to keep shuffler current inside `I_RATED` |
| Controller | `shuffler_string_ctrl.m` | 50 µs | centralised G⁻¹ decoupling PI — all 6 duties from all measurements |
| Plant | `Power Circuit` subsystem | — | 4 PV + 3 averaged-switch shufflers + current-sink load, 61 mΩ/phase damping |

Headline results: uniform 100.1% of MPP ceiling; M3 half-shade 100.2% (modules
equalised at Vmp, mismatch carried as 7.2 A of shuffled current); deep-shade
protection parks shuffler current at 0.9×rating for a measured 194 W harvest cost.

## Quick start

1. Open MATLAB in this folder, open `power_shuffler_sim.slx`.
2. Run the acceptance suite:
   ```matlab
   shuffler_string_validate
   ```
   It configures everything itself (closed loop, accelerator mode, Fast Restart),
   runs each test, prints a settled report, pops grouped plots, and waits for
   [Enter] between tests. Comment rows in/out of the `tests` table to run subsets.

## One place for parameters

**`init_params.m`** is the single source of truth: model name, every block path,
logged-signal names, PV datasheet numbers, ratings, MPPT/governor settings, test
settings. All scripts start with `P = init_params();`. If a block moves or gets
renamed, fix the path there once.

Caveat: the three MATLAB Function blocks embed their own constants (gains, M
matrix, thresholds). Those blocks are the authoritative copy; `init_params`
mirrors the values the *scripts* need (ratings, ceilings, IREF0). Keep in sync
when tuning — see Open items.

## Files

| File | Purpose |
|---|---|
| `init_params.m` | all parameters & paths (start here) |
| `shuffler_string_validate.m` | 7-test closed-loop acceptance suite + plots |
| `shuffler_string_ident.m` | open-loop plant identification → prints new `M` |
| `shuffler_string_baseline.m` | shaded-string baselines: shufflers idle / removed |
| `shuffler_string_ctrl.m` | inner controller (copy lives in the Controller block) |
| `shuffler_string_supervisor.m` | governor (copy lives in the Supervisor block) |
| `shuffler_string_mppt.m` | P&O MPPT (copy lives in the MPPT block) |
| `shuffler_pi_design.m`, `shuffler_mimo_*.m` | earlier 2-module design lineage |

## Typical workflows

- **Regression after any change**: run the full validate suite. Tests 1–4 prove
  the inner loop, 5 proves the governor, 6–7 prove MPPT + the whole stack.
- **Re-identification** (only when the *plant* changes — components, topology;
  never for gain tuning): configure the ident Variant (`CTRL_MODE==0` selects the
  six duty Constants; paths in `init_params`), then run `shuffler_string_ident`,
  paste the printed `M` into `shuffler_string_ctrl.m`, re-run validate.
  Mind the operating point note in the ident header.
- **Thesis bar chart**: run validate (controlled numbers), then
  `shuffler_string_baseline` (idle & no-shuffler numbers under the same shade).

## Hard-won rules (do not relearn these)

- Every discrete controller output that drives the physical network gets a
  **Unit Delay at its own sample time** (`rv`: 1 ms; `Iref`: 1 ms with
  **IC = IREF0**, not 0). Otherwise: algebraic loop.
- After a clean identification, closed-loop blow-up = **loop plumbing** (sign or
  content flip in feedback wiring), not gains. Probe: open-loop
  `dA=0.52/dB=0.48` on one shuffler → the controller's i_comm input must read
  ≈ −51.7 A.
- The averaged model needs the **61 mΩ per-phase resistance** (MOSFET Rds(on));
  ideal averaged switches delete the damping that keeps circulating currents
  finite.
- Identification reads **settled means**, never transient snapshots — noisy
  cross-terms scramble G⁻¹ and reappear as a mystery limit cycle.
- Gains are **versioned**: note which identification produced the current `M`
  (title-block annotation in the model).

## Open items

- **Switching-model confirmation**: the stack is validated on the averaged
  model only. One run of the final controller on the full 200 kHz PWM/MOSFET
  model (or QSPICE) to show it survives real ripple. Expect slow sim; use the
  short uniform + rv-step tests, not the MPPT climbs.
- **SIL → PIL → HIL ladder**: port controllers to C (C Caller in the same model
  = SIL); run on STM32G474 dev boards over serial lockstep (PIL); plant-on-a-chip
  on an STM32H7 speaking CAN (HIL). The validate suite is the regression harness
  at every rung.
- **Promote block constants to parameters**: move the MATLAB Function embedded
  constants (M, gains, thresholds) to mask/workspace parameters fed from
  `init_params`, so tuning truly happens in one file.
- **Baseline runs** for the thesis comparison chart (script ready, not yet run
  on the restructured model).
- **`mppt-shade` regression + full-suite re-run** on the restructured model.
- **Hardware design carry-overs**: isolated CAN + isolated logic supplies (board
  grounds sit at different string potentials — BMS-style), hall-effect string
  current sense, complementary PWM with hardware dead-time + break-input
  overcurrent trip (STM32G474 HRTIM), gain version stamps in every CAN state
  frame.