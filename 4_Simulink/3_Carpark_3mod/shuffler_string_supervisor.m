function [rv, beta, stress] = shuffler_string_supervisor(VM, IM, IL, d, en)
%SHUFFLER_STRING_SUPERVISOR  Feasibility governor (MATLAB Function block source).
%   Generic in N = numel(IM). IM may be ABSOLUTE (plant) or RELATIVE (recon
%   block): only max(imf) - imf is used, so a common offset cancels.
%   Inputs : VM (N) unused, IM (N), IL (2NS), d (2NS) applied duties, en.
%   Outputs: rv (NS x 1) relaxation refs, beta, stress. Sample time 1e-3, atomic.
%   Mirrors 6_RTOS/ctrl_core/shuffler_supervisor.c.
%#codegen
N = numel(IM);  NS = N - 1;  %#ok<NASGU>
ILc = IL(:);  IMc = IM(:);  dc = d(:);
id = ILc(1:2:end) - ILc(2:2:end);
Ts3 = 1e-3;  TF = 5e-3;  I_RATED = 10;
S_HI = 0.90;  S_LO = 0.70;  KB = 60;  KREL = 6;  BMAX = 4;  RVMAX = 30;
persistent b imf idf
if isempty(b), b = 0; imf = IMc; idf = id; end
if en == 0
    b = 0; imf = IMc; idf = id;
    rv = zeros(N-1,1); beta = 0; stress = 0; return;
end
imf = imf + (Ts3/TF)*(IMc - imf);
dl  = max(imf) - imf;
idf = idf + (Ts3/TF)*(id - idf);
stress = max( max(abs(idf))/I_RATED , max(abs(dc - 0.5))/0.45 );
if stress > S_HI
    b = b + Ts3*KB*(stress - S_HI);
elseif stress < S_LO
    b = b - Ts3*KREL*(S_LO - stress);
end
b = min(max(b,0), BMAX);
rv = b*(dl(2:N) - dl(1:N-1));
rv = min(max(rv,-RVMAX), RVMAX);
beta = b;
end
