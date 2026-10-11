function [Iref, Pav, state] = shuffler_string_mppt(Vstr, Istr, beta, en)
%#codegen
% SHUFFLER_STRING_MPPT  Adaptive-step P&O on the STRING CURRENT.
%   Sits above the governor: perturbs the load current sink's reference I_ref,
%   measures string power averaged over each perturb window, and climbs.
%   The DPP-equalised string has a UNIMODAL P-V curve (the shufflers remove the
%   multi-peak problem), so a hill climber is sufficient by construction.
%
%   Adaptive step: |step| = clip(KA*|dP|, SMIN, SMAX) -> big steps far from the
%   peak, small steps near it. Deadband DB parks it at the top (no dither).
%   Governor hold-off: while the supervisor's beta is MOVING, P is being changed
%   by protection, not by us -> freeze and re-baseline (never climb on a
%   confounded measurement). A parked (constant) beta, even nonzero, is fine.
%
%   Block sample time Ts = 1e-3. One perturb decision every TP seconds.
%
%   Inputs : Vstr  string voltage (N0-N4, or sum VM1..4)             [V]
%            Istr  string current (sensor at the sink)               [A]
%            beta  supervisor governor state (hold-off signal)      [V/A]
%            en    enable (0 -> hold IREF0, reset)
%   Outputs: Iref  command for the controlled-current-sink load      [A]
%            Pav   last windowed power measurement (scope it)        [W]
%            state 0 = holding (governor active/boot), 1 = climbing, 2 = parked

Ts    = 1e-3;      % this block's sample time [s]
TP    = 0.02;      % perturb period [s] (string settles in ~3-5 ms; 20 ms is safe)
IREF0 = 12;        % initial string current [A] (below MPP ~14.35 -> must climb ~2.3 A)
IMIN  = 5;         % lower clamp [A]
IMAX  = 14.5;      % upper clamp [A] — keep BELOW the strong modules' Isc (14.96):
                   %   above Isc the string voltage collapses; don't let P&O visit
DB    = 1.0;       % power deadband [W]: |dP| below this -> parked, no step
KA    = 0.01;      % adaptive step gain [A/W]
SMIN  = 0.05;      % step clamp [A]
SMAX  = 1.0;
S0    = 0.25;      % bootstrap first-step size [A]
BTOL  = 1e-3;      % beta movement per window that counts as "governor active"

N = round(TP/Ts); % samples per perturb window

persistent iref dirn Pprev acc n boot b0 st
if isempty(iref)
    iref=IREF0; dirn=1; Pprev=0; acc=0; n=0; boot=true; b0=beta; st=0;
end

if en == 0
    iref=IREF0; dirn=1; Pprev=0; acc=0; n=0; boot=true; b0=beta; st=0;
    Iref=iref; Pav=Vstr*Istr; state=0; return;
end

% ---- accumulate power over the perturb window ----
acc = acc + Vstr*Istr;
n   = n + 1;

if n >= N
    Pw  = acc/N;  acc = 0;  n = 0;
    govActive = abs(beta - b0) > BTOL;   b0 = beta;

    if govActive
        boot = true;  st = 0;            % protection is moving the plant:
                                          % freeze, re-baseline when it parks
    elseif boot
        Pprev = Pw;  boot = false;       % baseline window, then a first nudge
        iref  = iref + dirn*S0;  st = 1;
    else
        dP = Pw - Pprev;
        if dP > DB                        % better -> keep going, scaled step
            step = min(max(KA*abs(dP),SMIN),SMAX);
            iref = iref + dirn*step;  st = 1;
        elseif dP < -DB                   % worse -> reverse, scaled step
            dirn = -dirn;
            step = min(max(KA*abs(dP),SMIN),SMAX);
            iref = iref + dirn*step;  st = 1;
        else                              % inside deadband -> parked at MPP
            st = 2;
        end
        Pprev = Pw;                       % always track (follows irradiance)
    end
    iref = min(max(iref,IMIN),IMAX);
end

Iref  = iref;
Pav   = Pprev;
state = st;
end
