%% shuffler_string_ident.m
%  Plant identification, generic in the module count: baseline + 2*NS modal
%  duty steps -> (2NS x 2NS) DC gain G -> decoupler M = G \ diag(kI).
%  Prints the paste for shuffler_string_ctrl.m AND writes M into the shared
%  firmware parameter JSON (P.params_json); then regenerate params.h with
%      python3 6_RTOS/ctrl_core/params/gen_params.py     (or export_params.m)
%
%  PREREQUISITES
%   1. Variant Sources configured: CTRL_MODE==1 -> controller, ==0 -> the
%      ident Constant blocks (paths in P.path.dutyConst).
%   2. OPERATING POINT: small-signal measurement at ~Vmp with the string at
%      ~Imp. With the MPPT disabled the load sits at IREF0 (init_params /
%      shuffler_string_mppt.m) - keep IREF0 near Imp (8 A for the 150 W panels).

P = init_params();
assignin('base','CTRL_MODE',0);                % identification mode (variant)
N = P.N;  NS = P.NS;  NL = P.NL;

Tstop = 0.03;   Tavg = 0.005;   du = P.test.du;

% duty patterns: rows = baseline + 2NS modal runs, cols = the NL duties
base = 0.5*ones(1,NL);  runs = repmat(base, 1+2*NS, 1);
for k = 1:NS
    runs(1+k,    [2*k-1 2*k]) = 0.5 + du/2;                   % u_comm_k
    runs(1+NS+k, [2*k-1 2*k]) = [0.5+du/2, 0.5-du/2];         % u_diff_k
end

load_system(P.mdl);
set_param(P.mdl,'SimulationMode',P.test.simMode);
set_param(P.mdl,'FastRestart','on');
cleanup = onCleanup(@() set_param(P.mdl,'FastRestart','off'));
set_param(P.path.supEn, 'Value','0');              % supervisory layers OFF
set_param(P.path.mpptEn,'Value','0');
for g = 1:N, set_param(P.path.irr{g},'Value','1000'); end   % uniform sun

wmean = @(ts,t0) mean(ts.Data(ts.Time>=t0));
Y = zeros(1+2*NS, 2*NS);
for k = 1:size(runs,1)
    for b = 1:NL
        set_param(P.path.dutyConst{b},'Value',num2str(runs(k,b),'%.6f'));
    end
    out = sim(P.mdl,'StopTime',num2str(Tstop));
    t1 = Tstop - Tavg;
    vm = zeros(1,N);
    for mnum = 1:N, vm(mnum) = wmean(out.(P.sig.vm{mnum}), t1); end
    ic = zeros(1,NS);
    for j = 1:NS
        ic(j) = wmean(out.(P.sig.il{j,1}),t1) + wmean(out.(P.sig.il{j,2}),t1);
    end
    Y(k,:) = [vm(1:NS)-vm(2:N), ic];
    fprintf('run %d done:  vd=[%s]  ic=[%s]\n', k-1, ...
        strjoin(compose('% .3f',Y(k,1:NS)),' '), strjoin(compose('% .2f',Y(k,NS+1:end)),' '));
end

G = (Y(2:end,:) - Y(1,:)).' / du;
fprintf('\nG =\n'); disp(G);
fprintf('cond(G) = %.1f\n', cond(G));
if cond(G) > 100
    warning('G is poorly conditioned - do NOT invert. Check i_comm signal wiring.');
end
dg = diag(G(NS+1:end, NS+1:end)).';
if numel(unique(sign(dg)))>1 || max(abs(dg))/min(abs(dg)) > 3
    warning('ud->i_comm diagonals look unphysical: [%s]', num2str(dg));
end

M = G \ diag([P.ctrl.kI_v*ones(1,NS), P.ctrl.kI_i*ones(1,NS)]);
fprintf('\nPaste into shuffler_string_ctrl.m:\n\nM = [ ');
fprintf('%s', strjoin(compose('%10.6f',M(1,:)),' '));
for r = 2:2*NS, fprintf(';\n      %s', strjoin(compose('%10.6f',M(r,:)),' ')); end
fprintf(' ];\n');

% ---- write M (and the init_params mirrors) into the shared firmware JSON ----
J = jsondecode(fileread(P.params_json));
J = rmfield(J, intersect(fieldnames(J), {'x_comment'}));
J.version = sprintf('sps-params-2.%s-3mod', datestr(now,'yyyymmdd-HHMM'));
J.n_mod   = N;
J.ctrl.ts = P.ctrl.Ts;  J.ctrl.fc_lpf = P.ctrl.fc_lpf;
J.ctrl.dmin = P.ctrl.DMIN;  J.ctrl.dmax = P.ctrl.DMAX;
J.ctrl.kp_ratio_v = P.ctrl.kp_ratio_v;  J.ctrl.kp_ratio_i = P.ctrl.kp_ratio_i;
J.ctrl.M  = M;
J.sup  = struct('ts',P.sup.Ts,'tf',P.sup.TF,'i_rated',P.sup.I_RATED,'s_hi',P.sup.S_HI, ...
                's_lo',P.sup.S_LO,'kb',P.sup.KB,'krel',P.sup.KREL,'bmax',P.sup.BMAX,'rvmax',P.sup.RVMAX);
J.mppt = struct('ts',P.mppt.Ts,'tp',P.mppt.TP,'iref0',P.mppt.IREF0,'imin',P.mppt.IMIN,'imax',P.mppt.IMAX, ...
                'db',P.mppt.DB,'ka',P.mppt.KA,'smin',P.mppt.SMIN,'smax',P.mppt.SMAX,'s0',P.mppt.S0,'btol',P.mppt.BTOL);
fid = fopen(P.params_json,'w'); fprintf(fid,'%s\n', jsonencode(J,'PrettyPrint',true)); fclose(fid);
fprintf('\nwrote %s (%s)\n -> regenerate params.h: python3 6_RTOS/ctrl_core/params/gen_params.py\n', P.params_json, J.version);

assignin('base','CTRL_MODE',1);                    % leave model in closed loop
