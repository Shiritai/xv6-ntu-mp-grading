#!/usr/bin/env python3
"""Combine grade JSON with course CSV using student account mapping.

Inputs:
  --cool   Full grade sheet CSV exported from NTU COOL (the TA downloads this
           from the course's Grades page).
  --grade  final_grades.json produced by auto_grade_mp.sh (array of records
           with score + detail.student_info.github_username).
  --map    Student account mapping with columns:
             Name, StudentID, GithubUsername
           Accepts either TSV or CSV (delimiter auto-detected from the file
           extension, falling back to csv.Sniffer for ambiguous inputs).
"""

import argparse
import csv
import io
import json
import os
import sys
import unicodedata


def is_cjk(ch):
    """Check if a character is a CJK ideograph."""
    cp = ord(ch)
    # CJK Unified Ideographs
    if 0x4E00 <= cp <= 0x9FFF:
        return True
    # CJK Extension A
    if 0x3400 <= cp <= 0x4DBF:
        return True
    # CJK Extension B+
    if 0x20000 <= cp <= 0x2A6DF:
        return True
    # CJK Compatibility Ideographs
    if 0xF900 <= cp <= 0xFAFF:
        return True
    return False


def tokenize_name(name):
    """Split a name into words. Each CJK character is its own token.
    Punctuation is stripped. Latin words are split on whitespace."""
    tokens = []
    buf = []
    for ch in name:
        if is_cjk(ch):
            if buf:
                tokens.append("".join(buf))
                buf = []
            tokens.append(ch)
        elif unicodedata.category(ch).startswith("P") or ch in "(),，、。：":
            # punctuation — flush buffer, skip char
            if buf:
                tokens.append("".join(buf))
                buf = []
        elif ch.isspace():
            if buf:
                tokens.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        tokens.append("".join(buf))
    return [t.lower() for t in tokens if t]


def name_matches(map_name, csv_name):
    """Check that every word in map_name appears in csv_name (case-insensitive).
    CJK characters are individual tokens; punctuation is ignored."""
    map_tokens = tokenize_name(map_name)
    csv_tokens = tokenize_name(csv_name)
    for t in map_tokens:
        if t not in csv_tokens:
            return False
    return True


def find_mp_column(header, mp_keyword):
    """Find the column index whose header starts with the mp keyword (case-insensitive)."""
    kw = mp_keyword.lower()
    for i, col in enumerate(header):
        # Match column names like "MP0 (377381)" or "MP1 - Thread Operation (379086)"
        col_lower = col.strip().lower()
        if col_lower.startswith(kw) and (
            len(col_lower) == len(kw)
            or not col_lower[len(kw)].isalnum()
        ):
            return i
    return None


def detect_map_delimiter(path, sample):
    """Pick the delimiter for the --map file.

    Prefer the extension (.csv -> ',', .tsv -> '\\t'); fall back to csv.Sniffer
    for anything else (e.g. .txt) and default to tab if sniffing fails."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return ","
    if ext == ".tsv":
        return "\t"
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t").delimiter
    except csv.Error:
        return "\t"


def load_map(path):
    """Parse the Name/StudentID/GithubUsername mapping from TSV or CSV."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    if not text.strip():
        return []
    delimiter = detect_map_delimiter(path, text[:4096])
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    entries = []
    for parts in reader:
        if len(parts) < 3:
            continue
        name = parts[0].strip()
        student_id = parts[1].strip()
        github = parts[2].strip()
        if not (name and student_id and github):
            continue
        entries.append({
            "name": name,
            "student_id": student_id,
            "github_username": github,
        })
    return entries


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Translate auto_grade_mp's final_grades.json scores into a "
            "row of an NTU COOL grade sheet CSV, keyed by student ID and "
            "verified by name."
        ),
    )
    parser.add_argument(
        "--cool", required=True,
        help="Full grade sheet CSV downloaded from NTU COOL (input + template).",
    )
    parser.add_argument(
        "--grade", required=True,
        help="final_grades.json produced by auto_grade_mp.sh.",
    )
    parser.add_argument(
        "--map", required=True,
        help=(
            "Student account mapping with columns "
            "Name, StudentID, GithubUsername. Accepts .tsv or .csv "
            "(delimiter auto-detected)."
        ),
    )
    parser.add_argument(
        "--mp", required=True,
        help="Assignment keyword identifying the target COOL column (e.g. mp0).",
    )
    parser.add_argument(
        "--output", required=True,
        help="Destination CSV path (ready to upload back to NTU COOL).",
    )
    parser.add_argument(
        "--tmp", required=True,
        help="Intermediate TSV path used for auditing the merged mapping.",
    )
    args = parser.parse_args()

    # Load grade JSON
    with open(args.grade, "r", encoding="utf-8") as f:
        grades = json.load(f)

    # Load map (TSV or CSV, auto-detected): Name, StudentID, GithubUsername
    map_entries = load_map(args.map)

    # Build grade lookup by github_username (lowercase)
    grade_by_gh = {}
    for entry in grades:
        info = entry.get("detail", {}).get("student_info", {})
        gh = info.get("github_username", "").strip().lower()
        if gh:
            grade_by_gh[gh] = entry.get("score", 0.0)

    # Build tmp file: extend map with grade
    # Format: name \t student_id \t github_username \t grade
    tmp_rows = []
    for m in map_entries:
        gh_lower = m["github_username"].lower()
        grade = grade_by_gh.get(gh_lower)
        tmp_rows.append({
            **m,
            "grade": grade,
        })

    with open(args.tmp, "w", encoding="utf-8") as f:
        for row in tmp_rows:
            g = "" if row["grade"] is None else str(row["grade"])
            f.write(f"{row['name']}\t{row['student_id']}\t{row['github_username']}\t{g}\n")

    # Load course CSV — detect BOM and line endings to preserve them on output
    with open(args.cool, "rb") as f:
        raw = f.read()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    if has_bom:
        raw = raw[3:]
    # Detect line ending
    if b"\r\n" in raw:
        line_ending = "\r\n"
    else:
        line_ending = "\n"
    text = raw.decode("utf-8")
    reader = csv.reader(text.splitlines())
    rows = list(reader)

    if len(rows) < 3:
        print("Course CSV too short", file=sys.stderr)
        sys.exit(1)

    header = rows[0]
    mp_col = find_mp_column(header, args.mp)
    if mp_col is None:
        print(f"Column matching '{args.mp}' not found in header: {header}", file=sys.stderr)
        sys.exit(1)

    # Find SIS Login ID column
    sis_col = None
    for i, col in enumerate(header):
        if col.strip().lower() == "sis login id":
            sis_col = i
            break
    if sis_col is None:
        print("'SIS Login ID' column not found", file=sys.stderr)
        sys.exit(1)

    # Find Student column
    student_col = None
    for i, col in enumerate(header):
        if col.strip().lower() == "student":
            student_col = i
            break
    if student_col is None:
        print("'Student' column not found", file=sys.stderr)
        sys.exit(1)

    # Ensure all rows have enough columns up to mp_col
    for row in rows:
        while len(row) <= mp_col:
            row.append("")

    # Get points possible from row index 2 (0-indexed)
    points_possible_str = rows[2][mp_col].strip() if rows[2][mp_col] else ""
    try:
        points_possible = float(points_possible_str)
    except ValueError:
        points_possible = None

    # Build lookup: student_id (lowercase) -> row in tmp
    sid_to_tmp = {}
    for row in tmp_rows:
        sid_to_tmp[row["student_id"].lower()] = row

    # Track which course rows got a grade
    graded_rows = set()

    # Process course CSV data rows (skip header row 0, sub-header row 1, points row 2)
    for row_idx in range(3, len(rows)):
        row = rows[row_idx]
        sis_email = row[sis_col].strip().lower() if len(row) > sis_col else ""
        csv_student_name = row[student_col].strip() if len(row) > student_col else ""

        if not sis_email or not csv_student_name:
            continue

        # Extract student_id from email (part before @)
        email_sid = sis_email.split("@")[0].lower()

        if email_sid not in sid_to_tmp:
            continue

        tmp_entry = sid_to_tmp[email_sid]

        if tmp_entry["grade"] is None:
            continue

        # Student ID matched — trust it. Still warn on name mismatch so the
        # TA can eyeball suspicious rows, but don't skip the grade.
        if not name_matches(tmp_entry["name"], csv_student_name):
            print(
                f"Name mismatch (grade still applied): map={tmp_entry['name']!r} "
                f"vs COOL={csv_student_name!r} "
                f"({tmp_entry['student_id']}, GH {tmp_entry['github_username']}, "
                f"Score {tmp_entry['grade']}%)",
                file=sys.stderr,
            )

        # Compute grade value for CSV
        grade_pct = tmp_entry["grade"]
        if points_possible is not None:
            grade_value = grade_pct / 100.0 * points_possible
            # Format nicely: remove trailing zeros
            grade_str = f"{grade_value:.2f}"
        else:
            grade_str = str(grade_pct)

        row[mp_col] = grade_str
        graded_rows.add(row_idx)

    # Warn about rows without grade
    print("=" * 72, file=sys.stderr)
    for row_idx in range(3, len(rows)):
        if row_idx in graded_rows:
            continue
        row = rows[row_idx]
        csv_student_name = row[student_col].strip() if len(row) > student_col else ""
        sis_email = row[sis_col].strip() if len(row) > sis_col else ""
        student_id = sis_email.split("@")[0] if sis_email else ""

        if not csv_student_name:
            continue

        print(
            f"Student {csv_student_name}({student_id}) does not have a grade",
            file=sys.stderr,
        )

    # Write output CSV — preserve original BOM and line endings
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator=line_ending)
    for row in rows:
        writer.writerow(row)
    with open(args.output, "wb") as f:
        if has_bom:
            f.write(b"\xef\xbb\xbf")
        f.write(buf.getvalue().encode("utf-8"))

    print("=" * 72, file=sys.stderr)
    print(f"Saved to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
