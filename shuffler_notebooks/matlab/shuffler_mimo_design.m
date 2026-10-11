%% shuffler_mimo_design.m
%  Inner-loop MIMO regulator for ONE interleaved-half-bridge shuffler.
%  Replaces the three nested PI loops (phase current + voltage + balance) of
%  shuffler_integrated.ipynb with ONE constant-gain LQR + integral servo.
%
%    State   x  = [I_L1; I_L2; V_C1; V_C2]   (small-signal, about the op point)
%    Control d~ = [d_A; d_B]                  (duty deviation; PWM duty = D_OP + d~)
%    Tracked y  = [V_C1 - V_C2;  I_L1 - I_L2] (selector Cy)
%    Servo      xi[k+1] = xi[k] + Ts*(r - y),   d~ = -Kx*x - Ki*xi
%
%  IMPORTANT - designed in DISCRETE time (dlqr), NOT continuous lqr.
%  The notebook's sec.10 continuous-LQR gains are NOT implementable at the
%  200 kHz update rate: ZOH-sampling the proportional path makes the sampled
%  loop unstable (|eig| = 2.86 > 1) because the closed-loop resonant pair sits
%  near 0.4*f_sw. Designing with dlqr on the ZOH-discretised plant fixes this
%  (closed-loop |eig| = 0.98 < 1, verified). Requires Control System Toolbox.

clear; clc;

%% ---- averaged-SS component values (from shuffler_statespace.ipynb) ----
L_SELF=7.9e-6; L_M=5.85e-6; L_IND=8.2e-6; R_W=1.85e-3;
C_CAP=100e-6; F_SW=200e3; T_S=1/F_SW;          % 5 us update == one switching period
D_OP=0.5; VMOD_OP=38.7; IBAR=6.0; VSIG=2*VMOD_OP;
G_MOD=0.368;     % S, module conductance I_mp/V_mp at MPP -> PINS the cap common mode

%% ---- continuous pinned averaged plant  xdot = A x + B d~ ----
Linv=inv([L_SELF L_M; L_M L_SELF]);
A=zeros(4); B=zeros(4,2);
A(1:2,:)=Linv*([0 0 -D_OP (1-D_OP); 0 0 -D_OP (1-D_OP)] - R_W*[1 0 0 0;0 1 0 0]);
B(1:2,:)=Linv*[-VSIG 0; 0 -VSIG];
A(3,:)=[ D_OP/C_CAP      D_OP/C_CAP     0 0];
A(4,:)=[-(1-D_OP)/C_CAP -(1-D_OP)/C_CAP 0 0];
B(3,:)=[IBAR/C_CAP IBAR/C_CAP];  B(4,:)=[IBAR/C_CAP IBAR/C_CAP];
A(3,3)=A(3,3)-G_MOD/C_CAP;  A(4,4)=A(4,4)-G_MOD/C_CAP;
Cy=[0 0 1 -1; 1 -1 0 0];     % [V_C1-V_C2 ; I_L1-I_L2]

%% ---- ZOH-discretise, then state-scale for a well-conditioned Riccati solve ----
sysd=c2d(ss(A,B,Cy,0),T_S,'zoh');  Ad=sysd.A; Bd=sysd.B;
I0=10; V0=40; Dx=diag([I0 I0 V0 V0]); Dxi=inv(Dx);
Ads=Dxi*Ad*Dx;  Bds=Dxi*Bd;  Cs=Cy*Dx;

%% ---- augment with discrete integrators on the two tracked outputs, then dlqr ----
Ada=[Ads zeros(4,2); -T_S*Cs eye(2)];
Bda=[Bds; zeros(2,2)];
Q=diag([0.2 0.2 1.0 1.0 8e6 8e6]);   % [I_L1 I_L2 V_C1 V_C2 | int_ev int_ei]
R=diag([300 300]);                    % raise R to keep the resonant pair well inside Nyquist
Kd=dlqr(Ada,Bda,Q,R);

%% ---- physical gains + back-calculation anti-windup map ----
Kx  = Kd(:,1:4)*Dxi;     % duty per [I_L1 I_L2 V_C1 V_C2]
Ki  = Kd(:,5:6);         % duty per integral of [V_C1-V_C2 err, I_L1-I_L2 err]
Kaw = pinv(Ki);          % back-calc: feeds the saturation deficit back into xi

cl=abs(eig(Ada-Bda*Kd));
fprintf('discrete closed-loop |eig| max = %.4f  (stable: %d)\n',max(cl),max(cl)<1);
fprintf('\nKx =\n'); disp(Kx);
fprintf('Ki =\n'); disp(Ki);
fprintf('Kaw =\n'); disp(Kaw);

%% ---- save for the Simulink MATLAB Function block ----
mimo.Kx=Kx; mimo.Ki=Ki; mimo.Kaw=Kaw; mimo.Ts=T_S; mimo.D_OP=D_OP;
mimo.DLIM=0.45;                 % |d~| limit  (duty in [0.05,0.95])
mimo.IBAR=IBAR; mimo.VMOD=VMOD_OP;   % operating point subtracted before Kx
save('shuffler_mimo_gains.mat','-struct','mimo');
fprintf('\nSaved -> shuffler_mimo_gains.mat\n');
