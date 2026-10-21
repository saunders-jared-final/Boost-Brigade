| phase | setup | kscale | signal | y0 | y_final | delta | ss err | rise 10-90 | t peak | overshoot | t settle 2% | t settle 5% | n | model | tau / zeta, wn | fit r2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| analytical | BENCH | 0.1 | ic2 | 0 | -2.52e-07 | -2.52e-07 | -1 | - | 5.6 ms | peak dev -0.00435 | 0 ms | 0 ms | 0 | nan | - | - |
| analytical | BENCH | 0.3 | ic2 | 0 | -2.91e-09 | -2.91e-09 | -1 | - | 1.7 ms | peak dev -0.00457 | 0 ms | 0 ms | 0 | nan | - | - |
| analytical | BENCH | 1.0 | ic2 | 0 | 5.52e-18 | 5.52e-18 | -1 | - | 0.4 ms | peak dev -0.00752 | 0 ms | 0 ms | 0 | nan | - | - |
| analytical | PV80 | 0.1 | ic2 | 0 | -2.53e-06 | -2.53e-06 | -1 | - | 6.7 ms | peak dev -0.0045 | 0 ms | 0 ms | 0 | nan | - | - |
| analytical | PV80 | 0.3 | ic2 | 0 | -8.12e-08 | -8.12e-08 | -1 | - | 2.1 ms | peak dev -0.00468 | 0 ms | 0 ms | 0 | nan | - | - |
| analytical | PV80 | 1.0 | ic2 | 0 | -4.47e-18 | -4.47e-18 | -1 | - | 0.4 ms | peak dev -0.00683 | 0 ms | 0 ms | 0 | nan | - | - |
| qspice | BENCH | 0.1 | ic2 | -0.00268 | 0.00455 | 0.00723 | -0.995 | - | 4.65 ms | peak dev -0.0381 | 0 ms | 0 ms | 0 | nan | - | - |
| qspice | BENCH | 0.3 | ic2 | -0.000966 | 0.00558 | 0.00654 | -0.994 | - | 2.16 ms | peak dev -0.0224 | 0 ms | 0 ms | 0 | nan | - | - |
| qspice | BENCH | 1.0 | ic2 | 0.000612 | 0.00511 | 0.0045 | -0.995 | - | 0.562 ms | peak dev -0.0249 | 0 ms | 0 ms | 0 | nan | - | - |
| qspice | PV80 | 0.1 | ic2 | 0.0385 | 0.064 | 0.0255 | -0.936 | - | 7.75 ms | peak dev -0.0505 | 0 ms | 0 ms | 0 | nan | - | - |
| qspice | PV80 | 0.3 | ic2 | 0.0395 | 0.0414 | 0.00189 | -0.959 | - | 17.1 ms | peak dev 0.0723 | 0 ms | 0 ms | 0 | nan | - | - |
| qspice | PV80 | 1.0 | ic2 | 0.0485 | 0.0268 | -0.0217 | -0.973 | - | 0.762 ms | peak dev 0.12 | 0 ms | 0 ms | 0 | nan | - | - |
| simulink | BENCH | 0.1 | ic2 | 0.0104 | 0.0063 | -0.0041 | -0.994 | - | 1.3 ms | peak dev -0.00726 | 0 ms | 0 ms | 0 | nan | - | - |
| simulink | BENCH | 0.3 | ic2 | 0.0114 | 0.00623 | -0.00519 | -0.994 | - | 1 ms | peak dev -0.0285 | 0 ms | 0 ms | 0 | nan | - | - |
| simulink | BENCH | 1.0 | ic2 | 0.00307 | 0.0156 | 0.0125 | -0.984 | - | 0.5 ms | peak dev -0.0371 | 0 ms | 0 ms | 0 | nan | - | - |
| simulink | PV80 | 0.1 | ic2 | 0.0019 | -0.00976 | -0.0117 | -1.01 | - | 6.8 ms | peak dev 0.0173 | 0 ms | 0 ms | 0 | nan | - | - |
| simulink | PV80 | 0.3 | ic2 | 0.00571 | -0.00967 | -0.0154 | -1.01 | - | 2.9 ms | peak dev 0.0187 | 0 ms | 0 ms | 0 | nan | - | - |
| simulink | PV80 | 1.0 | ic2 | 1.29e-08 | -0.00203 | -0.00203 | -1 | - | 2.1 ms | peak dev -0.0177 | 0 ms | 0 ms | 0 | nan | - | - |
| analytical | BENCH | 0.1 | vd2 | 0 | 1 | 1 | -2.32e-05 | 23.2 ms | 125 ms | 0.00161 % | 41.3 ms | 31.7 ms | 413 | first | tau 10.5 ms +- 0.0016 | 1 |
| analytical | BENCH | 0.3 | vd2 | 0 | 1 | 1 | -2.84e-07 | 7.61 ms | 57.9 ms | 2.3e-05 % | 13.6 ms | 10.4 ms | 136 | first | tau 3.42 ms +- 0.0032 | 1 |
| analytical | BENCH | 1.0 | vd2 | 0 | 1 | 1 | -8.88e-16 | 2.04 ms | 34.2 ms | 4.44e-14 % | 3.8 ms | 2.9 ms | 38 | first | tau 0.909 ms +- 0.0046 | 1 |
| analytical | PV80 | 0.1 | vd2 | 0 | 1 | 1 | -0.00017 | 28.4 ms | 125 ms | 0.0105 % | 50.6 ms | 38.8 ms | 506 | first | tau 12.9 ms +- 0.0019 | 1 |
| analytical | PV80 | 0.3 | vd2 | 0 | 1 | 1 | -5.04e-06 | 9.35 ms | 57.9 ms | 0.000371 % | 16.7 ms | 12.8 ms | 167 | first | tau 4.21 ms +- 0.0033 | 1 |
| analytical | PV80 | 1.0 | vd2 | 0 | 1 | 1 | -5.55e-16 | 2.59 ms | 43.5 ms | 2.22e-14 % | 4.8 ms | 3.6 ms | 48 | first | tau 1.16 ms +- 0.0045 | 1 |
| qspice | BENCH | 0.1 | vd2 | -0.00198 | 0.973 | 0.975 | -0.0274 | 19.8 ms | 39.6 ms | 1.22 % | 30.7 ms | 25.8 ms | 308 | first | tau 9.72 ms +- 0.012 | 1 |
| qspice | BENCH | 0.3 | vd2 | -0.00239 | 1 | 1 | -0.000163 | 6.55 ms | 27 ms | 0.282 % | 11.9 ms | 8.86 ms | 119 | first | tau 2.84 ms +- 0.01 | 1 |
| qspice | BENCH | 1.0 | vd2 | 0.00125 | 0.997 | 0.996 | -0.00274 | 1.27 ms | 3.76 ms | 0.677 % | 2.16 ms | 1.56 ms | 22 | first | tau 0.549 ms +- 0.0088 | 0.99 |
| qspice | PV80 | 0.1 | vd2 | -0.00132 | 0.949 | 0.95 | -0.0514 | 22.5 ms | 39.6 ms | 1.2 % | 32.1 ms | 28.4 ms | 321 | first | tau 12.4 ms +- 0.022 | 1 |
| qspice | PV80 | 0.3 | vd2 | -3.97e-05 | 0.998 | 0.998 | -0.00197 | 8.7 ms | 28.3 ms | 1.71 % | 15.2 ms | 11.5 ms | 152 | first | tau 3.71 ms +- 0.018 | 1 |
| qspice | PV80 | 1.0 | vd2 | 0.00637 | 1 | 0.995 | 0.000899 | 1.91 ms | 8.46 ms | 4.18 % | 8.46 ms | 2.46 ms | 85 | first | tau 0.77 ms +- 0.017 | 0.99 |
| simulink | BENCH | 0.1 | vd2 | -0.00134 | 1 | 1 | 0.00137 | 22.9 ms | 81 ms | 0.0172 % | 41.4 ms | 31.4 ms | 414 | first | tau 10.1 ms +- 0.01 | 1 |
| simulink | BENCH | 0.3 | vd2 | -0.0016 | 1 | 1 | 0.00102 | 6.89 ms | 24 ms | 0.0558 % | 12.4 ms | 9.4 ms | 124 | first | tau 2.97 ms +- 0.01 | 1 |
| simulink | BENCH | 1.0 | vd2 | 0.00172 | 1 | 0.998 | -0.000116 | 0.759 ms | 1 ms | 8.79 % | 2.7 ms | 2.3 ms | 27 | first | tau 0.404 ms +- 0.0085 | 0.96 |
| simulink | PV80 | 0.1 | vd2 | 6.95e-05 | 0.999 | 0.999 | -0.00109 | 26 ms | 89 ms | 0.00309 % | 45.5 ms | 35.3 ms | 455 | first | tau 11.6 ms +- 0.0094 | 1 |
| simulink | PV80 | 0.3 | vd2 | 0.000209 | 1 | 1 | -4.92e-05 | 8.06 ms | 29.1 ms | 0.00481 % | 14.2 ms | 10.9 ms | 142 | first | tau 3.47 ms +- 0.01 | 1 |
| simulink | PV80 | 1.0 | vd2 | 0 | 1 | 1 | 0.000508 | 0.894 ms | 17 ms | 0.156 % | 3 ms | 2.4 ms | 30 | first | tau 0.562 ms +- 0.007 | 0.98 |
