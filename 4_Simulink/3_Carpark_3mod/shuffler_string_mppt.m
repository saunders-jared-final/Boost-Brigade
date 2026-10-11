function [Iref, Pav, state] = shuffler_string_mppt(Vstr, Istr, beta, en)
%SHUFFLER_STRING_MPPT  Adaptive-step P&O on string current (lab-load variant only).
%   The carpark load is the EcoFlow (its own MPPT); on hardware this block is
%   disabled (en = 0). Constants for the 150 W panels: IMAX below Isc.
%   Sample time 1e-3, atomic. Mirrors 6_RTOS/ctrl_core/shuffler_mppt.c.
%#codegen
Ts = 1e-3;  TP = 0.02;  IREF0 = 8;  IMIN = 2;  IMAX = 8.5;
DB = 1.0;  KA = 0.01;  SMIN = 0.05;  SMAX = 1.0;  S0 = 0.25;  BTOL = 1e-3;
N = round(TP/Ts);
persistent iref dirn Pprev acc n boot b0 st
if isempty(iref)
    iref=IREF0; dirn=1; Pprev=0; acc=0; n=0; boot=true; b0=beta; st=0;
end
if en == 0
    iref=IREF0; dirn=1; Pprev=0; acc=0; n=0; boot=true; b0=beta; st=0;
    Iref=iref; Pav=Vstr*Istr; state=0; return;
end
acc = acc + Vstr*Istr;
n   = n + 1;
if n >= N
    Pw  = acc/N;  acc = 0;  n = 0;
    govActive = abs(beta - b0) > BTOL;   b0 = beta;
    if govActive
        boot = true;  st = 0;
    elseif boot
        Pprev = Pw;  boot = false;
        iref  = iref + dirn*S0;  st = 1;
    else
        dP = Pw - Pprev;
        if dP > DB
            step = min(max(KA*abs(dP),SMIN),SMAX);
            iref = iref + dirn*step;  st = 1;
        elseif dP < -DB
            dirn = -dirn;
            step = min(max(KA*abs(dP),SMIN),SMAX);
            iref = iref + dirn*step;  st = 1;
        else
            st = 2;
        end
        Pprev = Pw;
    end
    iref = min(max(iref,IMIN),IMAX);
end
Iref = iref;  Pav = Pprev;  state = st;
end
