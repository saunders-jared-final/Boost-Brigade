| source | vd1/uc1 | vd2/uc2 | ic1/ud1 | ic2/ud2 | vd1/ud1 (cross) | cond(G) | note |
|---|---|---|---|---|---|---|---|
| analytical PV80, averaged R 61 mOhm (Simulink) | -40.4 | -40.4 | 672.1 | 672.1 | 0.0 | 16.8 | modes [('6973 Hz', 'z 0.36'), ('9296 Hz', 'z 0.27')] |
| analytical PV80, switching R 0.29 ohm (200 kHz) | -38.2 | -38.2 | 141.4 | 141.4 | 0.0 | 3.8 | modes [] |
| analytical PV80, switching R 1.72 ohm (400 kHz) | -29.2 | -29.2 | 23.8 | 23.8 | 0.0 | 1.4 | modes [] |
| analytical BENCH QSPICE point (all CC), R 0.29 ohm | -46.6 | -46.7 | 160.7 | 160.7 | 0.0 | 3.5 | modes [] |
| analytical BENCH ch1 CC / ch2,3 CV, R 0.29 ohm | -15.2 | -7.2 | 155.2 | 172.4 | 0.0 | 26.3 | modes [('20889 Hz', 'z 0.93')] |
| identified sps-params-2.20261015-1950-3mod-qspice200-bench | -46.3 | -46.9 | 142.5 | 139.0 | -24.7 | 3.2 | diag(kI) M^-1 of the gain set |
| identified sps-params-2.20261011-1634-3mod-qspice | -37.4 | -37.7 | 256.0 | 215.8 | 7.3 | 7.4 | diag(kI) M^-1 of the gain set |
| identified sps-params-2.20261015-1754-3mod-simulink-bench | -46.0 | -47.4 | 741.5 | 742.5 | -0.6 | 16.1 | diag(kI) M^-1 of the gain set |
| identified sps-params-2.20261016-1628-3mod-qspice300-bench | -45.3 | -45.7 | 58.8 | 56.8 | -17.0 | 1.6 | diag(kI) M^-1 of the gain set |
| identified sps-params-2.20261016-1751-3mod-qspice400-bench | -41.6 | -42.9 | 23.5 | 23.0 | -14.4 | 2.3 | diag(kI) M^-1 of the gain set |
| identified sps-params-2.20261016-1804-3mod-qspice400d1-bench | -42.7 | -43.8 | 26.2 | 26.0 | -10.3 | 1.9 | diag(kI) M^-1 of the gain set |

Rows [vd1 vd2 ic1 ic2], columns [uc1 uc2 ud1 ud2]; V per unit modal duty, A per unit modal duty.
