#!/bin/bash
set -e

if command -v uv &> /dev/null; then
    PYTHON_RUN="uv run"
else
    PYTHON_RUN="python3"
fi

# --- Parameter Parsing ---
USAGE="Usage: $0 --mp <mp_id> [--students <students_json_file> | --repo <owner/repo>] [--prefix <course_prefix>] [--force]"

MP_ID=""
STUDENTS_FILE=""
REPO=""
PREFIX="ntuos2026"
FORCE=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --mp) MP_ID="$2"; shift ;;
        --students) STUDENTS_FILE="$2"; shift ;;
        --repo) REPO="$2"; shift ;;
        --prefix) PREFIX="$2"; shift ;;
        --force) FORCE=true ;;
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
echo "=================================================="

# 1. Trigger CI Grading (Inject Payload)
TARGETS_FILE="${GRADING_WORKSPACE}/${MP_ID}/result/grading_targets.json"
echo "[Phase 1] Injecting Private Tests and Triggering GitHub Actions..."

FORCE_ARG=""
if [[ "$FORCE" == true ]]; then
    FORCE_ARG="--force"
fi

TARGET_ARG=""
if [[ -n "$STUDENTS_FILE" ]]; then
    TARGET_ARG="--students ${STUDENTS_FILE}"
elif [[ -n "$REPO" ]]; then
    TARGET_ARG="--repo ${REPO}"
fi

$PYTHON_RUN "${SDIR}/trigger_grading.py" --mp "${MP_ID}" ${TARGET_ARG} --grading-dir "${GRADING_WORKSPACE}" ${FORCE_ARG} --branch "${PREFIX}/${MP_ID}"

if [[ ! -f "$TARGETS_FILE" ]]; then
    echo "❌ Error: ${TARGETS_FILE} was not successfully generated. Aborting grading."
    exit 1
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

$PYTHON_RUN "${SDIR}/grading_crawler.py" --targets "${TARGETS_FILE}" --output "${TMP_JSON}" --reports-dir "${REPORTS_DIR}" >| crawler.log 2>&1 || true

# Copy final results from tmp to persistent storage
TMP_CSV="${TMP_JSON%.json}.csv"
cp "${TMP_JSON}" "${OUTPUT_JSON}" 2>/dev/null || true
cp "${TMP_CSV}" "${OUTPUT_CSV}" 2>/dev/null || true

IFS=$'\t' read -r _PENDING_COUNT _NEEDED PENDING_NAMES <<< "$($PYTHON_RUN "${SDIR}/check_progress.py" "${TMP_JSON}" 2>/dev/null || echo -e "0\t0\t")"

echo ""
if [ "$_PENDING_COUNT" -gt 0 ] || grep -q "\"In Progress\"" "${TMP_JSON}" 2>/dev/null; then
    echo "=================================================="
    echo "⏳ 尚有 CI 仍在背景執行中！"
    if [ -n "$PENDING_NAMES" ] && [ "$PENDING_NAMES" != " " ]; then
        echo "尚未完成名單: ${PENDING_NAMES}"
    fi
    echo "⚠️ 目前已將「最新成績快照」匯出至 ${OUTPUT_CSV}。"
    echo "💡 請稍後重新執行相同指令，以收齊所有最終成績。"
    echo "=================================================="
else
    if grep -q "Grading finished" crawler.log; then
        if grep -q "\"No Run / Missing\"" "${TMP_JSON}"; then
            echo "⚠️ 所有 CI 皆已停止執行，但部分學生沒有讀到對應的工作流 (標示為 'No Run / Missing')."
        fi
        echo "=================================================="
        echo "🎉 所有學生的 CI 皆已執行完畢！全自動化評分圓滿結束。"
        echo "=================================================="
    else
        echo "⚠️ Crawler 出現錯誤或未預期結束，請檢查 crawler.log 取得細節。"
    fi
fi

cat crawler.log | grep -A 10 "SUCCESS" || true
echo "=================================================="
echo "📊 Results aggregated at:"
echo " - JSON: ${OUTPUT_JSON}"
echo " - CSV:  ${OUTPUT_CSV}"
echo " - Detailed Artifacts backup directory: ${REPORTS_DIR}/"
echo "=================================================="
