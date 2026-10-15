function [VMm, ILm, Vstr_m] = sense_model(VM, IL, Vstr, SENSE)
%SENSE_MODEL  What the firmware sees (MATLAB Function block source, Sensing subsystem).
%   Sits between the plant's true signals and the Controller/Supervisor so the
%   gains are designed against the board's measurement chain, not ideal signals.
%   Inputs : VM (3) TRUE module voltages, IL (4) TRUE inductor currents in the
%            control-stack convention, Vstr TRUE string voltage at the load.
%   Param  : SENSE (struct from init_params, scope = Parameter).
%   Outputs: VMm (3) module voltages as formed in App/app.c, ILm (4) as from
%            Core/Src/sensors.c, Vstr_m the e-load readback the Pi would forward.
%   Block sample time: SENSE.Ts (100e-6), atomic.
%
%   Voltages: three INA239 bus readings, refreshed every SENSE.ina_div ticks
%     U12 = VM3            (CS1)
%     U11 = VM2 + VM3      (CS2)
%     U10 = VM1 + VM2      (CS3, PV1+ to PV3+, behind the ISO7762)
%   quantised to 3.125 mV, then VM3 = U12, VM2 = U11 - U12 and VM1 from SENSE.vm1_src:
%     0 INA         VM1 = U10 - VM2
%     1 VSTR_PARAM  VM1 = vstr_param - VM2 - VM3   (e-load CV setpoint, full rate)
%     2 VSTR_PI     VM1 = Vstr_m - VM2 - VM3       (e-load readback, ~2.2 Hz, held)
%   Currents: averaged plant -> the tick-mean is the sample; quantised on the 12-bit
%   ADC through the FITTED sensitivity and converted back with the FIRMWARE's one,
%   so kX_hw ~= kX_fw reproduces a scaling error.
%#codegen
persistent n_ina n_pi U Vpi
if isempty(n_ina)
    n_ina = 0;  n_pi = 0;  U = zeros(3,1);  Vpi = Vstr;
end
VMc = VM(:);  ILc = IL(:);

% ---- INA239 round robin (1 kHz) ----
if n_ina == 0
    Ut = [VMc(3); VMc(2) + VMc(3); VMc(1) + VMc(2)];
    if SENSE.noise_vm > 0, Ut = Ut + SENSE.noise_vm * randn(3,1); end
    U = SENSE.ina_lsb * round(Ut / SENSE.ina_lsb);
end
n_ina = n_ina + 1;
if n_ina >= SENSE.ina_div, n_ina = 0; end

% ---- e-load readback through the Pi ----
if n_pi == 0
    Vpi = SENSE.vstr_lsb * round(Vstr / SENSE.vstr_lsb);
end
n_pi = n_pi + 1;
if n_pi >= SENSE.vstr_pi_div, n_pi = 0; end
Vstr_m = Vpi;

VMm = zeros(3,1);
VMm(3) = U(1);
VMm(2) = U(2) - U(1);
switch SENSE.vm1_src
    case 1
        VMm(1) = SENSE.vstr_param - VMm(2) - VMm(3);
    case 2
        VMm(1) = Vpi - VMm(2) - VMm(3);
    otherwise
        VMm(1) = U(3) - VMm(2);
end

% ---- hall + ADC ----
khw = [SENSE.kA_hw; SENSE.kB_hw; SENSE.kA_hw; SENSE.kB_hw];
kfw = [SENSE.kA_fw; SENSE.kB_fw; SENSE.kA_fw; SENSE.kB_fw];
It = ILc;
if SENSE.noise_il > 0, It = It + SENSE.noise_il * randn(4,1); end
counts = min(max(round(It .* khw / SENSE.adc_lsb), -2048), 2047);   % 1.65 V mid-rail, 12-bit
ILm = counts * SENSE.adc_lsb ./ kfw;
end
