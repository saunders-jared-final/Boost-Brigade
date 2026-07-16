%% shuffler_string_baseline.m
%  Baseline power measurements for the thesis comparison, run with the model in
%  IDENTIFICATION mode (controller disconnected, duties from dA1_const..dB3_const).
%
%  Baseline A - "shufflers idle": all duties 0.5, M3 shaded. Shufflers present
%               but unregulated (passive half-bus clamping).
%  Baseline B - "no shufflers":  the three shuffler subsystems COMMENTED OUT,
%               M3 shaded. The plain series string - the true bypass-era baseline.
%
%  Both report module voltages/currents/powers from VM1..4 and IM1..4 logging
%  (nothing inside the shufflers is referenced, so Baseline B compiles).
%  The shuffler blocks are restored (uncommented) automatically afterwards.

%% ---------------- CONFIG ----------------
mdl    = 'power_shuffler_sim';
Tstop  = 0.06;
Tavg   = 0.01;
irrBlk = [mdl '/Irradiance 3'];
irr3   = 500;
dutyBlk = { [mdl '/dA1_const'], [mdl '/dB1_const'], ...
            [mdl '/dA2_const'], [mdl '/dB2_const'], ...
            [mdl '/dA3_const'], [mdl '/dB3_const'] };
shufBlk = { [mdl '/Power Shuffler1'], [mdl '/Power Shuffler2'], [mdl '/Power Shuffler3'] };
vmSig  = {'VM1','VM2','VM3','VM4'};
pvISig = {'IM1','IM2','IM3','IM4'};
Pceil  = 3*555 + 277;            % per-module MPP ceiling with M3 at 500 W/m2
%% -----------------------------------------

load_system(mdl);
set_param(mdl,'FastRestart','off');           % structural changes below
restore = onCleanup(@() cellfun(@(b) set_param(b,'Commented','off'), shufBlk));

wmean = @(ts,t0,t1) mean(ts.Data(ts.Time>=t0 & ts.Time<t1));
set_param(irrBlk,'Value',num2str(irr3));
for b = 1:6, set_param(dutyBlk{b},'Value','0.5'); end

for mode = 1:2
    if mode==1
        nm='A: shufflers idle (d=0.5)';
        cellfun(@(b) set_param(b,'Commented','off'), shufBlk);
    else
        nm='B: no shufflers (commented out)';
        cellfun(@(b) set_param(b,'Commented','on'),  shufBlk);
    end
    out = sim(mdl,'StopTime',num2str(Tstop));
    t1 = Tstop - Tavg;
    vm=zeros(1,4); im=zeros(1,4);
    for m=1:4
        vm(m)=wmean(out.(vmSig{m}),t1,Tstop);
        im(m)=wmean(out.(pvISig{m}),t1,Tstop);
    end
    P = vm.*im;
    fprintf('\n=== Baseline %s  (irr3=%d) ===\n', nm, irr3);
    fprintf('  VM    = [%7.2f %7.2f %7.2f %7.2f] V\n', vm);
    fprintf('  IM    = [%7.2f %7.2f %7.2f %7.2f] A\n', im);
    fprintf('  P_mod = [%7.1f %7.1f %7.1f %7.1f] W   total = %.1f W  (%.1f%% of %d W ceiling)\n', ...
            P, sum(P), 100*sum(P)/Pceil, round(Pceil));
end
fprintf('\n(shuffler blocks restored)\n');