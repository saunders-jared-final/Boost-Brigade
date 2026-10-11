function [rv1,rv2,rv3, beta, stress] = shuffler_string_supervisor( ...
          VM1,VM2,VM3,VM4, IM1,IM2,IM3,IM4, id1,id2,id3, ...
          dA1,dB1,dA2,dB2,dA3,dB3, en) %#ok<INUSD>
%#codegen
% SHUFFLER_STRING_SUPERVISOR  Feasibility governor for the 4-module string.
%   The inner centralised controller (shuffler_string_ctrl) already does perfect
%   equalisation at rv=0 — the max-harvest operating point. This supervisor's job
%   is PROTECTION: under deep shade, full equalisation can demand more shuffled
%   current than the duty range allows (duties rail, integrators walk — the
%   200 W/m2 failure). It detects that via duty utilisation and RELAXES the
%   equalisation just enough: slides the refs toward the string's natural sag
%   profile until the duties come off the rails.
%
%   Law:  deficit dl_k = max(IM) - IM_k   (shaded module -> large deficit)
%         stress      = max( max|i_diff|/I_RATED , max|d-0.5|/0.45 )
%                       -- the SHUFFLER CURRENT RATING is the binding constraint
%                       (duty authority ~ hundreds of amps, never binds; inductor
%                       saturation / MOSFET thermals bind at I_RATED)
%         beta        : slow integrator, up when stress > S_HI, decays when
%                       stress < S_LO (hysteresis band holds it)
%         rv_j        = beta * (dl_{j+1} - dl_j)   (M3 shaded -> (0,+,-) pattern)
%
%   Wire rv1..3 SUMMED with the manual Vref constants into shuffler_string_ctrl,
%   so the validation tests still work and the governor adds on top.
%   Block sample time: Ts3 = 1e-3 (slow, well under the inner-loop bandwidth).
%
%   Inputs : VM1..4 module voltages [V] (reserved for later MPPT trim)
%            IM1..4 module (PV) currents [A]
%            dA1..dB3 the six commanded duties
%            en     enable (0 -> outputs 0, state resets)
%   Outputs: rv1..3 protective reference offsets [V]
%            beta   governor state [V/A] (scope it)
%            stress duty utilisation 0..1 (scope it)

Ts3   = 1e-3;      % this block's sample time [s]
TF    = 5e-3;      % measurement LPF time constant [s]
I_RATED = 10;      % shuffler current rating [A]  *** SET TO YOUR HARDWARE ***
S_HI  = 0.90;      % engage threshold (fraction of rating; park just under rating —
                   %   backing off further is very expensive in harvest)
S_LO  = 0.70;      % relax threshold (hysteresis below this)
KB    = 60;        % beta ramp rate [(V/A)/s per unit over-stress]
KREL  = 6;         % beta decay rate when comfortable [(V/A)/s per unit under-stress]
BMAX  = 4;         % beta clamp [V/A]   (deep shade needs rv ~ 20-25 V: relief is
RVMAX = 30;        %   only ~0.14 A per V of sag — the strong modules' Voc knee)

persistent b imf idf
if isempty(b), b = 0; imf = [IM1;IM2;IM3;IM4]; idf = [id1;id2;id3]; end

if en == 0
    b = 0; imf = [IM1;IM2;IM3;IM4]; idf = [id1;id2;id3];
    rv1=0; rv2=0; rv3=0; beta=0; stress=0; return;
end

% ---- filtered measurements ----
im  = [IM1;IM2;IM3;IM4];
imf = imf + (Ts3/TF)*(im - imf);
dl  = max(imf) - imf;                       % >=0, large on the shaded module
idm = [id1;id2;id3];
idf = idf + (Ts3/TF)*(idm - idf);

% ---- stress = worst constraint utilisation (current rating binds first) ----
d6     = [dA1;dB1;dA2;dB2;dA3;dB3];
stress = max( max(abs(idf))/I_RATED , max(abs(d6 - 0.5))/0.45 );

% ---- governor integrator with hysteresis ----
if stress > S_HI
    b = b + Ts3*KB*(stress - S_HI);         % relax equalisation
elseif stress < S_LO
    b = b - Ts3*KREL*(S_LO - stress);       % recover toward max harvest
end                                          % in the band: hold (park)
b = min(max(b,0), BMAX);

% ---- protective references (consecutive deficit differences) ----
rv = b*(dl(2:4) - dl(1:3));
rv = min(max(rv,-RVMAX), RVMAX);

rv1=rv(1); rv2=rv(2); rv3=rv(3);
beta=b;
end
