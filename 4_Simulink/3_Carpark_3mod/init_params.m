function P = init_params()
%INIT_PARAMS  Single source of truth for the 3-module carpark string (Version 0 PCB).
%   Every script starts with  P = init_params();  All block paths, logged-signal
%   names, ratings and test settings live HERE. Generic in the module count P.N.
%
%   Model: carpark_shuffler_sim.slx, built from the MIL model per design-book
%   ch.2 (README.md has the short checklist).
%
%   TARGET ENVIRONMENT (choose before running anything; default BENCH):
%       SETUP = 'BENCH';  P = init_params();   % 3 x NGE103 channels into the DL3021
%       SETUP = 'PV80';   P = init_params();   % 3 x KAUSSP80 panels into the DL3021
%   init_params also pushes the numeric variant selectors and the CTRL / SENSE
%   parameter structs into the base workspace (the model's PreLoadFcn/InitFcn
%   calls it), so the blocks always see the same numbers as the scripts.
%
%   CONTROLLER GAINS: M, Kp ratios and fc are read from the shared firmware
%   parameter file (6_RTOS/ctrl_core/params/shuffler_params.json), so the model
%   runs exactly the gains the firmware is built with. shuffler_string_ident
%   writes a new M into that file; nothing is pasted into blocks any more.

%% ---- target environment ------------------------------------------------
P.setup = 'BENCH';
if evalin('base', 'exist(''SETUP'',''var'')'), P.setup = upper(evalin('base', 'SETUP')); end
assert(any(strcmp(P.setup, {'BENCH', 'PV80'})), 'SETUP must be ''BENCH'' or ''PV80''');

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
P.qspice_meas = fullfile(here, '..', '..', '2_Qspice', 'Claude''s outputs', 'PCB_Baseline', 'results', 'S9i.meas.json');

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
    P.path.dutyConst{2*k-1} = sprintf('%s/Power Circuit/Power Shuffler%d/dA%d_const', m, k, k);
    P.path.dutyConst{2*k}   = sprintf('%s/Power Circuit/Power Shuffler%d/dB%d_const', m, k, k);
end

%% ---- logged signal names (To Workspace, in Telemetry) -----------------
P.sig.vm   = arrayfun(@(k) sprintf('VM%d', k),  1:P.N, 'UniformOutput', false);   % TRUE plant module voltages
P.sig.vmm  = arrayfun(@(k) sprintf('VMm%d', k), 1:P.N, 'UniformOutput', false);   % as MEASURED (Sensing block)
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

%% ---- sources ----------------------------------------------------------
% BENCH: one NGE103 channel per module (32 V / 3 A / 33.6 W per channel). On the
% 13 Oct open-loop run the e-load held 70.0 V in CV and the string current sat at
% 0.95 A with module 1's voltage moving freely with shuffler-2 duty, i.e. the
% PSU channels were in CURRENT LIMIT: the bench source is a rectangular IV curve
% (current source Ilim, clamped at Vset). That is PV-like, which is the point.
% *** FILL IN the NGE103 settings used on the bench (front panel) ***
P.src.bench.Vset = [25 25 25];      % [V] CV setpoint per channel
P.src.bench.Ilim = [0.8 1.0 1.3];   % [A] current limit per channel
P.src.bench.Rs   = [0 0 0];         % [ohm] external series resistor, 0 if none
P.src.bench.Rclamp = 0.05;          % [ohm] CV-branch resistance (PSU output impedance + leads)
% "Shade" on the bench = a lower current limit on that channel. The Irradiance k
% constant (W/m2) scales Ilim_k: Ilim_k * g/1000.

% PV80: Kaus KAUSSP80 (owner's manual): 80 W, Voc 25.07 V, Isc 4.35 A, mono PERC.
% Not on the datasheet: cell count, Vmp/Imp, temperature coefficients. 36 cells
% assumed; Vmp/Imp are typical-fill-factor estimates - refine from a measured IV point.
P.src.pv80.Voc = 25.07;  P.src.pv80.Isc = 4.35;  P.src.pv80.Pmp = 80;
P.src.pv80.Ns  = 36;                         % series cells (assumed)
P.src.pv80.Voc_cell = P.src.pv80.Voc / P.src.pv80.Ns;   % 0.696 V
P.src.pv80.Vmp = 20.5;  P.src.pv80.Imp = 3.90;          % estimates (FF ~0.73)

switch P.setup
    case 'BENCH'
        P.pv.Vmp = P.src.bench.Vset(1);  P.pv.Imp = P.src.bench.Ilim(1);
        P.pv.Pmp = P.pv.Vmp * P.pv.Imp;
        P.pv.Voc = P.src.bench.Vset(1);  P.pv.Isc = P.src.bench.Ilim(1);
    case 'PV80'
        P.pv.Vmp = P.src.pv80.Vmp;  P.pv.Imp = P.src.pv80.Imp;  P.pv.Pmp = P.src.pv80.Pmp;
        P.pv.Isc = P.src.pv80.Isc;  P.pv.Voc = P.src.pv80.Voc;
end
% MPP vs irradiance for harvest ceilings (linear scaling)
P.pv.pmp_irr = [0 200 500 1000];
P.pv.pmp_w   = P.pv.Pmp * P.pv.pmp_irr / 1000;
P.pv.pmp     = @(g) interp1(P.pv.pmp_irr, P.pv.pmp_w, g);

%% ---- load: Rigol DL3021 (150 V / 40 A / 200 W) --------------------------
% CV is the default: it is what the bench used (70.0 V) and it pins Vstr, which
% makes VM1 recoverable as Vstr - VM2 - VM3 when U10 (CS3) is offline.
P.load.type = 'CV';                    % 'CV' or 'CC' (CC = current sink driven by Iref, MPPT off)
switch P.setup
    case 'BENCH', P.load.Vcv = 70;     % [V] as on 13 Oct
    case 'PV80',  P.load.Vcv = 3 * P.src.pv80.Vmp;   % ~61.5 V, near string MPP
end
P.load.Rcv  = 0.02;                    % [ohm] CV source resistance (DL3021 + leads)
P.load.Icc  = 0.9 * P.pv.Imp;          % [A] CC setpoint
P.load.Pmax = 200;                     % [W] DL3021 limit - validate checks the settled string power
if evalin('base', 'exist(''LOAD'',''var'')'), P.load.type = upper(evalin('base', 'LOAD')); end

%% ---- plant (Version 0 PCB; the circuit blocks hold the live values) ---
P.plant.L_self = 7.9e-6;   P.plant.L_m = 5.85e-6;  P.plant.R_w = 1.85e-3;  % TDK ERUC23-4R1K
P.plant.R_phase= 61e-3;    % per-phase series R (damping); STD45N10F7 Rds(on) is lower - keep until re-identified
P.plant.C      = 130e-6;   % per capacitor: 130 uF top-mid and 130 uF mid-bottom (TDK B40910A0137M000)
P.plant.ESR    = 28e-3;
P.plant.f_sw   = 200e3;    % HRTIM PWM (raised from 100 kHz for the coupled inductor; averaged model)

%% ---- sensing (what the firmware actually sees) -------------------------
S.Ts        = 100e-6;          % control tick; IL is the mean over the tick (20 PWM periods at 200 kHz)
S.ina_div   = 10;              % INA239 round-robin poll: VM refreshed every 10 ticks (1 kHz)
S.ina_lsb   = 3.125e-3;        % [V] INA239 bus-voltage LSB
S.adc_lsb   = 3.3 / 4096;      % [V] 12-bit ADC
S.kA_hw = 0.100;  S.kA_fw = 0.100;   % [V/A] hall sensitivity: fitted part vs firmware assumption
S.kB_hw = 0.025;  S.kB_fw = 0.025;   % set kB_hw = 0.100 to reproduce a B4 part read as B1 (x4 error)
S.noise_vm = 0;                % [V rms] per INA reading (bench estimate ~2e-3); 0 = off
S.noise_il = 0;                % [A rms] per hall reading (~0.02); 0 = off
S.vm1_src  = 0;                % 0 = INA (U10), 1 = VSTR_PARAM (CV setpoint), 2 = VSTR_PI (e-load readback)
S.vstr_param = P.load.Vcv;     % [V] used when vm1_src = 1
S.vstr_pi_div = round(0.45 / S.Ts);  % e-load readback refresh: 2.2 Hz measured through the Pi
S.vstr_lsb  = 1e-3;            % [V] DL3021 readback resolution (conservative)
P.sense = S;

%% ---- controller (mirror of shuffler_string_ctrl.m / ctrl_core) ---------
J = jsondecode(fileread(P.params_json));
P.ctrl.params_version = J.version;
P.ctrl.Ts    = J.ctrl.ts;          % 100e-6: 10 kHz inner loop on the STM32G474
P.ctrl.kI_v  = 2*pi*150;           % rad/s, v_diff channels  (ident builds M = G \ diag(kI))
P.ctrl.kI_i  = 2*pi*400;           % rad/s, i_comm channels
P.ctrl.kp_ratio_v = J.ctrl.kp_ratio_v;   P.ctrl.kp_ratio_i = J.ctrl.kp_ratio_i;
P.ctrl.fc_lpf = J.ctrl.fc_lpf;
P.ctrl.DMIN = J.ctrl.dmin;  P.ctrl.DMAX = J.ctrl.dmax;
P.ctrl.M     = J.ctrl.M;           % 4x4 from the JSON (QSPICE S9i or the latest Simulink ident)
P.ctrl.kscale = 1.0;               % global gain scale, mirrors the firmware runtime 'kscale'
if evalin('base', 'exist(''KSCALE'',''var'')'), P.ctrl.kscale = evalin('base', 'KSCALE'); end

%% ---- supervisor / feasibility governor (mirror) -----------------------
P.sup.Ts = 1e-3;  P.sup.TF = 5e-3;
P.sup.I_RATED = 10;                    % shuffler current rating [A] (TMCS1126 +-15.5 A, OC latch 12 A)
P.sup.S_HI = 0.90;  P.sup.S_LO = 0.70;
P.sup.KB = 60;  P.sup.KREL = 6;  P.sup.BMAX = 4;  P.sup.RVMAX = 30;

%% ---- MPPT (mirror; only meaningful with LOAD = 'CC') -------------------
P.mppt.Ts = 1e-3;  P.mppt.TP = 0.02;
P.mppt.IREF0 = P.load.Icc;  P.mppt.IMIN = 0.2 * P.pv.Isc;  P.mppt.IMAX = 0.98 * P.pv.Isc;
P.mppt.DB = 1.0;   P.mppt.KA = 0.01; P.mppt.SMIN = 0.05; P.mppt.SMAX = 1.0;
P.mppt.S0 = 0.25;  P.mppt.BTOL = 1e-3;

%% ---- test settings ----------------------------------------------------
P.test.Tavg    = 0.01;         % settled-stats window [s]
P.test.simMode = 'accelerator';
P.test.du      = 0.04;         % identification modal step size

%% ---- push what the blocks need into the base workspace -----------------
CTRL = struct('Ts', P.ctrl.Ts, 'M', P.ctrl.M, ...
    'Kp_ratio', [P.ctrl.kp_ratio_v*ones(P.NS,1); P.ctrl.kp_ratio_i*ones(P.NS,1)], ...
    'fc', P.ctrl.fc_lpf, 'DMIN', P.ctrl.DMIN, 'DMAX', P.ctrl.DMAX, 'kscale', P.ctrl.kscale);
assignin('base', 'CTRL', CTRL);
assignin('base', 'SENSE', P.sense);
assignin('base', 'SETUP_ID', find(strcmp(P.setup, {'BENCH', 'PV80'})));   % Variant: 1 bench, 2 PV80
assignin('base', 'LOAD_ID',  find(strcmp(P.load.type, {'CC', 'CV'})));    % Variant: 1 CC, 2 CV
assignin('base', 'SRC', P.src);
assignin('base', 'LOADP', P.load);
assignin('base', 'PLANT', P.plant);
if ~evalin('base', 'exist(''CTRL_MODE'',''var'')'), assignin('base', 'CTRL_MODE', P.ctrl_mode); end
end
