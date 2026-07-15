%% shuffler_string_ident.m
%  One-click identification + decoupler design for the 4-module / 3-shuffler
%  string. Replaces the manual 7-run procedure: sets the six duty constants,
%  runs baseline + 6 modal steps, extracts settled means, builds the 6x6 DC
%  gain G, checks conditioning, and prints a paste-ready M for
%  shuffler_string_ctrl.m.
%
%  SETUP (once):
%   1. Put the model in IDENTIFICATION mode: controller disconnected, each of
%      the six duties driven by a named Constant block.
%   2. Fill in the CONFIG section below (block paths + logged signal names).
%   3. Make sure these signals are logged to workspace as timeseries (To
%      Workspace or signal logging): VM1..VM4, ILA1,ILB1,ILA2,ILB2,ILA3,ILB3.
%
%  Then just run this script.

%% ---------------- CONFIG — edit to match your model ----------------
mdl   = 'power_shuffler_sim';        % model name (no .slx)
Tstop = 0.03;                        % per-run sim time [s] (must reach steady state)
Tavg  = 0.005;                       % average over the LAST Tavg seconds

% Paths to the six duty Constant blocks (Identification mode)
dutyBlk = { [mdl '/dA1_const'], [mdl '/dB1_const'], ...
            [mdl '/dA2_const'], [mdl '/dB2_const'], ...
            [mdl '/dA3_const'], [mdl '/dB3_const'] };

% Logged signal names on the 'out' SimulationOutput (timeseries)
vmSig = {'VM1','VM2','VM3','VM4'};
ilSig = {'ILA1','ILB1'; 'ILA2','ILB2'; 'ILA3','ILB3'};   % row j = shuffler j

du = 0.04;                           % modal step size
% Integral bandwidths for M = G^-1*diag(kI). To keep the closed-loop speed you
% have TODAY, set kI_v ~ |M11_now * G11_new| etc. Otherwise pick directly:
kI_v = 2*pi*150;                     % v_diff channels [rad/s]
kI_i = 2*pi*400;                     % i_comm channels [rad/s]
%% --------------------------------------------------------------------

% duty patterns: rows = runs (baseline + 6 modal), cols = the 6 duties
base = 0.5*ones(1,6);
runs = repmat(base,7,1);
runs(2,[1 2]) = 0.5+du/2;            % run1: u_comm_1  (dA1,dB1 both +du/2)
runs(3,[3 4]) = 0.5+du/2;            % run2: u_comm_2
runs(4,[5 6]) = 0.5+du/2;            % run3: u_comm_3
runs(5,[1 2]) = [0.5+du/2, 0.5-du/2];% run4: u_diff_1  (dA1 up, dB1 down)
runs(6,[3 4]) = [0.5+du/2, 0.5-du/2];% run5: u_diff_2
runs(7,[5 6]) = [0.5+du/2, 0.5-du/2];% run6: u_diff_3

load_system(mdl);
set_param(mdl,'FastRestart','on');   % compile once, run 7x
cleanup = onCleanup(@() set_param(mdl,'FastRestart','off'));

Y = zeros(7,6);                      % rows = runs; cols = [vd1 vd2 vd3 ic1 ic2 ic3]
for k = 1:7
    for b = 1:6
        set_param(dutyBlk{b},'Value',num2str(runs(k,b),'%.6f'));
    end
    out = sim(mdl,'StopTime',num2str(Tstop));
    vm = zeros(1,4);
    for m = 1:4
        ts = out.(vmSig{m});
        vm(m) = mean(ts.Data(ts.Time >= Tstop-Tavg));
    end
    ic = zeros(1,3);
    for j = 1:3
        tsA = out.(ilSig{j,1});  tsB = out.(ilSig{j,2});
        ic(j) = mean(tsA.Data(tsA.Time >= Tstop-Tavg)) + ...
                mean(tsB.Data(tsB.Time >= Tstop-Tavg));
    end
    Y(k,:) = [vm(1)-vm(2), vm(2)-vm(3), vm(3)-vm(4), ic];
    fprintf('run %d done:  vd=[% .3f % .3f % .3f]  ic=[% .2f % .2f % .2f]\n', ...
            k-1, Y(k,1),Y(k,2),Y(k,3),Y(k,4),Y(k,5),Y(k,6));
end

% G: subtract baseline, divide by step; columns = [uc1 uc2 uc3 ud1 ud2 ud3]
G = (Y(2:7,:) - Y(1,:)).' / du;
fprintf('\nG =\n'); disp(G);
fprintf('cond(G) = %.1f\n', cond(G));
if cond(G) > 100
    warning(['G is poorly conditioned - do NOT trust the inverse. ' ...
             'Check the i_comm measurement points / signal names.']);
end

% sanity: the three ud->ic diagonal gains must share one sign and similar size
dg = [G(4,4) G(5,5) G(6,6)];
if numel(unique(sign(dg)))>1 || max(abs(dg))/min(abs(dg)) > 3
    warning('ud->i_comm diagonals look unphysical: [%g %g %g]', dg);
end

M = G \ diag([kI_v kI_v kI_v kI_i kI_i kI_i]);   % = inv(G)*diag(kI)
fprintf('\nPaste into shuffler_string_ctrl.m:\n\nM = [ ');
fprintf('%s', strjoin(compose('%10.6f',M(1,:)),' '));
for r = 2:6
    fprintf(';\n      %s', strjoin(compose('%10.6f',M(r,:)),' '));
end
fprintf(' ];\n');