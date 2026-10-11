# Task: SIL implementation of a PV power-shuffler control stack in portable C

## Project context (you have none — this section is everything you need)

I have a validated Simulink model (`power_shuffler_sim.slx`) of a 4-PV-module /
3-shuffler differential-power-processing string. The **control stack** is three
MATLAB Function blocks — inner MIMO controller, supervisory feasibility
governor, P&O MPPT — validated by a 7-test acceptance suite (MIL). This task is
the **SIL step**: port the three blocks to hand-written portable C so the same
Simulink model runs with the production C in the loop (via C Caller blocks),
plant and telemetry untouched.

Downstream targets (they set constraints NOW, you are not building them):
- **PIL next**: Arduino Uno R3 (ATmega328P — 8-bit AVR, 16 MHz, 2 KB RAM, no
  FPU, avr-gcc where `double` == 32-bit and `int` == 16-bit).
- **Final**: STM32G474 nodes on CAN at a 1 kHz control tick.

You are writing code and build/test infrastructure only. You cannot open
Simulink; anything requiring model edits goes in an instructions file for me.

## Environment

- Windows, VS Code, CMake for host builds. Git repo; work goes in `firmware/`
  at the repo root (I will place it).
- MATLAB compiles the C Caller sources itself — no MEX build needed from you.
- Host compiler: gcc/clang (either fine). Also compile-check with
  `avr-gcc -mmcu=atmega328p` if available; if not, keep the code AVR-clean by
  construction.

## Authoritative reference implementations

The following MATLAB sources define the EXACT behavior to port — including
constants, reset semantics, and quirks. Do not redesign, improve, or "fix"
anything; a bit-faithful port is the deliverable. (E.g. the controller's
anti-windup recomputes the integrator through `Minv` every step, the MPPT's
`Pav` output is the *previous* window's power — keep all of it.)

### 1. Inner controller — runs every 50 µs tick

```matlab
function [dA1,dB1,dA2,dB2,dA3,dB3]  = shuffler_string_ctrl(VM, IL, rv)
VM1 = VM(1); VM2 = VM(2); VM3 = VM(3); VM4 = VM(4);
ic1 = IL(1) + IL(2); ic2 = IL(3) + IL(4); ic3 = IL(5) + IL(6);
rv1 = rv(1); rv2 = rv(2); rv3 = rv(3);
Ts = 50e-6;  DMIN = 0.05;  DMAX = 0.95;
M = [ -12.798383   0.000000  -0.000000  -0.000000   1.043947   0.000000;
       -0.132666 -12.627108   0.000000  -1.014057   1.021695   1.025829;
       -0.130486  -0.200085 -12.492219  -1.001002   0.000612   1.002715;
        0.000000   0.000000   0.000000  -1.945483   0.000000   0.000000;
       -0.000000  -0.000000  -0.000000  -0.000000  -2.061583  -0.000000;
       -0.000000  -0.000000  -0.000000  -0.000000   0.000000  -2.022595 ];
Kp_ratio = diag([1.58e-4, 1.58e-4, 1.58e-4, 1.08e-4, 1.08e-4, 1.08e-4]);
fc = 2000;
a  = 2*pi*fc*Ts / (1 + 2*pi*fc*Ts);
persistent xi y_f Minv Mp
if isempty(xi)
    xi = zeros(6,1); y_f = zeros(6,1); Minv = inv(M); Mp = M * Kp_ratio;
end
y   = [VM1-VM2; VM2-VM3; VM3-VM4; ic1; ic2; ic3];
y_f = y_f + a*(y - y_f);
r   = [rv1; rv2; rv3; 0; 0; 0];
e   = r - y_f;
xi_try = xi + Ts*e;
u      = Mp*e + M*xi_try;
uc = u(1:3);  ud = u(4:6);
dA = 0.5 + 0.5*(uc + ud);
dB = 0.5 + 0.5*(uc - ud);
dAs = min(max(dA, DMIN), DMAX);
dBs = min(max(dB, DMIN), DMAX);
uc_act = (dAs + dBs) - 1;
ud_act = (dAs - dBs);
u_act  = [uc_act; ud_act];
xi     = Minv * (u_act - Mp*e);
dA1=dAs(1); dB1=dBs(1); dA2=dAs(2); dB2=dBs(2); dA3=dAs(3); dB3=dBs(3);
end
```

### 2. Supervisor / feasibility governor — runs every 1 ms tick

```matlab
function [rv1,rv2,rv3, beta, stress] = shuffler_string_supervisor( ...
          VM, IM, IL, dA1,dB1,dA2,dB2,dA3,dB3, en)
VM1=VM(1); VM2=VM(2); VM3=VM(3); VM4=VM(4);
IM1=IM(1); IM2=IM(2); IM3=IM(3); IM4=IM(4);
id1 = IL(1) - IL(2); id2 = IL(3) - IL(4); id3 = IL(5) - IL(6);
Ts3 = 1e-3;  TF = 5e-3;  I_RATED = 10;
S_HI = 0.90;  S_LO = 0.70;  KB = 60;  KREL = 6;  BMAX = 4;  RVMAX = 30;
persistent b imf idf
if isempty(b), b = 0; imf = [IM1;IM2;IM3;IM4]; idf = [id1;id2;id3]; end
if en == 0
    b = 0; imf = [IM1;IM2;IM3;IM4]; idf = [id1;id2;id3];
    rv1=0; rv2=0; rv3=0; beta=0; stress=0; return;
end
im  = [IM1;IM2;IM3;IM4];
imf = imf + (Ts3/TF)*(im - imf);
dl  = max(imf) - imf;
idm = [id1;id2;id3];
idf = idf + (Ts3/TF)*(idm - idf);
d6     = [dA1;dB1;dA2;dB2;dA3;dB3];
stress = max( max(abs(idf))/I_RATED , max(abs(d6 - 0.5))/0.45 );
if stress > S_HI
    b = b + Ts3*KB*(stress - S_HI);
elseif stress < S_LO
    b = b - Ts3*KREL*(S_LO - stress);
end
b = min(max(b,0), BMAX);
rv = b*(dl(2:4) - dl(1:3));
rv = min(max(rv,-RVMAX), RVMAX);
rv1=rv(1); rv2=rv(2); rv3=rv(3); beta=b;
end
```

### 3. MPPT (adaptive-step P&O) — runs every 1 ms tick

```matlab
function [Iref, Pav, state] = shuffler_string_mppt(Vstr, Istr, beta, en)
Ts = 1e-3;  TP = 0.02;  IREF0 = 12;  IMIN = 5;  IMAX = 14.5;
DB = 1.0;  KA = 0.01;  SMIN = 0.05;  SMAX = 1.0;  S0 = 0.25;  BTOL = 1e-3;
N = round(TP/Ts);
persistent iref dirn Pprev acc n boot b0 st
if isempty(iref)
    iref=IREF0; dirn=1; Pprev=0; acc=0; n=0; boot=true; b0=beta; st=0;
end
if en == 0
    iref=IREF0; dirn=1; Pprev=0; acc=0; n=0; boot=true; b0=beta; st=0;
    Iref=iref; Pav=Vstr*Istr; state=0; return;
end
acc = acc + Vstr*Istr;
n   = n + 1;
if n >= N
    Pw  = acc/N;  acc = 0;  n = 0;
    govActive = abs(beta - b0) > BTOL;   b0 = beta;
    if govActive
        boot = true;  st = 0;
    elseif boot
        Pprev = Pw;  boot = false;
        iref  = iref + dirn*S0;  st = 1;
    else
        dP = Pw - Pprev;
        if dP > DB
            step = min(max(KA*abs(dP),SMIN),SMAX);
            iref = iref + dirn*step;  st = 1;
        elseif dP < -DB
            dirn = -dirn;
            step = min(max(KA*abs(dP),SMIN),SMAX);
            iref = iref + dirn*step;  st = 1;
        else
            st = 2;
        end
        Pprev = Pw;
    end
    iref = min(max(iref,IMIN),IMAX);
end
Iref = iref;  Pav = Pprev;  state = st;
end
```

## Timing & interconnect the C must reproduce

- Controller tick: **50 µs**. Supervisor and MPPT tick: **1 ms** (20:1
  decimation). Within a 1 ms tick the execution order is: supervisor first,
  then MPPT (MPPT consumes the fresh `beta` from the same tick).
- **rv path**: supervisor `rv1..3` pass through **one-sample (1 ms) unit
  delays**, are then **summed with three manual constants** (`Vref1..3`, test
  inputs), and that sum is the controller's `rv` input. In Simulink-SIL these
  delay/sum blocks stay in the model — the C Caller wrappers do NOT implement
  them. The standalone `stack.c` (see deliverables) MUST implement them.
- **Iref path**: MPPT `Iref` passes through a **1 ms unit delay with initial
  condition IREF0** before reaching the load. Same split: stays in Simulink for
  SIL; replicated in `stack.c`.
- `en` inputs default to 1; `en == 0` resets that module's state (port the
  exact reset semantics shown).

## Deliverables

```
firmware/
  core/            pure portable C99 — no I/O, no Arduino, no MATLAB includes
    shuffler_ctrl.c/.h        ctrl_init(state), ctrl_step(in, state, out)
    shuffler_supervisor.c/.h  sup_init / sup_step
    shuffler_mppt.c/.h        mppt_init / mppt_step
    stack.c/.h                stack_init / stack_step(): called at 50 µs, owns
                              the 20:1 decimation, the sup->MPPT order, the rv
                              and Iref one-tick delays, and the Vref summation
                              (Vref[3] and en flags are stack inputs)
    params.h                  ALL gain constants — generated, see below
  sil/
    sil_wrappers.c/.h         three flat-signature entry points for Simulink
                              C Caller (arrays + scalars only), state held in
                              statics (single instance), plus a reset function
    INSTRUCTIONS.md           exact steps for me to wire the C Caller blocks in
                              place of the three MATLAB Function blocks
                              (block settings, source paths, port mapping);
                              any ambiguity = a TODO note, never a silent guess
  test/
    replay.c                  golden-vector harness (see Testing)
    CMakeLists.txt
  matlab/
    export_params.m           computes Mp = M*Kp_ratio and Minv = inv(M) in
                              DOUBLE precision offline, emits params.h with
                              float32 arrays + a PARAMS_VERSION string
    export_golden.m           runs the Simulink model and writes golden CSVs
                              (per-50 µs-tick stack inputs and outputs); lists
                              at the top any To Workspace blocks I must add
                              (e.g. rv1..3 and Iref are not currently logged)
  CMakeLists.txt  .clang-format  README.md
```

## Hard design rules (each exists for a reason — do not relax)

1. **`float` everywhere, never `double`** (AVR `double` is 32-bit; SIL and PIL
   must compute identically). `stdint.h` types only — AVR `int` is 16-bit, so
   no bare `int` in arithmetic or indexing beyond loop counters < 127.
2. No `malloc`, no VLAs, no recursion, no printf in `core/`. State lives in
   caller-owned structs passed by pointer.
3. **No runtime matrix inversion** — `Minv` and `Mp` are precomputed into
   `params.h` by `export_params.m`.
4. Const matrices declared through a `MAT_CONST` macro so they can later be
   placed in AVR flash (`PROGMEM`) without touching the algorithm code.
5. Compile warning-free under `-Wall -Wextra` (host) and cleanly under
   `avr-gcc -mmcu=atmega328p -Os` (compile-only).
6. **Known numerical risk to test, not assume away**: the integrator update
   `xi += Ts*e` adds increments ~1e-7 of `xi`'s magnitude in float32 at 50 µs —
   near the 24-bit mantissa limit. If golden-vector replay shows drift or
   stagnation from this, switch the accumulator (and only it) to a typedef
   `accum_t` (double on host/ARM, float on AVR) and document the deviation.

## Testing / acceptance

1. **Golden-vector replay**: `export_golden.m` dumps input and expected-output
   CSVs from a MIL run; `replay` feeds inputs through `stack_step()` tick by
   tick and compares. Pass: max abs error < 1e-3 on duties, < 1e-2 on
   rv/Iref/beta, exact match on the MPPT state code. Nonzero exit on failure,
   per-channel max-error report always printed.
2. Host unit sanity: reset semantics (en 0->1), duty clamps at 0.05/0.95,
   supervisor hysteresis hold band, MPPT direction reversal.
3. (Run by me after) the Simulink acceptance suite with the C Callers in place.

## Out of scope

PIL serial protocol / Arduino sketch, CAN, any Embedded Coder usage, any
algorithm changes or retuning.
