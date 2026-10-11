%% shuffler_string_ident.m
%  Plant identification for the restructured model: baseline + 6 modal duty
%  steps -> 6x6 DC gain G -> decoupler matrix M for shuffler_string_ctrl.m.
%  All paths/names come from init_params.m.
%
%  PREREQUISITES
%   1. Variant Sources configured: CTRL_MODE==1 -> controller, ==0 -> the six
%      ident Constant blocks (paths in P.path.dutyConst).
%   2. OPERATING POINT: identification is a small-signal measurement — do it at
%      the operating point the closed loop will live at (~Vmp, string ~14.3 A).
%      With the MPPT disabled the load sits at IREF0 (see init_params); if that
%      is far from MPP current, set IREF0 ~ 14.3 in shuffler_string_mppt.m
%      first, or your G belongs to the wrong operating point.

P = init_params();
assignin('base','CTRL_MODE',0);                % identification mode (variant)

Tstop = 0.03;   Tavg = 0.005;   du = P.test.du;

% duty patterns: rows = baseline + 6 modal runs, cols = the 6 duties
base = 0.5*ones(1,6);  runs = repmat(base,7,1);
runs(2,[1 2]) = 0.5+du/2;                          % u_comm_1
runs(3,[3 4]) = 0.5+du/2;                          % u_comm_2
runs(4,[5 6]) = 0.5+du/2;                          % u_comm_3
runs(5,[1 2]) = [0.5+du/2, 0.5-du/2];              % u_diff_1
runs(6,[3 4]) = [0.5+du/2, 0.5-du/2];              % u_diff_2
runs(7,[5 6]) = [0.5+du/2, 0.5-du/2];              % u_diff_3

load_system(P.mdl);
set_param(P.mdl,'SimulationMode',P.test.simMode);
set_param(P.mdl,'FastRestart','on');
cleanup = onCleanup(@() set_param(P.mdl,'FastRestart','off'));
set_param(P.path.supEn, 'Value','0');              % supervisory layers OFF
set_param(P.path.mpptEn,'Value','0');
for g = 1:4, set_param(P.path.irr{g},'Value','1000'); end   % uniform sun

wmean = @(ts,t0) mean(ts.Data(ts.Time>=t0));
Y = zeros(7,6);
for k = 1:7
    for b = 1:6
        set_param(P.path.dutyConst{b},'Value',num2str(runs(k,b),'%.6f'));
    end
    out = sim(P.mdl,'StopTime',num2str(Tstop));
    t1 = Tstop - Tavg;
    vm = zeros(1,4);
    for mnum = 1:4, vm(mnum) = wmean(out.(P.sig.vm{mnum}), t1); end
    ic = zeros(1,3);
    for j = 1:3
        ic(j) = wmean(out.(P.sig.il{j,1}),t1) + wmean(out.(P.sig.il{j,2}),t1);
    end
    Y(k,:) = [vm(1)-vm(2), vm(2)-vm(3), vm(3)-vm(4), ic];
    fprintf('run %d done:  vd=[% .3f % .3f % .3f]  ic=[% .2f % .2f % .2f]\n', k-1, Y(k,:));
end

G = (Y(2:7,:) - Y(1,:)).' / du;
fprintf('\nG =\n'); disp(G);
fprintf('cond(G) = %.1f\n', cond(G));
if cond(G) > 100
    warning('G is poorly conditioned — do NOT invert. Check i_comm signal wiring.');
end
dg = [G(4,4) G(5,5) G(6,6)];
if numel(unique(sign(dg)))>1 || max(abs(dg))/min(abs(dg)) > 3
    warning('ud->i_comm diagonals look unphysical: [%g %g %g]', dg);
end

M = G \ diag([P.ctrl.kI_v*[1 1 1], P.ctrl.kI_i*[1 1 1]]);
fprintf('\nPaste into shuffler_string_ctrl.m:\n\nM = [ ');
fprintf('%s', strjoin(compose('%10.6f',M(1,:)),' '));
for r = 2:6, fprintf(';\n      %s', strjoin(compose('%10.6f',M(r,:)),' ')); end
fprintf(' ];\n');

assignin('base','CTRL_MODE',1);                    % leave model in closed loop