function P = init_params()
%INIT_PARAMS  Single source of truth for the power-shuffler string project.
%   Every script starts with  P = init_params();  All block paths, logged-signal
%   names, ratings and test settings live HERE — change them in one place.
%
%   NOTE ON CONTROLLER GAINS: the MATLAB Function blocks (shuffler_string_ctrl /
%   _supervisor / _mppt) carry their own embedded constants — those blocks are
%   the AUTHORITATIVE copy for anything the controllers compute with. The values
%   are mirrored here for reference and for the scripts (ceilings, ratings,
%   IREF0). Keep them in sync when tuning; promoting the block constants to
%   mask/workspace parameters is an open item (see README).

%% ---- model & modes ----------------------------------------------------
P.mdl        = 'SIL_power_shuffler_sim';
P.ctrl_mode  = 1;              % 1 = closed loop, 0 = identification (variant)

%% ---- block paths (update if blocks move) ------------------------------
m = P.mdl;
P.path.irr      = { [m '/Power Circuit/Irradiance 1'], ...
                    [m '/Power Circuit/Irradiance 2'], ...
                    [m '/Power Circuit/Irradiance 3'], ...
                    [m '/Power Circuit/Irradiance 4'] };
P.path.vref     = { [m '/Supervisor/Vref1'], ...
                    [m '/Supervisor/Vref2'], ...
                    [m '/Supervisor/Vref3'] };
P.path.supEn    =   [m '/Supervisor/Enable'];
P.path.mpptEn   =   [m '/MPPT/Enable'];
P.path.shuf     = { [m '/Power Circuit/Power Shuffler1'], ...
                    [m '/Power Circuit/Power Shuffler2'], ...
                    [m '/Power Circuit/Power Shuffler3'] };
% Identification-mode duty constants (the Variant Source inputs).
P.path.dutyConst= { [m '/Power Shuffler1/dA1_const'], ...
                    [m '/Power Shuffler1/dB1_const'], ...
                    [m '/Power Shuffler2/dA2_const'], ...
                    [m '/Power Shuffler2/dB2_const'], ...
                    [m '/Power Shuffler3/dA3_const'], ...
                    [m '/Power Shuffler3/dB3_const'] };

%% ---- logged signal names (To Workspace, in Telemetry) -----------------
P.sig.vm   = {'VM1','VM2','VM3','VM4'};
P.sig.im   = {'IM1','IM2','IM3','IM4'};
P.sig.il   = {'ILA1','ILB1'; 'ILA2','ILB2'; 'ILA3','ILB3'};
P.sig.duty = {'dA1','dB1','dA2','dB2','dA3','dB3'};
P.sig.vstr = 'V_String';
P.sig.istr = 'I_String';

%% ---- PV module (ERUC23-421K-ish, from the model) ----------------------
P.pv.Vmp = 38.7;   P.pv.Imp = 14.35;  P.pv.Pmp = 555.7;
P.pv.Isc = 14.96;  P.pv.Voc = 45.9;
% M3 MPP vs irradiance, for harvest ceilings (refine points from the model):
P.pv.pmp_irr = [0 200 500 1000];
P.pv.pmp_w   = [0 111 277 555.7];
P.pv.pmp     = @(g) interp1(P.pv.pmp_irr, P.pv.pmp_w, g);

%% ---- plant (reference; the circuit blocks hold the live values) -------
P.plant.L_self = 7.9e-6;   P.plant.L_m = 5.85e-6;  P.plant.R_w = 1.85e-3;
P.plant.R_phase= 61e-3;    % MOSFET Rds(on)+ESR per phase — damps circulating i_comm
P.plant.C      = 100e-6;   P.plant.f_sw = 200e3;   % (averaged model: no switching)

%% ---- controller (mirror of shuffler_string_ctrl.m) --------------------
P.ctrl.Ts    = 50e-6;
P.ctrl.kI_v  = 2*pi*150;   % rad/s, v_diff channels  (used by ident to build M)
P.ctrl.kI_i  = 2*pi*400;   % rad/s, i_comm channels
P.ctrl.kp_ratio_v = 1.58e-4;   P.ctrl.kp_ratio_i = 1.08e-4;
P.ctrl.fc_lpf = 2000;

%% ---- supervisor / feasibility governor (mirror) -----------------------
P.sup.Ts = 1e-3;  P.sup.TF = 5e-3;
P.sup.I_RATED = 10;                    % shuffler current rating [A]
P.sup.S_HI = 0.90;  P.sup.S_LO = 0.70;
P.sup.KB = 60;  P.sup.KREL = 6;  P.sup.BMAX = 4;  P.sup.RVMAX = 30;

%% ---- MPPT (mirror) ----------------------------------------------------
P.mppt.Ts = 1e-3;  P.mppt.TP = 0.02;
P.mppt.IREF0 = 12; P.mppt.IMIN = 5;  P.mppt.IMAX = 14.5;
P.mppt.DB = 1.0;   P.mppt.KA = 0.01; P.mppt.SMIN = 0.05; P.mppt.SMAX = 1.0;

%% ---- test settings ----------------------------------------------------
P.test.Tavg    = 0.01;         % settled-stats window [s]
P.test.simMode = 'accelerator';
P.test.du      = 0.04;         % identification modal step size
end