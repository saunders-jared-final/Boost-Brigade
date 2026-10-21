| phase | setup | kscale | signal | y0 | y_final | delta | ss err | rise 10-90 | t peak | overshoot | t settle 2% | t settle 5% | n | model | tau / zeta, wn | fit r2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hardware | PV80 | 0.1 | Pstr | 97.4 | 95.6 | -1.78 | - | - | 3.99e+04 ms | peak dev -16.6 | 4e+04 ms | 4e+04 ms | 1816 | nan | - | - |
| hardware | PV80 | 0.1 | Pstr | 74 | 32.9 | -41.2 | - | 2.17e+04 ms | 2.59e+04 ms | 8.87 % | 2.19e+04 ms | 2.19e+04 ms | 991 | first | tau 1.19e+04 ms +- 6.3e+02 | 0.46 |
| hardware | PV80 | 0.1 | Pstr | 30.5 | 20.4 | -10.1 | - | 2.66e+04 ms | 3.97e+04 ms | 4.01 % | 3.09e+04 ms | 3.09e+04 ms | 1405 | first | tau 1.14e+04 ms +- 1.2e+02 | 0.97 |
| hardware | PV80 | 0.2 | Pstr | 20.9 | 12.8 | -8.07 | - | 2.21e+03 ms | 6.06e+03 ms | 7.02 % | 2.4e+03 ms | 2.4e+03 ms | 109 | second | zeta 0.88, wn 0.223 Hz | 0.98 |
| hardware | PV80 | 0.2 | Pstr | 108 | 93.2 | -14.9 | - | 780 ms | 5.66e+03 ms | 194 % | 1.9e+04 ms | 1.9e+04 ms | 863 | first | tau 847 ms +- 1.4e+02 | 0.19 |
| hardware | PV80 | 0.2 | Pstr | 103 | 138 | 35.1 | - | 3.44e+03 ms | 6.03e+03 ms | 15.3 % | 2.06e+04 ms | 2.06e+04 ms | 936 | second | zeta 0.34, wn 0.0859 Hz | 0.75 |
| hardware | PV80 | 0.2 | Pstr | 127 | 88.6 | -38 | - | 1.41e+03 ms | 1e+04 ms | 0.859 % | 1.23e+03 ms | 1.23e+03 ms | 56 | second | zeta 0.64, wn 0.198 Hz | 0.88 |
| hardware | PV80 | 0.2 | Pstr | 156 | 111 | -44.8 | - | 190 ms | 1.2e+04 ms | 13.4 % | 1.2e+04 ms | 1.2e+04 ms | 545 | first | tau 49.1 ms +- 7.2 | 0.11 |
| hardware | PV80 | 0.2 | Pstr | 107 | 102 | -4.88 | - | 598 ms | 2.82e+03 ms | 170 % | 1.06e+04 ms | 1.06e+04 ms | 480 | second | zeta 0.11, wn 0.174 Hz | 0.33 |
| hardware | PV80 | 0.2 | Pstr | 111 | 109 | -1.48 | - | - | 2.87e+03 ms | peak dev -2.83 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | Pstr | 108 | 116 | 8.06 | - | 1.79e+04 ms | 3.99e+04 ms | 2.9 % | 2.31e+04 ms | 2.31e+04 ms | 1048 | second | zeta 0.39, wn 0.016 Hz | 0.93 |
| hardware | PV80 | 0.2 | Pstr | 47.1 | 18.4 | -28.7 | - | 5.86e+03 ms | 1.3e+04 ms | 0.428 % | 5.48e+03 ms | 5.48e+03 ms | 248 | first | tau 3.62e+03 ms +- 39 | 0.99 |
| hardware | PV80 | 0.3 | Pstr | 2.65 | 36.6 | 34 | - | 13.9 ms | 3.86e+03 ms | 411 % | 1.89e+04 ms | 1.46e+04 ms | 856 | second | zeta 0.05, wn 0.0661 Hz | 0.58 |
| hardware | PV80 | 0.3 | Pstr | 36.8 | 33.7 | -3.13 | - | 1.39e+04 ms | 1.42e+04 ms | 13.1 % | 1.8e+04 ms | 1.8e+04 ms | 817 | second | zeta 0.05, wn 0.0704 Hz | 0.62 |
| hardware | PV80 | 0.3 | Pstr | 28.8 | 174 | 145 | - | 855 ms | 1.1e+04 ms | 0.0826 % | 3.26e+03 ms | 3.26e+03 ms | 147 | second | zeta 0.58, wn 0.103 Hz | 0.91 |
| qspice | PV80 | 0.1 | Pstr | 237 | 210 | -27.1 | - | 0 ms | 0.05 ms | 6.24 % | 6.35 ms | 0.15 ms | 64 | first | tau 0.0013 ms +- - | -3.4e-10 |
| qspice | PV80 | 0.3 | Pstr | 237 | 210 | -27 | - | 0 ms | 0.0616 ms | 7.43 % | 3.26 ms | 0.162 ms | 33 | first | tau 0.001 ms +- - | -7.2e-12 |
| qspice | PV80 | 1.0 | Pstr | 237 | 210 | -26.9 | - | 0 ms | 0.0735 ms | 6.09 % | 0.673 ms | 0.173 ms | 7 | first | tau 0.00101 ms +- - | -1.4e-12 |
| simulink | PV80 | 0.1 | Pstr | 265 | 235 | -29.8 | - | <= 0 ms | <= 0 ms | 1.66 % | <= 0 ms | <= 0 ms | 1 | first | tau 0.001 ms +- - | -1.5e+02 |
| simulink | PV80 | 0.3 | Pstr | 265 | 235 | -29.8 | - | <= 0 ms | <= 0 ms | 1.66 % | <= 0 ms | <= 0 ms | 1 | first | tau 0.001 ms +- - | -1.7e+02 |
| simulink | PV80 | 1.0 | Pstr | 265 | 235 | -29.8 | - | <= 0 ms | <= 0 ms | 1.66 % | <= 0 ms | <= 0 ms | 1 | first | tau 0.001 ms +- - | -1.7e+02 |
| hardware | PV80 | 0.1 | VM3 | 20.3 | 20.3 | 0 | - | - | 1.18e+03 ms | peak dev 0.01 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.1 | VM3 | 20.3 | 20.3 | 0 | - | - | 864 ms | peak dev 0.02 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.1 | VM3 | 20.3 | 20.3 | 0 | - | - | 3.66e+04 ms | peak dev -0.02 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | VM3 | 20.6 | 20.4 | -0.125 | - | - | 215 ms | peak dev 0.135 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | VM3 | 21.9 | 20.6 | -1.33 | - | 0.779 ms | 1.42e+04 ms | 1.5 % | 2.23e+03 ms | 2.23e+03 ms | 106 | second | zeta 0.63, wn 0.113 Hz | 0.85 |
| hardware | PV80 | 0.2 | VM3 | 20.3 | 20.3 | 0 | - | - | 1.09e+04 ms | peak dev -0.02 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | VM3 | 20.3 | 20.3 | 0 | - | - | 7.33e+03 ms | peak dev 0.03 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | VM3 | 20.3 | 20.3 | 0 | - | - | 4.73e+03 ms | peak dev -0.05 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | VM3 | 20.3 | 20.3 | 0 | - | - | 3.39e+03 ms | peak dev 0.01 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | VM3 | 20.3 | 20.3 | 0 | - | - | 1.03e+03 ms | peak dev -0.02 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | VM3 | 20.3 | 20.3 | 0 | - | - | 8.56e+03 ms | peak dev 0.01 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | VM3 | 20.3 | 20.3 | 0 | - | - | 846 ms | peak dev -0.02 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | VM3 | 20.5 | 20.4 | -0.1 | - | - | 21.2 ms | peak dev 0.1 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.3 | VM3 | 22.6 | 22.2 | -0.34 | - | 72.6 ms | 2.36e+03 ms | 547 % | 2e+04 ms | 2e+04 ms | 907 | first | tau 706 ms +- 2.8e+02 | 0.056 |
| hardware | PV80 | 0.3 | VM3 | 22.2 | 22.2 | -0.03 | - | - | 1.87e+03 ms | peak dev -1.85 | 1.76e+04 ms | 1.76e+04 ms | 798 | nan | - | - |
| hardware | PV80 | 0.3 | VM3 | 22.2 | 20.4 | -1.89 | - | 466 ms | 8.44e+03 ms | 1.06 % | 1.96e+03 ms | 1.96e+03 ms | 89 | second | zeta 0.62, wn 0.141 Hz | 0.88 |
| qspice | PV80 | 0.1 | VM3 | 19.9 | 19.9 | -0.0652 | - | - | 0.55 ms | peak dev -0.277 | 0 ms | 0 ms | 0 | nan | - | - |
| qspice | PV80 | 0.3 | VM3 | 19.9 | 19.9 | -0.00777 | - | - | 0.562 ms | peak dev -0.328 | 1.36 ms | 1.36 ms | 14 | nan | - | - |
| qspice | PV80 | 1.0 | VM3 | 19.9 | 19.9 | -0.0127 | - | - | 0.173 ms | peak dev -0.312 | 0.373 ms | 0.373 ms | 4 | nan | - | - |
| simulink | PV80 | 0.1 | VM3 | 20.5 | 20.5 | -0.00379 | - | - | 0.1 ms | peak dev -0.105 | 0 ms | 0 ms | 0 | nan | - | - |
| simulink | PV80 | 0.3 | VM3 | 20.5 | 20.5 | -0.00374 | - | - | 0.1 ms | peak dev -0.105 | 0 ms | 0 ms | 0 | nan | - | - |
| simulink | PV80 | 1.0 | VM3 | 20.5 | 20.5 | -0.00309 | - | - | 0.1 ms | peak dev -0.105 | 0 ms | 0 ms | 0 | nan | - | - |
| analytical | PV80 | 0.1 | id2 | 0 | 1.73 | 1.73 | - | 0.235 ms | 125 ms | 0.00104 % | 18.9 ms | 6.7 ms | 189 | first | tau 0.0781 ms +- 0.012 | 0.75 |
| analytical | PV80 | 0.3 | id2 | 0 | 1.73 | 1.73 | - | 0.228 ms | 57.9 ms | 3.82e-05 % | 6.1 ms | 2.1 ms | 61 | first | tau 0.0786 ms +- 0.0095 | 0.91 |
| analytical | PV80 | 1.0 | id2 | 0 | 1.73 | 1.73 | - | 0.213 ms | 42.9 ms | 0 % | 1.6 ms | 0.5 ms | 16 | first | tau 0.0786 ms +- 0.0041 | 0.98 |
| hardware | PV80 | 0.1 | id2 | -1.33 | -1.33 | 0.005 | - | - | 3.4e+04 ms | peak dev -0.457 | 3.99e+04 ms | 3.99e+04 ms | 1809 | nan | - | - |
| hardware | PV80 | 0.1 | id2 | -1.06 | -0.385 | 0.68 | - | 2.76e+03 ms | 2.71e+04 ms | 71 % | 2.71e+04 ms | 2.71e+04 ms | 1231 | first | tau 1.13e+04 ms +- 1.1e+03 | 0.17 |
| hardware | PV80 | 0.1 | id2 | -0.329 | -0.161 | 0.168 | - | - | 876 ms | peak dev -0.448 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | id2 | 0.141 | 0.153 | 0.012 | - | - | 2.09e+03 ms | peak dev 0.141 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | id2 | 0.131 | -0.711 | -0.842 | - | 0.637 ms | 1.14e+04 ms | 44.7 % | 2.07e+04 ms | 2.07e+04 ms | 985 | first | tau 2.45e+03 ms +- 2.1e+02 | 0.48 |
| hardware | PV80 | 0.2 | id2 | -0.703 | -0.528 | 0.174 | - | - | 5.55e+03 ms | peak dev 0.526 | 1.77e+04 ms | 1.77e+04 ms | 804 | nan | - | - |
| hardware | PV80 | 0.2 | id2 | -0.699 | -0.893 | -0.194 | - | - | 35.4 ms | peak dev 0.437 | 2.8e+04 ms | 2.8e+04 ms | 1271 | nan | - | - |
| hardware | PV80 | 0.2 | id2 | -1.46 | 2.22 | 3.68 | - | 179 ms | 9.38e+03 ms | 10.3 % | 1.2e+04 ms | 1.2e+04 ms | 544 | second | zeta 0.05, wn 0.0538 Hz | 0.64 |
| hardware | PV80 | 0.2 | id2 | -1.52 | -1.63 | -0.109 | - | - | 2.68e+03 ms | peak dev -0.447 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | id2 | -1.58 | -1.56 | 0.0255 | - | - | 8.2e+03 ms | peak dev 0.454 | 1.05e+04 ms | 1.05e+04 ms | 479 | nan | - | - |
| hardware | PV80 | 0.2 | id2 | -1.61 | -1.66 | -0.0485 | - | - | 9.99e+03 ms | peak dev 0.506 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | id2 | -1.66 | -1.75 | -0.087 | - | - | 693 ms | peak dev 0.488 | 3.41e+04 ms | 3.41e+04 ms | 1550 | nan | - | - |
| hardware | PV80 | 0.2 | id2 | -0.487 | -0.236 | 0.252 | - | - | 417 ms | peak dev -0.542 | 1.14e+04 ms | 1.14e+04 ms | 519 | nan | - | - |
| hardware | PV80 | 0.3 | id2 | 0.152 | 0.147 | -0.005 | - | - | 4.13e+03 ms | peak dev -0.135 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.3 | id2 | 0.149 | 0.138 | -0.0115 | - | - | 1.07e+04 ms | peak dev 0.168 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.3 | id2 | 0.131 | 0.133 | 0.002 | - | - | 8.59e+03 ms | peak dev -0.138 | 0 ms | 0 ms | 0 | nan | - | - |
| qspice | PV80 | 0.1 | id2 | -0.313 | 1.46 | 1.77 | - | 0.137 ms | 36.6 ms | 0.541 % | 15.6 ms | 3.15 ms | 157 | first | tau 0.0659 ms +- 0.0068 | 0.65 |
| qspice | PV80 | 0.3 | id2 | -0.327 | 1.47 | 1.8 | - | 0.14 ms | 23.9 ms | 0.474 % | 7.46 ms | 2.16 ms | 75 | first | tau 0.0663 ms +- 0.0084 | 0.63 |
| qspice | PV80 | 1.0 | id2 | -0.329 | 1.47 | 1.8 | - | 0.0896 ms | 6.77 ms | 1.18 % | 0.873 ms | 0.273 ms | 9 | first | tau 0.0639 ms +- 0.0054 | 0.93 |
| simulink | PV80 | 0.1 | id2 | -3.83e-06 | 1.92 | 1.92 | - | <= 0 ms | <= 0 ms | 11.3 % | <= 0 ms | <= 0 ms | 2 | first | tau 0.00111 ms +- - | 0.99 |
| simulink | PV80 | 0.3 | id2 | -1.15e-05 | 1.92 | 1.92 | - | <= 0 ms | <= 0 ms | 11.3 % | <= 0 ms | <= 0 ms | 2 | first | tau 0.00111 ms +- - | 0.99 |
| simulink | PV80 | 1.0 | id2 | 1.58e-12 | 1.92 | 1.92 | - | <= 0 ms | <= 0 ms | 11.2 % | <= 0 ms | <= 0 ms | 2 | first | tau 0.00112 ms +- - | 0.99 |
| analytical | PV80 | 0.1 | vd2 | 0 | 9.05e-05 | 9.05e-05 | - | - | 0.3 ms | peak dev 0.455 | 20.3 ms | 20.3 ms | 203 | nan | - | - |
| analytical | PV80 | 0.3 | vd2 | 0 | 2.87e-06 | 2.87e-06 | - | - | 0.3 ms | peak dev 0.448 | 6.8 ms | 6.8 ms | 68 | nan | - | - |
| analytical | PV80 | 1.0 | vd2 | 0 | 2.22e-16 | 2.22e-16 | - | - | 0.2 ms | peak dev 0.448 | 2.1 ms | 2.1 ms | 21 | nan | - | - |
| hardware | PV80 | 0.1 | vd2 | -0.01 | 0 | 0.01 | - | - | 2.42e+04 ms | peak dev 0.07 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.1 | vd2 | -0.01 | 0 | 0.01 | - | - | 864 ms | peak dev -0.05 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.1 | vd2 | -0.01 | 0 | 0.01 | - | - | 5.79e+03 ms | peak dev 0.07 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | vd2 | -0.23 | 0.06 | 0.29 | - | 2.54e+03 ms | 5.97e+03 ms | 20.7 % | 2.66e+03 ms | 2.66e+03 ms | 121 | first | tau 4.66e+03 ms +- 7.5e+02 | 0.86 |
| hardware | PV80 | 0.2 | vd2 | 0.035 | -0.25 | -0.285 | - | 107 ms | 3.4e+03 ms | 17.5 % | 2.09e+04 ms | 2.09e+04 ms | 994 | second | zeta 0.61, wn 0.111 Hz | 0.78 |
| hardware | PV80 | 0.2 | vd2 | 0 | 0 | 0 | - | - | 463 ms | peak dev 0.06 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | vd2 | 0 | 0 | 0 | - | - | 4.24e+03 ms | peak dev 0.08 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | vd2 | 0 | 0 | 0 | - | - | 4.73e+03 ms | peak dev 0.14 | 4.73e+03 ms | 4.73e+03 ms | 215 | nan | - | - |
| hardware | PV80 | 0.2 | vd2 | -0.01 | 0 | 0.01 | - | - | 1.05e+03 ms | peak dev 0.06 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | vd2 | 0.005 | 0 | -0.005 | - | - | 5.78e+03 ms | peak dev 0.07 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | vd2 | 0 | 0 | 0 | - | - | 8.73e+03 ms | peak dev -0.05 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | vd2 | 0.01 | 0 | -0.01 | - | - | 2.53e+04 ms | peak dev 0.06 | 0 ms | 0 ms | 0 | nan | - | - |
| hardware | PV80 | 0.2 | vd2 | -0.21 | -0.11 | 0.1 | - | 4.1e+03 ms | 9.05e+03 ms | 60 % | 1.21e+04 ms | 1.21e+04 ms | 548 | first | tau 4.57e+03 ms +- 6.3e+02 | 0.51 |
| hardware | PV80 | 0.3 | vd2 | 0 | -0.02 | -0.02 | - | - | 1.16e+04 ms | peak dev 0.25 | 1.99e+04 ms | 1.99e+04 ms | 902 | nan | - | - |
| hardware | PV80 | 0.3 | vd2 | -0.1 | -0.03 | 0.07 | - | - | 1.78e+04 ms | peak dev -5.6 | 1.8e+04 ms | 1.8e+04 ms | 817 | nan | - | - |
| hardware | PV80 | 0.3 | vd2 | -5.8 | 0.03 | 5.83 | - | 466 ms | 8.44e+03 ms | 0.515 % | 1.96e+03 ms | 1.96e+03 ms | 89 | second | zeta 0.62, wn 0.141 Hz | 0.88 |
| qspice | PV80 | 0.1 | vd2 | 0.957 | 1.03 | 0.0766 | - | - | 0.55 ms | peak dev 0.322 | 16 ms | 16 ms | 161 | nan | - | - |
| qspice | PV80 | 0.3 | vd2 | 1 | 1 | 0.000284 | - | - | 0.562 ms | peak dev 0.392 | 7.66 ms | 7.66 ms | 77 | nan | - | - |
| qspice | PV80 | 1.0 | vd2 | 1 | 1 | 0.00221 | - | - | 0.173 ms | peak dev 0.373 | 1.77 ms | 1.77 ms | 18 | nan | - | - |
| simulink | PV80 | 0.1 | vd2 | 6.95e-05 | 0.00149 | 0.00142 | - | - | 0.1 ms | peak dev 0.12 | 3 ms | 3 ms | 30 | nan | - | - |
| simulink | PV80 | 0.3 | vd2 | 0.000209 | 0.00116 | 0.000947 | - | - | 0.1 ms | peak dev 0.12 | 1.6 ms | 1.6 ms | 16 | nan | - | - |
| simulink | PV80 | 1.0 | vd2 | 0 | -0.00209 | -0.00209 | - | - | 0.6 ms | peak dev 0.124 | 1.2 ms | 1.2 ms | 12 | nan | - | - |
