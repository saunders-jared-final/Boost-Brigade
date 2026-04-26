function main()
%% main() — Batzelis (2018) PV State-Space Model
%
% Author: Jared Saunders
% Date:   21/04/2026
%
% Purpose: Replicate Fig. 4 from (Batzelis, 2018)
%          Case Study A: irradiance step 600 -> 1000 W/m^2
%
% State vector:   x = [vC, iL, Psi, vref, vmppt, pmppt]'   (Eq. 13)
% Input vector:   u = [G, T]'                               (Eq. 13)
% Output:         y = Ppv                                   (Eq. 13)
%
% Run by typing:  main()  in the MATLAB Command Window


%% =========================================================================
%  SYSTEM PARAMETERS  (Table I — Batzelis 2018)
% ==========================================================================
R_L     = 0.01;         % Inductor parasitic resistance      [Ohm]
R_d     = 0.1;          % Boost diode series resistance      [Ohm]
a_0     = 18.34;        % Diode modified ideality factor STC [V]
V_dc    = 700;          % DC-link voltage                    [V]
R_c     = 0.3;          % Capacitor ESR                      [Ohm]
DelV_d  = 0.1;          % Boost diode forward voltage drop   [V]
R_s0    = 2.55;         % Series resistance at STC           [Ohm]
C       = 470e-6;       % Input capacitance                  [F]
R_sw    = 0.1;          % Switch on-resistance               [Ohm]
I_ph0   = 15.88;        % Photo-current at STC               [A]
R_sh0   = 531.5;        % Shunt resistance at STC            [Ohm]
L       = 1.2e-3;       % Inductance                         [H]
R_dc    = 0.0932;       % DC-link parasitic resistance       [Ohm]
I_s0    = 7.4e-10;      % Diode saturation current STC       [A]
V_step  = 4.2;          % MPPT perturbation step size        [V]
F_mppt  = 10;           % MPPT update frequency              [Hz]
Ts      = 100e-6;       % Simulation time step               [s]

% PI controller gains  (Table I, Batzelis 2018)
% Kp maps voltage error [V] -> duty cycle correction [-]
% Ki maps voltage error [V] -> duty cycle rate [1/s], integrated over Ts
% Values from Table I are used directly; the PI output D is clamped to [0,1]
K_p     = 2.4e-5;       % Proportional gain  [1/V]
K_i     = 0.12;         % Integral gain      [1/(V·s)]

% Derived
T_mppt      = 1 / F_mppt;
mppt_steps  = round(T_mppt / Ts);  % Integer step count — avoids float mod errors

% Temperature coefficients (standard crystalline silicon, IEC 60904-3)
% Using simple linear scaling; Is modelled as constant (variation small vs Iph)
G_stc  = 1000;      % Reference irradiance [W/m^2]
T_stc  = 25;        % Reference temperature [degC]
mu_Iph = 0.0004;    % Iph relative temp coeff  [1/degC]  (+0.04 %/degC typical)
mu_Is  = 0.0;       % Is temp coeff — set to 0 to use STC value directly
                    % (exponential dependence is negligible for T near STC)


%% =========================================================================
%  IRRADIANCE / TEMPERATURE PROFILE
%  600 W/m^2 for t = 0..0.4 s, then step to 1000 W/m^2
%  (power peaks near MPP at ~1.6 s as in paper Fig. 4)
% ==========================================================================
t_end = 2.5;
t     = (0 : Ts : t_end - Ts);
N     = length(t);

G_vec           = 600 * ones(1, N);
G_vec(t >= 0.4) = 1000;           % Step at 0.4 s

T_vec = 25 * ones(1, N);


% (helper functions defined at end of file)

% Bundle all parameters into a struct so local functions can receive them
p.G_stc  = G_stc;   p.T_stc  = T_stc;
p.I_ph0  = I_ph0;   p.I_s0   = I_s0;
p.a_0    = a_0;     p.R_s0   = R_s0;   p.R_sh0  = R_sh0;
p.mu_Iph = mu_Iph;  p.mu_Is  = mu_Is;
p.R_c    = R_c;     p.K_p    = K_p;


%% =========================================================================
%  INITIAL CONDITIONS  (Eqs. 20–24)
%  Steady state at MPP under G0 = 600 W/m^2
% ==========================================================================
[Iph0_op, Is0_op, a0_op, Rs0_op, Rsh0_op] = translate_params(G_vec(1), T_vec(1), p);

w0   = lambertw(0, Iph0_op * exp(1) / Is0_op);          % Eq. 23
Vmp0 = (1 + Rs0_op/Rsh0_op) * a0_op * (w0-1) ...
       - Rs0_op * Iph0_op * (1-1/w0);                   % Eq. 21
Imp0 = Iph0_op * (1-1/w0) - a0_op * (w0-1) / Rsh0_op;  % Eq. 22
Pmp0 = Vmp0 * Imp0;

D0   = (V_dc + DelV_d + (R_d + R_dc + R_L)*Imp0 - Vmp0) ...
     / (V_dc + DelV_d + (R_d + R_dc - R_sw)*Imp0);      % Eq. 20

% At steady state: iL = Ipv, so vC = Vpv + Rc*(Ipv - iL) = Vmp0
% (the Rc drop is zero at steady state since Ipv = iL)
Psi0 = D0;
vC0  = Vmp0;   % Correct: Rc*(Imp0 - Imp0) = 0

x0 = [vC0; Imp0; Psi0; Vmp0; Vmp0; Pmp0];

fprintf('--- Initial Conditions (G = %d W/m^2) ---\n', G_vec(1));
fprintf('  Vmp0 = %.3f V\n',  Vmp0);
fprintf('  Imp0 = %.3f A\n',  Imp0);
fprintf('  Pmp0 = %.1f W\n',  Pmp0);
fprintf('  D0   = %.4f\n',    D0);
if D0 < 0 || D0 > 1
    error('D0 = %.4f is outside [0,1] — check R_sw vs R_dc/R_d parameters.', D0);
end
fprintf('------------------------------------------\n\n');


%% =========================================================================
%  MAXIMUM AVAILABLE POWER  (reference overlay for plot)
% ==========================================================================
Pmax_vec = zeros(1, N);
for kk = 1:N
    [Iph_k, Is_k, a_k, Rs_k, Rsh_k] = translate_params(G_vec(kk), T_vec(kk), p);
    w_k            = lambertw(0, Iph_k * exp(1) / Is_k);
    Vmp_k          = (1 + Rs_k/Rsh_k)*a_k*(w_k-1) - Rs_k*Iph_k*(1-1/w_k);
    Imp_k          = Iph_k*(1-1/w_k) - a_k*(w_k-1)/Rsh_k;
    Pmax_vec(kk)   = Vmp_k * Imp_k;
end


%% =========================================================================
%  SIMULATION LOOP — Forward-Euler difference equations (Eqs. 14–19)
% ==========================================================================
vC_arr    = zeros(1,N);  iL_arr    = zeros(1,N);
Psi_arr   = zeros(1,N);  vref_arr  = zeros(1,N);
vmppt_arr = zeros(1,N);  pmppt_arr = zeros(1,N);
Vpv_arr   = zeros(1,N);  Ipv_arr   = zeros(1,N);
Ppv_arr   = zeros(1,N);  D_arr     = zeros(1,N);

% Step k = 1
vC_arr(1) = x0(1);  iL_arr(1)    = x0(2);
Psi_arr(1)= x0(3);  vref_arr(1)  = x0(4);
vmppt_arr(1)= x0(5);pmppt_arr(1) = x0(6);
[Ipv_arr(1), Vpv_arr(1), Ppv_arr(1), D_arr(1)] = ...
    algebraic_eqs(x0(1), x0(2), x0(3), x0(4), G_vec(1), T_vec(1), p);

for k = 2:N
    % --- Previous values ---
    vC_k1    = vC_arr(k-1);     iL_k1    = iL_arr(k-1);
    Psi_k1   = Psi_arr(k-1);    vref_k1  = vref_arr(k-1);
    vmppt_k1 = vmppt_arr(k-1);  pmppt_k1 = pmppt_arr(k-1);
    Ipv_k1   = Ipv_arr(k-1);    Vpv_k1   = Vpv_arr(k-1);
    Ppv_k1   = Ppv_arr(k-1);    D_k1     = D_arr(k-1);

    % Eq. 14 — capacitor voltage
    vC_k  = vC_k1 + (Ipv_k1 - iL_k1) / C * Ts;

    % Eq. 15 — inductor current
    iL_k  = iL_k1 ...
          + (Vpv_k1 - (R_L + D_k1*R_sw)*iL_k1) / L * Ts ...
          - (1 - D_k1)*(V_dc + DelV_d + (R_d + R_dc)*iL_k1) / L * Ts;

    % Eq. 16 — PI integrator (Psi clamped to keep D physical)
    Psi_k = Psi_k1 + K_i * (Vpv_k1 - vref_k1) * Ts;
    Psi_k = min(max(Psi_k, 0.0), 1.0);   % Anti-windup clamp

    % Eqs. 17–19 — P&O MPPT (fires every mppt_steps)
    if mod(k-1, mppt_steps) == 0
        dV = Vpv_k1 - vmppt_k1;
        dP = Ppv_k1 - pmppt_k1;
        if abs(dV) < 1e-6;  s = 0;  else;  s = sign(dP/dV);  end

        vref_k  = vref_k1 + s * V_step;
        vmppt_k = Vpv_k1;
        pmppt_k = Ppv_k1;
    else
        vref_k  = vref_k1;
        vmppt_k = vmppt_k1;
        pmppt_k = pmppt_k1;
    end

    % Algebraic outputs
    [Ipv_k, Vpv_k, Ppv_k, D_k] = algebraic_eqs( ...
        vC_k, iL_k, Psi_k, vref_k, G_vec(k), T_vec(k), p);

    % Divergence guard — stop early and warn if states blow up
    if ~isfinite(vC_k) || ~isfinite(iL_k) || ~isfinite(Ppv_k)
        warning('Simulation diverged at k=%d (t=%.4f s). Truncating.', k, t(k));
        N = k - 1;
        break
    end

    % Store
    vC_arr(k)=vC_k;  iL_arr(k)=iL_k;   Psi_arr(k)=Psi_k;
    vref_arr(k)=vref_k; vmppt_arr(k)=vmppt_k; pmppt_arr(k)=pmppt_k;
    Vpv_arr(k)=Vpv_k; Ipv_arr(k)=Ipv_k; Ppv_arr(k)=Ppv_k; D_arr(k)=D_k;
end


%% =========================================================================
%  PLOT — Replicating Fig. 4 from Batzelis (2018)
% ==========================================================================
figure('Name', 'Fig. 4 Replication — Case Study A', 'Color', 'w', ...
       'Position', [80 80 700 700]);

% ---- subplot (a): Power vs Time ----------------------------------------
subplot(2,1,1);
plot(t, Pmax_vec, '--', 'Color', [0.55 0.0 0.75], 'LineWidth', 1.8); hold on;
plot(t, Ppv_arr,  '-',  'Color', [1.0  0.6 0.0],  'LineWidth', 1.2);
xlabel('Time (s)');
ylabel('Power (W)');
title('(a) Maximum and Actual Output Power');
legend('Maximum power', 'Actual power (SS-100\mus)', 'Location', 'southeast');
xlim([0 t_end]);
ylim([2500 5000]);
grid on;  box on;

% ---- subplot (b): P-V curve + operating point trace --------------------
subplot(2,1,2);

V_sweep = linspace(0, 420, 2000);

% P-V curves (using simplified explicit single-diode, Rc=0 for the curve)
I_pv_curve = @(V, Iph, Is, a, Rs, Rsh) ...
    real((Rsh*Iph - V) / (Rs + Rsh) ...
    - a/Rs * lambertw(0, Rs*Rsh*Is/(a*(Rs+Rsh)) ...
    .* exp(Rsh*(Rs*Iph + V)./(a*(Rs+Rsh)))));

[Iph_600, Is_600, a_600, Rs_600, Rsh_600] = translate_params(600,  25, p);
[Iph_1k,  Is_1k,  a_1k,  Rs_1k,  Rsh_1k] = translate_params(1000, 25, p);

P_600 = max(V_sweep .* I_pv_curve(V_sweep, Iph_600, Is_600, a_600, Rs_600, Rsh_600), 0);
P_1k  = max(V_sweep .* I_pv_curve(V_sweep, Iph_1k,  Is_1k,  a_1k,  Rs_1k,  Rsh_1k),  0);

% MPP locus
G_locus   = linspace(600, 1000, 300);
Vmp_locus = zeros(1,300);  Pmp_locus = zeros(1,300);
for idx = 1:300
    [Iph_l, Is_l, a_l, Rs_l, Rsh_l] = translate_params(G_locus(idx), 25, p);
    w_l             = lambertw(0, Iph_l*exp(1)/Is_l);
    Vmp_locus(idx)  = (1+Rs_l/Rsh_l)*a_l*(w_l-1) - Rs_l*Iph_l*(1-1/w_l);
    Imp_l           = Iph_l*(1-1/w_l) - a_l*(w_l-1)/Rsh_l;
    Pmp_locus(idx)  = Vmp_locus(idx)*Imp_l;
end

plot(V_sweep, P_600,        '-',  'Color', [0.0 0.45 0.74], 'LineWidth', 1.8); hold on;
plot(V_sweep, P_1k,         '-',  'Color', [0.0 0.60 0.25], 'LineWidth', 1.8);
plot(Vmp_locus, Pmp_locus,  ':',  'Color', [0.55 0 0.75],   'LineWidth', 1.8);
plot(Vpv_arr, Ppv_arr,      '-',  'Color', [0.9 0.2 0.0],   'LineWidth', 1.2);

% Mark start/end MPPs
plot(Vmp_locus(1),   Pmp_locus(1),   'o', 'MarkerSize', 9, ...
     'MarkerFaceColor', [0.3 0.8 1.0], 'MarkerEdgeColor', 'k', 'LineWidth', 1);
plot(Vmp_locus(end), Pmp_locus(end), 'o', 'MarkerSize', 9, ...
     'MarkerFaceColor', [0.3 0.8 1.0], 'MarkerEdgeColor', 'k', 'LineWidth', 1);
text(Vmp_locus(1)-55,  Pmp_locus(1)-100, 'MPP  0 s',   'FontSize', 8.5);
text(Vmp_locus(end)+5, Pmp_locus(end)-200, 'MPP  2.2 s', 'FontSize', 8.5);

xlabel('Voltage (V)');
ylabel('Power (W)');
title('(b) P-V Curve and Operating Point Trace');
legend('P-V at 600 W/m^2','P-V at 1000 W/m^2','MPP trace', ...
       'Oper. point trace', 'Location', 'northwest');
xlim([0 430]);
ylim([0 5500]);
grid on;  box on;

end  % ---- end main() -------------------------------------------------------


%% =========================================================================
%  LOCAL FUNCTIONS  (must live after the end of main, at file scope)
% ==========================================================================

function [Iph, Is, a, Rs, Rsh] = translate_params(G, T, p)
% Translate STC five-parameters to operating conditions (G [W/m^2], T [degC])
    Iph = (G / p.G_stc) * p.I_ph0 * (1 + p.mu_Iph * (T - p.T_stc));
    Is  = p.I_s0 * (1 + p.mu_Is  * (T - p.T_stc));
    a   = p.a_0;
    Rs  = p.R_s0;
    Rsh = p.R_sh0 * (p.G_stc / G);
end

function [Ipv, Vpv, Ppv, D] = algebraic_eqs(vC, iL, Psi, vref, G, T, p)
% Compute algebraic outputs from states:
%   Ipv via Lambert W  (Eq. 2)
%   Vpv                (Eq. 3)
%   D from PI output   (Eq. 7)
    [Iph, Is, a, Rs, Rsh] = translate_params(G, T, p);
    Rc = p.R_c;   Kp = p.K_p;

    coeff    = (Rs + Rc) * Rsh * Is / (a * (Rs + Rc + Rsh));
    exponent = Rsh * ((Rs + Rc) * Iph + vC - Rc * iL) / (a * (Rs + Rc + Rsh));
    exponent = min(exponent, 500);          % Guard against overflow
    W_val    = lambertw(0, coeff * exp(exponent));

    Ipv = (Rsh * Iph - (vC - Rc * iL)) / (Rs + Rc + Rsh) ...
          - a / (Rs + Rc) * W_val;         % Eq. 2

    Vpv = vC - Rc * (Ipv - iL);            % Eq. 3
    Ppv = Vpv * Ipv;

    D   = Psi + Kp * (Vpv - vref);         % Eq. 7
    D   = min(max(D, 0.0), 0.99);          % Clamp to physical range
end