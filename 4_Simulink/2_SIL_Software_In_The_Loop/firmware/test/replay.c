/*
 * replay.c - golden-vector replay harness for the shuffler control stack
 *
 * Usage:
 *   replay <golden_inputs.csv> <golden_expected.csv>
 *   replay --selftest [outdir]
 *
 * Golden mode feeds the recorded per-50us-tick inputs through stack_step()
 * and compares every output tick against the MIL expectation. Acceptance
 * gates (from the SIL task spec):
 *   duties dA1..dB3          max abs error < 1e-3
 *   rv1..rv3, beta, Iref     max abs error < 1e-2
 *   MPPT state code          exact match
 *   stress, Pav              report-only (printed, never gated)
 * A per-channel max-error report is always printed; exit is nonzero on any
 * gate failure.
 *
 * CSV format (produced by firmware/matlab/export_golden.m): first line is a
 * header of comma-separated column names; columns are matched BY NAME, order
 * free. Inputs: t (optional), VM1..VM4, IM1..IM4, ILA1,ILB1,ILA2,ILB2,ILA3,
 * ILB3, V_String, I_String, Vref1..Vref3, en_sup, en_mppt. Expected: t
 * (optional), dA1,dB1,dA2,dB2,dA3,dB3, rv1..rv3, beta, Iref, state, and
 * optionally stress, Pav.
 *
 * --selftest generates a deterministic synthetic run, writes both CSVs, then
 * replays them expecting bit-exact agreement (validates the harness plumbing
 * and the %.9g float round-trip before real goldens exist).
 *
 * Host-only test code: stdio/double allowed here (core/ stays pure).
 */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "params.h"
#include "stack.h"

#define MAX_COLS 64
#define LINE_BUF 8192

/* ---------------------------------------------------------------- CSV --- */

typedef struct {
    FILE *f;
    const char *path;
    long line_no;
    int ncols;
    char header[LINE_BUF];
    char *names[MAX_COLS];
    char buf[LINE_BUF];
    float vals[MAX_COLS];
} csv_t;

/* returns field count, or -1 if the line holds more than maxf fields */
static int split_line(char *line, char **fields, int maxf)
{
    int n = 0;
    char *p = line;
    line[strcspn(line, "\r\n")] = '\0';
    while (n < maxf) {
        fields[n++] = p;
        p = strchr(p, ',');
        if (p == NULL) {
            break;
        }
        *p++ = '\0';
    }
    if (p != NULL) {
        return -1; /* text (more fields) left after maxf fields */
    }
    return n;
}

static void csv_close(csv_t *c)
{
    if (c->f != NULL) {
        fclose(c->f);
        c->f = NULL;
    }
}

static int csv_open(csv_t *c, const char *path)
{
    c->path = path;
    c->line_no = 0;
    c->f = fopen(path, "r");
    if (c->f == NULL) {
        fprintf(stderr, "error: cannot open %s\n", path);
        return -1;
    }
    if (fgets(c->header, LINE_BUF, c->f) == NULL) {
        fprintf(stderr, "error: %s: empty file\n", path);
        csv_close(c);
        return -1;
    }
    if (strchr(c->header, '\n') == NULL && !feof(c->f)) {
        fprintf(stderr, "error: %s: header line longer than %d bytes\n", path, LINE_BUF - 1);
        csv_close(c);
        return -1;
    }
    c->line_no = 1;
    c->ncols = split_line(c->header, c->names, MAX_COLS);
    if (c->ncols < 1) {
        fprintf(stderr, "error: %s: bad header (or more than %d columns)\n", path, MAX_COLS);
        csv_close(c);
        return -1;
    }
    return 0;
}

static int csv_col(const csv_t *c, const char *name)
{
    int i;
    for (i = 0; i < c->ncols; i++) {
        if (strcmp(c->names[i], name) == 0) {
            return i;
        }
    }
    return -1;
}

/* 1 = row read, 0 = clean EOF, -1 = parse error */
static int csv_row(csv_t *c)
{
    char *fields[MAX_COLS];
    int n, i;
    do { /* skip blank lines (e.g. trailing newline) */
        if (fgets(c->buf, LINE_BUF, c->f) == NULL) {
            return 0;
        }
        c->line_no++;
    } while (c->buf[0] == '\0' || c->buf[0] == '\n' || c->buf[0] == '\r');
    if (strchr(c->buf, '\n') == NULL && !feof(c->f)) {
        fprintf(stderr, "error: %s:%ld: line longer than %d bytes\n", c->path, c->line_no,
                LINE_BUF - 1);
        return -1;
    }
    n = split_line(c->buf, fields, MAX_COLS);
    if (n < 0) {
        fprintf(stderr, "error: %s:%ld: more than %d columns\n", c->path, c->line_no, MAX_COLS);
        return -1;
    }
    if (n != c->ncols) {
        fprintf(stderr, "error: %s:%ld: %d fields, header has %d\n", c->path, c->line_no, n,
                c->ncols);
        return -1;
    }
    for (i = 0; i < n; i++) {
        char *end = NULL;
        c->vals[i] = strtof(fields[i], &end);
        if (end == fields[i] || *end != '\0') {
            fprintf(stderr, "error: %s:%ld: bad number '%s' in column %s\n", c->path, c->line_no,
                    fields[i], c->names[i]);
            return -1;
        }
    }
    return 1;
}

/* ------------------------------------------------------------ channels --- */

typedef struct {
    const char *name;
    double tol;   /* gate tolerance; <0 = report-only */
    int exact;    /* 1 = exact-match gate (state code) */
    int required; /* header must contain this column */
    int col;      /* resolved column index, -1 if absent */
    double maxerr;
    long maxerr_tick;
    long nbad; /* exact-gate mismatch count */
    long first_bad_tick;
    long nnan; /* NaN-error count (NaN on either or both sides; always a FAIL) */
} chan_t;

enum {
    CH_DA1, CH_DB1, CH_DA2, CH_DB2, CH_DA3, CH_DB3,
    CH_RV1, CH_RV2, CH_RV3, CH_BETA, CH_IREF, CH_STATE,
    CH_STRESS, CH_PAV, CH_COUNT
};

static void chan_setup(chan_t *ch)
{
    static const struct {
        const char *name;
        double tol;
        int exact;
        int required;
    } def[CH_COUNT] = {
        {"dA1", 1e-3, 0, 1},   {"dB1", 1e-3, 0, 1},    {"dA2", 1e-3, 0, 1},
        {"dB2", 1e-3, 0, 1},   {"dA3", 1e-3, 0, 1},    {"dB3", 1e-3, 0, 1},
        {"rv1", 1e-2, 0, 1},   {"rv2", 1e-2, 0, 1},    {"rv3", 1e-2, 0, 1},
        {"beta", 1e-2, 0, 1},  {"Iref", 1e-2, 0, 1},   {"state", 0.0, 1, 1},
        {"stress", -1.0, 0, 0}, {"Pav", -1.0, 0, 0},
    };
    int i;
    for (i = 0; i < CH_COUNT; i++) {
        ch[i].name = def[i].name;
        ch[i].tol = def[i].tol;
        ch[i].exact = def[i].exact;
        ch[i].required = def[i].required;
        ch[i].col = -1;
        ch[i].maxerr = 0.0;
        ch[i].maxerr_tick = -1;
        ch[i].nbad = 0;
        ch[i].first_bad_tick = -1;
        ch[i].nnan = 0;
    }
}

static float chan_actual(const stack_out_t *o, int ch)
{
    switch (ch) {
    case CH_DA1: return o->d[0];
    case CH_DB1: return o->d[1];
    case CH_DA2: return o->d[2];
    case CH_DB2: return o->d[3];
    case CH_DA3: return o->d[4];
    case CH_DB3: return o->d[5];
    case CH_RV1: return o->rv[0];
    case CH_RV2: return o->rv[1];
    case CH_RV3: return o->rv[2];
    case CH_BETA: return o->beta;
    case CH_IREF: return o->Iref;
    case CH_STATE: return o->mppt_state;
    case CH_STRESS: return o->stress;
    case CH_PAV: return o->Pav;
    default: return 0.0f;
    }
}

/* -------------------------------------------------------------- replay --- */

static const char *IN_NAMES[] = {"VM1",  "VM2",  "VM3",  "VM4",  "IM1",      "IM2",
                                 "IM3",  "IM4",  "ILA1", "ILB1", "ILA2",     "ILB2",
                                 "ILA3", "ILB3", "V_String", "I_String", "Vref1", "Vref2",
                                 "Vref3", "en_sup", "en_mppt"};
#define IN_COUNT 21

static void in_from_row(const csv_t *c, const int *cols, stack_in_t *in)
{
    int k;
    float v[IN_COUNT];
    for (k = 0; k < IN_COUNT; k++) {
        v[k] = c->vals[cols[k]];
    }
    for (k = 0; k < 4; k++) {
        in->VM[k] = v[0 + k];
        in->IM[k] = v[4 + k];
    }
    for (k = 0; k < 6; k++) {
        in->IL[k] = v[8 + k];
    }
    in->Vstr = v[14];
    in->Istr = v[15];
    for (k = 0; k < 3; k++) {
        in->Vref[k] = v[16 + k];
    }
    in->en_sup = v[19];
    in->en_mppt = v[20];
}

static int run_replay(const char *in_path, const char *exp_path, double tol_scale)
{
    csv_t cin, cexp;
    chan_t ch[CH_COUNT];
    int in_cols[IN_COUNT];
    stack_state_t st;
    long tick = 0;
    int k, fail = 0;

    if (csv_open(&cin, in_path) != 0) {
        return 2;
    }
    if (csv_open(&cexp, exp_path) != 0) {
        csv_close(&cin);
        return 2;
    }
    for (k = 0; k < IN_COUNT; k++) {
        in_cols[k] = csv_col(&cin, IN_NAMES[k]);
        if (in_cols[k] < 0) {
            fprintf(stderr, "error: %s: missing required input column '%s'\n", in_path,
                    IN_NAMES[k]);
            csv_close(&cin);
            csv_close(&cexp);
            return 2;
        }
    }
    chan_setup(ch);
    for (k = 0; k < CH_COUNT; k++) {
        ch[k].col = csv_col(&cexp, ch[k].name);
        if (ch[k].col < 0 && ch[k].required) {
            fprintf(stderr, "error: %s: missing required expected column '%s'\n", exp_path,
                    ch[k].name);
            csv_close(&cin);
            csv_close(&cexp);
            return 2;
        }
    }

    stack_init(&st);
    for (;;) {
        stack_in_t in;
        stack_out_t out;
        int ri = csv_row(&cin);
        int re = csv_row(&cexp);
        if (ri < 0 || re < 0) {
            csv_close(&cin);
            csv_close(&cexp);
            return 2;
        }
        if (ri == 0 && re == 0) {
            break;
        }
        if (ri != re) {
            fprintf(stderr, "error: row count mismatch (%s ended first)\n",
                    (ri == 0) ? in_path : exp_path);
            csv_close(&cin);
            csv_close(&cexp);
            return 2;
        }
        in_from_row(&cin, in_cols, &in);
        stack_step(&in, &st, &out);
        for (k = 0; k < CH_COUNT; k++) {
            double err, act, exp;
            if (ch[k].col < 0) {
                continue;
            }
            act = (double)chan_actual(&out, k);
            exp = (double)cexp.vals[ch[k].col];
            if (ch[k].exact) {
                if (act != exp) {
                    if (ch[k].nbad == 0) {
                        ch[k].first_bad_tick = tick;
                    }
                    ch[k].nbad++;
                }
            }
            err = fabs(act - exp);
            if (isnan(err)) {
                ch[k].nnan++;
            } else if (err > ch[k].maxerr) {
                ch[k].maxerr = err;
                ch[k].maxerr_tick = tick;
            }
        }
        tick++;
    }
    csv_close(&cin);
    csv_close(&cexp);

    printf("replayed %ld ticks (%.4f s at 50 us)\n", tick, (double)tick * 50e-6);
    printf("%-8s %-13s %-10s %-12s %s\n", "channel", "max|err|", "at tick", "tolerance",
           "verdict");
    for (k = 0; k < CH_COUNT; k++) {
        const char *verdict;
        char tolstr[32];
        if (ch[k].col < 0) {
            printf("%-8s %-13s %-10s %-12s %s\n", ch[k].name, "-", "-", "-",
                   "SKIPPED (column absent)");
            continue;
        }
        if (ch[k].exact) {
            int bad = (ch[k].nbad > 0);
            fail |= bad;
            printf("%-8s %-13ld %-10ld %-12s %s\n", ch[k].name, ch[k].nbad,
                   ch[k].first_bad_tick, "exact", bad ? "FAIL (mismatch count)" : "PASS");
            continue;
        }
        if (ch[k].tol < 0.0) {
            verdict = "report-only";
            snprintf(tolstr, sizeof tolstr, "-");
        } else {
            /* spec gate: max abs error < tol; zero tolerance demands exact 0 */
            double tol = ch[k].tol * tol_scale;
            int bad = (tol > 0.0) ? (ch[k].maxerr >= tol) : (ch[k].maxerr > 0.0);
            bad = bad || (ch[k].nnan > 0);
            fail |= bad;
            verdict = bad ? "FAIL" : "PASS";
            snprintf(tolstr, sizeof tolstr, "%.3g", tol);
        }
        printf("%-8s %-13.6e %-10ld %-12s %s", ch[k].name, ch[k].maxerr, ch[k].maxerr_tick,
               tolstr, verdict);
        if (ch[k].nnan > 0) {
            printf("  (%ld NaN ticks)", ch[k].nnan);
        }
        printf("\n");
    }
    printf("replay: %s\n", fail ? "FAIL" : "PASS");
    return fail ? 1 : 0;
}

/* ------------------------------------------------------------ selftest --- */

static void selftest_inputs(long tick, stack_in_t *in)
{
    /* deterministic, physically-plausible synthetic profile (no rand/time) */
    float t = (float)tick * 50e-6f;
    float g1 = 1.0f + 0.02f * sinf(6.2831853f * 1.3f * t);
    float g2 = 0.95f + 0.03f * sinf(6.2831853f * 0.7f * t + 1.0f);
    float g3 = (t > 0.25f) ? 0.55f : 0.90f; /* shade step to exercise the governor */
    float g4 = 1.0f;
    int k;
    in->VM[0] = 38.7f * g1;
    in->VM[1] = 38.7f * g2;
    in->VM[2] = 38.7f * g3;
    in->VM[3] = 38.7f * g4;
    in->IM[0] = 14.0f * g1;
    in->IM[1] = 13.5f * g2;
    in->IM[2] = 13.0f * g3;
    in->IM[3] = 14.2f * g4;
    for (k = 0; k < 6; k++) {
        in->IL[k] = 3.0f * sinf(6.2831853f * 2.0f * t + 0.5f * (float)k) +
                    ((k % 2 == 0) ? 8.0f : -8.0f) * (1.0f - g3);
    }
    in->Vstr = in->VM[0] + in->VM[1] + in->VM[2] + in->VM[3];
    in->Istr = 11.0f + 0.5f * sinf(6.2831853f * 0.9f * t);
    in->Vref[0] = (t > 0.35f) ? 0.8f : 0.0f; /* manual rv offset step */
    in->Vref[1] = 0.0f;
    in->Vref[2] = 0.0f;
    in->en_sup = (t > 0.10f && t < 0.14f) ? 0.0f : 1.0f; /* reset windows */
    in->en_mppt = (t > 0.18f && t < 0.20f) ? 0.0f : 1.0f;
}

static int run_selftest(const char *dir)
{
    char in_path[512], exp_path[512];
    FILE *fi, *fe;
    stack_state_t st;
    long tick;
    const long NTICK = 10000; /* 0.5 s */
    int rc, k;

    snprintf(in_path, sizeof in_path, "%s/selftest_inputs.csv", dir);
    snprintf(exp_path, sizeof exp_path, "%s/selftest_expected.csv", dir);
    fi = fopen(in_path, "w");
    fe = fopen(exp_path, "w");
    if (fi == NULL || fe == NULL) {
        fprintf(stderr, "error: cannot write selftest CSVs in '%s'\n", dir);
        return 2;
    }
    fprintf(fi, "t");
    for (k = 0; k < IN_COUNT; k++) {
        fprintf(fi, ",%s", IN_NAMES[k]);
    }
    fprintf(fi, "\n");
    fprintf(fe, "t,dA1,dB1,dA2,dB2,dA3,dB3,rv1,rv2,rv3,beta,stress,Iref,Pav,state\n");

    stack_init(&st);
    for (tick = 0; tick < NTICK; tick++) {
        stack_in_t in;
        stack_out_t o;
        selftest_inputs(tick, &in);
        stack_step(&in, &st, &o);
        fprintf(fi, "%.9g", (double)tick * 50e-6);
        fprintf(fi, ",%.9g,%.9g,%.9g,%.9g", (double)in.VM[0], (double)in.VM[1], (double)in.VM[2],
                (double)in.VM[3]);
        fprintf(fi, ",%.9g,%.9g,%.9g,%.9g", (double)in.IM[0], (double)in.IM[1], (double)in.IM[2],
                (double)in.IM[3]);
        for (k = 0; k < 6; k++) {
            fprintf(fi, ",%.9g", (double)in.IL[k]);
        }
        fprintf(fi, ",%.9g,%.9g", (double)in.Vstr, (double)in.Istr);
        fprintf(fi, ",%.9g,%.9g,%.9g", (double)in.Vref[0], (double)in.Vref[1],
                (double)in.Vref[2]);
        fprintf(fi, ",%.9g,%.9g\n", (double)in.en_sup, (double)in.en_mppt);

        fprintf(fe, "%.9g", (double)tick * 50e-6);
        for (k = 0; k < 6; k++) {
            fprintf(fe, ",%.9g", (double)o.d[k]);
        }
        fprintf(fe, ",%.9g,%.9g,%.9g", (double)o.rv[0], (double)o.rv[1], (double)o.rv[2]);
        fprintf(fe, ",%.9g,%.9g,%.9g,%.9g,%.9g\n", (double)o.beta, (double)o.stress,
                (double)o.Iref, (double)o.Pav, (double)o.mppt_state);
    }
    fclose(fi);
    fclose(fe);

    /* replay with zero tolerance: %.9g round-trips float32 exactly, so any
     * nonzero error means a harness bug */
    printf("selftest: wrote %s and %s, replaying with zero tolerance\n", in_path, exp_path);
    rc = run_replay(in_path, exp_path, 0.0);
    if (rc == 0) {
        printf("selftest: PASS\n");
    } else {
        printf("selftest: FAIL\n");
    }
    return rc;
}

/* ---------------------------------------------------------------- main --- */

int main(int argc, char **argv)
{
    printf("shuffler stack golden replay, %s, accum=%s\n", PARAMS_VERSION,
#ifdef SHUF_ACCUM_DOUBLE
           "double"
#else
           "float"
#endif
    );
    if (argc == 2 || argc == 3) {
        if (strcmp(argv[1], "--selftest") == 0) {
            return run_selftest(argc == 3 ? argv[2] : ".");
        }
    }
    if (argc == 3) {
        return run_replay(argv[1], argv[2], 1.0);
    }
    fprintf(stderr,
            "usage: %s <golden_inputs.csv> <golden_expected.csv>\n"
            "       %s --selftest [outdir]\n",
            argv[0], argv[0]);
    return 2;
}
