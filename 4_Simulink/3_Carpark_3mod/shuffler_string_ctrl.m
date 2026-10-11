function d = shuffler_string_ctrl(VM, IL, rv)
%SHUFFLER_STRING_CTRL  Inner decoupling-PI controller (MATLAB Function block source).
%   Generic in the module count: N = numel(VM), NS = N-1 shufflers.
%   Inputs : VM (N x 1) module voltages, IL (2NS x 1) {ILA1,ILB1,ILA2,ILB2,..},
%            rv (NS x 1) voltage-difference references.
%   Output : d (2NS x 1) duties {dA1,dB1,dA2,dB2,..} clamped to [DMIN,DMAX].
%   Block sample time: Ts (explicit, atomic). Mirrors 6_RTOS/ctrl_core/shuffler_ctrl.c.
%#codegen
N  = numel(VM);  NS = N - 1;
Ts = 100e-6;  DMIN = 0.05;  DMAX = 0.95;
% ---- M = G \ diag(kI) from shuffler_string_ident (PASTE HERE, also in shuffler_params.json) ----
M = [ -12.798383   0.000000   0.000000   1.043947;
       -0.132666 -12.627108  -1.014057   1.021695;
        0.000000   0.000000  -1.945483   0.000000;
        0.000000   0.000000   0.000000  -2.061583 ];   % PLACEHOLDER (4-mod sub-blocks)
Kp_ratio = diag([1.58e-4*ones(1,NS), 1.08e-4*ones(1,NS)]);
fc = 2000;
a  = 2*pi*fc*Ts / (1 + 2*pi*fc*Ts);
persistent xi y_f Minv Mp
if isempty(xi)
    xi = zeros(2*NS,1); y_f = zeros(2*NS,1); Minv = inv(M); Mp = M * Kp_ratio;
end
VMc = VM(:);  ILc = IL(:);
y   = [VMc(1:NS) - VMc(2:N); ILc(1:2:end) + ILc(2:2:end)];
y_f = y_f + a*(y - y_f);
r   = [rv(:); zeros(NS,1)];
e   = r - y_f;
xi_try = xi + Ts*e;
u      = Mp*e + M*xi_try;
uc = u(1:NS);  ud = u(NS+1:2*NS);
dA = 0.5 + 0.5*(uc + ud);
dB = 0.5 + 0.5*(uc - ud);
dAs = min(max(dA, DMIN), DMAX);
dBs = min(max(dB, DMIN), DMAX);
u_act = [(dAs + dBs) - 1; dAs - dBs];
xi    = Minv * (u_act - Mp*e);
d = zeros(2*NS,1);
d(1:2:end) = dAs;
d(2:2:end) = dBs;
end
