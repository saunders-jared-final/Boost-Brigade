%% shuffler_string_validate.m
%  Closed-loop acceptance suite for the 3-module carpark model (generic in P.N).
%  Paths/names/ratings come from init_params.m. Per test: printed settled report
%  and SVG figures in ./figs (string / control / supervisory) + 00_summary.svg.
%
%  Modes: 'track' vd on refs & ic~0 | 'protect' settled & |i_diff|<=I_RATED
%         'mppt' settled & total power > 98.5% of ceiling (lab-load variant only)
%
%  Reconstruction check: if the Telemetry logs IMr1..IMrN (recon block output),
%  the report prints max_k std_over_modules(IM_true - IM_recon) in the settled
%  window - it must be ~0 (the difference is the unobservable string current).

P = init_params();
assignin('base','CTRL_MODE',P.ctrl_mode);
N = P.N;  NS = P.NS;  NL = P.NL;

% [name, irr on module N, rv(1..NS), Tstop, mode]
tests = { 'uniform-zero  ', 1000, zeros(1,NS),          0.06, 'track';
          'decoupling    ', 1000, [zeros(1,NS-1) 2],    0.06, 'track';
          'shade-balanced',  500, zeros(1,NS),          0.06, 'track';
          'shade-refs    ',  500, [2 -2 zeros(1,NS-2)], 0.06, 'track';
          'shade-deep    ',  200, zeros(1,NS),          0.50, 'protect';
          'mppt-uniform  ', 1000, zeros(1,NS),          0.60, 'mppt';
          'mppt-shade    ',  500, zeros(1,NS),          0.60, 'mppt' };
% The mppt rows need the controllable current-sink load (LOAD = 'CC'); with the
% DL3021 in CV (default) the string voltage is pinned and they are skipped.
if ~strcmp(P.load.type, 'CC')
    tests = tests(~strcmp(tests(:,5), 'mppt'), :);
end

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

nT = size(tests,1);
S = struct('name',{},'t',{},'pfrac',{},'Pfin',{},'Pc',{});

for k = 1:nT
    nm = strtrim(tests{k,1}); irrN = tests{k,2}; rv = tests{k,3};
    Tstop = tests{k,4}; mode = tests{k,5};
    fprintf('\n[%d/%d] %s - simulating %.2f s...\n', k, nT, nm, Tstop);

    for g = 1:N-1, set_param(P.path.irr{g},'Value','1000'); end
    set_param(P.path.irr{N},'Value',num2str(irrN));
    for j = 1:NS, set_param(P.path.vref{j},'Value',num2str(rv(j))); end
    out = sim(P.mdl,'StopTime',num2str(Tstop));

    % ---------------- settled stats ----------------
    t1 = Tstop - Tavg;  t0 = Tstop - 2*Tavg;
    vm = zeros(1,N); vmp = zeros(1,N);
    for mnum = 1:N
        ts = out.(P.sig.vm{mnum});
        vm(mnum) = wmean(ts,t1,Tstop);  vmp(mnum) = wmean(ts,t0,t1);
    end
    vd    = vm(1:NS) - vm(2:N);
    vdDft = (vmp(1:NS) - vmp(2:N)) - vd;
    ic=zeros(1,NS); idf=zeros(1,NS); icDft=zeros(1,NS); rip=zeros(1,NS);
    for j = 1:NS
        a = out.(P.sig.il{j,1});  b = out.(P.sig.il{j,2});
        ic(j)   = wmean(a,t1,Tstop)+wmean(b,t1,Tstop);
        idf(j)  = wmean(a,t1,Tstop)-wmean(b,t1,Tstop);
        icDft(j)= (wmean(a,t0,t1)+wmean(b,t0,t1)) - ic(j);
        rip(j)  = wpp(a,t1);
    end
    Pc = (N-1)*P.pv.Pmp + P.pv.pmp(irrN);

    fprintf('\n=== %s  (irr%d=%d, rv=[%s]) ===\n', nm, N, irrN, num2str(rv));
    fprintf('  VM      = [%s] V\n', strjoin(compose('%7.2f',vm),' '));
    fprintf('  v_diff  = [%s]  (ref [%s])   drift/%.0fms = [%s]\n', ...
            strjoin(compose('%7.3f',vd),' '), num2str(rv), Tavg*1e3, strjoin(compose('%6.3f',abs(vdDft)),' '));
    fprintf('  i_comm  = [%s] A   drift = [%s]\n', strjoin(compose('%7.2f',ic),' '), strjoin(compose('%.2f',abs(icDft)),' '));
    fprintf('  i_diff  = [%s] A   ripple(pp) = [%s]\n', strjoin(compose('%7.2f',idf),' '), strjoin(compose('%.2f',rip),' '));
    try
        d = zeros(1,NL);
        for j = 1:NL, ts = out.(P.sig.duty{j}); d(j) = wmean(ts,t1,Tstop); end
        fprintf('  duties  = [%s]%s\n', strjoin(compose('%5.3f',d),' '), ...
                ternary(any(d<0.07|d>0.93),'   <-- NEAR RAIL',''));
    catch, fprintf('  duties  : (not logged)\n');
    end
    Pm = nan(1,N);
    try
        for mnum = 1:N, ts = out.(P.sig.im{mnum}); Pm(mnum) = vm(mnum)*wmean(ts,t1,Tstop); end
        fprintf('  P_mod   = [%s] W   total = %.1f W  (%.1f%% of %d W ceiling)\n', ...
                strjoin(compose('%7.1f',Pm),' '), sum(Pm), 100*sum(Pm)/Pc, round(Pc));
    catch, fprintf('  P_mod   : (IM not logged)\n');
    end
    % reconstruction consistency: IM_true - IM_recon must be module-independent
    try
        D = zeros(N,1);
        for mnum = 1:N
            D(mnum) = wmean(out.(P.sig.im{mnum}),t1,Tstop) - wmean(out.(P.sig.imr{mnum}),t1,Tstop);
        end
        fprintf('  recon   : IM_true - IM_recon = [%s] A  (spread %.3f A, = string current if consistent)\n', ...
                strjoin(compose('%6.2f',D.'),' '), max(D)-min(D));
    catch, fprintf('  recon   : (IMr not logged)\n');
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

    S(k) = save_test_figs(out, nm, k, P, Pc, figdir);
end

save_summary_fig(S, figdir);
fprintf('\nAll figures saved to %s\n', figdir);

%% ======================= local functions =======================
function Srow = save_test_figs(out, nm, k, P, Pc, figdir)
tag = sprintf('%02d_%s', k, strrep(nm,' ','_'));
[tv, VD, IC, ID] = modal_traces(out, P);
try
    vs = out.(P.sig.vstr);  is = out.(P.sig.istr);
    n  = min(numel(vs.Data), numel(is.Data));
    tp = vs.Time(1:n);  Pstr = vs.Data(1:n).*is.Data(1:n);
    if max(abs(Pstr(tp > 0.5*tp(end)))) > P.load.Pmax
        fprintf(2, '  WARNING: string power above the DL3021 %g W limit in the second half of %s\n', P.load.Pmax, nm);
    end
catch, tp = []; Pstr = [];
end
lbl = @(pre) arrayfun(@(j) sprintf('%s_{%d}', pre, j), 1:P.NS, 'UniformOutput', false);

f = newfig([nm '  |  string'], 900, 620);
tl = tiledlayout(f,2,2,'TileSpacing','compact','Padding','compact');
title(tl,[nm ' - string quantities'],'Interpreter','none','FontWeight','bold');
nexttile; plot_group(out, P.sig.vm);  title('Module voltages'); ylabel('V');
nexttile; plot_group(out, [P.sig.im P.sig.imr]);  title('Module currents (true, reconstructed)'); ylabel('A');
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

f = newfig([nm '  |  control'], 900, 860);
tl = tiledlayout(f,3,2,'TileSpacing','compact','Padding','compact');
title(tl,[nm ' - control layer'],'Interpreter','none','FontWeight','bold');
nexttile; plot(tv,VD,'LineWidth',1.1); grid on; box on;
title('Differential voltages'); ylabel('V'); legend(lbl('v_d'),'Location','best');
nexttile; plot(tv,IC,'LineWidth',1.1); grid on; box on;
title('Common currents'); ylabel('A'); legend(lbl('i_c'),'Location','best');
nexttile; hold on; grid on; box on; plot(tv,ID,'LineWidth',1.1);
yline( P.sup.I_RATED,'--','+I_{RATED}'); yline(-P.sup.I_RATED,'--','-I_{RATED}');
title('Differential (shuffled) currents vs rating'); ylabel('A'); legend(lbl('i_d'),'Location','best');
nexttile; plot_group(out, P.sig.duty); title('Duty cycles'); ylim([0 1]);
nexttile; plot_group(out, reshape(P.sig.il.',1,[])); title('Phase inductor currents'); ylabel('A'); xlabel('t [s]');
nexttile; axis off;
savesvg(f, fullfile(figdir,[tag '_control.svg']));  close(f);

f = newfig([nm '  |  supervisory'], 900, 620);
tl = tiledlayout(f,2,2,'TileSpacing','compact','Padding','compact');
title(tl,[nm ' - supervisory layer'],'Interpreter','none','FontWeight','bold');
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
title(tl,'Suite summary - what each layer buys','FontWeight','bold');
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
vm = cell(1,P.N);
for m = 1:P.N, vm{m} = out.(P.sig.vm{m}); end
t = vm{1}.Time;
VD = zeros(numel(t), P.NS); IC = VD; ID = VD;
for j = 1:P.NS
    VD(:,j) = vm{j}.Data - vm{j+1}.Data;
    a = out.(P.sig.il{j,1}).Data;  b = out.(P.sig.il{j,2}).Data;
    IC(:,j) = a+b;  ID(:,j) = a-b;
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
