/** Schematic sheets for the viewer (SVG ids from scripts/prep_kicad.sh) with their callouts. */
export interface Callout { ref?: string; x?: number; y?: number; label: string; body?: string; }
export interface Sheet { id: string; title: string; blurb: string; callouts: Callout[]; }

export const SHEETS: Sheet[] = [
  {
    id: 'root', title: 'Top level', blurb: 'The string: three panel inputs, two shuffler blocks, the voltage-sensing block and the Nucleo. Each shuffler is a hierarchical sheet with its own gate drivers, current sensing and floating supply.',
    callouts: [
      { ref: 'XT60_1', label: 'Panel inputs (XT60_1–XT60_3) and string output (XT60_4)', body: 'PV1+ at the top, GND at the bottom; the midpoints PV2+ and PV3+ are where the shufflers act.' },
      { x: 33, y: 60, label: 'Shuffler 1 and shuffler 2 blocks', body: 'Converter 1 sits between PV1+ and PV3+ with its midpoint on PV2+; converter 2 between PV2+ and GND with its midpoint on PV3+. The two share module 2, which is why the plant is coupled.' },
      { x: 42, y: 42, label: 'Voltage sensing block', body: 'Three INA239 chip selects and the shared SPI bus, with the string-potential sensor behind an isolator.' },
      { ref: 'S2', label: 'S2: 3.3 V logic rail selector', body: 'Nucleo 3.3 V or on-board LDO; the grounded middle position is the digital kill switch.' },
      { ref: 'SW1', label: 'SW1: gate-driver 3.3 V', body: 'Cuts the drivers’ logic supply to stop switching instantly.' },
      { x: 72, y: 60, label: 'NUCLEO-G474RE headers (U1A, U1B)', body: 'PWM on PA8–PA11 and PB12–PB15, hall outputs on PA0/PA1/PA4/PC1, SPI3 on PB3–PB5 with chip selects PA7/PB6/PC7. The note on the sheet records the pull-up/pull-down finding from the proto-board.' },
    ],
  },
  {
    id: 'shuffle-converter-1', title: 'Shuffler 1: power stage', blurb: 'Two half-bridge legs across the module pair, the coupled inductor to the midpoint, bulk capacitors on each module and the HF decoupling bank sized by the parasitic model.',
    callouts: [
      { ref: 'L1', label: 'Coupled inductor L1 (ERUC23-4R1K)', body: 'Both windings on one core; the dotted ends set the inverse coupling that cancels the ripple at the midpoint.' },
      { ref: 'Q1', label: 'Half-bridge legs Q1–Q4', body: 'Leg A (top) and leg B (bottom), each a high-side and a low-side STD45N10F7, switched 180° apart with 200 ns dead time (100 ns from 16 Oct).' },
      { ref: 'C1', label: 'Bulk capacitors C1, C2', body: '130 µF 80 V hybrid polymer across each module of the pair.' },
      { ref: 'C61', label: 'HF decoupling bank (C61–C72)', body: '100 nF 250 V X7T ceramics beside each leg: added after the parasitic-aware simulation showed the rails ringing at tens of MHz without them.' },
      { ref: 'R47', label: 'RC snubbers (R47, R48 + 470 pF)', body: '4.7 Ω + 470 pF across each MOSFET, chosen from the snubber study; the 22 Ω turn-on option was left out.' },
      { ref: 'TP5', label: 'Test points TP5, TP6', body: 'Switch nodes for the oscilloscope: dead time and interleave were verified here at 200, 300 and 400 kHz.' },
    ],
  },
  {
    id: 'shuffle-converter-1-gate-drivers', title: 'Shuffler 1: gate drivers', blurb: 'Four isolated 1ED3140 drivers, one per switch, with bootstrap supplies for the high sides and separate turn-on and turn-off resistors.',
    callouts: [
      { ref: 'U4A_T1', label: 'High-side driver U4A_T1', body: 'Isolated input from the Nucleo PWM; 12 V bootstrap supply referenced to the switch node.' },
      { ref: 'U4A_B1', label: 'Low-side driver U4A_B1', body: 'Referenced to the module rail; the interlock logic prevents both outputs driving at once.' },
      { ref: 'D3', label: 'Bootstrap diode D3', body: '100 V Schottky charging the high-side bootstrap capacitor while the low side conducts.' },
      { ref: 'R12', label: 'Gate resistors', body: '10 Ω turn-on (R12–R14) and 4.7 Ω turn-off (R15, R16): the turn-on edge sets the overshoot, the turn-off edge only adds loss when slowed.' },
    ],
  },
  {
    id: 'shuffle-converter-1-current-sensing', title: 'Shuffler 1: current sensing', blurb: 'Two TMCS1126 hall sensors in series with the windings, with RC output filters into the Nucleo ADC.',
    callouts: [
      { ref: 'U4', label: 'Hall sensor U4 (leg A)', body: '100 mV/A about 1.65 V; ±15.5 A linear range; the 1 kΩ + 318 pF output network forms the 500 kHz pole modelled in QSPICE.' },
      { ref: 'U5', label: 'Hall sensor U5 (leg B)', body: 'Mounted reversed on Version 0, so its sign is flipped in firmware.' },
      { ref: 'R8', label: 'Output filters R8–R11', body: 'Series resistors and capacitors to the ADC pins; the ADC samples four times per switching period and averages 80 samples per control tick.' },
    ],
  },
  {
    id: 'shuffle-converter-1-flyback-converter-floating-ldo', title: 'Shuffler 1: floating supply', blurb: 'The wide-input buck module and LDO that make a 12 V gate-drive rail and a floating 3.3 V logic rail from the module voltages.',
    callouts: [
      { ref: 'U14', label: 'Würth 173951275 buck module', body: '18–74.5 V in, 12 V out at up to 4 A: gate drivers and bootstraps.' },
      { ref: 'U2', label: 'TPS7A4533 LDO', body: 'Fixed 3.3 V for the hall sensors and, for shuffler 1, the string-potential voltage sensor and its isolator.' },
      { ref: 'C55', label: 'Isolated-supply capacitors C55–C57', body: '10 µF 2220 ceramics on the floating rail.' },
    ],
  },
  {
    id: 'voltage-sensing', title: 'Voltage sensing', blurb: 'Three INA239 bus-voltage monitors on one SPI bus with separate chip selects; the one at string potential sits behind an ISO7762 isolator.',
    callouts: [
      { ref: 'U12', label: 'U12: module 3 (PV3+ to GND)', body: 'Chip select CS1 (PA7). Reads VM3 directly.' },
      { ref: 'U11', label: 'U11: modules 2+3 (PV2+ to GND)', body: 'Chip select CS2 (PB6). VM2 = U11 − U12.' },
      { ref: 'U10', label: 'U10: string (PV1+ to PV3+)', body: 'Chip select CS3 (PC7). Floats at string potential, hence the isolator. Wired reversed on Version 0 and not usable: VM1 is reconstructed from the electronic load reading the Pi forwards.' },
      { ref: 'U13', label: 'U13: ISO7762 digital isolator', body: 'Six channels for SCLK, MOSI, MISO and CS of U10. Removed during bring-up after the wiring error was found.' },
    ],
  },
  {
    id: 'shuffle-converter-2', title: 'Shuffler 2: power stage', blurb: 'The second converter, identical to the first, between PV2+ and GND with its midpoint on PV3+.',
    callouts: [
      { ref: 'L2', label: 'Coupled inductor L2' },
      { ref: 'Q5', label: 'Half-bridge legs Q5–Q8' },
      { ref: 'C3', label: 'Bulk capacitors C3, C4' },
      { ref: 'C73', label: 'HF decoupling bank (C73–C84)' },
    ],
  },
];
