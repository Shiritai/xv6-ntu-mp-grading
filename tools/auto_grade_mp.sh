#!/bin/bash
set -e

if command -v uv &> /dev/null; then
    PYTHON_RUN="uv run"
else
    PYTHON_RUN="python3"
fi

# --- Parameter Parsing ---
USAGE="Usage: $0 --mp <mp_id> [--students <students_json_file> | --repo <owner/repo>] [--prefix <course_prefix>] [--force-push] [--force-fetch] [--repair] [--exclude-repo <repo1,repo2>]"

MP_ID=""
STUDENTS_FILE=""
REPO=""
PREFIX="ntuos2026"
FORCE_PUSH=false
FORCE_FETCH=false
REPAIR=false
EXCLUDE_REPO=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --mp) MP_ID="$2"; shift ;;
        --students) STUDENTS_FILE="$2"; shift ;;
        --repo) REPO="$2"; shift ;;
        --prefix) PREFIX="$2"; shift ;;
        --force-push) FORCE_PUSH=true ;;
        --force-fetch) FORCE_FETCH=true ;;
        --repair) REPAIR=true ;;
        --exclude-repo) EXCLUDE_REPO="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; echo "$USAGE"; exit 1 ;;
    esac
    shift
done

if [[ -z "$MP_ID" ]]; then
    echo "Error: --mp argument is required."
    echo "$USAGE"
    exit 1
fi

if [[ -z "$STUDENTS_FILE" && -z "$REPO" ]]; then
    echo "Error: Either --students or --repo argument is required."
    echo "$USAGE"
    exit 1
fi

SDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
GRADING_WORKSPACE="$(dirname "$SDIR")"

echo "=================================================="
echo "Starting full auto-grading process - ${MP_ID}"
echo "Students roster: ${STUDENTS_FILE}"
echo "Workspace dir: ${GRADING_WORKSPACE}"
echo "Force Push: ${FORCE_PUSH}"
echo "Force Fetch: ${FORCE_FETCH}"
echo "Repair Mode: ${REPAIR}"
echo "Exclude Repo: ${EXCLUDE_REPO}"
echo "=================================================="

# 1. Trigger CI Grading (Inject Payload)
TARGETS_FILE="${GRADING_WORKSPACE}/${MP_ID}/result/grading_targets.json"
# Ensure we start with a clean state for push detection
rm -f "${GRADING_WORKSPACE}/${MP_ID}/result/.push_occurred"
echo "[Phase 1] Injecting Private Tests and Triggering GitHub Actions..."

FORCE_PUSH_ARG=""
if [[ "$FORCE_PUSH" == true ]]; then
    FORCE_PUSH_ARG="--force-push"
fi

TARGET_ARG=""
if [[ -n "$STUDENTS_FILE" ]]; then
    TARGET_ARG="--students ${STUDENTS_FILE}"
elif [[ -n "$REPO" ]]; then
    TARGET_ARG="--repo ${REPO}"
fi

REPAIR_ARG=""
if [[ "$REPAIR" == true ]]; then
    REPAIR_ARG="--repair"
fi

EXCLUDE_ARG=""
if [[ -n "$EXCLUDE_REPO" ]]; then
    EXCLUDE_ARG="--exclude-repo ${EXCLUDE_REPO}"
fi

$PYTHON_RUN "${SDIR}/trigger_grading.py" --mp "${MP_ID}" ${TARGET_ARG} --grading-dir "${GRADING_WORKSPACE}" ${FORCE_PUSH_ARG} ${REPAIR_ARG} --branch "${PREFIX}/${MP_ID}" ${EXCLUDE_ARG}

if [[ ! -f "$TARGETS_FILE" ]]; then
    echo "❌ Error: ${TARGETS_FILE} was not successfully generated. Aborting grading."
    exit 1
fi

PUSH_SIGNAL_FILE="${GRADING_WORKSPACE}/${MP_ID}/result/.push_occurred"
if [[ -f "$PUSH_SIGNAL_FILE" ]]; then
    echo ""
    echo "=================================================="
    echo "🚀 [Phase 1] New Push or Force Trigger detected!"
    echo "   GitHub Actions have been triggered. Please wait for CI to finish."
    echo "   Automatically skipping [Phase 2] Crawler."
    echo "=================================================="
    rm -f "$PUSH_SIGNAL_FILE"
    exit 0
fi

# 2. Wait and Crawl
OUTPUT_JSON="${GRADING_WORKSPACE}/${MP_ID}/result/final_grades.json"
OUTPUT_CSV="${GRADING_WORKSPACE}/${MP_ID}/result/final_grades.csv"
REPORTS_DIR="${GRADING_WORKSPACE}/${MP_ID}/result/reports"
TMP_JSON=$(mktemp /tmp/grading_${MP_ID}_XXXXXX.json)
# shellcheck disable=SC2064
trap "rm -f '${TMP_JSON}' '${TMP_JSON%.json}.csv'" EXIT
echo ""
echo "[Phase 2] Fetching current scores from GitHub Actions..."

FORCE_FETCH_ARG=""
if [[ "$FORCE_FETCH" == true ]]; then
    FORCE_FETCH_ARG="--force-fetch"
fi

$PYTHON_RUN "${SDIR}/grading_crawler.py" --targets "${TARGETS_FILE}" --output "${TMP_JSON}" --reports-dir "${REPORTS_DIR}" --cache "${OUTPUT_JSON}" ${FORCE_FETCH_ARG} >| crawler.log 2>&1 || true

# Copy final results from tmp to persistent storage
TMP_CSV="${TMP_JSON%.json}.csv"
cp "${TMP_JSON}" "${OUTPUT_JSON}" 2>/dev/null || true
cp "${TMP_CSV}" "${OUTPUT_CSV}" 2>/dev/null || true

IFS=$'\t' read -r _PENDING_COUNT _NEEDED PENDING_NAMES <<< "$($PYTHON_RUN "${SDIR}/check_progress.py" "${TMP_JSON}" 2>/dev/null || echo -e "0\t0\t")"

echo ""
if [ "$_PENDING_COUNT" -gt 0 ] || grep -q "\"In Progress\"" "${TMP_JSON}" 2>/dev/null; then
    echo "=================================================="
    echo "⏳ Some CI runs are still in progress!"
    if [ -n "$PENDING_NAMES" ] && [ "$PENDING_NAMES" != " " ]; then
        echo "Pending: ${PENDING_NAMES}"
    fi
    echo "⚠️ Latest score snapshots exported to ${OUTPUT_CSV}."
    echo "💡 Please run the same command later to gather final results."
    echo "=================================================="
else
    if grep -q "Grading finished" crawler.log; then
        if grep -q "\"No Run / Missing\"" "${TMP_JSON}"; then
            echo "⚠️ All CI runs stopped, but some students have no workflow runs (marked 'No Run / Missing')."
        fi
        echo "=================================================="
        echo "🎉 All student CI runs have finished! Grading complete."
        echo "=================================================="
    else
        echo "⚠️ Crawler exited unexpectedly. Please check crawler.log for details."
    fi
fi

cat crawler.log | grep -A 10 "SUCCESS" || true
echo "=================================================="
echo "📊 Results aggregated at:"
echo " - JSON: ${OUTPUT_JSON}"
echo " - CSV:  ${OUTPUT_CSV}"
echo " - Detailed Artifacts backup directory: ${REPORTS_DIR}/"
echo "=================================================="
