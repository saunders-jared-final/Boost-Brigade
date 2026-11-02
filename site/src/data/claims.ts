import { href } from '../lib/site';
/** Plain-language headline statements for the home page. Each links to the page with the evidence. */
export const CLAIMS = [
  { big: 'Within 10 mV', what: 'The closed loop holds neighbouring module voltages equal to within 10 millivolts, in every settled run on the bench and in the sun.', how: 'Measured by the on-board INA239 voltage monitors at 200, 300 and 400 kHz switching.', colour: 'blue', href: href('/results/') },
  { big: 'About 12 ms', what: 'A 1 volt disturbance is corrected in about 12 milliseconds with no overshoot.', how: 'From the switching-level QSPICE model at the deployed gains; the 44 Hz telemetry cannot resolve it on hardware.', colour: 'blue', href: href('/control/') },
  { big: '99 W back', what: 'With one of three panels shaded to almost nothing, the string still delivered up to 99 W and 10.6 Wh over 36 minutes: energy a plain string would have lost.', how: 'Carpark test, 20 Oct 2026, three 80 W panels into a 61 V load.', colour: 'accent', href: href('/results/') },
  { big: '93.8 % to the load', what: 'With one emulated panel limited to 0.5 A, the shufflers doubled the string output and passed 93.8 % of the supplied power to the load.', how: 'Open-loop bench test at 200 kHz; 93.6 % again on real panels.', colour: 'green', href: href('/hardware/pcb/') },
  { big: '100 V, 45 A switches', what: 'Rated to block two full-size panels and 1.7 times their short-circuit current, so test mistakes did not destroy it.', how: 'Designed for a 540 W Aiko module; every test stayed below the 120 V DC limit.', colour: 'green', href: href('/hardware/pcb/') },
  { big: 'Remote controlled', what: 'Driven from a phone or laptop: an IR remote with presets, a web page for parameters, a live Grafana dashboard, SSH.', how: 'A Raspberry Pi pod that also flashes the microcontroller; the laptop never plugs into the system.', colour: 'teal', href: href('/control/#pi') },
];
