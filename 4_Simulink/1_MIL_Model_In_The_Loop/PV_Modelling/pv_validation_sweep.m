%% pv_validation_sweep.m
%  Pre-Sim / Run-Sim / Post-Sim validation of the Simulink Solar Cell block.
%
%  Generates I-V and P-V curves at multiple irradiance and temperature
%  conditions, compares against datasheet, and saves figures as PDF.

clear; clc; close all;

%% ========================================================================
%  CONFIG
%  ========================================================================
USE_SIMULINK  = true;     % Set true when Simulink model is wired
MODEL         = 'power_shuffler_sim'; % Simulink model name

SAVE_DIR = 'figures';
if ~exist(SAVE_DIR, 'dir'), mkdir(SAVE_DIR); end

%% ========================================================================
%  PANEL DATASHEET  (AIKO A555)
%  ========================================================================
PV_Isc   = 14.96;   PV_Voc   = 45.90;
PV_Impp  = 14.35;   PV_Vmpp  = 38.70;
PV_Pmpp  = 555;     PV_Ns    = 60;
PV_ki    = 0.05;    PV_kv    = -0.22;
PV_kp    = -0.26;

% Extracted parameters (module-level)
PV_A_mod   = 1.0;
PV_Rs_mod  = 0.158;
PV_Rsh_mod = 51807;
PV_I0      = 1.7528e-12;
PV_Iph     = 14.96;

% Per-cell (for Simulink block)
PV_N       = PV_A_mod;
PV_Rs_cell = PV_Rs_mod / PV_Ns;
PV_Rsh_cell= PV_Rsh_mod / PV_Ns;
PV_ki_per_K= PV_ki / 100;

% Simulation
T_sim = 10;
V_max = 50;

q_ = 1.602176634e-19;
k_ = 1.380649e-23;
Tstc = 298.15;

%% ========================================================================
%  SWEEP CONDITIONS
%  ========================================================================
G_levels = [200, 400, 600, 800, 1000];
T_levels = [0, 25, 50, 75];

%% ========================================================================
%  SIMULINK SWEEP  (when ready)
%  ========================================================================
if USE_SIMULINK
    load_system(MODEL);

    % Irradiance sweep (T = 25 °C)
    T_cell_sim = 25; %#ok
    sim_G = struct([]);
    for jj = 1:length(G_levels)
        G_sim = G_levels(jj); %#ok
        simOut = sim(MODEL, 'StopTime', num2str(T_sim));
        V_data = simOut.pv_module_voltage.Data(:);
        I_data = simOut.pv_module_current.Data(:);
        % Clip to V >= 0 and I >= 0
        valid = V_data >= 0 & I_data >= 0;
        sim_G(jj).V = V_data(valid);
        sim_G(jj).I = I_data(valid);
        sim_G(jj).P = sim_G(jj).V .* sim_G(jj).I;
    end

    % Temperature sweep (G = 1000 W/m²)
    G_sim = 1000; %#ok
    sim_T = struct([]);
    for jj = 1:length(T_levels)
        T_cell_sim = T_levels(jj); %#ok
        simOut = sim(MODEL, 'StopTime', num2str(T_sim));
        V_data = simOut.pv_module_voltage.Data(:);
        I_data = simOut.pv_module_current.Data(:);
        valid = V_data >= 0 & I_data >= 0;
        sim_T(jj).V = V_data(valid);
        sim_T(jj).I = I_data(valid);
        sim_T(jj).P = sim_T(jj).V .* sim_T(jj).I;
    end

    %close_system(MODEL, 0);
end

%% ========================================================================
%  REFERENCE CURVES  (MATLAB single-diode solver)
%  ========================================================================
ref_G = struct([]);
for jj = 1:length(G_levels)
    [I, V, P] = pv_matlab(PV_Isc, PV_Voc, PV_Ns, PV_A_mod, ...
                           PV_Rs_mod, PV_Rsh_mod, PV_ki, PV_kv, ...
                           G_levels(jj), 25);
    ref_G(jj).G = G_levels(jj);
    ref_G(jj).V = V;  ref_G(jj).I = I;  ref_G(jj).P = P;
    [ref_G(jj).Pmpp, mi] = max(P);
    ref_G(jj).Vmpp = V(mi);
    ref_G(jj).Impp = I(mi);
    ref_G(jj).Isc  = I(1);
end

ref_T = struct([]);
for jj = 1:length(T_levels)
    [I, V, P] = pv_matlab(PV_Isc, PV_Voc, PV_Ns, PV_A_mod, ...
                           PV_Rs_mod, PV_Rsh_mod, PV_ki, PV_kv, ...
                           1000, T_levels(jj));
    ref_T(jj).T = T_levels(jj);
    ref_T(jj).V = V;  ref_T(jj).I = I;  ref_T(jj).P = P;
    [ref_T(jj).Pmpp, mi] = max(P);
    ref_T(jj).Vmpp = V(mi);
    ref_T(jj).Impp = I(mi);
    ref_T(jj).Isc  = I(1);
    vi = find(I > 0.01, 1, 'last');
    if ~isempty(vi), ref_T(jj).Voc = V(vi); else, ref_T(jj).Voc = PV_Voc; end
end

%% ========================================================================
%  COLOUR MAPS
%  ========================================================================
cmap_G = [0.5 0.5 0.5;  0 0 0.85;  0.6 0 0.6;  0 0.6 0;  0.85 0 0];
cmap_T = [0 0 0.85;  0 0.6 0;  0.9 0.45 0;  0.85 0 0];

%% ========================================================================
%  FIGURE 1 — IRRADIANCE I-V
%  ========================================================================
fig1 = figure('Name','Irradiance I-V','Position',[50 50 700 500]);
hold on;
h_lines = gobjects(length(G_levels), 1);
for jj = 1:length(G_levels)
    h_lines(jj) = plot(ref_G(jj).V, ref_G(jj).I, '-', ...
         'Color', cmap_G(jj,:), 'LineWidth', 2);
    plot(ref_G(jj).Vmpp, ref_G(jj).Impp, 'o', ...
         'Color', cmap_G(jj,:), 'MarkerSize', 8, ...
         'MarkerFaceColor', 'w', 'LineWidth', 1.5, ...
         'HandleVisibility', 'off');
    text(ref_G(jj).Vmpp + 0.8, ref_G(jj).Impp, ...
         sprintf('%.0f W', ref_G(jj).Pmpp), ...
         'Color', cmap_G(jj,:), 'FontSize', 10, 'FontWeight', 'bold');

    if USE_SIMULINK
        plot(sim_G(jj).V, sim_G(jj).I, '--', ...
             'Color', cmap_G(jj,:), 'LineWidth', 1.5, ...
             'HandleVisibility', 'off');
    end
end
xlabel('Voltage [V]', 'FontSize', 12);
ylabel('Current [A]', 'FontSize', 12);
title('I-V Characteristics — Irradiance Sweep (T = 25°C)', 'FontSize', 13);
legend(h_lines, arrayfun(@(g) sprintf('G = %d W/m²', g), G_levels, ...
       'UniformOutput', false), 'Location', 'southwest', 'FontSize', 10);
grid on;  xlim([0 50]);  ylim([0 17]);
set(gca, 'FontSize', 11);
exportgraphics(fig1, fullfile(SAVE_DIR, 'irradiance_IV.pdf'), 'ContentType', 'vector');
fprintf('Saved: %s\n', fullfile(SAVE_DIR, 'irradiance_IV.pdf'));

%% ========================================================================
%  FIGURE 2 — IRRADIANCE P-V
%  ========================================================================
fig2 = figure('Name','Irradiance P-V','Position',[770 50 700 500]);
hold on;
h_lines2 = gobjects(length(G_levels), 1);
for jj = 1:length(G_levels)
    h_lines2(jj) = plot(ref_G(jj).V, ref_G(jj).P, '-', ...
         'Color', cmap_G(jj,:), 'LineWidth', 2);
    plot(ref_G(jj).Vmpp, ref_G(jj).Pmpp, 'o', ...
         'Color', cmap_G(jj,:), 'MarkerSize', 8, ...
         'MarkerFaceColor', 'w', 'LineWidth', 1.5, ...
         'HandleVisibility', 'off');

    if USE_SIMULINK
        plot(sim_G(jj).V, sim_G(jj).P, '--', ...
             'Color', cmap_G(jj,:), 'LineWidth', 1.5, ...
             'HandleVisibility', 'off');
    end
end
xlabel('Voltage [V]', 'FontSize', 12);
ylabel('Power [W]', 'FontSize', 12);
title('P-V Characteristics — Irradiance Sweep (T = 25°C)', 'FontSize', 13);
legend(h_lines2, arrayfun(@(g) sprintf('G = %d W/m²', g), G_levels, ...
       'UniformOutput', false), 'Location', 'northwest', 'FontSize', 10);
grid on;  xlim([0 50]);  ylim([0 650]);
set(gca, 'FontSize', 11);
exportgraphics(fig2, fullfile(SAVE_DIR, 'irradiance_PV.pdf'), 'ContentType', 'vector');
fprintf('Saved: %s\n', fullfile(SAVE_DIR, 'irradiance_PV.pdf'));

%% ========================================================================
%  FIGURE 3 — TEMPERATURE I-V
%  ========================================================================
fig3 = figure('Name','Temperature I-V','Position',[50 580 700 500]);
hold on;
h_lines3 = gobjects(length(T_levels), 1);
for jj = 1:length(T_levels)
    h_lines3(jj) = plot(ref_T(jj).V, ref_T(jj).I, '-', ...
         'Color', cmap_T(jj,:), 'LineWidth', 2);
    plot(ref_T(jj).Vmpp, ref_T(jj).Impp, 'o', ...
         'Color', cmap_T(jj,:), 'MarkerSize', 8, ...
         'MarkerFaceColor', 'w', 'LineWidth', 1.5, ...
         'HandleVisibility', 'off');

    if USE_SIMULINK
        plot(sim_T(jj).V, sim_T(jj).I, '--', ...
             'Color', cmap_T(jj,:), 'LineWidth', 1.5, ...
             'HandleVisibility', 'off');
    end
end
xlabel('Voltage [V]', 'FontSize', 12);
ylabel('Current [A]', 'FontSize', 12);
title('I-V Characteristics — Temperature Sweep (G = 1000 W/m²)', 'FontSize', 13);
legend(h_lines3, arrayfun(@(t) sprintf('T = %d°C', t), T_levels, ...
       'UniformOutput', false), 'Location', 'southwest', 'FontSize', 10);
grid on;  xlim([0 55]);  ylim([0 17]);
set(gca, 'FontSize', 11);
exportgraphics(fig3, fullfile(SAVE_DIR, 'temperature_IV.pdf'), 'ContentType', 'vector');
fprintf('Saved: %s\n', fullfile(SAVE_DIR, 'temperature_IV.pdf'));

%% ========================================================================
%  FIGURE 4 — TEMPERATURE P-V
%  ========================================================================
fig4 = figure('Name','Temperature P-V','Position',[770 580 700 500]);
hold on;
h_lines4 = gobjects(length(T_levels), 1);
for jj = 1:length(T_levels)
    h_lines4(jj) = plot(ref_T(jj).V, ref_T(jj).P, '-', ...
         'Color', cmap_T(jj,:), 'LineWidth', 2);
    plot(ref_T(jj).Vmpp, ref_T(jj).Pmpp, 'o', ...
         'Color', cmap_T(jj,:), 'MarkerSize', 8, ...
         'MarkerFaceColor', 'w', 'LineWidth', 1.5, ...
         'HandleVisibility', 'off');

    if USE_SIMULINK
        plot(sim_T(jj).V, sim_T(jj).P, '--', ...
             'Color', cmap_T(jj,:), 'LineWidth', 1.5, ...
             'HandleVisibility', 'off');
    end
end
xlabel('Voltage [V]', 'FontSize', 12);
ylabel('Power [W]', 'FontSize', 12);
title('P-V Characteristics — Temperature Sweep (G = 1000 W/m²)', 'FontSize', 13);
legend(h_lines4, arrayfun(@(t) sprintf('T = %d°C', t), T_levels, ...
       'UniformOutput', false), 'Location', 'northwest', 'FontSize', 10);
grid on;  xlim([0 55]);  ylim([0 700]);
set(gca, 'FontSize', 11);
exportgraphics(fig4, fullfile(SAVE_DIR, 'temperature_PV.pdf'), 'ContentType', 'vector');
fprintf('Saved: %s\n', fullfile(SAVE_DIR, 'temperature_PV.pdf'));

%% ========================================================================
%  FIGURE 5 — STC VALIDATION (I-V + P-V side by side)
%  ========================================================================
fig5 = figure('Name','STC Validation','Position',[200 300 1100 450]);

subplot(1,2,1); hold on;
h_iv = plot(ref_G(5).V, ref_G(5).I, 'b-', 'LineWidth', 2);
h_ds1 = plot(0, PV_Isc, 'r^', 'MarkerSize', 10, 'MarkerFaceColor', 'r');
h_ds2 = plot(PV_Vmpp, PV_Impp, 'go', 'MarkerSize', 10, 'MarkerFaceColor', 'g');
h_ds3 = plot(PV_Voc, 0, 'ms', 'MarkerSize', 10, 'MarkerFaceColor', 'm');
xlabel('Voltage [V]'); ylabel('Current [A]');
title('I-V Curve — STC');
legend([h_iv, h_ds1, h_ds2, h_ds3], ...
       'Model', ...
       sprintf('Isc = %.2f A', PV_Isc), ...
       sprintf('MPP (%.1fV, %.2fA)', PV_Vmpp, PV_Impp), ...
       sprintf('Voc = %.1f V', PV_Voc), ...
       'Location', 'southwest');
grid on; xlim([0 50]); ylim([0 17]);

subplot(1,2,2); hold on;
h_pv = plot(ref_G(5).V, ref_G(5).P, 'b-', 'LineWidth', 2);
h_mpp = plot(PV_Vmpp, PV_Pmpp, 'go', 'MarkerSize', 10, 'MarkerFaceColor', 'g');
xlabel('Voltage [V]'); ylabel('Power [W]');
title('P-V Curve — STC');
legend([h_pv, h_mpp], 'Model', sprintf('Pmpp = %d W', PV_Pmpp), ...
       'Location', 'northwest');
grid on; xlim([0 50]); ylim([0 650]);

sgtitle('AIKO Neostar A555 — STC: Model vs Datasheet', 'FontWeight', 'bold');
exportgraphics(fig5, fullfile(SAVE_DIR, 'stc_validation.pdf'), 'ContentType', 'vector');
fprintf('Saved: %s\n', fullfile(SAVE_DIR, 'stc_validation.pdf'));

%% ========================================================================
%  CONSOLE SUMMARY
%  ========================================================================
fprintf('\n=== STC Verification ===\n');
fprintf('%-12s %10s %10s %10s\n', 'Parameter', 'Model', 'Datasheet', 'Error');
vi = find(ref_G(5).I > 0.01, 1, 'last');
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Isc [A]',  ref_G(5).Isc, PV_Isc,  100*(ref_G(5).Isc-PV_Isc)/PV_Isc);
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Voc [V]',  ref_G(5).V(vi), PV_Voc, 100*(ref_G(5).V(vi)-PV_Voc)/PV_Voc);
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Pmpp [W]', ref_G(5).Pmpp, PV_Pmpp, 100*(ref_G(5).Pmpp-PV_Pmpp)/PV_Pmpp);
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Vmpp [V]', ref_G(5).Vmpp, PV_Vmpp, 100*(ref_G(5).Vmpp-PV_Vmpp)/PV_Vmpp);
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Impp [A]', ref_G(5).Impp, PV_Impp, 100*(ref_G(5).Impp-PV_Impp)/PV_Impp);

fprintf('\n=== Irradiance Sweep (T = 25°C) ===\n');
fprintf('%-8s %8s %8s %8s %8s\n', 'G', 'Isc', 'Pmpp', 'Vmpp', 'Impp');
for jj = 1:length(G_levels)
    fprintf('%-8d %8.2f %8.1f %8.2f %8.2f\n', ...
            ref_G(jj).G, ref_G(jj).Isc, ref_G(jj).Pmpp, ref_G(jj).Vmpp, ref_G(jj).Impp);
end

fprintf('\n=== Temperature Sweep (G = 1000 W/m²) ===\n');
fprintf('%-8s %8s %8s %8s %8s\n', 'T [°C]', 'Isc', 'Pmpp', 'Vmpp', 'Voc');
for jj = 1:length(T_levels)
    fprintf('%-8d %8.2f %8.1f %8.2f %8.2f\n', ...
            ref_T(jj).T, ref_T(jj).Isc, ref_T(jj).Pmpp, ref_T(jj).Vmpp, ref_T(jj).Voc);
end

fprintf('\nAll figures saved to: %s/\n', SAVE_DIR);

%% ========================================================================
%  HELPER: Single-diode solver
%  ========================================================================
function [I_out, V_out, P_out] = pv_matlab(Isc, Voc, Ns, A, Rs, Rsh, ki, kv, G, T_degC)
    q_ = 1.602176634e-19;
    k_ = 1.380649e-23;
    Tstc = 298.15;
    T = T_degC + 273.15;

    Vt   = A * k_ * T / q_;
    nsVt = Ns * Vt;

    Isc_T = Isc * (1 + ki/100 * (T - Tstc));
    Voc_T = Voc * (1 + kv/100 * (T - Tstc));

    Io_T  = (Isc_T - (Voc_T - Isc_T*Rs)/Rsh) * exp(-Voc_T / nsVt);
    if Io_T <= 0, Io_T = Isc * exp(-Voc / nsVt); end
    Iph_T  = Io_T * exp(Voc_T / nsVt) + Voc_T / Rsh;
    Iph_GT = Iph_T * (G / 1000);

    Voc_GT = max(Voc_T, 0.1);
    for nn = 1:50
        f_  = Iph_GT - Io_T*exp(Voc_GT/nsVt) - Voc_GT/Rsh;
        fp_ = -Io_T/nsVt*exp(Voc_GT/nsVt) - 1/Rsh;
        dV  = -f_/fp_;
        Voc_GT = Voc_GT + dV;
        if abs(dV) < 1e-8, break; end
    end
    Voc_GT = max(Voc_GT, 0);

    % Only sweep up to Voc — no negative current/power region
    V_out = linspace(0, Voc_GT, 1000);
    I_out = zeros(size(V_out));
    opts  = optimset('Display','off','TolX',1e-12);
    for ii = 1:length(V_out)
        Vk = V_out(ii);
        fun = @(Ik) Iph_GT - Io_T*(exp((Vk+Ik*Rs)/nsVt)-1) ...
                    - (Vk+Ik*Rs)/Rsh - Ik;
        try
            I_out(ii) = fzero(fun, max(Iph_GT - Vk/Rsh, 0), opts);
        catch
            I_out(ii) = 0;
        end
    end
    I_out(I_out < 0) = 0;
    P_out = V_out .* I_out;
end