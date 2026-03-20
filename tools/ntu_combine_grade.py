#!/usr/bin/env python3
"""Combine grade JSON with course CSV using student account mapping."""

import argparse
import csv
import json
import re
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cool", required=True)
    parser.add_argument("--grade", required=True)
    parser.add_argument("--map", required=True)
    parser.add_argument("--mp", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tmp", required=True)
    args = parser.parse_args()

    # Load grade JSON
    with open(args.grade, "r", encoding="utf-8") as f:
        grades = json.load(f)

    # Load map TSV: columns are Name, StudentID, GithubUsername
    map_entries = []
    with open(args.map, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                map_entries.append({
                    "name": parts[0].strip(),
                    "student_id": parts[1].strip(),
                    "github_username": parts[2].strip(),
                })

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

        # Check name match
        if not name_matches(tmp_entry["name"], csv_student_name):
            print(
                f"Ghost {tmp_entry['name']}({tmp_entry['student_id']}), "
                f"GH-Name {tmp_entry['github_username']}, "
                f"Score {tmp_entry['grade']}%",
                file=sys.stderr,
            )
            continue

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
        row[mp_col] = "0.00" if points_possible is not None else "0"

    # Write output CSV — preserve original BOM and line endings
    import io
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
