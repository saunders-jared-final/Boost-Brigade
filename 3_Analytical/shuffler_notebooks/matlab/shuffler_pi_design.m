%% shuffler_pi_design.m
%  Inner controller for ONE interleaved-half-bridge shuffler, designed on the
%  REAL plant identified from open-loop step tests on the switching model
%  (NOT the analytical averaged model -- that model had the duty->state coupling
%  backwards, which is what kept blowing up the common mode).
%
%  Identified steady-state gain matrix (state per unit duty), from
%  test2_diff.csv (step u_diff=d_A-d_B by 0.04) and test3_comm.csv (u_comm by 0.04):
%
%                 u_comm=d_A+d_B    u_diff=d_A-d_B
%        i_comm        +3.5            -200.4     <- transfer current (Loop B knob)
%        i_diff       -32.2              -0.1
%        v_diff       -76.5              -0.4     <- balance voltage  (Loop A knob)
%        v_comm        -1.8              -0.1
%
%  => block-triangular: two DECOUPLED SISO loops. And v_diff/i_diff = 2.38 ohm ~
%     1/G_mod, i.e. v_diff & i_diff are ONE degree of freedom (load-locked), so
%     the old 2-output MIMO servo was ill-posed. Use two PI loops instead.
%
%  Requires Control System Toolbox.

clear; clc;
Ts = 5e-6;                              % 200 kHz controller update

%% ---- identified SISO plants ----
% Loop B: u_diff -> i_comm   (first order; settles ~0.1 ms)
Kb = -200.0;  tau_b = 80e-6;
Pb = tf(Kb, [tau_b 1]);
% Loop A: u_comm -> v_diff   (2nd-order resonant; fit zeta/wn from test3 overshoot)
Ka = -76.5;   wn = 2*pi*6340;  zta = 0.527;
Pa = tf(Ka*wn^2, [1 2*zta*wn wn^2]);

%% ---- PI synthesis: |L|=1 at fc, PI zero at fz, gain sign = sign(plant DC) ----
pidsiso = @(P,fc,fz) deal_pi(P,fc,fz);
[KpB,KiB] = pidsiso(Pb, 2000, 1500);    % transfer-current loop ~2 kHz
[KpA,KiA] = pidsiso(Pa, 1500,  500);    % balance loop ~1.5 kHz (below 6.3 kHz res.)

fprintf('Loop A (v_diff via u_comm):  KpA = %+.6f   KiA = %+.4f\n', KpA, KiA);
fprintf('Loop B (i_comm via u_diff):  KpB = %+.6f   KiB = %+.4f\n', KpB, KiB);

%% ---- verify discrete closed-loop stability ----
for L = {{'A',Pa,KpA,KiA},{'B',Pb,KpB,KiB}}
    nm=L{1}{1}; P=L{1}{2}; Kp=L{1}{3}; Ki=L{1}{4};
    C  = tf([Kp Ki],[1 0]);
    Pd = c2d(P,Ts,'zoh');  Cd = c2d(C,Ts,'tustin');
    T  = feedback(Cd*Pd,1);
    fprintf('Loop %s: discrete |pole|max = %.4f  (stable: %d)\n', ...
            nm, max(abs(pole(T))), max(abs(pole(T)))<1);
end

%% ---- paste KpA KiA KpB KiB into shuffler_mimo_ctrl.m ----
function [Kp,Ki] = deal_pi(P,fc,fz)
    wc=2*pi*fc; wz=2*pi*fz;
    magc=abs(freqresp(P,wc));
    Kmag=1/(magc*sqrt(1+(wz/wc)^2));
    s=sign(dcgain(P));
    Kp=s*Kmag; Ki=Kp*wz;
end
