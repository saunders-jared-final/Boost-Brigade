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
%   2. OPERATING POINT: set SETUP ('BENCH' | 'PV80') and LOAD ('CV' | 'CC') in the
%      base workspace first; the DL3021 in CV at P.load.Vcv is the default.
%   3. SIGN CHECKS (printed): every u_diff -> i_comm diagonal must be POSITIVE,
%      as identified on the switching model (QSPICE S9i, +256/+216 A per unit).
%      A negative diagonal means the ILA/ILB sign flip in the Power Shuffler
%      subsystems is missing (design book ch.2, step 3) - the script then refuses
%      to write the JSON. The u_comm -> v_diff diagonal should be about
%      -(VM_k + VM_k+1): the shuffler is a stiff ratio converter (bench: -47.6 V).
%   The previous JSON is copied to shuffler_params.<version>.json before writing.

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

% ---- sign / magnitude checks against the switching model and the bench ----
gi = diag(G(NS+1:end, NS+1:end)).';   % u_diff -> i_comm
gv = diag(G(1:NS, 1:NS)).';           % u_comm -> v_diff
fprintf('\nu_diff -> i_comm diagonal [A/unit]: %s\n', num2str(gi, '%9.1f'));
fprintf('u_comm -> v_diff diagonal [V/unit]: %s   (expect ~ -(VM_k+VM_k+1))\n', num2str(gv, '%9.2f'));
if exist(P.qspice_meas, 'file')
    Q = jsondecode(fileread(P.qspice_meas));
    Yq = [Q.y1(:) Q.y2(:) Q.y3(:) Q.y4(:)];
    Gq = (Yq(2:end,:) - Yq(1,:)).' / 0.04;
    fprintf('QSPICE S9i (150 W PV, 100 kHz) for comparison:\n'); disp(Gq);
    sgn_ok = isequal(sign(diag(Gq)), sign(diag(G)));
    fprintf('diagonal signs match QSPICE: %s\n', mat2str(sgn_ok));
else
    sgn_ok = all(gi > 0);
end
if any(gi <= 0) || ~sgn_ok
    error(['u_diff -> i_comm sign does not match the hardware/QSPICE convention. ' ...
           'Check the Gain -1 blocks on ILA/ILB in each Power Shuffler. JSON NOT written.']);
end

M = G \ diag([P.ctrl.kI_v*ones(1,NS), P.ctrl.kI_i*ones(1,NS)]);
fprintf('\nPaste into shuffler_string_ctrl.m:\n\nM = [ ');
fprintf('%s', strjoin(compose('%10.6f',M(1,:)),' '));
for r = 2:2*NS, fprintf(';\n      %s', strjoin(compose('%10.6f',M(r,:)),' ')); end
fprintf(' ];\n');

% ---- write M (and the init_params mirrors) into the shared firmware JSON ----
J = jsondecode(fileread(P.params_json));
cmt = {};  if isfield(J,'x_comment'), cmt = J.x_comment; J = rmfield(J,'x_comment'); end
bak = fullfile(fileparts(P.params_json), sprintf('shuffler_params.%s.json', J.version));
if ~exist(bak, 'file'), copyfile(P.params_json, bak); fprintf('backup: %s\n', bak); end
J.version = sprintf('sps-params-2.%s-3mod-simulink-%s', datestr(now,'yyyymmdd-HHMM'), lower(P.setup));
J.n_mod   = N;
J.ctrl.ts = P.ctrl.Ts;  J.ctrl.fc_lpf = P.ctrl.fc_lpf;
J.ctrl.dmin = P.ctrl.DMIN;  J.ctrl.dmax = P.ctrl.DMAX;
J.ctrl.kp_ratio_v = P.ctrl.kp_ratio_v;  J.ctrl.kp_ratio_i = P.ctrl.kp_ratio_i;
J.ctrl.M  = M;
J.sup  = struct('ts',P.sup.Ts,'tf',P.sup.TF,'i_rated',P.sup.I_RATED,'s_hi',P.sup.S_HI, ...
                's_lo',P.sup.S_LO,'kb',P.sup.KB,'krel',P.sup.KREL,'bmax',P.sup.BMAX,'rvmax',P.sup.RVMAX);
% J.mppt is left as it is: the MPPT is unused with the DL3021, and init_params scales
% it to the bench current limit (IMAX < IREF0+S0 breaks the host MPPT unit tests).
txt = jsonencode(J,'PrettyPrint',true);
if ~isempty(cmt), txt = ['{' newline '  "_comment": ' jsonencode(cmt) ',' txt(2:end)]; end   % keep the header comment
fid = fopen(P.params_json,'w'); fprintf(fid,'%s\n', txt); fclose(fid);
fprintf('\nwrote %s (%s)\n -> regenerate params.h: python3 6_RTOS/ctrl_core/params/gen_params.py\n', P.params_json, J.version);

assignin('base','CTRL_MODE',1);                    % leave model in closed loop
