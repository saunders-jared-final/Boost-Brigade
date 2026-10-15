%% bench_ratio_check.m
%  Open-loop sanity check of the new model against the 13 Oct bench run (100 kHz,
%  e-load CV 70 V, shuffler 2 stepped 0.49 / 0.50 / 0.51, shuffler 1 not switching).
%  On the bench VM2/(VM2+VM3) = 1 - d to three decimals: the shuffler is a stiff
%  ratio converter. The averaged model must reproduce that before identification.
%  Shuffler 1 cannot be "off" in an averaged model; it is held at 0.5, so only
%  the shuffler-2 ratio is compared, not VM1.
%  Run time: 3 sims x 0.03 s, well under a minute in accelerator mode.

P = init_params();
assignin('base','CTRL_MODE',0);
load_system(P.mdl);
set_param(P.mdl,'SimulationMode',P.test.simMode);
set_param(P.path.supEn,'Value','0');  set_param(P.path.mpptEn,'Value','0');
for g = 1:P.N, set_param(P.path.irr{g},'Value','1000'); end

bench = [0.49 0.5097; 0.50 0.4996; 0.51 0.4896];   % d, VM2/(VM2+VM3) measured (ol100k_a/b_oppoints.csv)
Tstop = 0.03;  t1 = Tstop - 0.005;
wmean = @(ts) mean(ts.Data(ts.Time >= t1));
fprintf('\n  d     model VM2/(VM2+VM3)   bench    1-d     VM1    VM2    VM3   [V]\n');
for r = 1:size(bench,1)
    d = bench(r,1);
    vals = [0.5 0.5 d d];
    for b = 1:P.NL, set_param(P.path.dutyConst{b},'Value',num2str(vals(b),'%.6f')); end
    out = sim(P.mdl,'StopTime',num2str(Tstop));
    vm = cellfun(@(s) wmean(out.(s)), P.sig.vm);
    ratio = vm(2) / (vm(2) + vm(3));
    fprintf('  %.2f      %.4f            %.4f   %.2f   %5.2f  %5.2f  %5.2f\n', d, ratio, bench(r,2), 1-d, vm);
end
assignin('base','CTRL_MODE',1);
fprintf('\nPass if the model ratio is within 0.005 of the bench column on every row.\n');
