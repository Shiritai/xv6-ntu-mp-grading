#!/bin/bash
set -e

if command -v uv &> /dev/null; then
    PYTHON_RUN="uv run"
else
    PYTHON_RUN="python3"
fi

# --- Parameter Parsing ---
USAGE="Usage: $0 --mp <mp_id> --students <students_json_file> [--wait-interval <seconds>] [--max-attempts <attempts>] [--init-wait <seconds>] [--no-wait] [--force]"

MP_ID=""
STUDENTS_FILE=""
WAIT_INTERVAL=15
MAX_ATTEMPTS=20
INIT_WAIT=180
NO_WAIT=false
FORCE=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --mp) MP_ID="$2"; shift ;;
        --students) STUDENTS_FILE="$2"; shift ;;
        --wait-interval) WAIT_INTERVAL="$2"; shift ;;
        --max-attempts) MAX_ATTEMPTS="$2"; shift ;;
        --init-wait) INIT_WAIT="$2"; shift ;;
        --no-wait) NO_WAIT=true ;;
        --force) FORCE=true ;;
        *) echo "Unknown parameter passed: $1"; echo "$USAGE"; exit 1 ;;
    esac
    shift
done

if [[ -z "$MP_ID" || -z "$STUDENTS_FILE" ]]; then
    echo "Error: --mp and --students arguments are required."
    echo "$USAGE"
    exit 1
fi

SDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
GRADING_WORKSPACE="$(dirname "$SDIR")"

echo "=================================================="
echo "Starting full auto-grading process - ${MP_ID}"
echo "Students roster: ${STUDENTS_FILE}"
echo "Workspace dir: ${GRADING_WORKSPACE}"
echo "=================================================="

# 1. Trigger CI Grading (Inject Payload)
TARGETS_FILE="${GRADING_WORKSPACE}/${MP_ID}/result/grading_targets.json"
echo "[Phase 1] Injecting Private Tests and Triggering GitHub Actions..."

FORCE_ARG=""
if [[ "$FORCE" == true ]]; then
    FORCE_ARG="--force"
fi

$PYTHON_RUN "${SDIR}/trigger_grading.py" --mp "${MP_ID}" --students "${STUDENTS_FILE}" --grading-dir "${GRADING_WORKSPACE}" ${FORCE_ARG}

if [[ ! -f "$TARGETS_FILE" ]]; then
    echo "❌ Error: ${TARGETS_FILE} was not successfully generated. Aborting grading."
    exit 1
fi

if [[ "$NO_WAIT" == true ]]; then
    echo "=================================================="
    echo "✅ [Phase 1] Trigger complete! You have enabled --no-wait mode."
    echo "All students' CI are now running in parallel in the background."
    echo "You can manually crawl the scores later at any time using the following command:"
    echo "  $PYTHON_RUN ${SDIR}/grading_crawler.py --targets ${TARGETS_FILE} --output final_grades_${MP_ID}.json --reports-dir reports_${MP_ID}"
    echo "=================================================="
    exit 0
fi

# 2. Wait and Crawl
OUTPUT_JSON="${GRADING_WORKSPACE}/${MP_ID}/result/final_grades.json"
OUTPUT_CSV="${GRADING_WORKSPACE}/${MP_ID}/result/final_grades.csv"
REPORTS_DIR="${GRADING_WORKSPACE}/${MP_ID}/result/reports"
TMP_JSON=$(mktemp /tmp/grading_${MP_ID}_XXXXXX.json)
trap "rm -f ${TMP_JSON} ${TMP_JSON%.json}.csv" EXIT
echo ""
echo "[Phase 2] Waiting for CI to finish and crawling scores..."

# Initial wait for CI pipelines to have a chance to complete
if [ "$INIT_WAIT" -gt 0 ]; then
    echo "Waiting ${INIT_WAIT}s for CI pipelines to run before first crawl..."
    REMAINING_WAIT=$INIT_WAIT
    while [ "$REMAINING_WAIT" -gt 0 ]; do
        MINS=$((REMAINING_WAIT / 60))
        SECS=$((REMAINING_WAIT % 60))
        printf "\r⏳ %02d:%02d remaining..." "$MINS" "$SECS"
        sleep 1
        ((REMAINING_WAIT--))
    done
    printf "\r✅ Initial wait complete.            \n"
fi

ATTEMPT=1
SUCCESS=false

CACHE_ARG=""
while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    echo "[Attempt $ATTEMPT / $MAX_ATTEMPTS] Crawling scores..."
    $PYTHON_RUN "${SDIR}/grading_crawler.py" --targets "${TARGETS_FILE}" --output "${TMP_JSON}" --reports-dir "${REPORTS_DIR}" ${CACHE_ARG} >| crawler.log 2>&1 || true
    CACHE_ARG="--cache ${TMP_JSON}"

    # Check if all runs are complete:
    # - "In Progress" = CI still running, worth retrying
    # - "No Run / Missing" = no workflow exists, permanent failure, don't retry for these
    if grep -q "Grading finished" crawler.log && ! grep -q "\"In Progress\"" "${TMP_JSON}"; then
        if grep -q "\"No Run / Missing\"" "${TMP_JSON}"; then
            echo "⚠️ All CI runs finished, but some students have no matching workflow run (marked 'No Run / Missing')."
        fi
        echo "✅ All scores successfully crawled!"
        SUCCESS=true
        break
    else
        # Check API rate limit before retrying
        REMAINING=$(gh api rate_limit --jq '.resources.core.remaining' 2>/dev/null || echo "0")
        IFS=$'\t' read -r PENDING_COUNT NEEDED PENDING_NAMES <<< "$($PYTHON_RUN "${SDIR}/check_progress.py" "${TMP_JSON}" 2>/dev/null)"
        if [ "$REMAINING" -lt "$NEEDED" ]; then
            echo "⛔ API rate limit too low (${REMAINING} remaining, ~${NEEDED} needed). Stopping retries."
            break
        fi
        echo "⏳ CIs of students ${PENDING_NAMES} still in progress. Waiting for ${WAIT_INTERVAL} seconds before retrying... (API: ${REMAINING} remaining)"
        sleep "$WAIT_INTERVAL"
    fi
    ((ATTEMPT++))
done

# Copy final results from tmp to persistent storage
TMP_CSV="${TMP_JSON%.json}.csv"
cp "${TMP_JSON}" "${OUTPUT_JSON}"
cp "${TMP_CSV}" "${OUTPUT_CSV}" 2>/dev/null || true

if [ "$SUCCESS" = false ]; then
    echo "⚠️ Warning: Maximum attempts reached ($MAX_ATTEMPTS). Some students' CI might have failed or timed out."
    echo "The system has saved the best results retrieved so far to ${OUTPUT_JSON} and ${OUTPUT_CSV}."
else
    echo "🎉 Fully automated grading process successfully concluded!"
fi

cat crawler.log | grep -A 10 "SUCCESS" || true
echo "=================================================="
echo "📊 Results aggregated at:"
echo " - JSON: ${OUTPUT_JSON}"
echo " - CSV:  ${OUTPUT_CSV}"
echo " - Detailed Artifacts backup directory: ${REPORTS_DIR}/"
echo "=================================================="
