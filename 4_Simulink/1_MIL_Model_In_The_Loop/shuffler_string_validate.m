function shuffler_string_validate(outdir, tests_sel)
%SHUFFLER_STRING_VALIDATE  Run the acceptance suite; outdir (optional) receives one CSV + JSON per test
%  (every logged signal on the controller grid), tests_sel (optional) a vector of test numbers to run.
if nargin < 1, outdir = ''; end
if nargin < 2, tests_sel = []; end
SVG_TOO = false;        % figures go to figs/<tag>.pdf (vector, selectable text); set true to keep the old SVGs as well
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

if ~isempty(tests_sel), tests = tests(tests_sel, :); end
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
    d = nan(1,6);
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
    stats = struct('vm',vm,'vd',vd,'vdDft',vdDft,'ic',ic,'icDft',icDft,'idf',idf,'rip',rip,'d',d,'Pm',Pm,'Pc',Pc);
    export_test(out, P, outdir, k, nm, irr3, rv, Tstop, mode, stats, ok);

    % ---------------- figures + summary data ----------------
    S(k) = save_test_figs(out, nm, k, P, Pc, figdir);
end

save_summary_fig(S, figdir);
fprintf('\nAll figures saved to %s\n', figdir);

end   % shuffler_string_validate

%% ======================= local functions =======================
function export_test(out, P, outdir, k, nm, irrN, rv, Tstop, mode, stats, ok)
%EXPORT_TEST  Every logged Timeseries of one test, interpolated ('previous') onto the controller grid (dA1's
%  time base), as <outdir>/<k>_<name>.csv plus a <k>_<name>.json with the test spec, settled stats and pass flag.
if isempty(outdir), return; end
if ~exist(outdir,'dir'), mkdir(outdir); end
tag = sprintf('%02d_%s', k, strrep(nm,' ','_'));
tc = out.(P.sig.duty{1}).Time(:);
names = out.who;
cols = {'t'}; data = tc;
for i = 1:numel(names)
    n = names{i};
    try, v = out.(n); catch, continue; end
    if ~isa(v,'timeseries') || isempty(v.Data), continue; end
    d = squeeze(v.Data);
    if size(d,1) ~= numel(v.Time), d = d.'; end
    if size(d,2) ~= 1, continue; end
    tt = v.Time(:);
    [tt, iu] = unique(tt, 'last');  d = double(d(iu));
    if numel(tt) < 2, x = repmat(d(1), numel(tc), 1);
    else, x = interp1(tt, d, tc, 'previous', 'extrap'); end
    cols{end+1} = n; data(:, end+1) = x; %#ok<AGROW>
end
T = array2table(data, 'VariableNames', cols);
writetable(T, fullfile(outdir, [tag '.csv']));
J = struct('id', tag, 'k', k, 'name', nm, 'model', P.mdl, 'N', numel(P.sig.vm), 'irrN', irrN, 'rv', rv, 'Tstop', Tstop, 'mode', mode, ...
           'dt', median(diff(tc)), 'rows', numel(tc), 'columns', {cols}, 'stats', stats, 'pass', ok);
fid = fopen(fullfile(outdir, [tag '.json']), 'w'); fwrite(fid, jsonencode(J, 'PrettyPrint', true)); fclose(fid);
fprintf('  exported %s (%d rows, %d columns) to %s\n', tag, numel(tc), numel(cols), outdir);
end

function [t, y] = dec(t, y, nmax)
%DEC  Uniform decimation to at most nmax samples (keeps the vector figures small and the PDF text selectable).
if nargin < 3, nmax = 4000; end
n = numel(t);
if n > nmax
    idx = unique(round(linspace(1, n, nmax)));
    t = t(idx); y = y(idx, :);
end
end

function plot_group_zoom(out, names, tmax)
hold on; grid on; box on; shown = {};
for s = 1:numel(names)
    try, ts = out.(names{s}); m = ts.Time <= tmax; plot(ts.Time(m)*1e3, ts.Data(m)); shown{end+1}=names{s}; catch, end %#ok<AGROW>
end
if ~isempty(shown), legend(shown,'Interpreter','none','Location','best'); end
end

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
f = newfig([nm '  |  string'], 1250, 620);
tl = tiledlayout(f,2,3,'TileSpacing','compact','Padding','compact');
title(tl,[nm ' — string quantities'],'Interpreter','none','FontWeight','bold');
nexttile; plot_group(out, P.sig.vm);  title('Module voltages'); ylabel('V');
nexttile; plot_group_zoom(out, P.sig.vm, 0.012); title('Module voltages, first 12 ms'); ylabel('V'); xlabel('t [ms]');
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
nexttile; hold on; grid on; box on;
if ~isempty(Pstr), tz = tp <= min(0.012, tp(end)); plot(tp(tz)*1e3, Pstr(tz), 'LineWidth',1.2); yline(Pc,'--','ceiling'); end
title('String power, first 12 ms'); ylabel('W'); xlabel('t [ms]');
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
nexttile; hold on; grid on; box on;
tz = tv <= min(0.012, tv(end));
yyaxis left;  plot(tv(tz)*1e3, VD(tz,:), 'LineWidth', 1.1); ylabel('v_d  [V]');
yyaxis right; plot(tv(tz)*1e3, IC(tz,:), '--', 'LineWidth', 1.0); ylabel('i_c  [A]');
title('Zoom, first 12 ms: v_d (solid), i_c (dashed)'); xlabel('t [ms]');
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
try, st = out.mppt_state; stairs(st.Time, st.Data,'LineWidth',1.1); catch, end
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
%MODAL_TRACES  v_d, i_c, i_d of every shuffler on the controller grid (dA1's time base); signals logged on other
%  grids are resampled with 'previous'. Decimated for plotting.
t = out.(P.sig.duty{1}).Time(:);
N = numel(P.sig.vm); NS = size(P.sig.il, 1);
VM = zeros(numel(t), N);
for m = 1:N, VM(:,m) = onto(out.(P.sig.vm{m}), t); end
VD = VM(:,1:NS) - VM(:,2:N);
IC = zeros(numel(t), NS); ID = IC;
for j = 1:NS
    a = onto(out.(P.sig.il{j,1}), t);  b = onto(out.(P.sig.il{j,2}), t);
    IC(:,j) = a+b;  ID(:,j) = a-b;
end
[t2, VD] = dec(t, VD); [~, IC] = dec(t, IC); [~, ID] = dec(t, ID); t = t2;
end

function x = onto(ts, t)
%ONTO  One logged Timeseries resampled ('previous') onto the time vector t.
tt = ts.Time(:); d = double(squeeze(ts.Data)); d = d(:);
[tt, iu] = unique(tt, 'last'); d = d(iu);
if numel(tt) < 2, x = repmat(d(1), numel(t), 1);
else, x = interp1(tt, d, t, 'previous', 'extrap'); end
end

function f = newfig(nm, w, h)
f = figure('Name',nm,'NumberTitle','off','Color','w','Position',[80 80 w h]);
try, f.Theme = 'light'; catch, end            % R2025 figure themes: -batch sessions may default to dark
set(f,'DefaultAxesColor','w','DefaultAxesXColor','k','DefaultAxesYColor','k','DefaultTextColor','k','DefaultAxesGridColor',[0.15 0.15 0.15]);
set(f,'DefaultAxesFontSize',10,'DefaultTextFontSize',10,'DefaultLegendFontSize',9,'DefaultAxesLineWidth',0.8, ...
      'DefaultLineLineWidth',1.1,'DefaultAxesBox','on','DefaultAxesXGrid','on', ...
      'DefaultAxesYGrid','on');
end

function plot_group(out, names)
hold on; grid on; box on; shown = {};
for s = 1:numel(names)
    try, ts = out.(names{s}); [tt, yy] = dec(ts.Time, ts.Data); plot(tt, yy); shown{end+1}=names{s}; catch, end %#ok<AGROW>
end
if isempty(shown), text(0.5,0.5,'(not logged)','HorizontalAlignment','center');
else, legend(shown,'Interpreter','none','Location','best'); end
xlabel('t [s]');
end

function plot_one(out, name)
hold on; grid on; box on;
try, ts = out.(name); [tt, yy] = dec(ts.Time, ts.Data); plot(tt, yy); catch, text(0.5,0.5,'(not logged)','HorizontalAlignment','center'); end
end

function savesvg(f, path)
%SAVESVG  (name kept) vector PDF with selectable text; SVG only when SVG_TOO is set in the caller.
drawnow;
try, for ax = findall(f, 'Type', 'axes')', ax.Toolbar.Visible = 'off'; end, catch, end   % keep the axes toolbar out of the export
[d, b] = fileparts(path);
exportgraphics(f, fullfile(d, [b '.pdf']), 'ContentType', 'vector', 'BackgroundColor', 'white');
if evalin('caller', 'exist(''SVG_TOO'',''var'') && SVG_TOO'), print(f,'-dsvg','-painters',path); end
end

function s = ternary(c,a,b), if c, s=a; else, s=b; end, end