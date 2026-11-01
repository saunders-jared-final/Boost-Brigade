import type { PartInfo } from '../components/Exploded';
/** Board parts for the exploded/identify view. `match` is a GLB node name or prefix (refdes from KiCad). */
export const BOARD_PARTS: PartInfo[] = [
  { match: ['L1', 'L2'], label: 'ERUC23 coupled inductors (L1, L2)', body: 'One per shuffler (TDK ERUC23-4R1K). Wired so the circulating mode sees L+M = 13.75 µH and the shuffled mode the 2.05 µH leakage. Ripple Δi_c = V̄ / 2f(L+M): 8.4 A pk-pk at 200 kHz, 4.1 A at 400 kHz.', explode: [0, 1, 0] },
  { match: ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8'], label: 'Half-bridge MOSFETs (Q1–Q8, STD45N10F7)', body: 'Two half-bridges per shuffler, interleaved 180°. Dead time 200 ns is set in the HRTIM; their output capacitance (C_p ≈ 2.2 nF) is the origin of the switching resistance R_sw = 64·C_p·f³·(L+M)².', explode: [0, 0.6, 0] },
  { match: 'U4A_*', label: '1ED3140 gate drivers, shuffler 1 (U4A_T1/B1) and shuffler 2 (U4A_T2/B2)', body: 'Isolated single-channel drivers, one per switch (A legs). They add no dead time and have no fault pins, so dead time and over-current protection are firmware.', explode: [0, 0.8, 0] },
  { match: 'U4B_*', label: '1ED3140 gate drivers, B legs (U4B_T1/B1, U4B_T2/B2)', body: 'Isolated single-channel drivers for the B half-bridges. Eight drivers in total.', explode: [0, 0.8, 0] },
  { match: ['U10', 'U11', 'U12'], label: 'INA229/239 voltage monitors (U10–U12)', body: 'Bus-voltage only (shunt inputs shorted) over SPI3. U12 = module 3, U11 = modules 2+3, U10 = string (behind U13). U10 sits behind a reversed ISO7762 isolator, so VM1 is taken from the e-load on the Version 0 board.', explode: [0, 1, 0] },
  { match: 'U13', label: 'ISO7762 digital isolator (U13)', body: 'Isolates the SPI link to U10 at string potential. Wired backwards on Version 0: the rework item that makes VM1 unreliable.', explode: [0, 1, 0] },
  { match: ['U4', 'U5', 'U8', 'U9'], label: 'TMCS1126 hall current sensors (U4, U5, U8, U9)', body: 'Four winding currents: ILA/ILB per shuffler. Averaged over exactly 20 PWM periods by the ADC + DMA comb filter. ILA + ILB = circulating, ILA − ILB = shuffled. B-phase sensors are mounted reversed.', explode: [0, 1, 0] },
  { match: ['U14', 'U15'], label: 'Würth isolated DC-DC modules (U14, U15)', body: 'WPME-FDSM 173951275 isolated supplies for the gate-driver and logic rails that sit at string potential.', explode: [0, 0.7, 0] },
  { match: ['U2', 'U6'], label: 'TPS7A4533 LDOs (U2, U6)', body: 'Low-dropout regulators for the sensing and logic rails.', explode: [0, 0.7, 0] },
  { match: ['D3', 'D5', 'D8', 'D10'], label: 'Bootstrap / supply diodes', body: 'SMA diodes in the gate-driver bootstrap and supply paths.', explode: [0, 0.5, 0] },
  { match: ['D1', 'D2', 'D4'], label: 'Status LEDs (D1 red, D2 blue, D4 green)', body: 'Board-level indicators; the operator LED legend lives on the pod.', explode: [0, 0.5, 0] },
  { match: ['S2', 'SW1'], label: 'Switches (S2 DP3T, SW1)', body: 'Mode/selection switches on the board edge.', explode: [0, 0.5, 0] },
  { match: 'C*', label: 'Decoupling and bulk capacitors', body: 'TDK 130 µF electrolytics on each module node (130 / 260 / 130 µF effective) plus ceramic decoupling at the half-bridges.', explode: [0, 0.5, 0] },
  { match: 'R*', label: 'Resistors', body: 'Gate resistors, dividers and pull-ups.', explode: [0, 0.3, 0] },
  { match: ['copper', 'silkscreen_top', 'soldermask_top', 'soldermask_bottom', 'board_body'], label: 'Version 0 PCB', body: 'Six copper layers (F, In1–In4, B). The Nucleo (U1) and the four XT60 connectors have no 3D model in the KiCad export, so they do not appear here; see the photos.', explode: [0, 0, 0] },
];
/** Enclosure bodies (names depend on the Fusion export; adjust after `gltf-transform inspect`). */
export const ENCLOSURE_PARTS: PartInfo[] = [
  { match: ['Lid*', 'lid*', 'Top*'], label: 'Lid', body: '3D-printed lid with a clear window over the board.', explode: [0, 1, 0] },
  { match: ['Heatsink*', 'heatsink*', 'HS*'], label: 'Heatsink', body: 'Under the board; DS18B20 probe taped to it, read by the Pi at 1 Hz. The pod sends C,ESTOP above 80 °C.', explode: [0, -1, 0] },
  { match: ['PCB*', 'Board*', 'board*', 'Version*'], label: 'Shuffler board', body: 'Version 0 six-layer PCB with the Nucleo on headers.', explode: [0, 0.3, 0] },
  { match: ['Pi*', 'Raspberry*', 'pod*', 'Pod*'], label: 'Raspberry Pi pod', body: 'Pi 4B with LCD, IR receiver and RGB status LED. Telemetry and UI only, never in the control loop.', explode: [-1, 0, 0] },
  { match: ['Base*', 'base*', 'Bottom*', 'Enclosure*'], label: 'Base', body: '3D-printed base carrying the board, heatsink and pod.', explode: [0, -0.4, 0] },
];
