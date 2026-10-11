function [rv, active] = shuffler_balance_loop(VC1, VC2, en)
%#codegen
% SHUFFLER_BALANCE_LOOP  Loop 3 — differential-current / mismatch equaliser.
%   Slow supervisor that commands rv = (V_C1 - V_C2)* to the inner loop so the
%   two series PV modules share the string current near each one's MPP. Moves
%   ONLY mismatch power (the inner loop realises the differential current; ri
%   stays 0). Idle/clamped under uniform irradiance; engages on real mismatch;
%   parks (freezes rv) once settled. Specialised to 2 modules from
%   DifferentialCurrentController (shuffler_integrated.ipynb, loop 3).
%
%   *** Set this block's sample time to Ts3 (1 ms) — it MUST be much slower than
%       the inner loop (2 ms settle). Do NOT run it at the 5 us inner rate. ***
%
%   Inputs : VC1,VC2  filtered module cap voltages (Vc_high, Vc_Low)   [V]
%            en       enable (Constant 1, or a switch for A/B testing) [-]
%   Outputs: rv       differential-voltage command -> inner block 'rv' [V]
%            active   1 while equalising, 0 when parked (for scoping)

% ---- tuning ----
Ts3   = 1e-3;     % loop-3 update period  [s]  (== this block's sample time)
KI3   = 50.0;     % integral rate [1/s] -> ~8 Hz loop, ~30 ms settle (slow, gentle)
SGN   = -1;       % sign that drives v_diff toward 0  *** CONFIRM ONCE IN SIM ***
RVMAX = 6.0;      % clamp on commanded imbalance [V] (keeps weak module off I_sc knee)
DBE   = 1.5;      % engage deadband on |spread| [V]  (idle under uniform)
DBP   = 0.4;      % "settled" spread threshold [V]
HOLD  = 25;       % consecutive settled ticks before park

% ---- state ----
persistent rv_i act cnt
if isempty(rv_i), rv_i = 0; act = false; cnt = 0; end

vdiff = VC1 - VC2;                       % module-voltage spread

if en == 0
    rv_i = 0; act = false; cnt = 0;
    rv = 0; active = false; return;
end

if abs(vdiff) > DBE                      % real mismatch -> engage
    act = true; cnt = 0;
end

if act
    rv_i = rv_i + SGN*KI3*Ts3*vdiff;     % slow integrate toward equalisation
    rv_i = max(min(rv_i, RVMAX), -RVMAX);% clamp authority / protect weak module
    if abs(vdiff) < DBP, cnt = cnt + 1; else, cnt = 0; end
    if cnt >= HOLD, act = false; end     % park: hold rv_i steady
end

rv = rv_i;                               % parked or active, hold/emit the command
active = act;
end
