# config.sh -- settings shared by run_cars.sh and run_thfis.sh
# ============================================================
# Sourced by both runners, so CARS and T-HFIS always run with the same values.
# Edit here, or override one run with VAR=value ./run_cars.sh (or ./run_thfis.sh).
# QUICK=1 swaps in tiny pop/gens/sample sizes for a smoke test.

QUICK="${QUICK:-0}"
if [ "$QUICK" = 1 ]; then q() { echo "$1"; }; else q() { echo "$2"; }; fi

# ---- shared by both methods -------------------------------------------------
SEEDS="${SEEDS:-${SEED:-42}}"               # space-separated list
MIN_RULES="${MIN_RULES:-12}"                # 12
MAX_RULES="${MAX_RULES:-35}"                # 35
MF_HIGH="${MF_HIGH:-50,80}"                 # High MF: 0 at 50 -> 100 at 80
AC_THR="${AC_THR:-65}"                      # FUZZRID_TAU_Q_PCT
TEST_FRAC="${TEST_FRAC:-0.3}"               # 30% test data
CONF_MARGIN="${CONF_MARGIN:-0.15}"          # confidence margin for rule selection
POP="${POP:-$(q 20 150)}"                   # select + finalize
GENS="${GENS:-$(q 5 250)}"                  # number of generations
TRAIN_SAMPLE="${TRAIN_SAMPLE:-$(q 3000 40000)}" # number of training samples
LOSO_POP="${LOSO_POP:-$(q 20 80)}"          # loso
LOSO_GENS="${LOSO_GENS:-$(q 5 120)}"        # number of generations for loso
LOSO_TRAIN="${LOSO_TRAIN:-$(q 3000 30000)}" # number of training samples for loso
CSV_ROOT="${CSV_ROOT:-data/processed}"      # path to processed CSV data
# Attack start for labelling is fixed at 300 s in common/real_data.py.

# ---- method-specific (the pools are built differently) -----------------------
CARS_MAX_TERMS="${CARS_MAX_TERMS:-4}"           # max number of terms in a CARS rule
CARS_MIN_SUPPORT="${CARS_MIN_SUPPORT:-0.005}"   # min support for a CARS rule
THFIS_MIN_SUPPORT="${THFIS_MIN_SUPPORT:-0.01}"  # min support for a T-HFIS unit rule
