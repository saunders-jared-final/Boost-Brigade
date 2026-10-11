%% shuffler_string_validate.m
%  Closed-loop acceptance suite. Paths/names/ratings come from init_params.m.
%
%  Per test: waitbar, printed settled report, and three PROFESSIONAL SVG
%  figures saved to ./figs :
%    <k>_<name>_string.svg      module V/I, string V/I, string power vs ceiling
%    <k>_<name>_control.svg     v_diff, i_comm, i_diff (vs rating), duties, IL
%    <k>_<name>_supervisory.svg beta, stress (vs thresholds), Pav, MPPT state
%  plus, after the last test:
%    00_summary.svg             %-of-ceiling vs time overlay + settled bar chart
%    -> the overlay is the "what MPPT/governor bring" picture: MPPT tests climb
%       to ~100%, fixed-current tests sit below it, deep shade shows the
%       governor trading harvest for the current rating.
%
%  Modes: 'track' vd on refs & ic~0 | 'protect' settled & |i_diff|<=I_RATED
%         'mppt' settled & total power > 98.5% of ceiling

P = init_params();
assignin('base','CTRL_MODE',P.ctrl_mode);

% [name, irr3, rv1 rv2 rv3, Tstop, mode]
tests = { 'uniform-zero  ', 1000, [0  0  0], 0.06, 'track';
          'decoupling    ', 1000, [0  2  0], 0.06, 'track';
          'shade-balanced',  500, [0  0  0], 0.06, 'track';
          'shade-refs    ',  500, [0  2 -2], 0.06, 'track';
          'shade-deep    ',  200, [0  0  0], 0.50, 'protect';
          'mppt-uniform  ', 1000, [0  0  0], 0.60, 'mppt';
          'mppt-shade    ',  500, [0  0  0], 0.60, 'mppt' };

figdir = fullfile(pwd,'figs');
if ~exist(figdir,'dir'), mkdir(figdir); end

load_system(P.mdl);
set_param(P.mdl,'SimulationMode',P.test.simMode);
set_param(P.mdl,'FastRestart','on');
cleanup = onCleanup(@() set_param(P.mdl,'FastRestart','off'));
set_param(P.path.supEn, 'Value','1');
set_param(P.path.mpptEn,'Value','1');

Tavg  = P.test.Tavg;
wmean = @(ts,t0,t1) mean(ts.Data(ts.Time>=t0 & ts.Time<t1));
wpp   = @(ts,t0)    max(ts.Data(ts.Time>=t0)) - min(ts.Data(ts.Time>=t0));

nT  = size(tests,1);
S = struct('name',{},'t',{},'pfrac',{},'Pfin',{},'Pc',{});   % summary data

for k = 1:nT
    nm = strtrim(tests{k,1}); irr3 = tests{k,2}; rv = tests{k,3};
    Tstop = tests{k,4}; mode = tests{k,5};
    fprintf('\n[%d/%d] %s — simulating %.2f s...\n', k, nT, nm, Tstop);

    set_param(P.path.irr{3},'Value',num2str(irr3));
    for j = 1:3, set_param(P.path.vref{j},'Value',num2str(rv(j))); end
    out = sim(P.mdl,'StopTime',num2str(Tstop));

    % ---------------- settled stats ----------------
    t1 = Tstop - Tavg;  t0 = Tstop - 2*Tavg;
    vm = zeros(1,4); vmp = zeros(1,4);
    for mnum = 1:4
        ts = out.(P.sig.vm{mnum});
        vm(mnum) = wmean(ts,t1,Tstop);  vmp(mnum) = wmean(ts,t0,t1);
    end
    vd    = [vm(1)-vm(2),  vm(2)-vm(3),  vm(3)-vm(4)];
    vdDft = [vmp(1)-vmp(2),vmp(2)-vmp(3),vmp(3)-vmp(4)] - vd;
    ic=zeros(1,3); idf=zeros(1,3); icDft=zeros(1,3); rip=zeros(1,3);
    for j = 1:3
        a = out.(P.sig.il{j,1});  b = out.(P.sig.il{j,2});
        ic(j)   = wmean(a,t1,Tstop)+wmean(b,t1,Tstop);
        idf(j)  = wmean(a,t1,Tstop)-wmean(b,t1,Tstop);
        icDft(j)= (wmean(a,t0,t1)+wmean(b,t0,t1)) - ic(j);
        rip(j)  = wpp(a,t1);
    end
    Pc = 3*P.pv.Pmp + P.pv.pmp(irr3);

    fprintf('\n=== %s  (irr3=%d, rv=[%g %g %g]) ===\n', nm, irr3, rv);
    fprintf('  VM      = [%7.2f %7.2f %7.2f %7.2f] V\n', vm);
    fprintf('  v_diff  = [%7.3f %7.3f %7.3f]  (ref [%g %g %g])   drift/%.0fms = [%6.3f %6.3f %6.3f]\n', ...
            vd, rv, Tavg*1e3, abs(vdDft));
    fprintf('  i_comm  = [%7.2f %7.2f %7.2f] A   drift = [%.2f %.2f %.2f]\n', ic, abs(icDft));
    fprintf('  i_diff  = [%7.2f %7.2f %7.2f] A   ripple(pp) = [%.2f %.2f %.2f]\n', idf, rip);
    try
        d = zeros(1,6);
        for j = 1:6, ts = out.(P.sig.duty{j}); d(j) = wmean(ts,t1,Tstop); end
        fprintf('  duties  = [%5.3f %5.3f | %5.3f %5.3f | %5.3f %5.3f]%s\n', d, ...
                ternary(any(d<0.07|d>0.93),'   <-- NEAR RAIL',''));
    catch, fprintf('  duties  : (not logged)\n');
    end
    Pm = nan(1,4);
    try
        for mnum = 1:4, ts = out.(P.sig.im{mnum}); Pm(mnum) = vm(mnum)*wmean(ts,t1,Tstop); end
        fprintf('  P_mod   = [%7.1f %7.1f %7.1f %7.1f] W   total = %.1f W  (%.1f%% of %d W ceiling)\n', ...
                Pm, sum(Pm), 100*sum(Pm)/Pc, round(Pc));
    catch, fprintf('  P_mod   : (IM1..4 not logged)\n');
    end

    settled = all(abs(vdDft)<0.05) && all(abs(icDft)<0.5);
    switch mode
        case 'track'
            ok = settled && all(abs(vd-rv)<0.25) && all(abs(ic)<1);
            msg = 'CHECK: not settled on refs';
        case 'mppt'
            ok  = settled && ~any(isnan(Pm)) && sum(Pm) > 0.985*Pc;
            msg = 'CHECK: below 98.5% of ceiling (or IM not logged)';
        otherwise
            ok  = settled && all(abs(ic)<1) && all(abs(idf)<=P.sup.I_RATED);
            msg = sprintf('CHECK: not settled or |i_diff| > %g A rating', P.sup.I_RATED);
    end
    fprintf('  --> %s\n', ternary(ok,'PASS',msg));

    % ---------------- figures + summary data ----------------
    S(k) = save_test_figs(out, nm, k, P, Pc, figdir);
end

save_summary_fig(S, figdir);
fprintf('\nAll figures saved to %s\n', figdir);

%% ======================= local functions =======================
function Srow = save_test_figs(out, nm, k, P, Pc, figdir)
tag = sprintf('%02d_%s', k, strrep(nm,' ','_'));

% shared computed traces
[tv, VD, IC, ID] = modal_traces(out, P);
try
    vs = out.(P.sig.vstr);  is = out.(P.sig.istr);
    n  = min(numel(vs.Data), numel(is.Data));
    tp = vs.Time(1:n);  Pstr = vs.Data(1:n).*is.Data(1:n);
catch, tp = []; Pstr = [];
end

% ---- figure 1: string ----
f = newfig([nm '  |  string'], 900, 620);
tl = tiledlayout(f,2,2,'TileSpacing','compact','Padding','compact');
title(tl,[nm ' — string quantities'],'Interpreter','none','FontWeight','bold');
nexttile; plot_group(out, P.sig.vm);  title('Module voltages'); ylabel('V');
nexttile; plot_group(out, P.sig.im);  title('Module currents'); ylabel('A');
nexttile; hold on; grid on; box on;
try
    yyaxis left;  plot(out.(P.sig.vstr).Time, out.(P.sig.vstr).Data); ylabel('V_{string}  [V]');
    yyaxis right; plot(out.(P.sig.istr).Time, out.(P.sig.istr).Data); ylabel('I_{string}  [A]');
catch, end
title('String voltage / current'); xlabel('t [s]');
nexttile; hold on; grid on; box on;
if ~isempty(Pstr)
    plot(tp, Pstr, 'LineWidth',1.2);
    yline(Pc,'--','ceiling','LabelHorizontalAlignment','left');
end
title('String power'); ylabel('W'); xlabel('t [s]');
savesvg(f, fullfile(figdir,[tag '_string.svg']));  close(f);

% ---- figure 2: control ----
f = newfig([nm '  |  control'], 900, 860);
tl = tiledlayout(f,3,2,'TileSpacing','compact','Padding','compact');
title(tl,[nm ' — control layer'],'Interpreter','none','FontWeight','bold');
nexttile; plot(tv,VD,'LineWidth',1.1); grid on; box on;
title('Differential voltages'); ylabel('V'); legend('v_{d1}','v_{d2}','v_{d3}','Location','best');
nexttile; plot(tv,IC,'LineWidth',1.1); grid on; box on;
title('Common currents'); ylabel('A'); legend('i_{c1}','i_{c2}','i_{c3}','Location','best');
nexttile; hold on; grid on; box on; plot(tv,ID,'LineWidth',1.1);
yline( P.sup.I_RATED,'--','+I_{RATED}'); yline(-P.sup.I_RATED,'--','-I_{RATED}');
title('Differential (shuffled) currents vs rating'); ylabel('A');
legend('i_{d1}','i_{d2}','i_{d3}','Location','best');
nexttile; plot_group(out, P.sig.duty); title('Duty cycles'); ylim([0 1]);
nexttile; plot_group(out, P.sig.il(:).'); title('Phase inductor currents'); ylabel('A'); xlabel('t [s]');
nexttile; axis off;
savesvg(f, fullfile(figdir,[tag '_control.svg']));  close(f);

% ---- figure 3: supervisory ----
f = newfig([nm '  |  supervisory'], 900, 620);
tl = tiledlayout(f,2,2,'TileSpacing','compact','Padding','compact');
title(tl,[nm ' — supervisory layer'],'Interpreter','none','FontWeight','bold');
nexttile; plot_one(out,'beta');   title('Governor \beta'); ylabel('V/A');
nexttile; hold on; grid on; box on; plot_one(out,'stress');
yline(P.sup.S_HI,'--','S_{HI}'); yline(P.sup.S_LO,'--','S_{LO}');
title('Stress (fraction of rating)');
nexttile; plot_one(out,'Pav');    title('MPPT windowed power'); ylabel('W'); xlabel('t [s]');
nexttile; hold on; grid on; box on;
try, st = out.state; stairs(st.Time, st.Data,'LineWidth',1.1); catch, end
yticks([0 1 2]); yticklabels({'hold','climb','parked'});
title('MPPT state'); xlabel('t [s]');
savesvg(f, fullfile(figdir,[tag '_supervisory.svg']));  close(f);

Srow = struct('name',nm,'t',tp,'pfrac',100*Pstr/Pc,'Pfin', ...
              mean(Pstr(max(1,end-50):end)), 'Pc',Pc);
end

function save_summary_fig(S, figdir)
f = newfig('summary', 1000, 460);
tl = tiledlayout(f,1,2,'TileSpacing','compact','Padding','compact');
title(tl,'Suite summary — what each layer buys','FontWeight','bold');
nexttile; hold on; grid on; box on;
for k = 1:numel(S)
    if ~isempty(S(k).t), plot(S(k).t, S(k).pfrac,'LineWidth',1.3); end
end
yline(100,'--','per-module MPP ceiling');
ylim([0 115]); ylabel('string power  [% of ceiling]'); xlabel('t [s]');
legend({S(~cellfun(@isempty,{S.t})).name}, 'Interpreter','none','Location','southeast');
title('Power trajectory per test');
nexttile; hold on; grid on; box on;
vals = 100*[S.Pfin]./[S.Pc];
bar(vals,'FaceAlpha',0.85);
yline(100,'--');
xticks(1:numel(S)); xticklabels({S.name}); xtickangle(30);
set(gca,'TickLabelInterpreter','none');
ylabel('settled power  [% of ceiling]'); ylim([0 115]);
for k = 1:numel(vals)
    text(k, vals(k)+3, sprintf('%.1f',vals(k)),'HorizontalAlignment','center','FontSize',8);
end
title('Settled harvest per test');
savesvg(f, fullfile(figdir,'00_summary.svg'));
end

function [t, VD, IC, ID] = modal_traces(out, P)
vm = cell(1,4);
for m = 1:4, vm{m} = out.(P.sig.vm{m}); end
t = vm{1}.Time;
VD = [vm{1}.Data-vm{2}.Data, vm{2}.Data-vm{3}.Data, vm{3}.Data-vm{4}.Data];
IC = []; ID = [];
for j = 1:3
    a = out.(P.sig.il{j,1}).Data;  b = out.(P.sig.il{j,2}).Data;
    IC = [IC, a+b];  ID = [ID, a-b]; %#ok<AGROW>
end
end

function f = newfig(nm, w, h)
f = figure('Name',nm,'NumberTitle','off','Color','w','Position',[80 80 w h]);
set(f,'DefaultAxesFontSize',9,'DefaultAxesLineWidth',0.8, ...
      'DefaultLineLineWidth',1.1,'DefaultAxesBox','on','DefaultAxesXGrid','on', ...
      'DefaultAxesYGrid','on');
end

function plot_group(out, names)
hold on; grid on; box on; shown = {};
for s = 1:numel(names)
    try, ts = out.(names{s}); plot(ts.Time, ts.Data); shown{end+1}=names{s}; catch, end %#ok<AGROW>
end
if isempty(shown), text(0.5,0.5,'(not logged)','HorizontalAlignment','center');
else, legend(shown,'Interpreter','none','Location','best'); end
xlabel('t [s]');
end

function plot_one(out, name)
hold on; grid on; box on;
try, ts = out.(name); plot(ts.Time, ts.Data); catch, text(0.5,0.5,'(not logged)','HorizontalAlignment','center'); end
end

function savesvg(f, path)
drawnow;
print(f,'-dsvg','-painters',path);
end

function s = ternary(c,a,b), if c, s=a; else, s=b; end, end