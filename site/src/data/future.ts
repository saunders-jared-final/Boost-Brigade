export interface Item { title: string; body: string; size: 'S' | 'M' | 'L'; }
/** From the report conclusion (§7) and DESIGN_LOG Part 3. */
export const FUTURE: Record<string, Item[]> = {
  'Hardware': [
    { title: 'Stackable, independently driven boards', body: 'Test strings of more than three modules and a varying number of panels per shuffler. The biggest open question is scalability.', size: 'L' },
    { title: 'Rework U10’s isolator', body: 'Restore the top INA239 so VM1 no longer depends on the e-load.', size: 'S' },
    { title: 'Hardware over-current trip', body: 'COMP1/COMP3 with DAC3 references into HRTIM FLT4/FLT5 on the A phases.', size: 'M' },
    { title: 'Revisit GaN switches', body: 'The system favours high switching frequencies; 400 kHz gave marginal gains at higher losses with silicon.', size: 'L' },
    { title: 'Mechanical pass', body: 'Smaller heatsink, better fasteners, PCB reconfiguration, enclosure redesign; consider one board for MCU and Pi.', size: 'M' },
  ],
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
    { title: 'A sunny day with every panel connected', body: 'Module 1 produced ~0 A all afternoon on 20 Oct; the loop was only partly exercised against real panel dynamics. Log irradiance.', size: 'S' },
    { title: 'Other panel arrangements and applications', body: 'Dynamic configurations; non-solar uses (mining, computing, industrial power, batteries, solar car racing).', size: 'L' },
  ],
};
