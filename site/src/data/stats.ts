import { repoUrl } from '../lib/site';
/** Headline numbers. Every value traces to 8_Results/analysis/REPORT.md §7 (computed findings). */
export const STATS = [
  { value: '±10 mV', label: 'module-voltage balance held by the closed loop across 22 settled segments, 200–400 kHz, bench and sun', evidence: 'REPORT §7 finding 2', href: repoUrl('8_Results/analysis/REPORT.md') },
  { value: '99 W · 10.6 Wh', label: 'peak power and energy returned to a 61 V load over 36 min with the top panel shaded to ~0 A', evidence: 'REPORT §7 finding 7', href: repoUrl('8_Results/analysis/REPORT.md') },
  { value: '1.2 %', label: 'agreement between the averaged model’s DC gain −V̄ and open-loop duty steps on hardware', evidence: 'REPORT §7 finding 1', href: repoUrl('8_Results/analysis/REPORT.md') },
  { value: '3 %', label: 'QSPICE switching ripple vs the closed-form law V̄ / 2f(L+M) at 200, 300 and 400 kHz', evidence: 'REPORT §7 finding 8', href: repoUrl('8_Results/analysis/REPORT.md') },
];
