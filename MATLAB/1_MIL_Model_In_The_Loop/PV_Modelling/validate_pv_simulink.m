%% validate_pv_simulink.m
%  Validate the Simulink Solar Cell block against datasheet values.
%
%  HOW TO USE:
%  1. Open your Simulink model (the one with the Solar Cell block).
%  2. Make sure you have "To Workspace" blocks logging voltage and current
%     (see SETUP section below if you need to add them).
%  3. Update the model name in the CONFIG section.
%  4. Run this script.
%
%  Alternatively, this script can run STANDALONE (without Simulink) using
%  the pure-MATLAB single-diode solver to generate all validation plots.
%  Set USE_SIMULINK = false below.

%% ========================================================================
%  CONFIG
%  ========================================================================
USE_SIMULINK  = true;   % Set true if you have the Simulink model ready
MODEL_NAME    = 'power_shuffler_sim';  % Your Simulink model name (no .slx)

%% ========================================================================
%  PANEL DATASHEET  (AIKO A555)
%  ========================================================================
ds.Isc   = 14.96;   ds.Voc   = 45.90;
ds.Impp  = 14.35;   ds.Vmpp  = 38.70;
ds.Pmpp  = 555;     ds.Ns    = 60;
ds.ki    = 0.05;    ds.kv    = -0.22;
ds.kp    = -0.26;   ds.Tstc  = 298.15;

% Extracted model parameters (module-level)
mod.A    = 1.0;
mod.Rs   = 0.158;       % Module-level [Ohm]
mod.Rsh  = 51807;       % Module-level [Ohm]
mod.I0   = 1.7528e-12;  % [A]
mod.Iph  = 14.96;       % [A]

% Physical constants
q = 1.602176634e-19;
k = 1.380649e-23;

%% ========================================================================
%  PURE-MATLAB SINGLE DIODE SOLVER  (used for reference curves)
%  ========================================================================

    function I_out = solve_IV(V, Iph, I0, Rs, Rsh, nsVt)
        I_out = zeros(size(V));
        opts = optimset('Display','off','TolX',1e-12);
        for ii = 1:length(V)
            Vk = V(ii);
            fun = @(Ik) Iph - I0*(exp((Vk + Ik*Rs)/nsVt) - 1) ...
                        - (Vk + Ik*Rs)/Rsh - Ik;
            try
                I_out(ii) = fzero(fun, max(Iph - Vk/Rsh, 0), opts);
            catch
                I_out(ii) = 0;
            end
        end
        I_out(I_out < 0) = 0;
    end

    function [I_out, V_out, P_out] = pv_model_GT(ds, mod, G, T_degC)
        q_ = 1.602176634e-19;  k_ = 1.380649e-23;
        T    = T_degC + 273.15;
        Vt   = mod.A * k_ * T / q_;
        nsVt = ds.Ns * Vt;

        Isc_T = ds.Isc * (1 + ds.ki/100 * (T - ds.Tstc));
        Voc_T = ds.Voc * (1 + ds.kv/100 * (T - ds.Tstc));

        Io_T  = (Isc_T - (Voc_T - Isc_T*mod.Rs)/mod.Rsh) * exp(-Voc_T/nsVt);
        if Io_T <= 0, Io_T = mod.I0; end
        Iph_T = Io_T * exp(Voc_T/nsVt) + Voc_T/mod.Rsh;
        Iph_GT = Iph_T * (G / 1000);

        % Voc at irradiance
        Voc_GT = Voc_T;
        for nn = 1:50
            f_  = Iph_GT - Io_T*exp(Voc_GT/nsVt) - Voc_GT/mod.Rsh;
            fp_ = -Io_T/nsVt*exp(Voc_GT/nsVt) - 1/mod.Rsh;
            Voc_GT = Voc_GT - f_/fp_;
            if abs(f_/fp_) < 1e-8, break; end
        end

        V_out = linspace(0, max(Voc_GT,1)*1.02, 1000);
        I_out = solve_IV(V_out, Iph_GT, Io_T, mod.Rs, mod.Rsh, nsVt);
        P_out = V_out .* I_out;
    end

%% ========================================================================
%  1. STC VALIDATION  (G = 1000 W/m², T = 25°C)
%  ========================================================================
fprintf('================================================================\n');
fprintf('  AIKO A555 — Single Diode Model Validation\n');
fprintf('================================================================\n\n');

[I_stc, V_stc, P_stc] = pv_model_GT(ds, mod, 1000, 25);
[Pmax, idx] = max(P_stc);
Voc_idx = find(I_stc > 0.01, 1, 'last');

fprintf('--- STC (1000 W/m², 25°C) ---\n');
fprintf('%-12s %10s %10s %10s\n', 'Parameter', 'Model', 'Datasheet', 'Error');
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Isc [A]',  I_stc(1), ds.Isc,  100*(I_stc(1)-ds.Isc)/ds.Isc);
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Voc [V]',  V_stc(Voc_idx), ds.Voc, 100*(V_stc(Voc_idx)-ds.Voc)/ds.Voc);
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Pmpp [W]', Pmax, ds.Pmpp, 100*(Pmax-ds.Pmpp)/ds.Pmpp);
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Vmpp [V]', V_stc(idx), ds.Vmpp, 100*(V_stc(idx)-ds.Vmpp)/ds.Vmpp);
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Impp [A]', I_stc(idx), ds.Impp, 100*(I_stc(idx)-ds.Impp)/ds.Impp);
fprintf('%-12s %10.4f\n\n', 'FF', Pmax/(I_stc(1)*V_stc(Voc_idx)));

%% ========================================================================
%  2. NOCT VALIDATION  (G = 800 W/m², T ≈ 45°C)
%  ========================================================================
T_noct = 45;
[I_noct, V_noct, P_noct] = pv_model_GT(ds, mod, 800, T_noct);
[Pmax_n, idx_n] = max(P_noct);
Voc_n_idx = find(I_noct > 0.01, 1, 'last');

fprintf('--- NOCT (800 W/m², ~45°C cell) ---\n');
fprintf('%-12s %10s %10s %10s\n', 'Parameter', 'Model', 'Datasheet', 'Error');
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Pmpp [W]', Pmax_n, 421, 100*(Pmax_n-421)/421);
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Vmpp [V]', V_noct(idx_n), 36.72, 100*(V_noct(idx_n)-36.72)/36.72);
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Impp [A]', I_noct(idx_n), 11.47, 100*(I_noct(idx_n)-11.47)/11.47);
fprintf('%-12s %10.2f %10.2f %9.2f%%\n', 'Isc  [A]', I_noct(1), 12.09, 100*(I_noct(1)-12.09)/12.09);
fprintf('%-12s %10.2f %10.2f %9.2f%%\n\n', 'Voc  [V]', V_noct(Voc_n_idx), 43.55, 100*(V_noct(Voc_n_idx)-43.55)/43.55);

%% ========================================================================
%  3. TEMPERATURE COEFFICIENT VALIDATION
%  ========================================================================
fprintf('--- Temperature Coefficient Check ---\n');
dT = 1;  % 1°C step
[~, V25, P25] = pv_model_GT(ds, mod, 1000, 25);
[~, V26, P26] = pv_model_GT(ds, mod, 1000, 25 + dT);

[P25max,~] = max(P25);
[P26max,~] = max(P26);
kp_model = (P26max - P25max) / P25max * 100;  % %/°C
fprintf('Pmax temp coeff:  model = %.3f %%/°C,  datasheet = %.2f %%/°C\n', kp_model, ds.kp);

I25_sc = solve_IV(0, mod.Iph, mod.I0, mod.Rs, mod.Rsh, ds.Ns*mod.A*k*(25+273.15)/q);
[I26, ~, ~] = pv_model_GT(ds, mod, 1000, 26);
ki_model = (I26(1) - I_stc(1)) / I_stc(1) * 100;
fprintf('Isc  temp coeff:  model = %.4f %%/°C, datasheet = +%.2f %%/°C\n\n', ki_model, ds.ki);

%% ========================================================================
%  4. PLOT — STC I-V and P-V with datasheet points
%  ========================================================================
figure('Name','STC Validation','Position',[50 50 1100 450]);

subplot(1,2,1);
plot(V_stc, I_stc, 'b-', 'LineWidth', 2); hold on;
% Datasheet key points
plot(0, ds.Isc, 'r^', 'MarkerSize', 10, 'MarkerFaceColor', 'r');
plot(ds.Vmpp, ds.Impp, 'go', 'MarkerSize', 10, 'MarkerFaceColor', 'g');
plot(ds.Voc, 0, 'ms', 'MarkerSize', 10, 'MarkerFaceColor', 'm');
xlabel('Voltage [V]'); ylabel('Current [A]');
title('I-V Curve — STC Validation');
legend('Model', ...
       sprintf('Isc = %.2f A (DS)', ds.Isc), ...
       sprintf('MPP = (%.1fV, %.2fA) (DS)', ds.Vmpp, ds.Impp), ...
       sprintf('Voc = %.1f V (DS)', ds.Voc), ...
       'Location', 'southwest');
grid on; xlim([0 50]); ylim([0 17]);

subplot(1,2,2);
plot(V_stc, P_stc, 'b-', 'LineWidth', 2); hold on;
plot(ds.Vmpp, ds.Pmpp, 'go', 'MarkerSize', 10, 'MarkerFaceColor', 'g');
xlabel('Voltage [V]'); ylabel('Power [W]');
title('P-V Curve — STC Validation');
legend('Model', sprintf('Pmpp = %d W (DS)', ds.Pmpp), 'Location', 'northwest');
grid on; xlim([0 50]);

sgtitle('AIKO A555 — STC: Model vs Datasheet', 'FontWeight','bold');

exportgraphics(gcf, 'figures/PV_Module_STC_VI_PV.pdf', 'ContentType', 'vector')

%% ========================================================================
%  5. PLOT — Irradiance sweep (mimics datasheet Image 2)
%  ========================================================================
figure('Name','Irradiance Sweep','Position',[50 520 1100 450]);
irr_levels = [200 400 600 800 1000];
cmap = [0.5 0.5 0.5;  0 0 1;  0.5 0 0.5;  0 0.6 0;  0.8 0 0];  % gray,blue,purple,green,red

subplot(1,2,1); hold on;
subplot(1,2,2); hold on;

fprintf('--- Irradiance Sweep (T = 25°C) ---\n');
fprintf('%-8s %8s %8s %8s\n', 'G', 'Isc', 'Pmpp', 'Voc');

for jj = 1:length(irr_levels)
    G = irr_levels(jj);
    [I_g, V_g, P_g] = pv_model_GT(ds, mod, G, 25);
    [Pg_max, ig] = max(P_g);
    Voc_g = V_g(find(I_g > 0.01, 1, 'last'));
    fprintf('%-8d %8.2f %8.1f %8.1f\n', G, I_g(1), Pg_max, Voc_g);

    subplot(1,2,1);
    plot(V_g, I_g, '-', 'Color', cmap(jj,:), 'LineWidth', 1.8);
    % Mark MPP
    plot(V_g(ig), I_g(ig), 'o', 'Color', cmap(jj,:), 'MarkerSize', 7, ...
         'MarkerFaceColor', 'w', 'LineWidth', 1.5);
    text(V_g(ig)+0.5, I_g(ig), sprintf('%.0fW', Pg_max), ...
         'Color', cmap(jj,:), 'FontSize', 9);

    subplot(1,2,2);
    plot(V_g, P_g, '-', 'Color', cmap(jj,:), 'LineWidth', 1.8);
end

subplot(1,2,1);
xlabel('Voltage [V]'); ylabel('Current [A]');
title('I-V at Different Irradiances');
legend(arrayfun(@(g) sprintf('G = %d W/m²', g), irr_levels, 'UniformOutput', false), ...
       'Location', 'southwest');
grid on; xlim([0 50]); ylim([0 17]);

subplot(1,2,2);
xlabel('Voltage [V]'); ylabel('Power [W]');
title('P-V at Different Irradiances');
legend(arrayfun(@(g) sprintf('G = %d W/m²', g), irr_levels, 'UniformOutput', false), ...
       'Location', 'northwest');
grid on; xlim([0 50]);

sgtitle('AIKO A555 — Irradiance Dependence (T = 25°C)', 'FontWeight','bold');
fprintf('\n');

exportgraphics(gcf, 'figures/PV_Module_Irradiance_Sweep.pdf', 'ContentType', 'vector')

%% ========================================================================
%  6. PLOT — Temperature sweep
%  ========================================================================
figure('Name','Temperature Sweep','Position',[50 990 1100 450]);
temp_levels = [0 25 50 75];
cmap2 = [0 0 1; 0 0.6 0; 1 0.5 0; 1 0 0];

subplot(1,2,1); hold on;
subplot(1,2,2); hold on;

fprintf('--- Temperature Sweep (G = 1000 W/m²) ---\n');
fprintf('%-8s %8s %8s %8s %8s\n', 'T [°C]', 'Isc', 'Voc', 'Pmpp', 'Vmpp');

for jj = 1:length(temp_levels)
    T = temp_levels(jj);
    [I_t, V_t, P_t] = pv_model_GT(ds, mod, 1000, T);
    [Pt_max, it] = max(P_t);
    Voc_t = V_t(find(I_t > 0.01, 1, 'last'));
    fprintf('%-8d %8.2f %8.2f %8.1f %8.2f\n', T, I_t(1), Voc_t, Pt_max, V_t(it));

    subplot(1,2,1);
    plot(V_t, I_t, '-', 'Color', cmap2(jj,:), 'LineWidth', 1.8);
    subplot(1,2,2);
    plot(V_t, P_t, '-', 'Color', cmap2(jj,:), 'LineWidth', 1.8);
end

subplot(1,2,1);
xlabel('Voltage [V]'); ylabel('Current [A]');
title('I-V at Different Temperatures');
legend(arrayfun(@(t) sprintf('T = %d°C', t), temp_levels, 'UniformOutput', false), ...
       'Location', 'southwest');
grid on; xlim([0 55]); ylim([0 17]);

subplot(1,2,2);
xlabel('Voltage [V]'); ylabel('Power [W]');
title('P-V at Different Temperatures');
legend(arrayfun(@(t) sprintf('T = %d°C', t), temp_levels, 'UniformOutput', false), ...
       'Location', 'northwest');
grid on; xlim([0 55]);

sgtitle('AIKO A555 — Temperature Dependence (G = 1000 W/m²)', 'FontWeight','bold');
fprintf('\n');

exportgraphics(gcf, 'figures/PV_Module_Temperature_Sweep.pdf', 'ContentType', 'vector')

%% ========================================================================
%  7. PLOT — Combined validation summary
%  ========================================================================
figure('Name','Validation Summary','Position',[50 100 600 500]);

% Bar chart comparing model vs datasheet at STC and NOCT
categories = {'Isc_{STC}','Voc_{STC}','Pmpp_{STC}','Vmpp_{STC}','Impp_{STC}', ...
              'Pmpp_{NOCT}','Vmpp_{NOCT}','Impp_{NOCT}'};

ds_vals  = [ds.Isc, ds.Voc, ds.Pmpp, ds.Vmpp, ds.Impp, 421, 36.72, 11.47];
mod_vals = [I_stc(1), V_stc(Voc_idx), Pmax, V_stc(idx), I_stc(idx), ...
            Pmax_n, V_noct(idx_n), I_noct(idx_n)];

pct_err = 100 * (mod_vals - ds_vals) ./ ds_vals;

barh(1:length(categories), pct_err, 'FaceColor', [0.2 0.6 0.9]);
set(gca, 'YTick', 1:length(categories), 'YTickLabel', categories);
xlabel('Error [%]');
title('Model vs Datasheet — Percentage Error');
xline(0, 'k--');
xlim([-2 2]);
grid on;

for ii = 1:length(pct_err)
    text(pct_err(ii) + sign(pct_err(ii))*0.05, ii, sprintf('%.2f%%', pct_err(ii)), ...
         'VerticalAlignment', 'middle', 'FontSize', 9);
end

exportgraphics(gcf, 'figures/PV_Module_Summary.pdf', 'ContentType', 'vector')

%% ========================================================================
%  8. SIMULINK INTEGRATION NOTES
%  ========================================================================
fprintf('================================================================\n');
fprintf('  SIMULINK CONFIGURATION REMINDER\n');
fprintf('================================================================\n');
fprintf('  Parameterize by:  "By equivalent circuit parameters, 5 parameter"\n');
fprintf('  Is (saturation):  %.4e A\n', mod.I0);
fprintf('  Iph (solar):      %.4f A\n', mod.Iph);
fprintf('  N (quality):      %.1f\n', mod.A);
fprintf('  Rs (per cell):    %.6f Ohm   (module %.4f / %d cells)\n', mod.Rs/ds.Ns, mod.Rs, ds.Ns);
fprintf('  Rsh (per cell):   %.4f Ohm   (module %d / %d cells)\n', mod.Rsh/ds.Ns, round(mod.Rsh), ds.Ns);
fprintf('  Ns:               %d\n', ds.Ns);
fprintf('  Npar:             1\n');
fprintf('  Iph temp coeff:   0.0005 1/K\n');
fprintf('  EG:               1.12 eV\n');
fprintf('  TXIS1:            3\n');
fprintf('================================================================\n');
fprintf('\n  To validate in Simulink:\n');
fprintf('  1. Use a Ramp block (0 to 50V over 10s) as a Controlled Voltage Source.\n');
fprintf('  2. Log V and I to workspace with "To Workspace" blocks.\n');
fprintf('  3. After sim, plot(V.Data, I.Data) for I-V curve.\n');
fprintf('  4. Compare with the reference curves from this script.\n');