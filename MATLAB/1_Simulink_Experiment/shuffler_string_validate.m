%% shuffler_string_validate.m
%  Closed-loop validation sequence for the 4-module / 3-shuffler string with
%  the centralised controller. Runs the four acceptance tests back-to-back
%  (Fast Restart) and prints settled means, drift, and ripple for every
%  channel — no scope-reading.
%
%  Tests:
%   1. uniform-zero   : 1000 W/m2 all, refs (0,0,0)   -> everything ~0
%   2. decoupling     : uniform, refs (0,+2,0)        -> ONLY vd2 moves
%   3. shade-balanced : M3=500 W/m2, refs (0,0,0)     -> vd,ic ~0, i_diff carries mismatch
%   4. shade-refs     : M3=500 W/m2, refs (0,+2,-2)   -> vd tracks (0,+2,-2)
%
%  SETUP: model in CLOSED-LOOP mode (controller connected). Refs and module-3
%  irradiance driven by named Constant blocks (paths below). If you have a
%  'Mismatch' Step block adding to Irradiance 3, set it to 0 / delete it —
%  this script sets shade via the Constant.

%% ---------------- CONFIG — edit to match your model ----------------
mdl    = 'power_shuffler_sim';
Tstop  = 0.06;                 % per-run sim time [s]
Tavg   = 0.01;                 % settled window: stats over the LAST Tavg secs

refBlk = { [mdl '/Vref1'], [mdl '/Vref2'], [mdl '/Vref3'] };
irrBlk =   [mdl '/Irradiance 3'];      % module-3 irradiance Constant

vmSig  = {'VM1','VM2','VM3','VM4'};
ilSig  = {'ILA1','ILB1'; 'ILA2','ILB2'; 'ILA3','ILB3'};
dutySig= {'dA1','dB1','dA2','dB2','dA3','dB3'};   % optional; skipped if not logged

% [name, irr3, rv1 rv2 rv3]
tests = { 'uniform-zero  ', 1000, [0  0  0];
          'decoupling    ', 1000, [0  2  0];
          'shade-balanced',  500, [0  0  0];
          'shade-refs    ',  500, [0  2 -2] };
%% --------------------------------------------------------------------

load_system(mdl);
set_param(mdl,'FastRestart','on');
cleanup = onCleanup(@() set_param(mdl,'FastRestart','off'));

wmean = @(ts,t0,t1) mean(ts.Data(ts.Time>=t0 & ts.Time<t1));
wpp   = @(ts,t0)    max(ts.Data(ts.Time>=t0)) - min(ts.Data(ts.Time>=t0));

for k = 1:size(tests,1)
    nm = tests{k,1};  irr3 = tests{k,2};  rv = tests{k,3};
    set_param(irrBlk,'Value',num2str(irr3));
    for j = 1:3, set_param(refBlk{j},'Value',num2str(rv(j))); end
    out = sim(mdl,'StopTime',num2str(Tstop));

    t1 = Tstop - Tavg;  t0 = Tstop - 2*Tavg;      % last window / window before
    vm  = zeros(1,4); for m=1:4, ts=out.(vmSig{m}); vm(m)=wmean(ts,t1,Tstop); end
    vmp = zeros(1,4); for m=1:4, ts=out.(vmSig{m}); vmp(m)=wmean(ts,t0,t1);   end
    vd    = [vm(1)-vm(2),  vm(2)-vm(3),  vm(3)-vm(4)];
    vdDft = [vmp(1)-vmp(2),vmp(2)-vmp(3),vmp(3)-vmp(4)] - vd;   % window-to-window drift

    ic=zeros(1,3); idf=zeros(1,3); icDft=zeros(1,3); rip=zeros(1,3);
    for j = 1:3
        a=out.(ilSig{j,1}); b=out.(ilSig{j,2});
        ic(j)  = wmean(a,t1,Tstop)+wmean(b,t1,Tstop);
        idf(j) = wmean(a,t1,Tstop)-wmean(b,t1,Tstop);
        icDft(j)= (wmean(a,t0,t1)+wmean(b,t0,t1)) - ic(j);
        rip(j) = wpp(a,t1);
    end

    fprintf('\n=== %s  (irr3=%d, rv=[%g %g %g]) ===\n', nm, irr3, rv);
    fprintf('  VM      = [%7.2f %7.2f %7.2f %7.2f] V\n', vm);
    fprintf('  v_diff  = [%7.3f %7.3f %7.3f]  (ref [%g %g %g])   drift/%.0fms = [%6.3f %6.3f %6.3f]\n', ...
            vd, rv, Tavg*1e3, abs(vdDft));
    fprintf('  i_comm  = [%7.2f %7.2f %7.2f] A   drift = [%.2f %.2f %.2f]\n', ic, abs(icDft));
    fprintf('  i_diff  = [%7.2f %7.2f %7.2f] A   ripple(pp) = [%.2f %.2f %.2f]\n', idf, rip);

    try   % duties, if logged
        d=zeros(1,6); for j=1:6, ts=out.(dutySig{j}); d(j)=wmean(ts,t1,Tstop); end
        fprintf('  duties  = [%5.3f %5.3f | %5.3f %5.3f | %5.3f %5.3f]%s\n', d, ...
                ternary(any(d<0.07|d>0.93),'   <-- NEAR RAIL',''));
    catch, fprintf('  duties  : (not logged - add To Workspace on dA1..dB3 to check railing)\n');
    end

    ok = all(abs(vd-rv)<0.25) && all(abs(ic)<1) && all(abs(vdDft)<0.05) && all(abs(icDft)<0.5);
    fprintf('  --> %s\n', ternary(ok,'PASS','CHECK: not settled on refs'));
end

function s = ternary(c,a,b), if c, s=a; else, s=b; end, end