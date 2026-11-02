import { repoUrl, reportUrl, href } from '../lib/site';
export type Stream = 'hw' | 'ctrl';
export type Tag = 'pcb' | 'enclosure' | 'firmware' | 'simulink' | 'qspice' | 'ops' | 'analysis' | 'bench';
export interface Gotcha { stream: Stream; tag: Tag; title: string; body: string; fix?: string; link?: { label: string; href: string }; }
export interface Item { title: string; body: string; size: 'S' | 'M' | 'L'; }

/** Known issues: what happened, why, what to do instead. Split by stream. */
export const GOTCHAS: Gotcha[] = [
  // hardware
  { stream: 'hw', tag: 'pcb', title: 'U10 (top INA239) sits behind a reversed ISO7762', body: 'The string-potential voltage monitor cannot be read on Version 0. The isolator was removed during bring-up and the sensor wired directly, but U10 stayed dead. The top module voltage is derived from the electronic load reading pushed by the Pi (vm1_src = 2) or a fixed string voltage (vm1_src = 1).', fix: 'Restore isolation and the sensor before closing the loop on converter 1 alone. Keep vm1_prot = 0 until it is trusted.', link: { label: 'Hardware report §3.8', href: reportUrl('hardware', 12) } },
  { stream: 'hw', tag: 'pcb', title: 'B-phase hall sensors are mounted reversed', body: 'ILB reads positive out of the converter midpoint. The firmware flips the sign; ILA + ILB is the circulating current, ILA − ILB the shuffled current.', fix: 'Sign and gain live in hall_mva0..3 (params.yaml); check with a known DC current after any sensor change.' },
  { stream: 'hw', tag: 'pcb', title: 'Sensor variant versus ADC gain', body: 'The ADC gain was set for 100 mV/A while one fitted sensor output 25 mV/A, which showed as a 3.3 A phantom DC current in one leg until it was divided by four. One leg of shuffler 1 (ILA1) still read about −2 A with noise during the PV test while ILB1 read near zero; the cause was not established.', fix: 'Verify every current channel against a direct measurement (current probe) before trusting the telemetry.', link: { label: 'Hardware report §4.6–4.7', href: reportUrl('hardware', 20) } },
  { stream: 'hw', tag: 'pcb', title: 'Nucleo GND pads have no net on the PCB', body: 'A bodge wire ties the Nucleo ground to the board ground. Do not assume the header carries it.' },
  { stream: 'hw', tag: 'pcb', title: 'The two shufflers are hard-wired together', body: 'OL1/CL1/OL2/CL2 modes exist in firmware, but the Version 0 board cannot run a converter in isolation under load, and boards cannot be stacked. Scalability beyond three modules is untested.' },
  { stream: 'hw', tag: 'pcb', title: '1ED3140 drivers add no dead time and have no fault pins', body: 'Dead time (HRTIM, 100–200 ns) and over-current trips are firmware. The COMP/DAC hardware trip is wired on the schematic but not implemented.' },
  { stream: 'hw', tag: 'pcb', title: 'Fixed dead time distorts the duty at high frequency', body: 'Two 200 ns dead times are 8 % of the period at 200 kHz and 16 % at 400 kHz; the module-voltage spread grew from 0.2 V to 1.1 V and the output fell. 400 kHz is the practical ceiling for these MOSFETs as driven.', fix: 'Adaptive dead time, or stay at 200–300 kHz.', link: { label: 'Hardware report §4.6', href: reportUrl('hardware', 20) } },
  { stream: 'hw', tag: 'pcb', title: 'Coupled-inductor wiring was second-guessed', body: 'The winding arrangement was reworked during bring-up; the final arrangement is the one the control model assumes (circulating mode sees L+M). The hall sensors and the model agree only for that arrangement.', fix: 'If an inductor is replaced, confirm with an open-loop probe: duties 0.52 / 0.48 and the sign of the circulating current.' },
  { stream: 'hw', tag: 'enclosure', title: 'Heatsink mounting and thermal path', body: 'The heatsink is clamped under the board by printed keepers with thermal paste; the first fit needed trimming and the paste was reapplied. Inductor temperature was never measured, only estimated by touch (noticeably hotter at 100 kHz).', fix: 'Add a probe on the inductors; consider a smaller heatsink and better fasteners in a mechanical pass.' },
  { stream: 'hw', tag: 'enclosure', title: 'Some holes and threads printed the wrong size', body: 'Several enclosure holes came out undersize or with the wrong thread for the inserts and had to be drilled or tapped by hand.', fix: 'Re-check the hole and insert dimensions in the Fusion model against the actual inserts before the next print.' },
  { stream: 'hw', tag: 'bench', title: 'Telemetry only as Grafana screenshots for the hardware report', body: 'The hardware stream’s results were read off Grafana at low rate; fast transients were not captured, and the Keysight DSOX2004A used outdoors was too slow for waveform captures.', fix: 'Every Grafana panel has a CSV behind it (influx_export.py); use the exports and the R&S scope.' },
  // control
  { stream: 'ctrl', tag: 'firmware', title: 'Never C,APPLY a new gain set while the loop is running', body: 'In three bench cases a live APPLY tripped within 2 s: fault 0x2000 (main-loop stall) or module under-voltage.', fix: 'Set kscale / M, APPLY, then C,MODE,CL + C,EN,1. Future work: refuse APPLY in RUN_CL.', link: { label: 'Results', href: href('/results/') } },
  { stream: 'ctrl', tag: 'firmware', title: 'Hall samples must average over whole PWM periods', body: 'A point sample locked to the PWM aliased the ripple into a 6.8 A bias. The firmware takes 80 samples per channel per tick = the mean over exactly 20 periods (comb filter with nulls at k·f_sw).', link: { label: 'sensors.c', href: repoUrl('6_RTOS/Core/Src/sensors.c') } },
  { stream: 'ctrl', tag: 'firmware', title: 'INA239 conversion time defaults to about 1 ms', body: 'That delay made the voltage loop ring with 50 % overshoot. Firmware sets 84 µs.', link: { label: 'ina2x9.c', href: repoUrl('6_RTOS/Core/Src/ina2x9.c') } },
  { stream: 'ctrl', tag: 'firmware', title: 'Soft start is not optional', body: 'Without the 150 ms ramp from the pre-bias duty d0 = Vbot/(Vtop+Vbot), a 1 V module mismatch rails the hall sensors at enable.' },
  { stream: 'ctrl', tag: 'firmware', title: 'A gain set travels with its plant and switching frequency', body: 'The 300 kHz set was identified at the 200 kHz plant resistance and oscillated at k = 0.6. Re-identify (or recompute with R_sw(f)) whenever f_sw changes.', link: { label: 'DESIGN_LOG 6.8', href: repoUrl('3_Analytical/shuffler_notebooks/DESIGN_LOG.md') } },
  { stream: 'ctrl', tag: 'firmware', title: 'Run-time parameters are RAM only', body: 'Everything set with C,SET is lost on reset. Push params.yaml from the web page (:8080) after every reset, and check PARAMS_VERSION in the banner.' },
  { stream: 'ctrl', tag: 'simulink', title: 'C Caller static state survives between runs', body: 'Especially with Fast Restart. Reset it with an Initialize Function block calling sil_reset_pass. Acceptance test: two back-to-back runs must be bit-identical.', link: { label: 'SIL INSTRUCTIONS.md', href: repoUrl('4_Simulink/2_SIL_Software_In_The_Loop/firmware/sil/INSTRUCTIONS.md') } },
  { stream: 'ctrl', tag: 'simulink', title: 'Do not mark the C functions “deterministic”', body: 'Simulink may cache calls and corrupt the state. Keep the explicit sample times (50 µs / 1 ms, atomic) and do not add stack.c to the SIL build; the model does the scheduling.' },
  { stream: 'ctrl', tag: 'simulink', title: 'The 4-module MIL plant has the opposite u_d → i_c sign to the PCB', body: 'Which is why the Simulink bench gain set was rejected. Check cond(G) and the signs on every identification.' },
  { stream: 'ctrl', tag: 'qspice', title: 'Names inside hierarchical blocks use a bullet (U+2022)', body: 'e.g. I(V4•XS1). Port nets have no inner name; use the top-sheet name. The resistor-type load stalls the solver at t = 0, so use the current sink.', link: { label: 'Power_Shuffler_Integrated.md', href: repoUrl('2_Qspice/Power_Shuffler_Integrated.md') } },
  { stream: 'ctrl', tag: 'qspice', title: 'The integrated sheets are generated, do not hand-edit', body: 'build_power_shuffler_integrated.py writes them; hand edits and the generator do not mix. The hierarchical netlist solves in 34 s vs 81 s flat.' },
  { stream: 'ctrl', tag: 'qspice', title: 'Build the control DLL with QSPICE’s bundled Digital Mars compiler', body: 'build_dll.bat. The DLL models firmware sampling: INA 1 kHz hold with 3.125 mV steps, 12-bit hall ADC, 10 kHz tick.', link: { label: 'ctrl_dll README', href: repoUrl('2_Qspice/ctrl_dll/README.md') } },
  { stream: 'ctrl', tag: 'ops', title: 'Grafana shows stale values outside RUN states', body: 'The analysis uses RUN rows only. Every Grafana screenshot has a CSV behind it, regenerable with influx_export.py.', link: { label: 'influx_export.py', href: repoUrl('7_Pi/tools/influx_export.py') } },
  { stream: 'ctrl', tag: 'ops', title: 'E,LOCAL in closed loop trips the stale-VM1 fault after 2 s', body: 'When vm1_src = 2 the string voltage comes from the e-load at 2 Hz. Switch to vm1_src 0 or 1 before handing the front panel to an operator.' },
  { stream: 'ctrl', tag: 'analysis', title: 'Three naming schemes look alike', body: 'B01–B09 / S01–S11 are hardware windows. S1 / S3 / S4 / S5 are simulation scenarios (loop-close, shade, +1 V step, duty steps). S1–S11 in QSPICE are build stages.', link: { label: 'TestCases README', href: repoUrl('8_Results/TestCases/README.md') } },
  { stream: 'ctrl', tag: 'analysis', title: 'The root README describes an older plan', body: 'It mentions 150 W panels, an EcoFlow load and 100 kHz. The campaign actually used 3 × 80 W KAUSSP80 panels, a Rigol DL3021 e-load and 200 / 300 / 400 kHz. Take setup facts from experiment_checklist.md and 8_Results.', link: { label: 'experiment_checklist.md', href: repoUrl('0_Documentation/experiment_checklist.md') } },
];

/** Future work by stream, from both reports' conclusions and DESIGN_LOG part 3. */
export const FUTURE: Record<Stream, Record<string, Item[]>> = {
  hw: {
    'Power stage': [
      { title: 'Adaptive dead time', body: 'Follow the shuffled current instead of the fixed 200 ns: body-diode conduction at light load, too short at heavy load, and 16 % of the period at 400 kHz.', size: 'M' },
      { title: 'Variable switching frequency', body: 'Lower the frequency as the shuffled current rises so the legs keep zero-voltage switching under heavy mismatch.', size: 'M' },
      { title: 'Revisit GaN switches', body: 'The system favours high switching frequencies; 400 kHz gave marginal gains at higher losses with silicon.', size: 'L' },
      { title: 'Hardware over-current trip', body: 'COMP1/COMP3 with DAC3 references into HRTIM FLT4/FLT5 on the A phases; the schematic has it, the firmware does not.', size: 'M' },
    ],
    'Board and sensing': [
      { title: 'Restore isolation for the top voltage sensor', body: 'Fix the ISO7762 wiring so VM1 no longer depends on the electronic load.', size: 'S' },
      { title: 'Verify the current telemetry against a direct measurement', body: 'One leg of shuffler 1 read wrongly during the PV test; the cause is open.', size: 'S' },
      { title: 'A simpler single-shuffler board', body: 'Boards interlinked through headers or terminal blocks, so strings of more than three modules can be tested and a fault disables one shuffler, not the whole board.', size: 'L' },
      { title: 'Integration with an MPPT converter', body: 'Removed from scope this year; the electronic load stood in for it at a fixed string voltage, so the true gain over a tracked string was never measured.', size: 'L' },
    ],
    'Mechanical': [
      { title: 'Mechanical pass', body: 'Smaller heatsink, better fasteners, correct hole and insert sizes, inductor temperature probe; consider one board for the MCU and the Pi.', size: 'M' },
    ],
  },
  ctrl: {
    'Firmware': [
      { title: 'Refuse C,APPLY while the loop is running', body: 'Live gain swaps caused all three bench trips.', size: 'S' },
      { title: 'Move from the superloop to FreeRTOS', body: 'Control stays in the HRTIM ISR; sensing, safety and telemetry become tasks with explicit priorities and deadlines.', size: 'M' },
      { title: 'Streamline gain generation per switching frequency', body: 'R_sw(f_sw) is now a formula, so the averaged model can be corrected without a new identification.', size: 'M' },
    ],
    'Control research': [
      { title: 'Compare other controllers', body: 'LQR, MPC, an observer-based design, EKF; cost-function or machine-learning gain search against the decoupling PI.', size: 'L' },
      { title: 'MPPT on the Raspberry Pi', body: 'The Pi already drives the e-load over USB; an MPPT there would allow proper efficiency measurements.', size: 'M' },
      { title: 'PIL and HIL rungs', body: 'Planned but not done: processor-in-the-loop on a small MCU, plant-on-a-chip HIL on an STM32H7 over CAN with fault injection.', size: 'L' },
    ],
    'Experiments': [
      { title: 'A sunny day with every panel connected', body: 'Module 1 produced about 0 A all afternoon on 20 Oct; the loop was only partly exercised against real panel dynamics. Log irradiance.', size: 'S' },
      { title: 'Other panel arrangements and applications', body: 'Dynamic configurations; non-solar uses (mining, computing, industrial power, batteries, solar car racing).', size: 'L' },
    ],
  },
};
