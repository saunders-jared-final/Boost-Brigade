/*
 * shuffler_recon.h - module-current reconstruction from shuffler currents
 *
 * The Version 0 board measures module voltages (INA239, bus only) and the
 * four inductor currents (TMCS1126) but no module or string current. Module
 * currents follow from KCL at the inter-module nodes once the averaged
 * converter terminal currents are known:
 *
 *   shuffler k (1-based) spans modules k, k+1: top terminal at node k,
 *   midpoint at node k+1, bottom terminal at node k+2 (node 1 = PV1+ ...
 *   node N+1 = string negative). Per leg with duty d and physical inductor
 *   current i (positive INTO the midpoint): the top rail supplies d*i, the
 *   bottom rail (1-d)*i, and the midpoint receives iA + iB.
 *
 *   SIGN CONVENTION of the control stack (from the Simulink identification):
 *   IL = {ILA, ILB, ...} with ILA positive INTO the midpoint and ILB positive
 *   OUT of it, so that ILA + ILB is the circulating (phase-to-phase) current
 *   the controller nulls and ILA - ILB is the shuffled (midpoint) current the
 *   supervisor rates. Hence here iA = ILA, iB = -ILB. On the PCB the B-phase
 *   hall sensors are mounted the other way round, i.e. their raw output IS
 *   this convention.
 *
 *   KCL at node j (2..N), module current I_j positive in the generating
 *   direction (from node j+1 up to node j):
 *       I_{j-1} = I_j + ic_{j-1} - itop_j - ibot_{j-2}
 *   (terms whose shuffler index is outside 1..N-1 are zero).
 *
 * The string current is a common offset on all I_j and is NOT observable, so
 * the result is RELATIVE: IM[N_MOD-1] = 0 by definition. The supervisor only
 * uses max(IM) - IM, which is offset-free. Simulink validation: the true
 * plant module currents minus this output must be the same number for all
 * modules (= the true current of module N).
 *
 * Pure portable C99, float32, no state.
 */
#ifndef SHUFFLER_RECON_H
#define SHUFFLER_RECON_H

#include <stdint.h>

#include "params.h"

/* IL = {ILA1, ILB1, ILA2, ILB2, ...}, d = {dA1, dB1, dA2, dB2, ...}, IM[N_MOD] out */
void recon_module_currents(const float IL[N_LEG], const float d[N_LEG], float IM[N_MOD]);

#endif /* SHUFFLER_RECON_H */
