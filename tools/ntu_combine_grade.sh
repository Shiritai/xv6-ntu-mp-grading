#!/usr/bin/env bash
set -euo pipefail

COOL=""
GRADE=""
MAP=""
OUTPUT="combined_grade.csv"
MP=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --cool)  COOL="$2";   shift 2 ;;
        --grade) GRADE="$2";  shift 2 ;;
        --map)   MAP="$2";    shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        --mp)    MP="$2";     shift 2 ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$COOL" || -z "$GRADE" || -z "$MAP" || -z "$MP" ]]; then
    echo "Usage: $0 --cool <course.csv> --grade <grades.json> --map <accounts.tsv> --mp <keyword> [--output <out.csv>]" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TMPFILE="$(mktemp)"
trap 'rm -f "$TMPFILE"' EXIT

python3 "$SCRIPT_DIR/ntu_combine_grade.py" \
    --cool "$COOL" \
    --grade "$GRADE" \
    --map "$MAP" \
    --mp "$MP" \
    --output "$OUTPUT" \
    --tmp "$TMPFILE"
