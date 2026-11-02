/**
 * Project schedules for the Story page.
 *  - PLANNED: the proposal's 34-week team Gantt (17 Apr 2026), project week 1 = 23 Feb 2026.
 *  - CTRL_ACTUAL: the control stream as it happened (delivery report, appendix A).
 *  - HW_ACTUAL: the hardware stream as it happened (hardware report, appendix 1).
 */
export type Stream = 'ctrl' | 'hw' | 'both';
export interface GanttTask { label: string; start: string | number; end: string | number; stream: Stream; kind?: 'planned' | 'actual'; milestone?: string; note?: string; }

const WEEK1 = new Date(2026, 1, 23); // Monday 23 Feb 2026
/** Project week (1-based, from the proposal) or ISO date -> Date. A week number maps to its Monday; add .99 for its end. */
export function toDate(d: string | number): Date {
  if (typeof d === 'number') return new Date(WEEK1.getTime() + (d - 1) * 7 * 86400e3);
  const [y, m, day] = d.split('-').map(Number);
  return new Date(y, m - 1, day ?? 1);
}
export const AXIS = { start: '2026-02-16', end: '2026-11-01' };
export const SEMESTERS = [
  { label: 'Semester 1 (wk 1–13)', start: '2026-02-23', end: '2026-05-31', band: true },
  { label: 'mid-year break', start: '2026-06-01', end: '2026-07-26', band: false },
  { label: 'Semester 2 (wk 1–13)', start: '2026-07-27', end: '2026-10-25', band: true },
];

/** Proposal Gantt (appendix B of the proposal): a V1 → V2 → V3 board ladder plus an MPPT stage. */
export const PLANNED: GanttTask[] = [
  { label: 'Project set-up, supervisor meeting', start: 1, end: 2.99, stream: 'both', kind: 'planned', milestone: 'M1' },
  { label: 'Planning and literature review', start: 3, end: 7.99, stream: 'both', kind: 'planned' },
  { label: 'High-level system architecture', start: 8, end: 8.99, stream: 'both', kind: 'planned', milestone: 'M2' },
  { label: 'Shuffler V1: circuit design and control model', start: 9, end: 12.99, stream: 'ctrl', kind: 'planned' },
  { label: 'Shuffler V1: power circuit and hardware design', start: 9, end: 12.99, stream: 'hw', kind: 'planned' },
  { label: 'Documented simulation models / BOM', start: 12, end: 12.99, stream: 'both', kind: 'planned', milestone: 'M3' },
  { label: 'Unit test plans; V1 testing and report', start: 13, end: 14.99, stream: 'both', kind: 'planned', milestone: 'M4' },
  { label: 'Shuffler V2 and MPPT V1 ordered', start: 15, end: 15.99, stream: 'both', kind: 'planned' },
  { label: 'Shuffler pair control (V2) and MPPT V1 design', start: 16, end: 17.99, stream: 'ctrl', kind: 'planned', milestone: 'M5' },
  { label: 'PCB design: pair configuration and MPPT', start: 16, end: 17.99, stream: 'hw', kind: 'planned', milestone: 'M5' },
  { label: 'Subsystem test plan; V2 and MPPT V1 testing', start: 18, end: 19.99, stream: 'both', kind: 'planned', milestone: 'M6' },
  { label: 'Shuffler V3 and MPPT V2 ordered', start: 20, end: 20.99, stream: 'both', kind: 'planned' },
  { label: 'String control (V3) and MPPT V2 design', start: 21, end: 23.99, stream: 'ctrl', kind: 'planned', milestone: 'M7' },
  { label: 'PCB string configuration design', start: 21, end: 23.99, stream: 'hw', kind: 'planned', milestone: 'M7' },
  { label: 'System test plan and risk assessment', start: 24, end: 24.99, stream: 'both', kind: 'planned' },
  { label: 'System validation and integration testing', start: 25, end: 27.99, stream: 'both', kind: 'planned', milestone: 'M8' },
  { label: 'Buffer / contingency', start: 28, end: 31.99, stream: 'both', kind: 'planned' },
  { label: 'Final report and handover', start: 32, end: 32.99, stream: 'both', kind: 'planned', milestone: 'M9' },
  { label: 'Presentation preparation and delivery', start: 33, end: 34.99, stream: 'both', kind: 'planned', milestone: 'M10' },
];

export const CTRL_ACTUAL: GanttTask[] = [
  { label: 'Problem identification, proposal', start: '2026-02-23', end: '2026-03-22', stream: 'ctrl', milestone: 'wk 4' },
  { label: 'Literature: DPP and MPPT control strategies', start: '2026-03-09', end: '2026-04-12', stream: 'ctrl', milestone: 'wk 7' },
  { label: 'Analytical solution, classical methods', start: '2026-04-06', end: '2026-05-03', stream: 'ctrl', milestone: 'wk 10' },
  { label: 'Simulink plant model, progress report', start: '2026-04-27', end: '2026-05-31', stream: 'ctrl', milestone: 'wk 13' },
  { label: 'Break: N-module MIMO rework, MIL, SIL', start: '2026-06-08', end: '2026-07-26', stream: 'ctrl' },
  { label: 'Component selection, KiCad interface', start: '2026-07-27', end: '2026-08-23', stream: 'ctrl', milestone: 'wk 4' },
  { label: 'PCB order, assembly, enclosure', start: '2026-08-17', end: '2026-09-27', stream: 'ctrl', milestone: 'wk 9–10' },
  { label: 'Firmware, software, Pi pod', start: '2026-09-14', end: '2026-10-11', stream: 'ctrl', milestone: 'wk 11' },
  { label: 'Gain refinement, QSPICE integration', start: '2026-09-28', end: '2026-10-18', stream: 'ctrl', milestone: 'wk 12' },
  { label: 'Bench test', start: '2026-10-16', end: '2026-10-17', stream: 'both', milestone: '16 Oct' },
  { label: 'Solar test in the carpark', start: '2026-10-20', end: '2026-10-21', stream: 'both', milestone: '20 Oct' },
  { label: 'Post-processing, report, presentation', start: '2026-10-19', end: '2026-10-24', stream: 'ctrl', milestone: 'wk 13' },
];

export const HW_ACTUAL: GanttTask[] = [
  { label: 'Project set-up and literature review', start: '2026-02-23', end: '2026-04-19', stream: 'hw' },
  { label: 'System architecture', start: '2026-04-20', end: '2026-04-26', stream: 'hw', milestone: 'M2' },
  { label: 'PV model, topology comparison, shuffler models', start: '2026-04-27', end: '2026-05-31', stream: 'hw', milestone: 'M3' },
  { label: 'First PCB schematic and BOM (deferred)', start: '2026-06-01', end: '2026-06-14', stream: 'hw', note: 'inductor change and late controller interface' },
  { label: 'Sensor set and QSPICE schematic agreed with control', start: '2026-06-15', end: '2026-06-28', stream: 'both' },
  { label: 'PCB design, revisions, ordering', start: '2026-07-27', end: '2026-09-19', stream: 'hw', milestone: 'ordered 19 Sep' },
  { label: 'Parasitic model; snubber and HF capacitor order', start: '2026-09-20', end: '2026-09-30', stream: 'hw' },
  { label: 'Board assembly, bring-up, open-loop bench tests', start: '2026-10-04', end: '2026-10-16', stream: 'hw' },
  { label: 'Bench test', start: '2026-10-16', end: '2026-10-17', stream: 'both', milestone: '16 Oct' },
  { label: 'Live PV string test', start: '2026-10-20', end: '2026-10-21', stream: 'both', milestone: '20 Oct' },
  { label: 'Final report and presentation', start: '2026-10-19', end: '2026-10-25', stream: 'hw', milestone: 'wk 13' },
];

/** Both streams on one axis, ordered by start, with the hand-over points between them. */
export const COMBINED: GanttTask[] = [
  { label: 'Proposal and literature review (both)', start: '2026-02-23', end: '2026-04-12', stream: 'both' },
  { label: 'HW · PV model, topology comparison', start: '2026-04-20', end: '2026-05-31', stream: 'hw' },
  { label: 'CTRL · analytical model, Simulink plant', start: '2026-04-06', end: '2026-05-31', stream: 'ctrl' },
  { label: 'HW · first schematic, coupled inductor chosen', start: '2026-06-01', end: '2026-06-14', stream: 'hw' },
  { label: 'HAND-OVER · sensor set + QSPICE schematic', start: '2026-06-15', end: '2026-06-28', stream: 'both' },
  { label: 'CTRL · N-module MIMO rework, MIL, SIL', start: '2026-06-08', end: '2026-07-26', stream: 'ctrl' },
  { label: 'HW · PCB design, reviews, order (19 Sep)', start: '2026-07-27', end: '2026-09-19', stream: 'hw' },
  { label: 'CTRL · component selection, KiCad input', start: '2026-07-27', end: '2026-08-23', stream: 'ctrl' },
  { label: 'CTRL · firmware, pod, proto-board (28 Aug)', start: '2026-08-24', end: '2026-10-03', stream: 'ctrl' },
  { label: 'HW · parasitic model, snubber order', start: '2026-09-20', end: '2026-09-30', stream: 'hw' },
  { label: 'HAND-OVER · board assembled (4 Oct)', start: '2026-10-04', end: '2026-10-05', stream: 'both' },
  { label: 'Joint bring-up: 100 kHz, U10, inductor', start: '2026-10-06', end: '2026-10-15', stream: 'both' },
  { label: 'CTRL · gain refinement in QSPICE', start: '2026-10-08', end: '2026-10-18', stream: 'ctrl' },
  { label: 'Bench test (both)', start: '2026-10-16', end: '2026-10-17', stream: 'both', milestone: '16 Oct' },
  { label: 'Solar test (both)', start: '2026-10-20', end: '2026-10-21', stream: 'both', milestone: '20 Oct' },
  { label: 'Reports and presentation (both)', start: '2026-10-19', end: '2026-10-25', stream: 'both' },
];
export const COMBINED_LINKS = [
  { from: 1, to: 4, label: 'topology settled late in semester 1: the control model had to wait for it' },
  { from: 4, to: 5, label: 'the agreed QSPICE schematic and sensor set became the plant for the control rework' },
  { from: 6, to: 10, label: 'board ordered 19 Sep, assembled 4 Oct' },
  { from: 10, to: 11, label: 'from here on the two streams worked on one bench' },
];
