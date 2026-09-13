#!/bin/bash
# Run the full VulnNotes lab sequence:
#   Phase 1: baseline traffic   (normal_traffic.py)
#   Phase 2: API enumeration    (enumerate_api.py)
#   Phase 3: attacks            (exploit_*.py)
#
# Logs to /var/log/notes-scripts.log (falls back to <scriptdir>/notes-scripts.log).
#
# Usage:
#   ./run_all.sh [BASE_URL]                # default http://localhost:8000
#   BASELINE_DURATION=180 ./run_all.sh ... # override baseline length (default 60s)

BASE_URL="${1:-http://localhost:8000}"
BASELINE_DURATION="${BASELINE_DURATION:-60}"

# prefer /var/log, fall back to the script dir if not writable
LOG_FILE="/var/log/notes-scripts.log"
if ! ( : > "$LOG_FILE" ) 2>/dev/null; then
    LOG_FILE="$(cd "$(dirname "$0")" && pwd)/notes-scripts.log"
fi
DIR="$(cd "$(dirname "$0")" && pwd)"

now() { date '+%Y-%m-%d %H:%M:%S'; }

# run_phase NAME SCRIPT TIMEOUT_S [extra args...]
run_phase() {
    local name="$1" script="$2" timeout_s="$3"; shift 3
    if [ ! -f "$DIR/$script" ]; then
        echo "[$(now)] $name: NOT FOUND ($script)" >> "$LOG_FILE"
        return
    fi
    if timeout "$timeout_s" python3 "$DIR/$script" --base-url "$BASE_URL" "$@" >> "$LOG_FILE" 2>&1; then
        echo "[$(now)] $name: SUCCESS" >> "$LOG_FILE"
    else
        local rc=$?
        if [ "$rc" -eq 124 ]; then
            echo "[$(now)] $name: TIMEOUT (${timeout_s}s)" >> "$LOG_FILE"
        else
            echo "[$(now)] $name: FAILED (rc=$rc)" >> "$LOG_FILE"
        fi
    fi
}

{
    echo "============================================================"
    echo "[$(now)] VulnNotes lab run — target: $BASE_URL  baseline: ${BASELINE_DURATION}s"
    echo "============================================================"

    # timeout must exceed the baseline duration (duration + 30s grace)
    echo "[$(now)] ── Phase 1: baseline traffic ──"
    run_phase "normal_traffic" "normal_traffic.py" $((BASELINE_DURATION + 30)) --duration "$BASELINE_DURATION"

    echo "[$(now)] ── Phase 2: API enumeration ──"
    run_phase "enumerate_api" "enumerate_api.py" 60

    echo "[$(now)] ── Phase 3: attacks ──"
    run_phase "default_creds"  "exploit_default_creds.py" 60
    run_phase "jwt_forge"      "exploit_jwt.py" 60
    run_phase "bola_rw"        "exploit_bola.py" 60
    run_phase "bola_delete"    "exploit_bola_delete.py" 60

    echo "[$(now)] VulnNotes lab run complete"
} >> "$LOG_FILE" 2>&1

echo "Done. Log: $LOG_FILE"
tail -n 20 "$LOG_FILE"
