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
    cat >&2 <<EOF
Usage: $0 --cool <cool_gradebook.csv> \\
          --grade <final_grades.json> \\
          --map <accounts.tsv|accounts.csv> \\
          --mp <keyword> \\
          [--output <out.csv>]

  --cool   Full grade sheet downloaded from NTU COOL (course Grades page).
  --grade  final_grades.json produced by auto_grade_mp.sh.
  --map    Student account mapping (Name, StudentID, GithubUsername).
           TSV or CSV — the delimiter is auto-detected from the extension.
  --mp     Assignment keyword matching the target COOL column (e.g. mp0).
  --output Destination CSV (default: combined_grade.csv).
EOF
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
