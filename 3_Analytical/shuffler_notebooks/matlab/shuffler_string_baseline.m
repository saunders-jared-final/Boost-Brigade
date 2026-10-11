%% shuffler_string_baseline.m
%  Baseline harvest measurements under shade (M3), for the thesis comparison:
%    A - "shufflers idle":  identification mode, all duties 0.5 (shufflers
%        present but unregulated -> passive half-bus clamping)
%    B - "no shufflers":    the three shuffler subsystems commented out
%        (plain series string)
%  Both with the MPPT disabled -> the load sinks a FIXED current = IREF0
%  (init_params). Compare totals against the controlled 'mppt-shade' result
%  from shuffler_string_validate.
%
%  Needs the same prerequisites as ident (variant CTRL_MODE, duty constants).

P = init_params();
assignin('base','CTRL_MODE',0);                % ident mode: duties from constants

Tstop = 0.06;   Tavg = 0.01;   irr3 = 500;

load_system(P.mdl);
set_param(P.mdl,'SimulationMode',P.test.simMode);
set_param(P.mdl,'FastRestart','off');          % baseline B is a structural change
restore = onCleanup(@() cellfun(@(b) set_param(b,'Commented','off'), P.path.shuf));

set_param(P.path.supEn, 'Value','0');
set_param(P.path.mpptEn,'Value','0');
set_param(P.path.irr{3},'Value',num2str(irr3));
for g = [1 2 4], set_param(P.path.irr{g},'Value','1000'); end
for b = 1:6, set_param(P.path.dutyConst{b},'Value','0.5'); end

wmean = @(ts,t0) mean(ts.Data(ts.Time>=t0));
Pceil = 3*P.pv.Pmp + P.pv.pmp(irr3);

for mode = 1:2
    if mode==1
        nm = 'A: shufflers idle (d=0.5)';
        cellfun(@(b) set_param(b,'Commented','off'), P.path.shuf);
    else
        nm = 'B: no shufflers (commented out)';
        cellfun(@(b) set_param(b,'Commented','on'),  P.path.shuf);
    end
    out = sim(P.mdl,'StopTime',num2str(Tstop));
    t1 = Tstop - Tavg;
    vm = zeros(1,4); im = zeros(1,4);
    for mnum = 1:4
        vm(mnum) = wmean(out.(P.sig.vm{mnum}), t1);
        im(mnum) = wmean(out.(P.sig.im{mnum}), t1);
    end
    Pm = vm.*im;
    fprintf('\n=== Baseline %s  (irr3=%d, Iload=%g A fixed) ===\n', nm, irr3, P.mppt.IREF0);
    fprintf('  VM    = [%7.2f %7.2f %7.2f %7.2f] V\n', vm);
    fprintf('  IM    = [%7.2f %7.2f %7.2f %7.2f] A\n', im);
    fprintf('  P_mod = [%7.1f %7.1f %7.1f %7.1f] W   total = %.1f W  (%.1f%% of %d W ceiling)\n', ...
            Pm, sum(Pm), 100*sum(Pm)/Pceil, round(Pceil));
end

assignin('base','CTRL_MODE',1);
fprintf('\n(shuffler blocks restored, CTRL_MODE back to 1)\n');
