# Power Shuffler — Design Decision Log & Task Breakdown

A chronological record of the design decisions, the alternatives weighed, and the
evidence that settled each one. Written to support the thesis narrative (the
*process* is a result in itself) and to anchor the task breakdown at the end.

---

## Part 1 — Decision log

### Phase 0 · Analytical groundwork (notebooks)

| # | Decision | Alternatives considered | Rationale / evidence | Status |
|---|----------|------------------------|----------------------|--------|
| 0.1 | Averaged state-space model of the interleaved half-bridge shuffler as the design basis | switching-level analysis only | tractable control design; switching detail deferred to simulation | ✅ (later corrected — see 1.6) |
| 0.2 | Multi-rate, timescale-separated architecture: fast electrical loops, slow string loops (~1000× gap) | monolithic single-rate controller | inner loops settle in µs–ms, string phenomena in s; separation makes each layer designable alone | ✅ carried through to hardware architecture |
| 0.3 | Evolve cascaded PI → one MIMO servo per shuffler | keep 3 nested PI loops | modal analysis showed the controllable DOF are modal pairs, not per-loop quantities | ✅ concept survived; realization changed (1.7) |

### Phase 1 · 2-module / 1-shuffler switching model (bring-up)

| # | Decision | Alternatives | Rationale / evidence | Status |
|---|----------|--------------|----------------------|--------|
| 1.1 | Bring up on 2 PV / 1 shuffler before the full string | build 4/3 immediately | isolate converter physics from string coupling | ✅ |
| 1.2 | Load = battery (stiff current sink), not resistor | 15 Ω resistor, voltage sweep | resistor couples string V and I; battery pins the operating point | ✅ (superseded by 4.6 for MPPT) |
| 1.3 | Discrete `dlqr` gains, not continuous LQR | continuous gains sampled at 200 kHz | sampled continuous design unstable (\|eig\| = 2.86); resonance near 0.4·f_sw | ✅ |
| 1.4 | Coupled-inductor dot = positive mutual (flip one winding) | as first wired | ±47 A common-mode ripple → common mode must see L+M (13.75 µH), differential L−M (2.05 µH) | ✅ |
| 1.5 | Moving-average / continuous-LPF sensing; **reject** synchronized/triggered sampling | carrier-synchronized S&H at peak/valley | trigger path broke the working loop (lost interleaving, common-mode collapse); documented dead end | ✅ hard lesson |
| 1.6 | **Identify the plant from step tests; distrust the analytical model** | keep refining hand-derived model | measured coupling is *swapped* vs derivation: `d_A−d_B → i_comm` (−200 A/duty), `d_A+d_B → v_diff` (−76.5 V/duty); explains every prior runaway | ✅ project-defining decision |
| 1.7 | Replace the 2-output MIMO LQR servo with **two decoupled SISO PI loops** on the measured plant | retune LQR on corrected model | measured `v_diff/i_diff = 2.38 Ω ≈ 1/G_mod` → the two outputs are rank-1 (one DOF); a 2-output servo is ill-posed regardless of gains | ✅ validated: equilibrium + 2 V tracking |

### Phase 2 · Averaged-switch model (fast rig for outer loops)

| # | Decision | Alternatives | Rationale / evidence | Status |
|---|----------|--------------|----------------------|--------|
| 2.1 | Build an averaged (PWM-switch) model: CVS = d·V_bus, CCS = d·i_L per leg | persist with switching model | 250 ms shading transient = 50k switching periods → hours; averaged model runs it in seconds | ✅ |
| 2.2 | Break signal-domain algebraic loops with slow-filtered *sensed* V_bus and a filter on i_L into the CCS | constant V_bus; filters on the product | constant V_bus hid real bus dynamics and biased the string; filtering the *product* lagged the loop and destabilized it — filter placement matters | ✅ |
| 2.3 | Accept that averaging deletes damping; retune (KpA −0.012 → −0.006) | pretend models are equivalent | averaged model drops switching/ESR losses (measured ζ≈0.53 → less); conservative gain stable on both | ✅ (superseded by 3.2 at string scale) |
| 2.4 | Balancing "Loop 3" **not built** — inner loop shown to do near-ideal DPP alone | port the notebook's equalizer loop | shade test: rv=0 already puts every module at its own MPP (99.6 % of ceiling, +49 % vs bypass); a v_diff-nulling outer loop is redundant | ✅ architecture simplification |

### Phase 3 · 4-module / 3-shuffler string

| # | Decision | Alternatives | Rationale / evidence | Status |
|---|----------|--------------|----------------------|--------|
| 3.1 | Scale by replicating the validated shuffler; **decentralized control rejected after test** | assume 3 local loops compose | interior modules (shared nodes) limit-cycle at *any* gain — detuning only shrinks amplitude; dropping the current loops diverges | ✅ negative result, load-bearing |
| 3.2 | Add ~61 mΩ series R per phase (= MOSFET R_ds(on)) to the averaged model | tune around it; RC snubbers | differential-duty step drove i_comm on a −1600 A *ramp*: circulating interior current never reaches the load's damping; ideal averaged switches deleted the resistance that damps it. Snubber rejected — that's for HF parasitics, not control resonances | ✅ model-fidelity rule |
| 3.3 | **Centralized decoupling controller**: u = G⁻¹·diag(kI)·∫e, integral-only | decentralized + supervisor refs; full MIMO LQR | one block sees all couplings and cancels them by construction; supervisor refs can't stabilize a fast inner fight (fails at rv=0) | ✅ 7/7 tests |
| 3.4 | Integral-only; **no proportional** into the static decoupler | PI decoupler for resonance damping | G⁻¹ is a *DC* decoupler; pushing bandwidth toward the ~6 kHz resonance re-couples the loops (tried, blew up). Resonance is passively damped (3.2) | ✅ |
| 3.5 | Identification hygiene: settled means only, scripted pipeline with cond(G) and sign sanity checks | read scopes by hand | hand-read transient cross-terms corrupted G⁻¹ → mystery ±4.7 V limit cycle; clean re-ident collapsed it. cond(G)≈18–19 | ✅ `shuffler_string_ident.m` |
| 3.6 | Debugging doctrine: after a clean ident, closed-loop blow-up = **loop plumbing, not gains** | retune first | ic-runaway post-rewire was a feedback wiring flip; decisive probe: open-loop dA/dB = 0.52/0.48 → controller's ic input must read −51.7 A | ✅ standing rule |

### Phase 4 · Supervisory layers

| # | Decision | Alternatives | Rationale / evidence | Status |
|---|----------|--------------|----------------------|--------|
| 4.1 | Supervisor = **feasibility governor** (protect hardware), not equalizer | notebook's balancing supervisor | inner loop equalizes perfectly at rv=0 even at 200 W/m² (duties 0.505); nothing to balance | ✅ |
| 4.2 | Stress metric = \|i_diff\|/I_RATED (current rating), not duty utilization | duty-saturation stress | duty authority ≈ ±580 A-equivalent — never binds; inductor/MOSFET current rating binds first | ✅ |
| 4.3 | Governor law: β-integrator with hysteresis, refs = β·(deficit differences), park just under rating (S_HI = 0.90) | fixed protective refs; aggressive backoff | relief physics is weak (~0.14 A per V of sag — strong modules' Voc knee), so protection is expensive: measured **194 W to shed 2.7 A**. Park close to the rating | ✅ validated at 200 W/m² |
| 4.4 | Sizing insight for hardware: rate magnetics for worst-case mismatch; governor = rarely-used safety net | under-rate + rely on governor | ~20 % under-rating costs ~11 % of harvest under deep shade | ✅ thesis result |
| 4.5 | MPPT = **adaptive-step P&O** with windowed power, deadband park, governor hold-off | IncCond; extremum seeking | DPP-equalized string has a *unimodal* P–V curve (shufflers remove multi-peak) → hill climber sufficient; IncCond's edge vanishes under deadbands; P&O already validated in notebooks | ✅ 100.1 / 100.2 % of ceiling |
| 4.6 | Load swapped battery → controlled current sink commanded by MPPT | MPPT trimming rv only | MPPT needs a string-level DOF; battery pinned it. IMAX clamp below Isc (voltage-collapse cliff) | ✅ |
| 4.7 | Wiring rule: every discrete supervisory output driving the network gets a **unit delay at its own rate** (rv: 1 ms; Iref: 1 ms, IC = IREF0) | ad-hoc loop breaking | otherwise algebraic loops (a controller instantly measuring its own command); delays = the future CAN latency, for free | ✅ standing rule |

### Phase 5 · Engineering & process infrastructure

| # | Decision | Alternatives | Rationale / evidence | Status |
|---|----------|--------------|----------------------|--------|
| 5.1 | Controller Ts 5 µs → 50 µs; accelerator mode + Fast Restart; decimated logging | live with 15 min / 60 ms sims | loops are 150/400 Hz integral-only — 5 µs was a switching-era relic; ~10× fewer forced solver steps | ✅ |
| 5.2 | Model restructure: 5-block top level, buses, subsystem hierarchy, Variant Source (CTRL_MODE) for ident vs closed loop, Telemetry subsystem | flat Goto/From canvas | presentability + kills the rewiring error class (3.6 was caused by manual rewiring); buses mirror the future CAN frames | ✅ |
| 5.3 | Single source of truth: `init_params.m` (paths/signals/ratings) + scripted validate/ident/baseline + README | per-script constants | reproducibility; the validate suite is the regression harness at *every* test-ladder rung | ✅ |
| 5.4 | Automated SVG figure pipeline in the validate suite (per-test string/control/supervisory + cross-test summary) | screenshot scopes | publication-grade, repeatable, zero manual steps | ✅ |
| 5.5 | Testing ladder adopted: MIL → SIL → PIL → HIL → bench → field, same 7-test suite carried down | ad-hoc "build then debug" | each rung isolates one new risk class; plant model ported once, never re-derived | 🔄 MIL done, SIL in progress |
| 5.6 | SIL = **hand-written portable C** (float32, stdint, no malloc, generated params.h), one C Caller per block; **not** Embedded Coder | auto code generation | no extra licenses; 2 KB-RAM-target-friendly; full authorship for the thesis; params.h *generated* to end transcription errors | 🔄 |
| 5.7 | PIL target = Arduino Uno R3 as a *portability/logic* waypoint (AVR: 32-bit double, 16-bit int); timing numbers explicitly non-transferable | jump straight to STM32 | on-hand hardware; the AVR quirks are a genuine portability stress test; final target remains STM32G474 | ⬜ planned |
| 5.8 | Production architecture: local MCUs run *their rows* of M off broadcast CAN state; supervisor MCU = sync master + shadow-ξ auditor + governor/MPPT; Pi = telemetry only (never in loop) | Pi-in-the-loop; pure central MCU | CAN broadcast makes distributed rows latency-optimal; distributed-integrator risks countered by freeze-on-stale, saturation-flag broadcast, checkpoint audit, gain version stamps | ⬜ design settled, build pending |
| 5.9 | Hardware carry-overs decided early: isolated CAN + isolated logic supplies (board grounds sit at string potentials — BMS pattern), hall string-current sense, HRTIM complementary PWM + hardware break-input OC trip | decide at PCB time | these are architecture facts, not layout details; discovered cheaply in sim/planning | ⬜ feeds PCB design |

---

## Part 2 — Distilled lessons (the process story)

1. **Measure, don't derive.** The hand-derived model was wrong in *kind* (swapped
   coupling), not degree. Every controller that worked was designed on an
   identified plant; every one that failed was designed on the derivation.
2. **Negative results steered the architecture**: triggered sampling (1.5),
   decentralized string control (3.1), proportional decoupling (3.4) — each
   rejected on evidence, each redirection load-bearing.
3. **Model fidelity is a *selective* property.** Averaging is fine for control
   design but silently deletes damping (2.3, 3.2) — know what an abstraction
   throws away before trusting it.
4. **After clean identification, suspect plumbing before gains** (3.6). Sign and
   routing errors mimic instability; one open-loop probe distinguishes them.
5. **Protection has a measurable price** (4.3/4.4) — quantifying it converts a
   tuning knob into a hardware-sizing argument.
6. **Infrastructure is leverage**: scripted ident/validate + single-source params
   turned every later question into a 15-minute experiment instead of an
   afternoon of scope-reading.

---

## Part 3 — Task breakdown

### Complete ✅
- [x] Analytical notebooks: averaged SS model, cascaded PI, integrated 4-loop sim, behavioural string study
- [x] 2-module switching model bring-up (PWM, gate drive, sensing, battery load)
- [x] Plant identification (2-module) + SISO PI redesign; tracking validated
- [x] Averaged-switch fast rig (2-module) + gain transfer
- [x] 2-module DPP result: 99.6 % of ceiling, +49 % vs bypass
- [x] 4-module / 3-shuffler averaged string model (incl. 61 mΩ damping fix)
- [x] String identification pipeline (scripted, guarded) + centralized G⁻¹ controller
- [x] Feasibility governor + protection-cost measurement
- [x] Adaptive P&O MPPT + current-sink load; full 7-test suite passing
- [x] Model restructure (buses/hierarchy/variants) + init_params + README
- [x] Validate suite with automated SVG reporting
- [x] SIL prompt/spec; C port scaffolded; state-reset bug diagnosed

### In progress 🔄
- [ ] SIL acceptance: Initialize-Function reset verified (bit-identical double-run), golden-vector replay in tolerance, 7-test suite passing on C
- [ ] Retrospective notebook reconciling analytical models with measured findings (parked mid-verification)

### Planned ⬜
- [ ] 1 kHz gain rescale (kI·Ts ≈ 0.5) + suite re-run — hardware-rate validation for CAN/PIL
- [ ] Baseline comparison runs (controlled vs idle vs no-shuffler) — thesis bar chart
- [ ] Switching-model confirmation run of the final stack (ripple robustness figure)
- [ ] Promote MATLAB-Function embedded constants to parameters fed from init_params
- [ ] PIL on Arduino Uno R3: serial lockstep harness, replay + suite on target
- [ ] Bench CAN network (4× dev boards): sync, freeze-on-stale, saturation-flag broadcast, ξ checkpoint audit, gain version stamps
- [ ] Plant-on-a-chip HIL (STM32H7 running the 10-state plant over CAN) + fault injection
- [ ] Shuffler PCB design: isolated CAN + supplies, HRTIM PWM + hardware OC trip, sensing chain (QSPICE support studies for the power stage)
- [ ] Bench power testing against electronic load / bench supply
- [ ] Field test: real panels + battery
