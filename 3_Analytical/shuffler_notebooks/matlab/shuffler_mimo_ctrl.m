function [dA, dB] = shuffler_mimo_ctrl(IL1, IL2, VC1, VC2, rv, ri)
%#codegen
% SHUFFLER_MIMO_CTRL  Inner controller for one interleaved-half-bridge shuffler.
%   Two DECOUPLED SISO PI loops, designed on the MEASURED plant (open-loop step
%   tests test2_diff / test3_comm, see shuffler_pi_design.m). Drop into a
%   Simulink MATLAB Function block at T_s = 5 us (one 200 kHz switching period).
%   SAME I/O as the old LQR block -> drop-in replacement, no re-wiring.
%
%   *** WHY THIS REPLACED THE LQR/MIMO SERVO ***
%   The real circuit's duty->state coupling is the OPPOSITE of the analytical
%   averaged model the LQR was built on:
%        u_diff = d_A - d_B  ->  i_comm = IL_A + IL_B   (gain -200 A/duty)
%        u_comm = d_A + d_B  ->  v_diff = V_C1 - V_C2   (gain  -76.5 V/duty)
%   and v_diff,i_diff are locked by the module conductance (one DOF), so a
%   2-output MIMO servo tracking both was ill-posed. The old gains pushed the
%   common mode straight into runaway. These two SISO loops use the right knobs.
%
%   Inputs (sensed each switching period, filtered):
%     IL1,IL2 : phase inductor currents IL_A, IL_B               [A]
%     VC1,VC2 : module cap voltages Vc_high (top), Vc_Low (bot)  [V]
%     rv      : balance reference, V_C1-V_C2*  (0 under uniform irradiance) [V]
%     ri      : transfer-current reference, (IL_A+IL_B)*  (0 = no shuffling)[A]
%   Outputs:
%     dA,dB   : the two half-bridge duty cycles -> PWM comparators.

% ---- gains from shuffler_pi_design.m (identified-plant PI, 200 kHz) ----
Ts  = 5e-6;   D_OP = 0.5;   DMAX = 0.95;   DMIN = 0.05;
KpA = -0.012108;  KiA = -38.0399;   % Loop A: v_diff via u_comm = d_A+d_B
KpB = -0.005672;  KiB = -53.4563;   % Loop B: i_comm via u_diff = d_A-d_B

% ---- integrator states, persistent across steps ----
persistent xiA xiB
if isempty(xiA), xiA = 0; end
if isempty(xiB), xiB = 0; end

% ---- modal measurements ----
v_diff = VC1 - VC2;          % balance error coordinate
i_comm = IL1 + IL2;          % transfer (common) current
e_v = rv - v_diff;           % Loop A error
e_i = ri - i_comm;           % Loop B error

% ---- PI outputs (unsaturated modal duties) ----
u_comm_un = KpA*e_v + KiA*xiA;
u_diff_un = KpB*e_i + KiB*xiB;

% ---- reconstruct + saturate the two half-bridge duties ----
dA_un = D_OP + 0.5*(u_comm_un + u_diff_un);
dB_un = D_OP + 0.5*(u_comm_un - u_diff_un);
dA = min(max(dA_un, DMIN), DMAX);
dB = min(max(dB_un, DMIN), DMAX);

% ---- back-calculation anti-windup (MIMO-correct: use the REALISED duties) ----
u_comm_r = (dA - D_OP) + (dB - D_OP);    % modal duty actually applied
u_diff_r = (dA - D_OP) - (dB - D_OP);
xiA = xiA + Ts*e_v + (1/KiA)*(u_comm_r - u_comm_un);
xiB = xiB + Ts*e_i + (1/KiB)*(u_diff_r - u_diff_un);
end
