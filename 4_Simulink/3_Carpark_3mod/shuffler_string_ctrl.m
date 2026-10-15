function d = shuffler_string_ctrl(VM, IL, rv, CTRL)
%SHUFFLER_STRING_CTRL  Inner decoupling-PI controller (MATLAB Function block source).
%   Generic in the module count: N = numel(VM), NS = N-1 shufflers.
%   Inputs : VM (N x 1) module voltages AS MEASURED, IL (2NS x 1) {ILA1,ILB1,ILA2,ILB2,..}
%            in the control-stack convention (ILA into the midpoint, ILB out of it),
%            rv (NS x 1) voltage-difference references.
%   Param  : CTRL (struct from init_params, scope = Parameter in the block's
%            Ports and Data Manager - no port): Ts, M, Kp_ratio, fc, DMIN, DMAX, kscale.
%   Output : d (2NS x 1) duties {dA1,dB1,dA2,dB2,..} clamped to [DMIN,DMAX].
%   Block sample time: CTRL.Ts (explicit, atomic). Mirrors 6_RTOS/ctrl_core/shuffler_ctrl.c;
%   kscale mirrors the firmware runtime gain scale (Mp and M scaled, Minv by 1/kscale).
%#codegen
N  = numel(VM);  NS = N - 1;
Ts = CTRL.Ts;
M    = CTRL.kscale * CTRL.M;
Mp   = M * diag(CTRL.Kp_ratio);
Minv = inv(M);                      % recomputed each call: tunable CTRL survives Fast Restart
a    = 2*pi*CTRL.fc*Ts / (1 + 2*pi*CTRL.fc*Ts);
persistent xi y_f
if isempty(xi)
    xi = zeros(2*NS,1); y_f = zeros(2*NS,1);
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
dAs = min(max(dA, CTRL.DMIN), CTRL.DMAX);
dBs = min(max(dB, CTRL.DMIN), CTRL.DMAX);
u_act = [(dAs + dBs) - 1; dAs - dBs];
xi    = Minv * (u_act - Mp*e);
d = zeros(2*NS,1);
d(1:2:end) = dAs;
d(2:2:end) = dBs;
end
