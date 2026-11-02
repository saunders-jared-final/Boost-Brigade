/** Bill of materials of the Version 0 board: the 19 Sep 2026 component order (hardware report, appendix 4). */
export interface BomLine { item: string; part: string; refs: string; qty: number; cost?: number; }
export const BOM: BomLine[] = [
  { item: 'Isolated gate driver', part: '1ED3140MU12F', refs: 'U4A_B1, U4A_B2, U4A_T1, U4A_T2, U4B_B1, U4B_B2, U4B_T1, U4B_T2', qty: 8, cost: 19.44 },
  { item: 'Power MOSFET, 100 V, 45 A', part: 'STD45N10F7', refs: 'Q1–Q8', qty: 8, cost: 37.44 },
  { item: 'Coupled inductor, 4.1 µH', part: 'ERUC23-4R1K', refs: 'L1, L2', qty: 2, cost: 29.46 },
  { item: 'Bulk capacitor, 130 µF 80 V polymer', part: 'B40910A0137M000', refs: 'C1–C4', qty: 4, cost: 20.28 },
  { item: '10 µF ceramic, 1210', part: '12105C106KAT2A', refs: 'C6, C7, C9, C10, C12, C13, C19, C20, C25–C29, C32, C33, C35, C36, C42, C43, C48, C49, C57–C59', qty: 24, cost: 26.05 },
  { item: '10 µF ceramic, 2220 (isolated supply)', part: 'C5750X7S2A106K230KB', refs: 'C30, C31, C55, C56', qty: 4, cost: 20.82 },
  { item: '100 nF ceramic, 0805, 50 V', part: 'KGM21NR71H104KM', refs: 'C11, C14–C18, C21–C24, C34, C37–C41, C44–C47, C50–C54, C61–C84', qty: 49, cost: 19.35 },
  { item: 'Hall-effect current sensor', part: 'TMCS1126B4AQDVGRQ1', refs: 'U4, U5, U8, U9', qty: 4, cost: 44.10 },
  { item: 'Power monitor', part: 'INA239AQDGSRQ1', refs: 'U10, U11, U12', qty: 3, cost: 36.60 },
  { item: 'Six-channel digital isolator', part: 'ISO7762QDBQRQ1', refs: 'U13', qty: 1, cost: 11.62 },
  { item: '3.3 V LDO regulator', part: 'TPS7A4533KTTR', refs: 'U2, U6', qty: 2, cost: 15.04 },
  { item: 'Wide-input buck module, 12 V', part: '173951275 (Würth)', refs: 'U14, U15', qty: 2, cost: 22.50 },
  { item: 'Bootstrap diode, 100 V Schottky', part: 'VSSA210-E3/61T', refs: 'D3, D5, D8, D10', qty: 4, cost: 5.70 },
  { item: 'LED, red', part: 'LSM0805412V', refs: 'D1', qty: 1, cost: 1.08 },
  { item: 'LED, green', part: 'LSM0805452V', refs: 'D4', qty: 1, cost: 0.82 },
  { item: 'LED, blue', part: 'LSM0805463V', refs: 'D2', qty: 1, cost: 1.32 },
  { item: '10 Ω gate turn-on resistor, 0805', part: 'SG73S2ATTD10R0F', refs: 'R12–R14, R18–R20, R35–R37, R41–R43', qty: 12, cost: 3.50 },
  { item: '4.7 Ω turn-off and snubber resistor, 0805', part: 'SG73P2ATTD4R70F', refs: 'R15, R16, R21, R22, R38–R40, R44–R52', qty: 16, cost: 4.50 },
  { item: '1 kΩ resistor, 0805', part: 'ERA-6AEB102V', refs: 'R8, R10, R26, R31, R33', qty: 5, cost: 1.20 },
  { item: '1.5 kΩ resistor, 0805', part: 'ERA-6AEB152V', refs: 'R9, R11, R32, R34', qty: 4, cost: 0.90 },
  { item: '680 Ω resistor, 0805', part: 'RK73H2ATTD6800F', refs: 'R23, R25', qty: 2 },
  { item: '100 Ω resistor, 0805', part: 'RK73H2ATTD1000F', refs: 'R24', qty: 1, cost: 0.15 },
  { item: 'SPDT slide switch', part: 'L101011MS02Q', refs: 'SW1', qty: 1, cost: 12.26 },
  { item: 'DP3T slide switch', part: 'L203011MS02Q', refs: 'S2', qty: 1, cost: 22.14 },
  { item: 'XT60PW PV connector', part: 'Amass XT60PW', refs: 'XT60_1–XT60_4', qty: 4, cost: 27.65 },
  { item: 'Test point, through-hole', part: 'Keystone 5014', refs: 'TP1–TP4, TP11–TP14', qty: 8 },
  { item: 'Test point, SMD', part: 'Keystone 5019', refs: 'TP5–TP10', qty: 6 },
  { item: 'Development board', part: 'NUCLEO-G474RE', refs: 'U1', qty: 1, cost: 29.31 },
];
export const BOM_TOTAL = { qty: 179, cost: 413.23 };
export const BOM_NOTES = 'The 100 nF capacitors in this order are 50 V parts; after the parasitic model, the 24 HF decoupling positions (C61–C84) and the eight 470 pF snubber capacitors were re-ordered as 250 V parts. The 22 Ω turn-on resistors were not ordered. Spares for assembly losses and rework are included in the line costs.';

/** Enclosure bill of materials (Fusion 360 assembly shuffler_assembly.f3z). */
export interface EnclosureLine { n: number; item: string; what: string; qty: number; source: string; }
export const ENCLOSURE_BOM: EnclosureLine[] = [
  { n: 1, item: 'Lid', what: '3D-printed, PLA', qty: 1, source: 'Fusion body Lid' },
  { n: 2, item: 'Side walls', what: '3D-printed, PLA; XT60 cut-outs on one side, pod cut-outs on the other', qty: 1, source: 'Fusion body Side_Walls' },
  { n: 3, item: 'End panels', what: '3D-printed, PLA; cable entries', qty: 1, source: 'Fusion body End_Panels' },
  { n: 4, item: 'Belly pan', what: '3D-printed, PLA; floor and feet', qty: 1, source: 'Fusion body Belly_Pan' },
  { n: 5, item: 'Heatsink keepers', what: '3D-printed clamps for the heatsink', qty: 1, source: 'Fusion body HS_Keepers' },
  { n: 6, item: 'Heatsink', what: 'Altronics H0582 extruded aluminium, thermal paste', qty: 1, source: 'Altronics' },
  { n: 7, item: 'Shuffler PCB, Version 0', what: 'six-layer board, PCBWay, with stencil', qty: 1, source: '5_Kicad' },
  { n: 8, item: 'NUCLEO-G474RE', what: 'controller, on stacking headers', qty: 1, source: 'ST' },
  { n: 9, item: '2×20 stacking headers', what: 'Nucleo and Raspberry Pi risers', qty: 4, source: 'generic' },
  { n: 10, item: 'XT60PW-F connectors', what: 'panel inputs and string output', qty: 4, source: 'Amass' },
  { n: 11, item: 'Raspberry Pi 4B', what: 'telemetry pod with 16×2 I²C LCD, IR receiver (GPIO17), RGB LED, DS18B20 probe (GPIO4)', qty: 1, source: 'Raspberry Pi' },
  { n: 12, item: 'Fasteners and inserts', what: 'machine screws into heat-set inserts; standoffs under the board', qty: 1, source: 'as modelled in the CAD' },
];
