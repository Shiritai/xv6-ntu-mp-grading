#!/bin/bash
set -e

# --- Parameter Parsing ---
USAGE="Usage: $0 --mp <mp_id> --students <students_json_file> [--wait-interval <seconds>] [--max-attempts <attempts>] [--no-wait] [--force]"

MP_ID=""
STUDENTS_FILE=""
WAIT_INTERVAL=15
MAX_ATTEMPTS=40
NO_WAIT=false
FORCE=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --mp) MP_ID="$2"; shift ;;
        --students) STUDENTS_FILE="$2"; shift ;;
        --wait-interval) WAIT_INTERVAL="$2"; shift ;;
        --max-attempts) MAX_ATTEMPTS="$2"; shift ;;
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
TARGETS_FILE="../${MP_ID}/result/grading_targets.json"
echo "[Phase 1] Injecting Private Tests and Triggering GitHub Actions..."

FORCE_ARG=""
if [[ "$FORCE" == true ]]; then
    FORCE_ARG="--force"
fi

python3 "${SDIR}/trigger_grading.py" --mp "${MP_ID}" --students "${STUDENTS_FILE}" --grading-dir "${GRADING_WORKSPACE}" ${FORCE_ARG}

if [[ ! -f "$TARGETS_FILE" ]]; then
    echo "❌ Error: ${TARGETS_FILE} was not successfully generated. Aborting grading."
    exit 1
fi

if [[ "$NO_WAIT" == true ]]; then
    echo "=================================================="
    echo "✅ [Phase 1] Trigger complete! You have enabled --no-wait mode."
    echo "All students' CI are now running in parallel in the background."
    echo "You can manually crawl the scores later at any time using the following command:"
    echo "  python3 ${SDIR}/grading_crawler.py --targets ${TARGETS_FILE} --output final_grades_${MP_ID}.json --reports-dir reports_${MP_ID}"
    echo "=================================================="
    exit 0
fi

# 2. Wait and Crawl
OUTPUT_JSON="../${MP_ID}/result/final_grades.json"
OUTPUT_CSV="../${MP_ID}/result/final_grades.csv"
REPORTS_DIR="../${MP_ID}/result/reports"
echo ""
echo "[Phase 2] Waiting for CI to finish and crawling scores..."

ATTEMPT=1
SUCCESS=false

while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    echo "[Attempt $ATTEMPT / $MAX_ATTEMPTS] Crawling scores..."
    python3 "${SDIR}/grading_crawler.py" --targets "${TARGETS_FILE}" --output "${OUTPUT_JSON}" --reports-dir "${REPORTS_DIR}" > crawler.log 2>&1
    
    # Check if all runs are complete (No missing or running status in output JSON)
    if grep -q "Grading finished" crawler.log && ! grep -q "\"No Run / Missing\"" "${OUTPUT_JSON}"; then
        echo "✅ All scores successfully crawled!"
        SUCCESS=true
        break
    else
        echo "⏳ Some students' CI or Artifacts are not ready yet. Waiting for ${WAIT_INTERVAL} seconds before retrying..."
        sleep "$WAIT_INTERVAL"
    fi
    ((ATTEMPT++))
done

if [ "$SUCCESS" = false ]; then
    echo "⚠️ Warning: Maximum attempts reached ($MAX_ATTEMPTS). Some students' CI might have failed or timed out."
    echo "The system has saved the best results retrieved so far to ${OUTPUT_JSON} and ${OUTPUT_CSV}."
else
    echo "🎉 Fully automated grading process successfully concluded!"
fi

cat crawler.log | grep -A 10 "SUCCESS" || true
echo "=================================================="
echo "📊 結果已匯總至:"
echo " - JSON: $(pwd)/${OUTPUT_JSON}"
echo " - CSV:  $(pwd)/${OUTPUT_CSV}"
echo " - 詳細 Artifact 備份目錄: $(pwd)/${REPORTS_DIR}/"
echo "=================================================="
