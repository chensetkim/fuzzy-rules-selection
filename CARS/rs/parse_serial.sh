#!/usr/bin/env bash
#
# parse_serial.sh -- parse every Cooja log in a folder into an events CSV
# =======================================================================
# For each *.log directly inside $LOG_PATH -- sub-folders are not searched --
# run parse_serial.py and write a CSV of the same name into $OUTPUT_PATH:
#
#   $LOG_PATH/foo.log  ->  $OUTPUT_PATH/foo.csv
#
# Edit the two paths below, or override them per run:
#
#   LOG_PATH=../../Data/Mobile/r1/6 OUTPUT_PATH=../../Data/csv/mobile/r1/6 ./parse_serial.sh
#
set -euo pipefail

# Resolve paths relative to this script, not the caller's cwd.
cd "$(dirname "$0")"
#=======================================================================#
# Run script with sub sub-folders.
# for r in r2 r3; do for n in 3 6 9; do
#   LOG_PATH=../../Data/Mobile/$r/$n OUTPUT_PATH=../../Data/csv/mobile/$r/$n ./parse_serial.sh
# done; done
#=======================================================================#

LOG_PATH="${LOG_PATH:-../../Data/Static/r3/3}"        # folder holding the *.log files
OUTPUT_PATH="${OUTPUT_PATH:-../../Data/csv/Static/r3/3}" # folder to write the *.csv files
TIME_UNIT="${TIME_UNIT:-us}"                        # unit of the Cooja script's `time`

#=======================================================================#
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# Prefer a project venv (CARS/.venv, then repo-root .venv); else system python3.
PY=""
for cand in ../.venv ../../.venv; do
    if   [ -x "$cand/bin/python" ];         then PY="$cand/bin/python";         break
    elif [ -x "$cand/Scripts/python.exe" ]; then PY="$cand/Scripts/python.exe"; break
    fi
done
[ -n "$PY" ] || PY=python3

[ -d "$LOG_PATH" ] || die "log folder not found: $LOG_PATH"

# -maxdepth 1: only the *.log sitting directly in $LOG_PATH. Sub-folders are
# their own run -- point LOG_PATH/OUTPUT_PATH at r1/6, r1/9, ... in turn.
mapfile -t LOGS < <(find "$LOG_PATH" -maxdepth 1 -type f -name '*.log' | sort)
[ "${#LOGS[@]}" -gt 0 ] || die "no .log files directly in $LOG_PATH (sub-folders are not searched)"

mkdir -p "$OUTPUT_PATH"
printf '\n\033[1m== %d logs: %s -> %s ==\033[0m\n' "${#LOGS[@]}" "$LOG_PATH" "$OUTPUT_PATH"

FAILED=()
for LOG in "${LOGS[@]}"; do
    NAME="$(basename "$LOG")"; NAME="${NAME%.*}"   # foo.log -> foo
    CSV="$OUTPUT_PATH/$NAME.csv"
    printf '\n\033[1m--- %s ---\033[0m\n' "$LOG"

    # Attacker motes announce themselves at boot. The mote column is "ID:<n>"
    # in a captured log and bare "<n>" in the Cooja script's own output; strip
    # the prefix or `sort -n` collapses every attacker to a single entry.
    ATK_NODES="$(awk '/Starting 2H-FuzzRID attacker/ { id = $2; sub(/^ID:/, "", id); print id }' "$LOG" \
                 | sort -n -u | paste -sd, -)"
    if [ -z "$ATK_NODES" ]; then
        printf '\033[33mskip\033[0m no attacker motes found\n' >&2
        FAILED+=("$LOG")
        continue
    fi
    echo "attackers : $ATK_NODES"

    # A bad log must not abandon the rest, so collect failures and report them
    # after the loop instead of letting `set -e` abort here.
    "$PY" parse_serial.py "$LOG" "$CSV" \
        --time-unit "$TIME_UNIT" \
        --atk-nodes "$ATK_NODES" || FAILED+=("$LOG")
done

if [ "${#FAILED[@]}" -gt 0 ]; then
    printf '\n\033[31m%d/%d logs failed:\033[0m\n' "${#FAILED[@]}" "${#LOGS[@]}" >&2
    printf '  %s\n' "${FAILED[@]}" >&2
    exit 1
fi
printf '\n\033[1m== done: %d CSVs in %s ==\033[0m\n' "${#LOGS[@]}" "$OUTPUT_PATH"
#=======================================================================#