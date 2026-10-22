/*
 * fuzzrid-fuzzy-hfs.c -- T-HFIS: Taxonomy-driven Hierarchical Fuzzy
 * Inference System for 2H-FuzzRID.
 *
 * Drop-in replacement for the flat 18-rule engine at the
 * fuzzrid_fuzzy_infer_ml() seam in fuzzrid-fuzzy.c. All downstream code
 * (AMLM mitigation, aggregation, root corroboration) is unchanged: this
 * file still returns AC in [0,100].
 *
 * Architecture (2 layers, 4 Sugeno units, 25 rules, integer-only):
 *
 *   RA = f_RA(v1, v3, v4)   rank-trajectory anomaly      [6 rules]
 *   SI = f_SI(v2, v5)       signal instability           [5 rules]
 *   CX = f_CX(v6, v7)       corroboration/context score  [5 rules]
 *                           (0 = mobility-excused, 50 = neutral,
 *                            100 = two-hop forgery corroborated)
 *   AC = f_TOP(RA, SI, CX)  final anomaly confidence     [9 rules]
 *
 * Same MF family and arithmetic as the flat engine: piecewise-linear
 * L/M/H sets on the 0..100 integer scale, min t-norm, singleton
 * consequents {0,25,50,75,100}, epsilon=1 Sugeno weighted average.
 * No FPU, no division except one uint32 divide per unit (4 total,
 * vs 1 in the flat engine). Flash: 25 rule entries vs 18; RAM: +3 bytes
 * for intermediates. Complete-grid bound: 72 rules vs 2187 flat (30.4x).
 *
 * DOCUMENTED BEHAVIOUR CHANGE vs flat base: flat R1 (v1 High -> VH) is
 * unconditional. Here a High rank anomaly with exculpatory context
 * (CX Low: mobile node, no forgery evidence) yields AC = 50 (rule T3),
 * i.e. suspicion without conviction. State this in the manuscript.
 */

#include <stdint.h>

/* ---- membership functions: identical family to fuzzrid-fuzzy.c ---- */
/* Low : 100 on [0,20], linear to 0 at 50                               */
/* Med : 0 at 20, peak 100 at 50, 0 at 80                               */
/* High: 0 at 60, linear to 100 at 90, 100 on [90,100]                  */
/*       (pre-Mar-2026 base used 50/80; change HI_C/HI_D to revert)     */

#define HI_C 60
#define HI_D 90

static uint8_t mu_L(uint8_t v)
{
  if (v <= 20) return 100;
  if (v >= 50) return 0;
  return (uint8_t)(((50 - v) * 100u) / 30u);
}

static uint8_t mu_M(uint8_t v)
{
  if (v <= 20 || v >= 80) return 0;
  if (v <= 50) return (uint8_t)(((v - 20) * 100u) / 30u);
  return (uint8_t)(((80 - v) * 100u) / 30u);
}

static uint8_t mu_H(uint8_t v)
{
  if (v <= HI_C) return 0;
  if (v >= HI_D) return 100;
  return (uint8_t)(((v - HI_C) * 100u) / (HI_D - HI_C));
}

static uint8_t min2(uint8_t a, uint8_t b) { return a < b ? a : b; }

/* Sugeno weighted average, epsilon = 1, weights on 0..100 scale */
static uint8_t sugeno(const uint8_t *w, const uint8_t *z, uint8_t n)
{
  uint32_t num = 0, den = 1;
  uint8_t r;
  for (r = 0; r < n; r++) {
    num += (uint32_t)w[r] * z[r];
    den += w[r];
  }
  return (uint8_t)(num / den);
}

/* ---- Layer 1 ------------------------------------------------------- */

/* RA(v1, v3, v4): rank-trajectory anomaly */
static uint8_t infer_ra(uint8_t v1, uint8_t v3, uint8_t v4)
{
  uint8_t w[6], z[6];
  w[0] = mu_H(v1);                                z[0] = 100; /* A1 <- R1  */
  w[1] = mu_H(v3);                                z[1] = 75;  /* A2 <- R6/R7 */
  w[2] = mu_H(v4);                                z[2] = 75;  /* A3 <- R3/R4 */
  w[3] = min2(mu_M(v3), mu_M(v4));                z[3] = 50;  /* A4 <- R12 */
  w[4] = mu_M(v1);                                z[4] = 50;  /* A5 graded */
  w[5] = min2(mu_L(v1), min2(mu_L(v3), mu_L(v4))); z[5] = 0;  /* A6 benign */
  return sugeno(w, z, 6);
}

/* SI(v2, v5): control-plane / signal instability */
static uint8_t infer_si(uint8_t v2, uint8_t v5)
{
  uint8_t w[5], z[5];
  w[0] = min2(mu_H(v2), mu_H(v5)); z[0] = 100; /* B1 <- R10 */
  w[1] = mu_H(v5);                 z[1] = 75;  /* B2 <- R9  */
  w[2] = mu_H(v2);                 z[2] = 50;  /* B3 trickle alone weak */
  w[3] = min2(mu_M(v2), mu_M(v5)); z[3] = 50;  /* B4 graded */
  w[4] = min2(mu_L(v2), mu_L(v5)); z[4] = 0;   /* B5 benign */
  return sugeno(w, z, 5);
}

/* CX(v6, v7): corroboration/context. 0 excused .. 50 neutral .. 100 forged */
static uint8_t infer_cx(uint8_t v6, uint8_t v7)
{
  uint8_t w[5], z[5];
  w[0] = mu_H(v7);                 z[0] = 100; /* C1 <- R2  */
  w[1] = mu_M(v7);                 z[1] = 75;  /* C2 graded */
  w[2] = min2(mu_H(v6), mu_L(v7)); z[2] = 0;   /* C3 <- R13/R18 */
  w[3] = min2(mu_M(v6), mu_L(v7)); z[3] = 25;  /* C4 partial excuse */
  w[4] = min2(mu_L(v6), mu_L(v7)); z[4] = 50;  /* C5 neutral */
  return sugeno(w, z, 5);
}

/* ---- Layer 2 ------------------------------------------------------- */

static uint8_t infer_top(uint8_t ra, uint8_t si, uint8_t cx)
{
  uint8_t w[9], z[9];
  w[0] = mu_H(cx);                                  z[0] = 100; /* T1 */
  w[1] = min2(mu_H(ra), mu_M(cx));                  z[1] = 100; /* T2 */
  w[2] = min2(mu_H(ra), mu_L(cx));                  z[2] = 50;  /* T3 NEW */
  w[3] = min2(mu_H(si), mu_M(cx));                  z[3] = 75;  /* T4 */
  w[4] = min2(mu_M(ra), mu_H(si));                  z[4] = 75;  /* T5 */
  w[5] = min2(mu_M(ra), min2(mu_M(si), mu_M(cx)));  z[5] = 50;  /* T6 */
  w[6] = min2(mu_L(ra), min2(mu_L(si), mu_L(cx)));  z[6] = 0;   /* T7 */
  w[7] = min2(mu_L(ra), min2(mu_L(si), mu_M(cx)));  z[7] = 0;   /* T8 */
  w[8] = min2(mu_H(si), mu_L(cx));                  z[8] = 25;  /* T9 */
  return sugeno(w, z, 9);
}

/* ---- Public entry point: the fuzzrid-fuzzy.c seam ------------------ */

uint8_t fuzzrid_fuzzy_infer_ac_hfs(const uint8_t v[7])
{
  uint8_t ra = infer_ra(v[0], v[2], v[3]); /* v1, v3, v4 */
  uint8_t si = infer_si(v[1], v[4]);       /* v2, v5     */
  uint8_t cx = infer_cx(v[5], v[6]);       /* v6, v7     */
  return infer_top(ra, si, cx);
}

/* Optional: expose intermediates for logging/explainability
 * ([HFS] ra=.. si=.. cx=.. ac=..) so parse_serial.py can extract the
 * per-branch attribution -- a strong explainability figure for Sec. 6. */
void fuzzrid_fuzzy_infer_ac_hfs_x(const uint8_t v[7], uint8_t *ra,
                                  uint8_t *si, uint8_t *cx, uint8_t *ac)
{
  *ra = infer_ra(v[0], v[2], v[3]);
  *si = infer_si(v[1], v[4]);
  *cx = infer_cx(v[5], v[6]);
  *ac = infer_top(*ra, *si, *cx);
}
