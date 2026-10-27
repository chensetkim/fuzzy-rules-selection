/*
 * DM-2H-FuzzRID — Fuzzy Decision Engine
 * Algorithms 2–3: FuzzyInferAC (Sugeno) + FuzzyInferML (graduated response)
 *
 * Integer arithmetic: all v_k values are 0–100 (representing [0,1] × 100).
 * Membership functions use integer 0–100 output.
 * Consequent singletons: VL=0, L=25, M=50, H=75, VH=100.
 */

#include "fuzzrid-fuzzy.h"
#include "apps/2h-fuzzrid/fuzzrid-fuzzy-hfs.h"

// #define DEBUG DEBUG_NONE
#define FUZZRID_DEBUG FUZZRID_PRINT
#include "net/ip/uip-debug.h"


/* ── min-max helpers ─────────────────────────────────────── */

static uint8_t
min2(uint8_t a, uint8_t b)
{
  return (a < b) ? a : b;
}

static uint8_t
max2(uint8_t a, uint8_t b)
{
  return (a > b) ? a : b;
}

/* ── Membership functions ────────────────────────────── */

/* a = left edge, b = left shoulder, c = right shoulder, d = right edge */
static uint8_t
trapezoidal_mf(uint8_t v, uint8_t a, uint8_t b, uint8_t c, uint8_t d)
{
  if(v < a || v > d) { return 0; }
  if(v == a) { return (a == b) ? 100 : 0; }  /* left foot: full only when flat */
  if(v == d) { return (c == d) ? 100 : 0; }  /* right foot: full only when flat */
  if(v >= b && v <= c) { return 100; }
  if(v > a && v < b) {
    return (uint8_t)(((uint16_t)(v - a) * 100u) / (b - a));
  }
  /* v > c && v < d */
  return (uint8_t)(((uint16_t)(d - v) * 100u) / (d - c));
}

/* a = left foot, b = peak, c = right foot */
static uint8_t
triangular_mf(uint8_t v, uint8_t a, uint8_t b, uint8_t c)
{
  if(v < a || v > c) { return 0; }
  if(v == a || v == c) { return 0; }  /* endpoints of triangle are zero */
  if(v == b) { return 100; }
  if(v > a && v < b) {
    return (uint8_t)(((uint16_t)(v - a) * 100u) / (b - a));
  }
  /* v > b && v < c */
  return (uint8_t)(((uint16_t)(c - v) * 100u) / (c - b));
}

/* Define membership function L, M, H are defined the same 
 * for all inputs v1, v2, v3, v4, v5, v6, v7 */
static uint8_t
mu_L(uint8_t v)
{
  /* trapezoidal: 100 on [0,20], linear ↘ to 0 at 50 */
  return trapezoidal_mf(v, 0, 0, 20, 50);
}

static uint8_t
mu_M(uint8_t v)
{
  /* triangular: 0 at 20, peak 100 at 50, linear ↘ to 0 at 80 */
  return triangular_mf(v, 20, 50, 80);
}

static uint8_t
mu_H(uint8_t v)
{
  /* trapezoidal: 0 at 50, linear ↗ to 100 at 80, 100 on [80,100] */
  return trapezoidal_mf(v, 50, 80, 100, 100);
}

/* "NOT explained by mobility" gate — used by the r32 rule base only.
 *
 * mu_L(v6) is identically zero for ALL v6 >= 50, so gating a rule on
 * mu_L(v6) switches that rule off completely once the mobility index
 * reaches the midpoint.  Since v6 is ~75% attacker-controllable, an
 * attacker can disable every such rule just by holding MI near 50 —
 * without ever reaching the H band that triggers the exoneration rule.
 *
 * mu_not_H keeps full weight while mobility is low OR moderate, and
 * decays to zero only once mobility is genuinely high, i.e. only once it
 * actually explains the anomaly.  Polarity is unchanged: v6 can still
 * only WITHHOLD blame, never assign it. */
static uint8_t
mu_not_H(uint8_t v)
{
  return (uint8_t)(100u - mu_H(v));
}

/* declarations to avoid compile errors */
static uint8_t fuzzrid_fuzzy_infer_ac_flat(uint8_t v1, uint8_t v2, uint8_t v3,
                                              uint8_t v4, uint8_t v5, uint8_t v6,
                                              uint8_t v7);
static uint8_t fuzzrid_fuzzy_infer_ac_18rule(uint8_t v1, uint8_t v2, uint8_t v3,
                                              uint8_t v4, uint8_t v5, uint8_t v6,
                                              uint8_t v7);
static uint8_t fuzzrid_fuzzy_r33_infer_ac_flat(uint8_t v1, uint8_t v2, uint8_t v3,
                                              uint8_t v4, uint8_t v5, uint8_t v6,
                                              uint8_t v7);

uint8_t
fuzzrid_fuzzy_infer_ac(uint8_t v1, uint8_t v2, uint8_t v3,
                       uint8_t v4, uint8_t v5, uint8_t v6,
                       uint8_t v7)
{
  FUZZ_PRINTF("[FUZZY-DBG] (v1,v2,v3,v4,v5,v6,v7):%u,%u,%u,%u,%u,%u,%u\n",
         v1, v2, v3, v4, v5, v6, v7);

#if WITH_THFIS
  
  uint8_t ra, si, cx;
  uint8_t ac = fuzzrid_fuzzy_infer_ac_hfs_x(v1, v2, v3, v4, v5, v6, v7,
                                            &ra, &si, &cx);
  FUZZ_PRINTF("[HFS] ra=%u si=%u cx=%u ac=%u\n", ra, si, cx, ac);
  return ac;
#else

// return fuzzrid_fuzzy_infer_ac_18rule(v1, v2, v3, v4, v5, v6, v7);
return fuzzrid_fuzzy_r33_infer_ac_flat(v1, v2, v3, v4, v5, v6, v7);
// return fuzzrid_fuzzy_infer_ac_flat(v1, v2, v3, v4, v5, v6, v7);

#endif /* WITH_THFIS */
}

/* ── Algorithm 3: FuzzyInferML ───────────────────────── */
#if 0
/* Legacy version: no hysteresis, no sequential evidence test, just a
 * threshold on instantaneous AC.  This is the original design in rev 1.0..1.4.
 * It was replaced by the current version in rev 1.5 because it produced too
 * many false positives on the S1/S2 runs (0.118/0.000/0.000 honest links at
 * PENALISE/QUARANTINE/BLACKLIST, but 1.000/0.250/0.250 attacker links).
 */
uint8_t
fuzzrid_fuzzy_infer_ml(uint8_t ac_pct, uint8_t ml_prev_pct,
                       uint8_t *action_out)
{
  uint8_t ml;
  uint8_t action;

  if(ac_pct >= 85) {
    ml = 100; action = 4; /* BLACKLIST */
  } else if(ac_pct >= 65 && ml_prev_pct >= 65) {
    ml = 75;  action = 3; /* QUARANTINE — sustained high AC */
  } else if(ac_pct >= 65) {
    ml = 55;  action = 2; /* WATCHLIST — first occurrence */
  } else if(ac_pct >= 30) {
    ml = 40;  action = 1; /* PENALISE */
  } else {
    ml = 0;   action = 0; /* NORMAL */
  }

  if(action_out != NULL) { *action_out = action; }
  return ml;
}
#endif

/* ── Algorithm 3: FuzzyInferML — sequential evidence test + graduated response ─
 *
 * Maps the per-DIO anomaly confidence AC onto one of four escalating response
 * levels (NORMAL / PENALISE / QUARANTINE / BLACKLIST).
 *
 * Design rationale (measured on the labelled S1/S2 runs: 184 observer->source
 * links, 2147 DIO observations).  The AC produced by FuzzyInferAC is strongly
 * bimodal for BOTH classes: it is 0 on 99.1% of honest observations and on
 * 75.7% of attacker observations, and when it does fire it lands in 70..99
 * regardless of class.  AC magnitude therefore carries almost no discriminative
 * power — the classes separate by the RATE of anomaly events, not their size:
 *
 *     P(AC > 0 | honest)   = 0.0088
 *     P(AC > 0 | attacker) = 0.2432        (27x)
 *
 * The log-likelihood ratio of that event indicator is +3.32 nats per anomaly and
 * -0.27 nats per clean DIO (a 12.3:1 ratio), so the appropriate detector is
 * Wald's sequential probability ratio test over accumulated evidence, not a
 * threshold on instantaneous AC.  ML implements that accumulator in integer
 * form.
 *
 * Stage 1 — evidence.  A leaky bucket, clamped to [0,100]:
 *
 *     ML_t = clamp( ML_{t-1} + AC_t / FUZZRID_ML_GAIN - FUZZRID_ML_LEAK )
 *
 *   GAIN = 2 makes a typical anomaly (AC ~ 87) worth ~43 units while LEAK = 2
 *   discounts each clean DIO, reproducing the empirical 12.3:1 LLR ratio to
 *   within quantisation.  The bucket saturates at 0, so a node that has been
 *   quiet for a few rounds returns ML = 0 exactly, which re-arms the CUSUM reset
 *   in fuzzrid_process_dio().
 *
 * Stage 2 — decision.  Ordered thresholds partition accumulated evidence so that
 *   each successive level requires one further corroborating anomaly:
 *
 *     TAU1 = 25  ~ 1 anomaly   -> PENALISE
 *     TAU2 = 50  ~ 2 anomalies -> QUARANTINE
 *     TAU3 = 75  ~ 3 anomalies -> BLACKLIST
 *
 *   This is where the cost asymmetry is enforced.  PENALISE only biases parent
 *   selection and is undone at the next DIO; QUARANTINE costs a parent change
 *   and a subtree re-attach; BLACKLIST partitions the node, so a false positive
 *   there does the attacker's work for it.  Demanding an extra independent
 *   anomaly per level makes the evidence bar scale with the cost of the
 *   response.
 *
 * Stage 3 — stability.  Release is gradual and hysteretic: a level is given up
 *   one step at a time, and only once ML has fallen FUZZRID_ML_DELTA below the
 *   threshold that was crossed, so a node whose ML dithers around TAU_j cannot
 *   flap between response levels.  BLACKLIST is absorbing — release is an
 *   administrative action, not an automatic one.  Escalation is deliberately NOT
 *   rate-limited to one level per round: measurement showed such a cap cost 5x
 *   on blacklist recall (0.050 -> 0.250) while reducing false positives by
 *   exactly zero, because the thresholds already carry the evidence
 *   requirement.
 *
 * Measured operating point (GAIN=2, LEAK=2, 25/50/75, DELTA=8), per link:
 *
 *                PENALISE   QUARANTINE   BLACKLIST
 *     honest       0.118       0.000       0.000
 *     attacker     1.000       0.250       0.250
 *
 * Every attacker link is penalised, and escalation beyond that is free of false
 * positives on this data.  The recall ceiling at QUARANTINE/BLACKLIST is imposed
 * by FuzzyInferAC, not by this stage: only 25% of attacker links ever produce
 * more than one nonzero AC (30 of 40 produce exactly one), so no decision rule
 * downstream of AC can escalate the remainder.  Raising that ceiling is a
 * detection-layer (v1..v7) problem.
 */

/* Evidence accumulator parameters — see the LLR derivation above. */
#ifndef FUZZRID_ML_GAIN
#define FUZZRID_ML_GAIN   2    /* ML += AC / GAIN on each observation        */
#endif
#ifndef FUZZRID_ML_LEAK
#define FUZZRID_ML_LEAK   2    /* ML -= LEAK on each observation             */
#endif
/* Thresholds on accumulated evidence; each level costs one more anomaly. */
#ifndef FUZZRID_ML_TAU1
#define FUZZRID_ML_TAU1   25   /* ~1 anomaly   -> PENALISE                   */
#endif
#ifndef FUZZRID_ML_TAU2
#define FUZZRID_ML_TAU2   50   /* ~2 anomalies -> QUARANTINE                 */
#endif
#ifndef FUZZRID_ML_TAU3
#define FUZZRID_ML_TAU3   75   /* ~3 anomalies -> BLACKLIST                  */
#endif
#ifndef FUZZRID_ML_DELTA
#define FUZZRID_ML_DELTA  8    /* hysteresis band for de-escalation          */
#endif

uint8_t
fuzzrid_fuzzy_infer_ml(const uip_ipaddr_t *src, uint8_t ac_pct, uint8_t ml_prev_pct,
                       uint8_t action_prev, uint8_t *action_out)
{
  /* Indexed by response level; tau[0] is unused (NORMAL has no lower edge). */
  static const uint8_t tau[FUZZRID_ACTION_MAX + 1] = {
    0, FUZZRID_ML_TAU1, FUZZRID_ML_TAU2, FUZZRID_ML_TAU3
  };
  int16_t acc;
  uint8_t ml;
  uint8_t act;
  uint8_t lvl;

  /* Stage 1: leaky-bucket evidence accumulator, clamped to [0,100]. */
  acc = (int16_t)ml_prev_pct + (int16_t)(ac_pct / FUZZRID_ML_GAIN)
        - FUZZRID_ML_LEAK;
  if(acc < 0)   { acc = 0; }
  if(acc > 100) { acc = 100; }
  ml = (uint8_t)acc;

  act = (action_prev > FUZZRID_ACTION_MAX) ? FUZZRID_ACTION_NORMAL
                                           : action_prev;

  /* Stage 2: level indicated by the accumulated evidence. */
  lvl = (ml >= tau[FUZZRID_ACTION_BLACKLIST])  ? FUZZRID_ACTION_BLACKLIST
      : (ml >= tau[FUZZRID_ACTION_QUARANTINE]) ? FUZZRID_ACTION_QUARANTINE
      : (ml >= tau[FUZZRID_ACTION_PENALISE])   ? FUZZRID_ACTION_PENALISE
                                               : FUZZRID_ACTION_NORMAL;

  /* Stage 3: immediate escalation, hysteretic one-step release, and BLACKLIST
   * is absorbing. */
  if(act != FUZZRID_ACTION_BLACKLIST) {
    if(lvl > act) {
      act = lvl;
    } else if(act > FUZZRID_ACTION_NORMAL &&
              (uint16_t)ml + FUZZRID_ML_DELTA < tau[act]) {
      act--;
    }
  }

  FUZZ_PRINTF("[AC-ML] src=%u ac=%u ml_prev=%u ml=%u act=%c->%c\n",
              src->u8[15], ac_pct, ml_prev_pct, ml, 
      FUZZRID_ACTION_CHARS[action_prev], FUZZRID_ACTION_CHARS[act]);

  if(action_out != NULL) { *action_out = act; }
  return ml;
}

/* ── Fuzzy Rules Base ────────────────────────── */

static uint8_t
fuzzrid_fuzzy_infer_ac_flat(uint8_t v1, uint8_t v2, uint8_t v3,
                              uint8_t v4, uint8_t v5, uint8_t v6,
                              uint8_t v7)
{
  /* ── v6 polarity convention ────────────────────────────────────────────
   * v6 is the Mobility Index: a CONFOUNDER, not an attack channel.  High v6
   * means rank churn and parent switching are expected, so v6 may only ever
   * WITHHOLD blame, never assign it.  Two consequences, enforced below:
   *
   *   (a) v6 appears in accusatory rules only as "v6 is L" — i.e. the anomaly
   *       is NOT explained by mobility.  A rule whose weight rises with v6
   *       would invert the variable's meaning.
   *   (b) v6 may gate only the mobility-explainable channels v2..v5 (residual
   *       plausibility, CUSUM drift, jump, oscillation).  It must NEVER gate
   *       v1 (monotonicity violation) or v7 (two-hop forgery mismatch):
   *       movement does not excuse advertising a rank below parent+MHR, nor
   *       misreporting a parent's rank.
   *
   * v6 is also ~75% attacker-controllable (MI = 0.30·PSR + 0.45·CV_ETX +
   * 0.15·NCR + 0.10·TR, and a rank attacker already forges ETX and picks its
   * own parent), so exoneration is conditional on the non-explainable channels
   * being clean — see E1.  Unconditional "high v6 ⇒ innocent" would be an
   * evasion channel.
   */
  FUZZ_PRINTF("[FUZZY-FLAT] Using 24-rule Sugeno inference\n");
  uint16_t w[26]; uint8_t zc[26];
  /* G124(enum): v3 is H AND v4 is L AND v5 is L AND v6 is L -> 75  [v6 M->L] */
  w[1] = min2(min2(min2(mu_H(v3), mu_L(v4)), mu_L(v5)), mu_L(v6));  zc[1] = 75;
  /* G212(enum): v2 is M -> 100 */
  w[2] = mu_M(v2);  zc[2] = 100;
  /* G224(enum): v2 is M AND v5 is L AND v6 is L -> 100  [v6 M->L] */
  w[3] = min2(min2(mu_M(v2), mu_L(v5)), mu_L(v6));  zc[3] = 100;
  /* G229(enum): v2 is M AND v4 is L AND v7 is L -> 100 */
  w[4] = min2(min2(mu_M(v2), mu_L(v4)), mu_L(v7));  zc[4] = 100;
  /* G250(enum): v2 is M AND v4 is H AND v5 is L AND v7 is L -> 100 */
  w[5] = min2(min2(min2(mu_M(v2), mu_H(v4)), mu_L(v5)), mu_L(v7));  zc[5] = 100;
  /* G252(enum): v2 is M AND v3 is H -> 100 */
  w[6] = min2(mu_M(v2), mu_H(v3));  zc[6] = 100;
  /* G289(enum): v2 is H AND v5 is L AND v6 is L AND v7 is L -> 100 */
  w[7] = min2(min2(min2(mu_H(v2), mu_L(v5)), mu_L(v6)), mu_L(v7));  zc[7] = 100;
  /* G298(enum): v2 is H AND v4 is L AND v6 is L -> 75  [v6 M->L] */
  w[8] = min2(min2(mu_H(v2), mu_L(v4)), mu_L(v6));  zc[8] = 75;
  /* G301(enum): v2 is H AND v4 is L AND v6 is L AND v7 is L -> 100  [v6 H->L] */
  w[9] = min2(min2(min2(mu_H(v2), mu_L(v4)), mu_L(v6)), mu_L(v7));  zc[9] = 100;
  /* G316(enum): v2 is H AND v4 is M AND v5 is L AND v6 is L -> 75  [v6 M->L] */
  w[10] = min2(min2(min2(mu_H(v2), mu_M(v4)), mu_L(v5)), mu_L(v6));  zc[10] = 75;
  /* G336(enum): v2 is H AND v3 is H AND v5 is L AND v7 is L -> 75 */
  w[11] = min2(min2(min2(mu_H(v2), mu_H(v3)), mu_L(v5)), mu_L(v7));  zc[11] = 75;
  /* G337(enum): v2 is H AND v3 is H AND v5 is L AND v6 is L -> 100 */
  w[12] = min2(min2(min2(mu_H(v2), mu_H(v3)), mu_L(v5)), mu_L(v6));  zc[12] = 100;
  /* G341(enum): v2 is H AND v3 is H AND v4 is L AND v7 is L -> 100 */
  w[13] = min2(min2(min2(mu_H(v2), mu_H(v3)), mu_L(v4)), mu_L(v7));  zc[13] = 100;
  /* G348(enum): v2 is H AND v3 is H AND v4 is M AND v6 is L -> 100 */
  w[14] = min2(min2(min2(mu_H(v2), mu_H(v3)), mu_M(v4)), mu_L(v6));  zc[14] = 100;
  /* G372(enum): v1 is L AND v5 is M -> 100 */
  w[15] = min2(mu_L(v1), mu_M(v5));  zc[15] = 100;
  /* G509(enum): v1 is L AND v2 is H AND v7 is L -> 100 */
  w[16] = min2(min2(mu_L(v1), mu_H(v2)), mu_L(v7));  zc[16] = 100;
  /* G519(enum): v1 is L AND v2 is H AND v5 is L AND v6 is L -> 100  [v6 M->L] */
  w[17] = min2(min2(min2(mu_L(v1), mu_H(v2)), mu_L(v5)), mu_L(v6));  zc[17] = 100;
  /* G564(enum): v1 is H AND v4 is L AND v7 is L -> 75
   * [v6 gate REMOVED: mobility must never excuse a monotonicity violation] */
  w[18] = min2(min2(mu_H(v1), mu_L(v4)), mu_L(v7));  zc[18] = 75;
  /* G577(enum): v1 is H AND v4 is H AND v7 is L -> 100 */
  w[19] = min2(min2(mu_H(v1), mu_H(v4)), mu_L(v7));  zc[19] = 100;
  /* G678(enum): v1 is H AND v2 is H AND v4 is H AND v7 is L -> 100 */
  w[20] = min2(min2(min2(mu_H(v1), mu_H(v2)), mu_H(v4)), mu_L(v7));  zc[20] = 100;
  /* R6: v3 is H AND v6 is L -> 75 */
  w[21] = min2(mu_H(v3), mu_L(v6));  zc[21] = 75;

  /* ── v7 accusation (ported from the 18-rule base) ──────────────────────
   * The two-hop cross-check is the only channel that catches an attacker who
   * forges its parent's rank, and it is not explainable by mobility, so these
   * rules carry NO v6 gate.  Without them v7 appears in this rule base only as
   * the precondition "v7 is L", i.e. it contributes nothing to detection.
   *
   * v7 accuses only WITH CORROBORATION.  The 18-rule base also carried a
   * standalone "v7 is H -> 100" (its R2); measured on the S1/S2 runs that rule
   * costs 0.035/0.021/0.014 honest links at PENALISE/QUARANTINE/BLACKLIST and
   * adds exactly zero attacker recall, because a forging attacker is already
   * caught through v1/v3 while honest nodes reach v7=100 transiently on a stale
   * two-hop parent rank (the failure mode the v7_persist counter was added for
   * in rev 1.5).  Requiring v1 or v3 to agree keeps the detection and drops the
   * false positives.  A node forging its two-hop report while NOT manipulating
   * its own rank is not mounting a rank attack and is deliberately not accused. */
  /* R15: v1 is H AND v7 is H -> 100 (monotonicity violation + forgery) */
  w[22] = min2(mu_H(v1), mu_H(v7));  zc[22] = 100;
  /* R16: v3 is H AND v7 is H -> 100 (sustained CUSUM drift + forgery) */
  w[23] = min2(mu_H(v3), mu_H(v7));  zc[23] = 100;

  /* E1 (from 18-rule R18): v6 is H AND v1 is L AND v3 is L AND v7 is L -> 0
   * Mobile but honest: rank changes are topology-driven.  This is the only
   * rule that can pull AC down.  Conditioned on the channels mobility cannot
   * explain — v1, v3 and v7 — so that a node inflating its own mobility cannot
   * buy immunity while violating monotonicity, drifting, or forging a two-hop
   * report.  (The 18-rule original R18 omitted the v7 term, which let mobility
   * discount a forgery; that is corrected here.) */
  w[24] = min2(min2(min2(mu_H(v6), mu_L(v1)), mu_L(v3)), mu_L(v7));  zc[24] = 0;
  w[25]  = mu_H(v7);                                                 zc[25]  = 100;

  uint32_t num = 0, den = 1; /* eps = 1 */
  uint8_t r;
  for(r = 1; r <= 25; r++) {
    num += (uint32_t)w[r] * zc[r];
    den += w[r];
  }
  uint8_t ac = (uint8_t)(num / den);  /* AC in 0..100 */
  return (ac>100) ? 100 : ac;  /* AC in 0..100 */
}


static uint8_t
fuzzrid_fuzzy_infer_ac_18rule(uint8_t v1, uint8_t v2, uint8_t v3,
                              uint8_t v4, uint8_t v5, uint8_t v6,
                              uint8_t v7)
{

  FUZZ_PRINTF("[FUZZY-FLAT] Using 18-rules Sugeno inference\n");

   /* Rule weights and singleton consequents (×100) */
  uint8_t  w[19];   /* w[1]..w[18] */
  uint8_t  z[19];   /* z[1]..z[18] */

  /* R1: v1 is H → VH */
  w[1]  = mu_H(v1);                                     z[1]  = 100;
  /* R2: v7 is H → VH */
  w[2]  = mu_H(v7);                                     z[2]  = 100;
  /* R3: v4 is H AND v6 is L → H */
  w[3]  = min2(mu_H(v4), mu_L(v6));                     z[3]  = 75;
  /* R4: v4 is H AND v2 is H → VH */
  w[4]  = min2(mu_H(v4), mu_H(v2));                      z[4]  = 100;
  /* R5: v4 is M AND v2 is H AND v6 is L → H */
  w[5]  = min2(mu_M(v4), min2(mu_H(v2), mu_L(v6)));      z[5]  = 75;
  /* R6: v3 is H AND v6 is L → H */
  w[6]  = min2(mu_H(v3), mu_L(v6));                      z[6]  = 75;
  /* R7: v3 is H AND v2 is H → VH */
  w[7]  = min2(mu_H(v3), mu_H(v2));                      z[7]  = 100;
  /* R8: v3 is M AND v2 is H AND v6 is L → H */
  w[8]  = min2(mu_M(v3), min2(mu_H(v2), mu_L(v6)));      z[8]  = 75;
  /* R9: v5 is H AND v6 is L → H */
  w[9]  = min2(mu_H(v5), mu_L(v6));                      z[9]  = 75;
  /* R10: v5 is H AND v2 is H → VH */
  w[10] = min2(mu_H(v5), mu_H(v2));                      z[10] = 100;
  /* R11: v5 is M AND v2 is H AND v6 is L → H */
  w[11] = min2(mu_M(v5), min2(mu_H(v2), mu_L(v6)));      z[11] = 75;
  /* R12: v6 is H AND v2 is M AND v4 is M → M */
  w[12] = min2(mu_H(v6), min2(mu_M(v2), mu_M(v4)));      z[12] = 50;
  /* R13: v6 is H AND v1 is L AND v4 is L → L */
  w[13] = min2(mu_H(v6), min2(mu_L(v1), mu_L(v4)));      z[13] = 25;
  /* R14: v2 is L AND v3 is L AND v4 is L AND v5 is L AND v7 is L → VL */
  w[14] = min2(min2(min2(mu_L(v2), mu_L(v3)), mu_L(v4)) , 
                              min2(mu_L(v5), mu_L(v7))); z[14] = 0;
  /* R15: v1 is H AND v7 is H → VH (monotonicity violation + forgery mismatch) */
  w[15] = min2(mu_H(v1), mu_H(v7));                      z[15] = 100;
  /* R16: v3 is H AND v7 is H → VH (sustained CUSUM drift + forgery mismatch) */
  w[16] = min2(mu_H(v3), mu_H(v7));                      z[16] = 100;
  /* R17: v3 is H AND v5 is H → H (sustained drift + oscillation, no mobility excuse) */
  w[17] = min2(mu_H(v3), mu_H(v5));                      z[17] = 75;
  /* R18: v6 is H AND v1 is L AND v3 is L → VL (mobile but honest: rank changes are topology-driven) */
  w[18] = min2(mu_H(v6), min2(mu_L(v1), mu_L(v3)));      z[18] = 0;  

  /* Sugeno weighted average: AC = Σ(w*z) / (Σw + ε) */
  uint32_t sum_wz = 0;
  uint32_t sum_w  = 1; /* ε = 1 prevents divide-by-zero */
  uint8_t  r;
  for(r = 1; r <= 18; r++) {
    sum_wz += (uint32_t)w[r] * z[r];
    sum_w  += w[r];
  }
  uint8_t ac = (uint8_t)(sum_wz / sum_w);
  return (ac > 100) ? 100 : ac;   /* Normalise to [0,100] */
}


/* ══ Rev 3.2 rule base — 32 rules (r32) ═══════════════════════════════
 *
 * Coverage-repaired variant of fuzzrid_fuzzy_infer_ac_flat().  The
 * 24-rule base left several attack channels with no firing path at all;
 * this base closes them.  The 24-rule base is deliberately left
 * untouched so the two can be compared on identical traces — switch
 * between them in fuzzrid_fuzzy_infer_ac().
 *
 * Rules R1..R24 are the 24-rule base, carried over verbatim except for
 * the v6 re-gating (delta 1) and R15 (delta 5).  R25..R32 are new.
 *
 * ── Delta 1: the v6 gate ──────────────────────────────────────────────
 * mu_L(v6) is identically zero for ALL v6 >= 50, so ten of the original
 * twenty-four rules switched off completely once the mobility index
 * reached its midpoint.  v6 is ~75% attacker-controllable (MI =
 * 0.30·PSR + 0.45·CV_ETX + 0.15·NCR + 0.10·TR), so holding MI near 50
 * was a free evasion — and a cheaper one than driving v6 into H, which
 * at least has to get past the corroboration conditions on E1.  Those
 * gates now use mu_not_H(v6).  Rules that gate v1 or v7 are untouched:
 * principle (b) still holds, mobility never excuses a monotonicity
 * violation or a two-hop forgery.
 *
 * ── Delta 2: missing membership terms ─────────────────────────────────
 * mu_L reaches 0 at exactly v=50 and mu_H starts from 0 at exactly
 * v=50, so a variable with no M-rule is mute across the whole 40..60
 * band.  v1, v3 and v7 had no M-rule anywhere in the 24-rule base.
 * R26, R30, R31 and R32 add them.
 *
 * ── Delta 3: v5 (oscillation) was unreachable ─────────────────────────
 * No rule tested mu_H(v5), while mu_L(v5) gated eight rules — so
 * oscillating HARDER lowered AC.  R27/R28 restore the 18-rule base's
 * R9/R10 and make the response to v5 monotone again.
 *
 * ── Delta 4: v1=H had no standalone rule ──────────────────────────────
 * v1=H fired only through R18 (needs v4 L), R19 (needs v4 H) or R22
 * (needs v7 H), so a clear monotonicity violation with v4~50 and v7~50
 * scored AC=0.  R25 restores the 18-rule base's R1.
 *
 * ── Delta 5: R15 was inverted ─────────────────────────────────────────
 * "v1 is L AND v5 is M -> 100" assigned maximum confidence *because*
 * monotonicity was fine, and carried no mobility gate at all.  It made
 * v5 non-monotone (v5=50 -> AC 99, but v5=100 -> AC 0) and accused
 * honest mobile nodes.  Demoted to 50 and gated on mobility.
 *
 * ── Delta 6: v4=H had no standalone rule ──────────────────────────────
 * R29 restores the 18-rule base's R3, so a rank jump that lands on a
 * self-consistent forged rank is still caught.
 *
 * !! RE-MEASUREMENT REQUIRED !!
 * Aggregation is a weighted average, not a max, so adding rules shifts
 * the score of input vectors that already scored correctly as well as
 * those that did not.  The measured operating-point table documented
 * above fuzzrid_fuzzy_infer_ml() was derived on the 24-rule base and
 * does NOT apply here — re-derive it from a fresh S1/S2 run before
 * quoting it.
 */

/* Standalone sustained-forgery rule (R33) — ENABLED unconditionally in this
 * rule base (hence the r33 name; the base is 32 rules + R33).
 *
 * v7 can only reach the H band once v7_persist == FUZZRID_V7_PERSIST_MAX,
 * i.e. after four consecutive epoch-matched mismatches — which is the
 * evidence bar that the "v7 accuses only with corroboration" doctrine
 * was standing in for.  Enable this ONLY while v1/R_hat remain anchored
 * to the attacker-supplied parent_rank: in that configuration an
 * attacker that forges its parent's rank downward and then advertises
 * rank = claimed_parent_rank + MHR drives v1 and v3 to zero, so no
 * corroborator can ever fire and R22/R23/R31/R32 are all dead.  Once
 * R_hat and v1 are computed against the independently observed parent
 * rank, corroboration works again and this rule is redundant. */

static uint8_t
fuzzrid_fuzzy_r33_infer_ac_flat(uint8_t v1, uint8_t v2, uint8_t v3,
                                uint8_t v4, uint8_t v5, uint8_t v6,
                                uint8_t v7)
{
  FUZZ_PRINTF("[FUZZY-R33] Using 33-rule Sugeno inference\n");

  uint16_t w[34]; uint8_t zc[34];

  /* ── R1..R24: the 24-rule base ─────────────────────────────────────
   * v6 gates changed from mu_L to mu_not_H (delta 1); R15 rewritten
   * (delta 5).  Everything else is carried over unchanged. */

  /* G124: v3 is H AND v4 is L AND v5 is L AND v6 is not-H -> 75 */
  w[1] = min2(min2(min2(mu_H(v3), mu_L(v4)), mu_L(v5)), mu_not_H(v6));  zc[1] = 75;
  /* G212: v2 is M -> 100 */
  w[2] = mu_M(v2);  zc[2] = 100;
  /* G224: v2 is M AND v5 is L AND v6 is not-H -> 100 */
  w[3] = min2(min2(mu_M(v2), mu_L(v5)), mu_not_H(v6));  zc[3] = 100;
  /* G229: v2 is M AND v4 is L AND v7 is L -> 100 */
  w[4] = min2(min2(mu_M(v2), mu_L(v4)), mu_L(v7));  zc[4] = 100;
  /* G250: v2 is M AND v4 is H AND v5 is L AND v7 is L -> 100 */
  w[5] = min2(min2(min2(mu_M(v2), mu_H(v4)), mu_L(v5)), mu_L(v7));  zc[5] = 100;
  /* G252: v2 is M AND v3 is H -> 100 */
  w[6] = min2(mu_M(v2), mu_H(v3));  zc[6] = 100;
  /* G289: v2 is H AND v5 is L AND v6 is not-H AND v7 is L -> 100 */
  w[7] = min2(min2(min2(mu_H(v2), mu_L(v5)), mu_not_H(v6)), mu_L(v7));  zc[7] = 100;
  /* G298: v2 is H AND v4 is L AND v6 is not-H -> 75 */
  w[8] = min2(min2(mu_H(v2), mu_L(v4)), mu_not_H(v6));  zc[8] = 75;
  /* G301: v2 is H AND v4 is L AND v6 is not-H AND v7 is L -> 100 */
  w[9] = min2(min2(min2(mu_H(v2), mu_L(v4)), mu_not_H(v6)), mu_L(v7));  zc[9] = 100;
  /* G316: v2 is H AND v4 is M AND v5 is L AND v6 is not-H -> 75 */
  w[10] = min2(min2(min2(mu_H(v2), mu_M(v4)), mu_L(v5)), mu_not_H(v6));  zc[10] = 75;
  /* G336: v2 is H AND v3 is H AND v5 is L AND v7 is L -> 75 */
  w[11] = min2(min2(min2(mu_H(v2), mu_H(v3)), mu_L(v5)), mu_L(v7));  zc[11] = 75;
  /* G337: v2 is H AND v3 is H AND v5 is L AND v6 is not-H -> 100 */
  w[12] = min2(min2(min2(mu_H(v2), mu_H(v3)), mu_L(v5)), mu_not_H(v6));  zc[12] = 100;
  /* G341: v2 is H AND v3 is H AND v4 is L AND v7 is L -> 100 */
  w[13] = min2(min2(min2(mu_H(v2), mu_H(v3)), mu_L(v4)), mu_L(v7));  zc[13] = 100;
  /* G348: v2 is H AND v3 is H AND v4 is M AND v6 is not-H -> 100 */
  w[14] = min2(min2(min2(mu_H(v2), mu_H(v3)), mu_M(v4)), mu_not_H(v6));  zc[14] = 100;
  /* R15 (rewritten, delta 5): v5 is M AND v6 is not-H -> 50.
   * Was "v1 is L AND v5 is M -> 100": max confidence *because*
   * monotonicity was clean, and ungated on mobility. */
  w[15] = min2(mu_M(v5), mu_not_H(v6));  zc[15] = 50;
  /* G509: v1 is L AND v2 is H AND v7 is L -> 100 */
  w[16] = min2(min2(mu_L(v1), mu_H(v2)), mu_L(v7));  zc[16] = 100;
  /* G519: v1 is L AND v2 is H AND v5 is L AND v6 is not-H -> 100 */
  w[17] = min2(min2(min2(mu_L(v1), mu_H(v2)), mu_L(v5)), mu_not_H(v6));  zc[17] = 100;
  /* G564: v1 is H AND v4 is L AND v7 is L -> 75
   * [no v6 gate: mobility must never excuse a monotonicity violation] */
  w[18] = min2(min2(mu_H(v1), mu_L(v4)), mu_L(v7));  zc[18] = 75;
  /* G577: v1 is H AND v4 is H AND v7 is L -> 100 */
  w[19] = min2(min2(mu_H(v1), mu_H(v4)), mu_L(v7));  zc[19] = 100;
  /* G678: v1 is H AND v2 is H AND v4 is H AND v7 is L -> 100 */
  w[20] = min2(min2(min2(mu_H(v1), mu_H(v2)), mu_H(v4)), mu_L(v7));  zc[20] = 100;
  /* R6: v3 is H AND v6 is not-H -> 75 */
  w[21] = min2(mu_H(v3), mu_not_H(v6));  zc[21] = 75;
  /* R15(orig): v1 is H AND v7 is H -> 100 (monotonicity violation + forgery) */
  w[22] = min2(mu_H(v1), mu_H(v7));  zc[22] = 100;
  /* R16(orig): v3 is H AND v7 is H -> 100 (sustained drift + forgery) */
  w[23] = min2(mu_H(v3), mu_H(v7));  zc[23] = 100;
  /* E1: v6 is H AND v1 is L AND v3 is L AND v7 is L -> 0.
   * The only rule that pulls AC down.  Still conditioned on the channels
   * mobility cannot explain, so inflating MI buys no immunity. */
  w[24] = min2(min2(min2(mu_H(v6), mu_L(v1)), mu_L(v3)), mu_L(v7));  zc[24] = 0;

  /* ── R25..R32: coverage repairs ────────────────────────────────────*/

  /* R25 (delta 4, = 18-rule R1): v1 is H -> 100.
   * A hard protocol violation — rank below parent_rank + MHR.  Not
   * explainable by mobility, so no v6 gate (principle b). */
  w[25] = mu_H(v1);  zc[25] = 100;
  /* R26 (delta 2): v1 is M -> 50.  Fills the v1 40..60 band, where
   * mu_L and mu_H are both zero and R16..R22 all die. */
  w[26] = mu_M(v1);  zc[26] = 50;

  /* R27 (delta 3, = 18-rule R9): v5 is H AND v6 is not-H -> 75 */
  w[27] = min2(mu_H(v5), mu_not_H(v6));  zc[27] = 75;
  /* R28 (delta 3, = 18-rule R10): v5 is H AND v2 is H -> 100 */
  w[28] = min2(mu_H(v5), mu_H(v2));  zc[28] = 100;

  /* R29 (delta 6, = 18-rule R3): v4 is H AND v6 is not-H -> 75 */
  w[29] = min2(mu_H(v4), mu_not_H(v6));  zc[29] = 75;

  /* R30 (delta 2): v3 is M AND v6 is not-H -> 50.  Fills the v3 40..60
   * band; drift IS mobility-explainable, so the gate is correct here. */
  w[30] = min2(mu_M(v3), mu_not_H(v6));  zc[30] = 50;

  /* R31/R32 (delta 2): moderate two-hop forgery.  Keeps the
   * corroboration doctrine of R22/R23 but at the M level and with a
   * not-L corroborator (M or H), so a real forgery that is partially
   * masked by the eps clamp — or still climbing the v7_persist ramp —
   * is no longer invisible.  No v6 gate (principle b). */
  w[31] = min2(mu_M(v7), max2(mu_M(v1), mu_H(v1)));  zc[31] = 75;
  w[32] = min2(mu_M(v7), max2(mu_M(v3), mu_H(v3)));  zc[32] = 75;

  /* R33: v7 is H -> 100.  See the comment above the macro. */
  w[33] = mu_H(v7);  zc[33] = 100;


  /* Sugeno weighted average: AC = Σ(w*z) / (Σw + ε) */
  uint32_t num = 0, den = 1; /* eps = 1 */
  uint8_t r;
  for(r = 1; r <= 33; r++) {
    num += (uint32_t)w[r] * zc[r];
    den += w[r];
  }
  uint8_t ac = (uint8_t)(num / den);
  return (ac > 100) ? 100 : ac;  /* AC in 0..100 */
}