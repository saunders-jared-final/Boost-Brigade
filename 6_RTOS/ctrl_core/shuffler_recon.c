/*
 * shuffler_recon.c - module-current reconstruction (see header for the KCL)
 */
#include "shuffler_recon.h"

void recon_module_currents(const float IL[N_LEG], const float d[N_LEG], float IM[N_MOD])
{
    float itop[N_SHUF];
    float ibot[N_SHUF];
    float ic[N_SHUF];
    uint8_t k;
    uint8_t j;

    for (k = 0u; k < (uint8_t)N_SHUF; k++) {
        float ia = IL[2u * k];
        float ib = IL[2u * k + 1u];
        itop[k] = d[2u * k] * ia + d[2u * k + 1u] * ib;
        ic[k] = ia + ib;
        ibot[k] = ic[k] - itop[k];
    }

    /* module N (index N_MOD-1) is the reference; walk upward. With j = node-1
     * (0-based), node j+1 joins module j (index j-1, above) and module j+1
     * (index j, below): I[j-1] = I[j] + ic[j-1] - itop[j] - ibot[j-2]. */
    IM[(uint8_t)N_MOD - 1u] = 0.0f;
    for (j = (uint8_t)N_MOD - 1u; j >= 1u; j--) {
        float acc = IM[j] + ic[j - 1u];
        if (j < (uint8_t)N_SHUF) {
            acc -= itop[j]; /* shuffler with its top terminal at this node */
        }
        if (j >= 2u) {
            acc -= ibot[j - 2u]; /* shuffler with its bottom terminal at this node */
        }
        IM[j - 1u] = acc;
    }
}
