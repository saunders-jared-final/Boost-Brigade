function export_golden(Tend)
%EXPORT_GOLDEN  Run the carpark model (MATLAB blocks active) and dump golden CSVs
%   for the C replay test. Generic in P.N; column names follow replay.c:
%   inputs  t,VM1..VMn,IM1..IMn,ILA1,ILB1,..,V_String,I_String,Vref1..,en_sup,en_mppt
%   expected t,dA1,dB1,..,rv1..,beta,stress,Iref,Pav,state
%   Writes to P.golden_dir. Then on the host:
%     cd 4_Simulink/2_SIL_Software_In_The_Loop/firmware && cmake -B build && cmake --build build
%     ./build/test/replay test/golden/golden_inputs.csv test/golden/golden_expected.csv
%   *** RUN ON THE MIL VARIANT (MATLAB Function blocks in the loop) ***
%   To Workspace blocks required (Timeseries, inherit sample time): the
%   init_params telemetry set plus rv1..rv(NS) (tapped BEFORE their unit
%   delays), beta, stress, Iref (BEFORE its delay), Pav, mppt_state.

P   = init_params();
mdl = P.mdl;
load_system(mdl);
N = P.N; NS = P.NS;

Vref = zeros(1, NS);
for k = 1:NS, Vref(k) = str2double(get_param(P.path.vref{k}, 'Value')); end
en_sup  = str2double(get_param(P.path.supEn,  'Value'));
en_mppt = str2double(get_param(P.path.mpptEn, 'Value'));
assert(all(~isnan([Vref en_sup en_mppt])), 'Vref/Enable constants did not parse - fix init_params paths');

if nargin < 1 || isempty(Tend), simOut = sim(mdl);
else, simOut = sim(mdl, 'StopTime', num2str(Tend)); end

[tc, ~] = getsig(simOut, P.sig.duty{1});
dt = diff(tc);
assert(~isempty(dt) && max(abs(dt - P.ctrl.Ts)) < 1e-9, 'dA1 is not logged on a uniform Ts grid');
fast = @(name) resample_prev(getsig_pair(simOut, name), tc);

in_cols = [P.sig.vm, P.sig.im, reshape(P.sig.il.', 1, []), {P.sig.vstr, P.sig.istr}];
IN = zeros(numel(tc), 1 + numel(in_cols) + NS + 2);
IN(:, 1) = tc;
for k = 1:numel(in_cols), IN(:, 1 + k) = fast(in_cols{k}); end
c = 1 + numel(in_cols);
IN(:, c+1:c+NS) = repmat(Vref, numel(tc), 1);
IN(:, c+NS+1) = en_sup;
IN(:, c+NS+2) = en_mppt;

rvn = arrayfun(@(k) sprintf('rv%d', k), 1:NS, 'UniformOutput', false);
exp_cols = [P.sig.duty, rvn, {'beta','stress','Iref','Pav','mppt_state'}];
EX = zeros(numel(tc), 1 + numel(exp_cols));
EX(:, 1) = tc;
for k = 1:numel(exp_cols), EX(:, 1 + k) = fast(exp_cols{k}); end

outdir = P.golden_dir;
if ~exist(outdir, 'dir'), mkdir(outdir); end
hdr_in = strjoin([{'t'}, in_cols, arrayfun(@(k) sprintf('Vref%d',k), 1:NS, 'UniformOutput', false), {'en_sup','en_mppt'}], ',');
hdr_ex = strjoin([{'t'}, P.sig.duty, rvn, {'beta','stress','Iref','Pav','state'}], ',');
writecsv(fullfile(outdir, 'golden_inputs.csv'),   hdr_in, single(IN));
writecsv(fullfile(outdir, 'golden_expected.csv'), hdr_ex, single(EX));
fprintf('wrote %d ticks (%.3f s) to %s\n', numel(tc), tc(end), outdir);
end

function [t, x] = getsig(simOut, name)
v = [];
if ~isempty(simOut) && any(strcmp(name, simOut.who)), v = simOut.get(name);
elseif evalin('base', sprintf('exist(''%s'', ''var'')', name)), v = evalin('base', name); end
assert(~isempty(v), 'signal ''%s'' not found - add/rename its To Workspace block', name);
if isa(v, 'timeseries'), t = v.Time(:); x = squeeze(v.Data); x = x(:);
elseif isstruct(v) && isfield(v, 'time'), t = v.time(:); x = v.signals.values(:);
else, error('signal ''%s'': unsupported To Workspace format %s', name, class(v)); end
assert(numel(t) == numel(x), 'signal ''%s'': time/data length mismatch', name);
end

function tx = getsig_pair(simOut, name)
[t, x] = getsig(simOut, name);  tx = {t, x};
end

function xg = resample_prev(tx, tg)
t = tx{1};  x = tx{2};
if numel(t) == numel(tg) && max(abs(t - tg)) < 1e-9, xg = x;
else
    xg = interp1(t, x, tg, 'previous', 'extrap');
    assert(~any(isnan(xg)), 'resampling produced NaN (signal starts after t=0?)');
end
end

function writecsv(path, header, data)
fid = fopen(path, 'w');  assert(fid > 0, 'cannot open %s', path);
cu  = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', header);
fmt = ['%.9g' repmat(',%.9g', 1, size(data,2) - 1) '\n'];
fprintf(fid, fmt, double(data)');
end
