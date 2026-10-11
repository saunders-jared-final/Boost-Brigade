function P = init_params()
%INIT_PARAMS  Single source of truth for the 3-module carpark string (Version 0 PCB).
%   Every script starts with  P = init_params();  All block paths, logged-signal
%   names, ratings and test settings live HERE. Generic in the module count P.N.
%
%   Model: carpark_shuffler_sim.slx = copy of SIL_power_shuffler_sim.slx reduced
%   to 3 modules / 2 shufflers (see README.md in this folder for the edit list).
%
%   NOTE ON CONTROLLER GAINS: the MATLAB Function blocks carry embedded
%   constants (Ts, M, thresholds). shuffler_string_ident writes M into the JSON
%   parameter file that generates the firmware params.h, and prints the block
%   paste. Keep the block copies in sync with the values here.

%% ---- model & modes ----------------------------------------------------
P.mdl        = 'carpark_shuffler_sim';
P.N          = 3;                       % PV modules in the string
P.NS         = P.N - 1;                 % shufflers
P.NL         = 2 * P.NS;                % half-bridge legs (A,B per shuffler)
P.ctrl_mode  = 1;                       % 1 = closed loop, 0 = identification (variant)

%% ---- firmware parameter file (shared with the C core) -----------------
here = fileparts(mfilename('fullpath'));
P.params_json = fullfile(here, '..', '..', '6_RTOS', 'ctrl_core', 'params', 'shuffler_params.json');
P.golden_dir  = fullfile(here, '..', '2_SIL_Software_In_The_Loop', 'firmware', 'test', 'golden');

%% ---- block paths (update if blocks move) ------------------------------
m = P.mdl;
P.path.irr  = arrayfun(@(k) sprintf('%s/Power Circuit/Irradiance %d', m, k), 1:P.N,  'UniformOutput', false);
P.path.vref = arrayfun(@(k) sprintf('%s/Supervisor/Vref%d',           m, k), 1:P.NS, 'UniformOutput', false);
P.path.shuf = arrayfun(@(k) sprintf('%s/Power Circuit/Power Shuffler%d', m, k), 1:P.NS, 'UniformOutput', false);
P.path.supEn  = [m '/Supervisor/Enable'];
P.path.mpptEn = [m '/MPPT/Enable'];
% Identification-mode duty constants (the Variant Source inputs), order dA1,dB1,dA2,dB2,...
P.path.dutyConst = cell(1, P.NL);
for k = 1:P.NS
    P.path.dutyConst{2*k-1} = sprintf('%s/Power Shuffler%d/dA%d_const', m, k, k);
    P.path.dutyConst{2*k}   = sprintf('%s/Power Shuffler%d/dB%d_const', m, k, k);
end

%% ---- logged signal names (To Workspace, in Telemetry) -----------------
P.sig.vm   = arrayfun(@(k) sprintf('VM%d', k),  1:P.N, 'UniformOutput', false);
P.sig.im   = arrayfun(@(k) sprintf('IM%d', k),  1:P.N, 'UniformOutput', false);   % TRUE plant module currents
P.sig.imr  = arrayfun(@(k) sprintf('IMr%d', k), 1:P.N, 'UniformOutput', false);   % reconstructed (recon block)
P.sig.il   = [arrayfun(@(k) sprintf('ILA%d', k), (1:P.NS).', 'UniformOutput', false), ...
              arrayfun(@(k) sprintf('ILB%d', k), (1:P.NS).', 'UniformOutput', false)];
P.sig.duty = cell(1, P.NL);
for k = 1:P.NS
    P.sig.duty{2*k-1} = sprintf('dA%d', k);
    P.sig.duty{2*k}   = sprintf('dB%d', k);
end
P.sig.vstr = 'V_String';
P.sig.istr = 'I_String';

%% ---- PV module: 150 W hard-frame panel (README datasheet) -------------
P.pv.Vmp = 18.28;  P.pv.Imp = 8.207;  P.pv.Pmp = 150;
P.pv.Isc = 8.721;  P.pv.Voc = 22.407;
% MPP vs irradiance for harvest ceilings (linear scaling; refine from the model)
P.pv.pmp_irr = [0 200 500 1000];
P.pv.pmp_w   = [0 30 75 150];
P.pv.pmp     = @(g) interp1(P.pv.pmp_irr, P.pv.pmp_w, g);

%% ---- plant (Version 0 PCB; the circuit blocks hold the live values) ---
P.plant.L_self = 7.9e-6;   P.plant.L_m = 5.85e-6;  P.plant.R_w = 1.85e-3;  % TDK ERUC23-4R1K
P.plant.R_phase= 61e-3;    % per-phase series R (damping); STD45N10F7 Rds(on) is lower - keep until re-identified
P.plant.C      = 2*130e-6; % two 130 uF electrolytics per converter half (TDK B40910A0137M000)
P.plant.f_sw   = 100e3;    % HRTIM PWM as flashed on the bench (averaged model: no switching)

%% ---- controller (mirror of shuffler_string_ctrl.m) --------------------
P.ctrl.Ts    = 100e-6;     % 10 kHz inner loop on the STM32G474
P.ctrl.kI_v  = 2*pi*150;   % rad/s, v_diff channels  (ident builds M = G \ diag(kI))
P.ctrl.kI_i  = 2*pi*400;   % rad/s, i_comm channels
P.ctrl.kp_ratio_v = 1.58e-4;   P.ctrl.kp_ratio_i = 1.08e-4;
P.ctrl.fc_lpf = 2000;
P.ctrl.DMIN = 0.05;  P.ctrl.DMAX = 0.95;

%% ---- supervisor / feasibility governor (mirror) -----------------------
P.sup.Ts = 1e-3;  P.sup.TF = 5e-3;
P.sup.I_RATED = 10;                    % shuffler current rating [A] (TMCS1126B4 +-15.5 A, OC latch 10 A)
P.sup.S_HI = 0.90;  P.sup.S_LO = 0.70;
P.sup.KB = 60;  P.sup.KREL = 6;  P.sup.BMAX = 4;  P.sup.RVMAX = 30;

%% ---- MPPT (mirror; lab-load variant only - the EcoFlow does string MPPT) --
P.mppt.Ts = 1e-3;  P.mppt.TP = 0.02;
P.mppt.IREF0 = 8;  P.mppt.IMIN = 2;  P.mppt.IMAX = 8.5;   % IMAX below Isc = 8.72 A
P.mppt.DB = 1.0;   P.mppt.KA = 0.01; P.mppt.SMIN = 0.05; P.mppt.SMAX = 1.0;
P.mppt.S0 = 0.25;  P.mppt.BTOL = 1e-3;

%% ---- test settings ----------------------------------------------------
P.test.Tavg    = 0.01;         % settled-stats window [s]
P.test.simMode = 'accelerator';
P.test.du      = 0.04;         % identification modal step size
end
