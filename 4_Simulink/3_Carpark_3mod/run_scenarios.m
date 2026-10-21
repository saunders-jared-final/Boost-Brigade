function run_scenarios(which, outdir, filter)
%RUN_SCENARIOS  Headless scenario runs of the Simulink models for the results synthesis (8_Results/analysis).
%
%   run_scenarios('carpark', outdir, filter)   3-module carpark model (this folder)
%   run_scenarios('mil',     outdir, filter)   4-module MIL model (../1_MIL_Model_In_The_Loop), kscale 1 only
%
%   From WSL:  matlab.exe -batch "cd('C:\...\4_Simulink\3_Carpark_3mod'); run_scenarios('carpark','C:\...\out\sim','S4_vref_PV80_k1')"
%
%   Scenarios (matched with QSPICE and the hardware, see analysis/config.py): S4 = +1 V step on the VM2-VM3
%   reference from a settled loop; S1 = the loop closing on the open-loop mismatch, reproduced as the mirrored
%   reference step rv = -vd_OL from a settled loop (the firmware's bumpless rebase makes the engagement an
%   error-driven response, so the two are the same to first order); S3 = module N irradiance 1000 -> 667 W/m2 from a
%   settled loop (PV80), with an open-loop twin (CTRL_MODE 0, duties 0.5).
%   Model edits are made in memory only (the Vref and last-irradiance Constants become Step blocks) and the model
%   is closed without saving. One CSV (100 us grid for carpark, 50 us for MIL) + one JSON per case in outdir.
if nargin < 1 || isempty(which), which = 'carpark'; end
here = fileparts(mfilename('fullpath'));
if nargin < 2 || isempty(outdir), outdir = fullfile(here, '..', '..', '8_Results', 'analysis', 'out', 'sim'); end
if nargin < 3, filter = ''; end
outdir = fullfile(outdir, which);
if ~exist(outdir, 'dir'), mkdir(outdir); end
KI_V = 2*pi*150;

if strcmp(which, 'mil')
    addpath(fullfile(here, '..', '1_MIL_Model_In_The_Loop'));
    cd(fullfile(here, '..', '1_MIL_Model_In_The_Loop'));
    setups = {''};  kscales = 1;
else
    setups = {'BENCH', 'PV80'};  kscales = [0.1 0.3 1];
end

% ---- scenario list
cases = {};
for s = 1:numel(setups)
    for k = kscales
        t0 = 0.03 + 0.03*(k < 0.2);
        Tstop = t0 + max(0.06, 10/(k*KI_V));
        tag = sprintf('%s_k%g', setups{s}, k);  tag = regexprep(tag, '^_', '');
        cases(end+1,:) = {['S4_vref_' tag], setups{s}, k, 'vref', t0, Tstop, 1}; %#ok<AGROW>
        cases(end+1,:) = {['S1_close_' tag], setups{s}, k, 'close', t0, Tstop, 1}; %#ok<AGROW>
        if strcmp(setups{s}, 'PV80') || strcmp(which, 'mil')
            cases(end+1,:) = {['S3_shade_' tag], setups{s}, k, 'shade', t0, Tstop, 1}; %#ok<AGROW>
            cases(end+1,:) = {['S3_shade_OL_' tag], setups{s}, k, 'shade', t0, Tstop, 0}; %#ok<AGROW>
        end
    end
end
if ~isempty(filter), cases = cases(contains(cases(:,1), filter), :); end
fprintf('%d cases\n', size(cases,1));

% ---- model, in-memory edits
if ~strcmp(which, 'mil'), assignin('base', 'SETUP', 'PV80'); assignin('base', 'LOAD', 'CV'); assignin('base', 'KSCALE', 1); end
assignin('base', 'CTRL_MODE', 1);
P = init_params();
load_system(P.mdl);
set_param(P.mdl, 'FastRestart', 'off');
cleanup = onCleanup(@() close_system(P.mdl, 0));
N = numel(P.path.irr);  NS = numel(P.path.vref);      % P.N exists only in the carpark init_params
steps.vref = cell(1, NS);
for j = 1:NS, steps.vref{j} = swap_const_for_step(P.path.vref{j}, 1, 0, 0); end
steps.irr = swap_const_for_step(P.path.irr{N}, 1, 1000, 1000);
set_param(P.path.supEn, 'Value', '1');
set_param(P.path.mpptEn, 'Value', '0');
for g = 1:N-1, set_param(P.path.irr{g}, 'Value', '1000'); end
% the identification variant (CTRL_MODE 0) drives the legs from these Constants; the model file leaves them at the
% Simulink default of 1, so every open-loop run here must first put them at 0.5
for b = 1:numel(P.path.dutyConst)
    try, set_param(P.path.dutyConst{b}, 'Value', '0.5');
    catch, warning('duty constant %s not found: open-loop cases of this model use the block as saved', P.path.dutyConst{b}); end
end

for c = 1:size(cases,1)
    [id, setup, k, kind, t0, Tstop, mode] = cases{c,:};
    fprintf('\n=== %s\n', id);
    if ~strcmp(which, 'mil'), assignin('base', 'SETUP', setup); assignin('base', 'LOAD', 'CV'); assignin('base', 'KSCALE', k); end
    assignin('base', 'CTRL_MODE', mode);
    P = init_params();
    meta = struct('id', id, 'which', which, 'setup', setup, 'kscale', k, 'scenario', kind(1:min(end,5)), 't0', t0, 'Tstop', Tstop, 'ctrl_mode', mode);
    if isfield(P, 'ctrl') && isfield(P.ctrl, 'version'), meta.params_version = P.ctrl.version; end
    % defaults: no steps
    for j = 1:NS, set_param(steps.vref{j}, 'Time', '1', 'Before', '0', 'After', '0'); end
    set_param(steps.irr, 'Time', '1', 'Before', '1000', 'After', '1000');
    switch kind
        case 'vref'
            j = min(2, NS);
            set_param(steps.vref{j}, 'Time', num2str(t0), 'Before', '0', 'After', '1');
            meta.step = sprintf('Vref%d 0 -> +1 V at t0', j);
        case 'close'
            % open-loop operating point at 0.5 duties
            assignin('base', 'CTRL_MODE', 0);  init_params();
            set_param(P.mdl, 'StopTime', '0.03');
            ol = sim(P.mdl);
            vd = zeros(1, NS);
            for j = 1:NS
                [ta, a] = getsig(ol, sprintf('VM%d', j));  [~, b] = getsig(ol, sprintf('VM%d', j+1));
                m = ta >= 0.025;  vd(j) = mean(a(m) - b(m));
            end
            meta.vd_OL = vd;
            assignin('base', 'CTRL_MODE', 1);  init_params();
            for j = 1:NS, set_param(steps.vref{j}, 'Time', num2str(t0), 'Before', '0', 'After', num2str(-vd(j), '%.6g')); end
            meta.step = sprintf('Vref 0 -> -vd_OL = [%s] at t0 (mirrored engagement)', num2str(-vd, '%.4g '));
        case 'shade'
            set_param(steps.irr, 'Time', num2str(t0), 'Before', '1000', 'After', '667');
            meta.step = sprintf('Irradiance %d 1000 -> 667 W/m2 at t0', N);
    end
    set_param(P.mdl, 'StopTime', num2str(Tstop));
    tic;  out = sim(P.mdl);  meta.sim_seconds = toc;
    export_case(out, P, N, NS, fullfile(outdir, id), meta);
end
end

% ------------------------------------------------------------------ helpers
function h = swap_const_for_step(path, t, before, after)
ph = get_param(path, 'PortHandles');
pos = get_param(path, 'Position');  parent = get_param(path, 'Parent');
line = get_param(ph.Outport(1), 'Line');
dst = get_param(line, 'DstPortHandle');
delete_line(line);  delete_block(path);
h = add_block('simulink/Sources/Step', path, 'Position', pos, 'Time', num2str(t), 'Before', num2str(before), ...
              'After', num2str(after), 'SampleTime', '-1');
nph = get_param(h, 'PortHandles');
for q = 1:numel(dst), add_line(parent, nph.Outport(1), dst(q), 'autorouting', 'on'); end
end

function export_case(out, P, N, NS, base, meta)
[tc, ~] = getsig(out, 'dA1');
names = {};
for k = 1:N, names{end+1} = sprintf('VM%d', k); end %#ok<AGROW>
for k = 1:N, names{end+1} = sprintf('VMm%d', k); end %#ok<AGROW>
for k = 1:N, names{end+1} = sprintf('IM%d', k); end %#ok<AGROW>
for k = 1:NS, names = [names, {sprintf('ILA%d', k), sprintf('ILB%d', k)}]; end %#ok<AGROW>
for k = 1:NS, names = [names, {sprintf('dA%d', k), sprintf('dB%d', k)}]; end %#ok<AGROW>
for k = 1:NS, names{end+1} = sprintf('rv%d', k); end %#ok<AGROW>
names = [names, {'beta', 'stress', 'V_String', 'I_String'}];
cols = {'t'};  D = tc(:);
for k = 1:numel(names)
    try
        [t, x] = getsig(out, names{k});
        D(:, end+1) = interp1(t, x, tc, 'previous', 'extrap'); %#ok<AGROW>
        cols{end+1} = names{k}; %#ok<AGROW>
    catch
    end
end
meta.columns = cols;  meta.dt = median(diff(tc));  meta.rows = numel(tc);
fid = fopen([base '.csv'], 'w');  fprintf(fid, '%s\n', strjoin(cols, ','));
fprintf(fid, ['%.9g' repmat(',%.9g', 1, numel(cols)-1) '\n'], D');  fclose(fid);
fid = fopen([base '.json'], 'w');  fprintf(fid, '%s', jsonencode(meta));  fclose(fid);
fprintf('wrote %s (%d rows, %d columns, sim %.1f s)\n', [base '.csv'], numel(tc), numel(cols), meta.sim_seconds);
end

function [t, x] = getsig(simOut, name)
v = [];
if ~isempty(simOut) && any(strcmp(name, simOut.who)), v = simOut.get(name);
elseif evalin('base', sprintf('exist(''%s'', ''var'')', name)), v = evalin('base', name); end
assert(~isempty(v), 'signal ''%s'' not found', name);
if isa(v, 'timeseries'), t = v.Time(:); x = squeeze(v.Data); x = x(:);
elseif isstruct(v) && isfield(v, 'time'), t = v.time(:); x = v.signals.values(:);
else, error('signal ''%s'': unsupported format %s', name, class(v)); end
end
