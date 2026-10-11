function [dA1,dB1,dA2,dB2,dA3,dB3] = shuffler_string_ctrl(VM1,VM2,VM3,VM4, ic1,ic2,ic3, rv1,rv2,rv3)
%#codegen
% SHUFFLER_STRING_CTRL  Centralised decoupling controller for the 4-module /
%   3-shuffler string. Replaces the three local PI controllers (which limit-cycle
%   because the loops couple through the shared nodes). Sees ALL module voltages +
%   common currents, commands all six duties.
%
%   Law (INTEGRAL-only decoupler):  xi += Ts*(r-y);  u = M*xi , M = G^-1*diag(kI).
%   G*M = diag(kI) -> six independent integrators, coupling cancelled at DC.
%   Kept integral-only ON PURPOSE: a proportional term pushes the loop up into the
%   ~6 kHz resonance where the STATIC G^-1 decoupling breaks down (coupling returns)
%   and it re-destabilises. The residual ~±5 V differential ring is the lightly-
%   damped diff resonance -> handle it with PASSIVE damping (small snubber / more
%   series R), not more loop gain. kI: v_diff ~150 Hz, i_comm ~400 Hz. Ts = 5 us.
%
%   Inputs : VM1..VM4 module V [V]; ic1..ic3 = IL_A+IL_B per shuffler [A];
%            rv1..rv3 balance refs (0 for now, later from shuffler_string_supervisor)
%   Outputs: dA1,dB1,dA2,dB2,dA3,dB3.

Ts = 50e-6;  DMIN = 0.05;  DMAX = 0.95;   % 50 us: loops are 150/400 Hz integral-
                                          % only -> still 50x oversampled, but 10x
                                          % fewer forced solver steps than 5 us.
                                          % *** SET THE BLOCK SAMPLE TIME TO MATCH ***

% ---- M = G^-1 * diag(kI)  (rows: uc1,uc2,uc3,ud1,ud2,ud3) ----
% Built from CLEAN identification (all 6 modal steps re-read as settled means).
M = [ -13.1997   0.0000  -0.9198  -0.0725   1.0611   0.0819;
       -0.2685 -12.7794  -0.0187  -1.0277   1.0521   1.0356;
       -0.9198   0.0000 -13.1997  -1.0402   0.2325   1.1747;
        0        0        0       -1.9456   0        0     ;
        0        0        0        0       -2.0681   0     ;
        0        0        0        0        0       -2.0334 ];

persistent xi
if isempty(xi), xi = zeros(6,1); end

y = [VM1-VM2; VM2-VM3; VM3-VM4; ic1; ic2; ic3];   % [v_diff_1..3 ; i_comm_1..3]
r = [rv1; rv2; rv3; 0; 0; 0];                     % i_comm ref = 0

xi_try = xi + Ts*(r - y);
u  = M*xi_try;
uc = u(1:3);  ud = u(4:6);

dA = 0.5 + 0.5*(uc + ud);
dB = 0.5 + 0.5*(uc - ud);
dAs = min(max(dA, DMIN), DMAX);
dBs = min(max(dB, DMIN), DMAX);
if isequal(dAs,dA) && isequal(dBs,dB)   % anti-windup: commit only if unsaturated
    xi = xi_try;
end

dA1=dAs(1); dB1=dBs(1);
dA2=dAs(2); dB2=dBs(2);
dA3=dAs(3); dB3=dBs(3);
end
