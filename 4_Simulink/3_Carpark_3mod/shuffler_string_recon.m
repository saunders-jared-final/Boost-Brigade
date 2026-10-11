function IM = shuffler_string_recon(IL, d)
%SHUFFLER_STRING_RECON  Module currents from shuffler currents + duties (KCL).
%   What the hardware can compute (no module/string current sensors): module
%   currents RELATIVE to module N (IM(N) = 0). Shuffler k spans modules k,k+1:
%   top terminal node k, midpoint node k+1, bottom terminal node k+2. Averaged
%   per leg: top rail supplies d*iL, bottom rail (1-d)*iL, ic = iLA+iLB into
%   the midpoint. KCL at node j+1 (j = 1..N-1):
%       I_j = I_{j+1} + ic_j - itop_{j+1} - ibot_{j-1}   (out-of-range terms = 0)
%   Inputs: IL (2NS) {ILA1,ILB1,..} in the CONTROL-STACK convention (ILA positive
%   into the midpoint, ILB positive OUT of it, so ILA+ILB = circulating current
%   and ILA-ILB = shuffled current), d (2NS) duties.
%   Stateless; run at the supervisor rate. Mirrors 6_RTOS/ctrl_core/shuffler_recon.c.
%   Validation: (true IM) - IM must be the SAME number for every module.
%#codegen
ILc = IL(:);  dc = d(:);
NS = numel(ILc)/2;  N = NS + 1;
ia = ILc(1:2:end);  ib = -ILc(2:2:end);   % physical B-phase current into the midpoint
da = dc(1:2:end);   db = dc(2:2:end);
itop = da.*ia + db.*ib;
ic   = ia + ib;
ibot = ic - itop;
IM = zeros(N,1);
for j = N-1:-1:1
    acc = IM(j+1) + ic(j);
    if j < NS,  acc = acc - itop(j+1); end
    if j >= 2,  acc = acc - ibot(j-1); end
    IM(j) = acc;
end
end
