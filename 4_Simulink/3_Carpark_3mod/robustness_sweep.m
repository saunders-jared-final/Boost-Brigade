%% robustness_sweep.m
%  Closed-loop runs of the 'decoupling' case (rv2 = +2 V step from t = 0, uniform
%  source) under the conditions tomorrow can actually hit. Each row is one short
%  sim (0.06 s); the whole sweep is a couple of minutes.
%    nominal       measured signals, kscale 1
%    kscale 0.3    the firmware's safe start-up gain scale
%    ILB x4        B-phase hall fitted as 100 mV/A but read as 25 mV/A
%    VM1 param     VM1 = e-load CV setpoint - VM2 - VM3 (U10 offline)
%    VM1 Pi        VM1 from the e-load readback via the Pi (~2.2 Hz, held)
%    noise         2 mV rms on each INA reading, 20 mA rms on each hall
%  Report per row: settled v_diff vs ref, |i_comm|, peak |i_diff| and peak |d - 0.5|
%  after the first 5 ms (start-up transient excluded).

P0 = init_params();
cases = { 'nominal',     struct();
          'kscale 0.3',  struct('kscale', 0.3);
          'ILB x4',      struct('kB_hw', 0.100);
          'VM1 param',   struct('vm1_src', 1);
          'VM1 Pi',      struct('vm1_src', 2);
          'noise',       struct('noise_vm', 2e-3, 'noise_il', 0.02) };
Tstop = 0.06;  Tavg = P0.test.Tavg;
load_system(P0.mdl);
% The model's InitFcn re-runs init_params at every sim start, which would reset CTRL/SENSE
% to defaults and hide the per-case overrides. Switch it off for the sweep (not saved).
initFcn = get_param(P0.mdl,'InitFcn');  set_param(P0.mdl,'InitFcn','');
restoreInit = onCleanup(@() restore_init(P0.mdl, initFcn));
set_param(P0.mdl,'SimulationMode',P0.test.simMode);
set_param(P0.path.supEn,'Value','1');  set_param(P0.path.mpptEn,'Value','0');
for g = 1:P0.N, set_param(P0.path.irr{g},'Value','1000'); end
rv = [zeros(1,P0.NS-1) 2];
for j = 1:P0.NS, set_param(P0.path.vref{j},'Value',num2str(rv(j))); end
wmean = @(ts) mean(ts.Data(ts.Time >= Tstop - Tavg));
tskip = 5e-3;                                  % ignore the start-up transient (caps/inductors at t = 0)
late  = @(ts) ts.Data(ts.Time >= tskip);

fprintf('\n%-12s %-22s %-18s %-12s %-10s\n', 'case', 'v_diff (ref 0, 2)', '|i_comm| [A]', 'max|i_diff|', 'max|d-.5|');
for c = 1:size(cases,1)
    P = init_params();                         % fresh CTRL / SENSE in base
    o = cases{c,2};  C = evalin('base','CTRL');  S = evalin('base','SENSE');
    if isfield(o,'kscale'), C.kscale = o.kscale; end
    for f = setdiff(fieldnames(o).', {'kscale'}), S.(f{1}) = o.(f{1}); end
    assignin('base','CTRL',C);  assignin('base','SENSE',S);
    out = sim(P.mdl,'StopTime',num2str(Tstop));
    vm = cellfun(@(s) wmean(out.(s)), P.sig.vm);
    ic = zeros(1,P.NS);  idm = 0;
    for j = 1:P.NS
        a = out.(P.sig.il{j,1});  b = out.(P.sig.il{j,2});
        ic(j) = abs(wmean(a) + wmean(b));
        idm = max(idm, max(abs(late(a) - late(b))));
    end
    dm = max(cellfun(@(s) max(abs(late(out.(s)) - 0.5)), P.sig.duty));
    fprintf('%-12s %-22s %-18s %-12.2f %-10.3f\n', cases{c,1}, ...
        mat2str(round(vm(1:end-1)-vm(2:end),3)), mat2str(round(ic,2)), idm, dm);
end
init_params();   % restore defaults in base
fprintf(['\nRead it as: every row should settle near the refs with |i_comm| < 1 A and\n' ...
         'max|i_diff| under I_RATED. ILB x4 is expected to leave a real circulating\n' ...
         'current (the loop nulls the wrong number) - that is the bench DC check''s job.\n']);

function restore_init(mdl, fcn)
if bdIsLoaded(mdl), set_param(mdl,'InitFcn',fcn); end
end
