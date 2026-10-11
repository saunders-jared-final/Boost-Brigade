function export_golden(Tend)
%EXPORT_GOLDEN  Run the MIL model and dump golden CSVs for the C replay test.
%
%   export_golden        - run with the model's configured StopTime
%   export_golden(2.0)   - override stop time [s]
%
%   Writes firmware/test/golden/golden_inputs.csv and golden_expected.csv
%   (per-50us-tick stack inputs and expected outputs, float32 values, %.9g).
%   Then on the host:
%       cd firmware && cmake -B build && cmake --build build
%       ./build/test/replay test/golden/golden_inputs.csv test/golden/golden_expected.csv
%
%   *** RUN THIS ON THE MIL VARIANT *** - the three MATLAB Function blocks
%   must still be in the loop (or the C Callers would be compared against
%   themselves). Generate goldens BEFORE swapping in the C Caller blocks, or
%   after switching the variant back.
%
%   ------------------------------------------------------------------------
%   To Workspace blocks you must ADD to the model first (the telemetry set in
%   init_params covers the rest). Suggested placement: next to the existing
%   Telemetry logs. For each: Save format = Timeseries, Sample time = -1
%   (inherit), Variable name as listed:
%       rv1, rv2, rv3   <- the three Supervisor block rv outputs, tapped
%                          BEFORE their 1 ms Unit Delays
%       beta            <- Supervisor beta output
%       stress          <- Supervisor stress output
%       Iref            <- MPPT Iref output, tapped BEFORE its 1 ms Unit
%                          Delay (IC = IREF0)
%       Pav             <- MPPT Pav output
%       mppt_state      <- MPPT state output
%   Already logged per init_params (P.sig.*): VM1..VM4, IM1..IM4,
%   ILA1,ILB1,ILA2,ILB2,ILA3,ILB3, dA1..dB3, V_String, I_String.
%
%   TODO(user): if your To Workspace blocks use "Structure With Time" instead
%   of Timeseries that is handled too; plain "Array" format is NOT (no time
%   vector) - switch those blocks to Timeseries.
%   ------------------------------------------------------------------------

here = fileparts(mfilename('fullpath'));
proj = fullfile(here, '..', '..');       % 2_SIL_Software_In_The_Loop
addpath(proj);
P   = init_params();
mdl = P.mdl;
load_system(mdl);

%% ---- constants wired outside the blocks --------------------------------
% Vref1..3: the manual constants summed onto the delayed rv (block paths from
% init_params). en flags: the Enable constants feeding supervisor and MPPT.
Vref = zeros(1, 3);
for k = 1:3
    Vref(k) = str2double(get_param(P.path.vref{k}, 'Value'));
end
en_sup  = str2double(get_param(P.path.supEn,  'Value'));
en_mppt = str2double(get_param(P.path.mpptEn, 'Value'));
assert(all(~isnan([Vref en_sup en_mppt])), ...
    ['Vref/Enable constants did not parse - if these blocks are not plain ' ...
     'Constant blocks (or moved), fix the paths in init_params.m. If en or ' ...
     'Vref VARY during your golden scenario, log them with To Workspace as ' ...
     'en_sup / en_mppt / Vref1..3 instead and extend getsig() use below.']);
% TODO(user): constants are sampled once here. A scenario that steps Vref/en
% mid-run needs them logged as signals (see assert message).

%% ---- simulate -----------------------------------------------------------
if nargin < 1 || isempty(Tend)
    simOut = sim(mdl);
else
    simOut = sim(mdl, 'StopTime', num2str(Tend));
end

%% ---- collect signals ----------------------------------------------------
% master 50 us grid from dA1 (controller-rate output)
[t50, ~] = getsig(simOut, P.sig.duty{1});
dt = diff(t50);
assert(~isempty(dt) && max(abs(dt - 50e-6)) < 1e-9, ...
    'dA1 is not logged on a uniform 50 us grid (check To Workspace/solver)');

fast = @(name) resample_prev(getsig_pair(simOut, name), t50);

% logged-signal names come from init_params (single source of truth); the CSV
% HEADER strings below stay literal - they are the replay.c contract
in_cols = [P.sig.vm, P.sig.im, reshape(P.sig.il', 1, []), {P.sig.vstr, P.sig.istr}];
IN = zeros(numel(t50), 22);
IN(:, 1) = t50;
for k = 1:numel(in_cols)
    IN(:, 1 + k) = fast(in_cols{k});
end
IN(:, 18:20) = repmat(Vref, numel(t50), 1);
IN(:, 21) = en_sup;
IN(:, 22) = en_mppt;

exp_cols = [P.sig.duty, ...
            {'rv1','rv2','rv3','beta','stress','Iref','Pav','mppt_state'}];
EX = zeros(numel(t50), 15);
EX(:, 1) = t50;
for k = 1:numel(exp_cols)
    EX(:, 1 + k) = fast(exp_cols{k});
end

%% ---- write (float32 values, %.9g: exact round-trip into C strtof) -------
outdir = fullfile(here, '..', 'test', 'golden');
if ~exist(outdir, 'dir'), mkdir(outdir); end
hdr_in = ['t,VM1,VM2,VM3,VM4,IM1,IM2,IM3,IM4,ILA1,ILB1,ILA2,ILB2,ILA3,ILB3,' ...
          'V_String,I_String,Vref1,Vref2,Vref3,en_sup,en_mppt'];
hdr_ex = 't,dA1,dB1,dA2,dB2,dA3,dB3,rv1,rv2,rv3,beta,stress,Iref,Pav,state';
writecsv(fullfile(outdir, 'golden_inputs.csv'),   hdr_in, single(IN));
writecsv(fullfile(outdir, 'golden_expected.csv'), hdr_ex, single(EX));
fprintf('wrote %d ticks (%.3f s) to %s\n', numel(t50), t50(end), outdir);
end

%% ------------------------------------------------------------------------
function [t, x] = getsig(simOut, name)
% fetch a logged signal as [time, data] from the SimulationOutput (To
% Workspace, Timeseries or Structure With Time) or the base workspace
v = [];
if ~isempty(simOut) && any(strcmp(name, simOut.who))
    v = simOut.get(name);
elseif evalin('base', sprintf('exist(''%s'', ''var'')', name))
    v = evalin('base', name);
end
assert(~isempty(v), ['signal ''%s'' not found in the simulation output or base ' ...
    'workspace - add/rename its To Workspace block (see the header of this ' ...
    'file for the required list)'], name);
if isa(v, 'timeseries')
    t = v.Time(:);
    x = squeeze(v.Data);
    x = x(:);
elseif isstruct(v) && isfield(v, 'time') && isfield(v, 'signals')
    t = v.time(:);
    x = v.signals.values(:);
else
    error(['signal ''%s'': unsupported To Workspace format %s - use ' ...
           'Timeseries (preferred) or Structure With Time'], name, class(v));
end
assert(numel(t) == numel(x), 'signal ''%s'': time/data length mismatch', name);
end

function tx = getsig_pair(simOut, name)
[t, x] = getsig(simOut, name);
tx = {t, x};
end

function x50 = resample_prev(tx, t50)
% zero-order-hold resample onto the master grid; pass-through when already on it
t = tx{1};  x = tx{2};
if numel(t) == numel(t50) && max(abs(t - t50)) < 1e-9
    x50 = x;
else
    x50 = interp1(t, x, t50, 'previous', 'extrap');
    assert(~any(isnan(x50)), 'resampling produced NaN (signal starts after t=0?)');
end
end

function writecsv(path, header, data)
fid = fopen(path, 'w');      % binary mode: LF line endings
assert(fid > 0, 'cannot open %s for writing', path);
cu  = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', header);
ncol = size(data, 2);
fmt  = ['%.9g' repmat(',%.9g', 1, ncol - 1) '\n'];
fprintf(fid, fmt, double(data)');    % single->double is exact; %.9g round-trips
end
