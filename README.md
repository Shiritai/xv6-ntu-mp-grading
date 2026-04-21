# xv6-ntu-mp Grading & Automation Complete Guide

This guide is designed for Teaching Assistants (TAs), detailing the complete lifecycle and operational commands from assignment release to final zero-submission automated grading.

## 1. Repository Architecture

We use a Dual-Repo architecture to isolate "student-facing content" from "TA-grading content":

### 📌 `xv6-ntu-mp` (Public Template Repository) -> [Shiritai/xv6-ntu-mp](https://github.com/Shiritai/xv6-ntu-mp)

This repository serves as the starting point for student assignments. Students need to fork or use this template (the latter supports Private repositories) when an assignment is released.

* **`doc/`**: Contains the complete specification documents (in Markdown).
* **`kernel/`, `user/`**: Contains the system kernel and skeleton code for students to implement.
* **`tests/`**: Contains **only Public Tests** (`test_mpX_public.py`). This allows students to verify their basic scores both locally and on their own GitHub CI.
* **`mp.sh` & `.github/workflows/grading.yml`**: The CI/CD automated grading engine entry point and GitHub Actions settings.

### 📌 `xv6-ntu-mp-grading` (TA Grading Repository)

This repository is used for managing student whitelists, automation scripts, and hidden dependencies for each assignment.

* **`tools/`**: Contains the universal suite of automated grading scripts, including invite acceptance, grading triggers, and score crawling.
* **`mpX/`**: Contains the specific private answers and testing payloads for each assignment (e.g., `mp0/`).

## 2. Assignment Release & Payload Preparation (e.g., MPX)

When releasing a new assignment (e.g., `mpX`) to students, you must set up the following two core directories within `xv6-ntu-mp-grading`. By default, actual grading assets (like `mp0/` or `mp1/`) are excluded by `.gitignore` to prevent leaking private tests to the public. You can refer to the tracked `mp-example/` directory to understand the required file structure:

### A. Prepare Official Solutions (`mpX/local_answer/`)

Contains the Reference Solution for the assignment (e.g., `mpX.c`). This is used internally by the TA team to verify that the scripts and tests can achieve a perfect score. **This is not distributed to students**, and it may also be entirely omitted.

### B. Prepare Public Sync Assets (`mpX/public/`) [Crucial for Hot-Sync]

📌 **This directory is for 'Assignment Period' updates.**
Contains any content that needs to be distributed to students before the deadline (e.g., spec fixes in `doc/`, new public tests in `tests/`).

* **Broadcast Tool**: Use `tools/broadcast_update.sh` to push these assets to the student private repositories directly.
* **Sync Mechanism**: When students run `mp.sh sync`, they will automatically merge the latest TA commits.
* **Caution**: Ensure **no private information** is placed here.

### C. Prepare Grading Payload & Private Tests (`mpX/payload/`) [Crucial for Zero-Submission]

📌 **This directory is for 'Post-Deadline' grading only. DO NOT publish during the assignment.**
The zero-submission model relies on forcefully **overwriting the student's repository** with the `payload/` directory exactly as-is right after the deadline. This ensures:

1. Students cannot tamper with the CI execution process.
2. Private test cases and official grading configurations (`mp.conf`, `grading.conf`) remain strictly hidden until the deadline has concluded.

Example structure:

```text
xv6-ntu-mp-grading/mpX/payload/
├── .github/workflows/grading.yml   # Forces reset of Action workflows
├── mp.sh                           # Forces reset of test entry points
├── mp.conf                         # Forces reset of grading environment
├── tests/grading.conf              # Official test list and weights
└── tests/test_mpX_private.py       # Private test cases
```

> **⚠️ TA Notice**: Whenever a new assignment is released, ensure that the payload's `mp.sh`, `mp.conf`, and `grading.conf` are fully synchronized with the desired official configuration. **Note that the payload purposely does NOT include Git Hooks (`scripts/pre-commit` etc.) as they are not needed for automated grading.**

---

## 3. Automated Grading SOP

During the assignment period, the student workflow is extremely simple: no Google forms, no uploading to COOL. They just write code and push it to their Private Repositories (ensuring they have invited the TA's GitHub account as a Collaborator).
When the deadline arrives, follow these **3 Steps** to finalize the grades for the entire class.

### Step 1: Prepare Student Whitelist

> 🛑 **Crucial Policy**: All student repositories **MUST be set to Private**. The grading tools naturally enforce this: `accept_invite.sh` will outright reject invitations from public repositories (and warn you), and `grading_crawler.py` will actively check the visibility of the repo at grading time. If a repository is public, the student receives **0 points** regardless of the CI result.

First, extract the **GitHub Usernames** submitted by your students from your institution's Learning Management System (LMS like Canvas, Moodle, Blackboard) or a registration form (e.g., Google Forms). Place these usernames line-by-line into a plain text file named `whitelist.txt`.

If you are using a **Google Form spreadsheet** where the GitHub username is the 3rd column, you can automate this extraction process. For example, assuming you know its Sheet ID and GID:

```bash
cd xv6-ntu-mp-grading/tools

# Define your Google Sheet configuration
SHEET_ID="..."
SHEET_GID="..."

# 1. Download the TSV, skip the header (tail -n +2), select relevant columns (cut -f3,4,5), and format as CSV:
curl -s -L "https://docs.google.com/spreadsheets/d/$SHEET_ID/export?format=tsv&gid=$SHEET_GID" | \
tr -d '\r' | tail -n +2 | cut -f3,4,5 | \
awk -F'\t' '{for(i=1;i<=NF;i++) printf "\"%s\"%s", $i, (i==NF?ORS:",")}' > student-github-accounts.csv

# 2. Extract the 3rd column (GitHub Username), remove quotes, and save to whitelist.txt:
awk -F'","' '{print $3}' student-github-accounts.csv | sed 's/"//g' > ../whitelist.txt
```

* 📂 **Output Path**: `xv6-ntu-mp-grading/whitelist.txt`
* 📝 **Example Content**:

  ```text
  b12345678-test
  os-genius
  anon-chihaya
  ```

### Step 2: Batch Accept Invites & Inventory Management

After creating their Private Repositories, students will send collaborator invitations to the TA account. There is no need to accept these manually one-by-one; use the following commands:

```bash
cd xv6-ntu-mp-grading/tools
# Log into the authorized TA GitHub account (only required once)
gh auth login

# Create `whitelist.txt` manually or automatically

# Run the auto-accept script. Output is saved to the corresponding assignment directory
./accept_invite.sh -f ../whitelist.txt -r "ntuos2026-mpX" -o ../mpX/result/students_mpX.json
```

**What does this do?**

1. **Phase 1 (Accept Invites)**: Calls the GitHub API to list all pending repository invitations, cross-references against `whitelist.txt` and the `"ntuos2026-mpX"` keyword, and automatically batch accepts them. **Crucially, it skips any invitations originating from Public repositories and warns the TA so students can be notified to fix their visibility.**
2. **Phase 2 (Global Scan & Failsafe)**: Regardless of whether new invitations existed, the script will forcefully crawl all repositories where the TA account holds `Collaborator` permissions. It natively queries GitHub's active states and performs an intersection match against `whitelist.txt`.
3. **Safe Export**: Finally, it writes this 100% accurate, definitive list (e.g., `anon-chihaya/ntuos2026-mpX`) into `../mpX/result/students_mpX.json`, establishing the target inventory for the next phase.

> 💡 **Tip**: Because Phase 2 queries the definitive "connected states" directly from GitHub, this script possesses **perfect idempotency**. Even if the terminal closes or script execution drops 100 times, re-running this script guarantees a flawless, zero-omission rebuild of the `students_mpX.json` roster!

### Step 3: One-Click Automated Grading & Summarization

**This is a fully automated command.** Once all repositories are successfully logged into `../mpX/result/students_mpX.json`, launch the grading engine:

```bash
cd xv6-ntu-mp-grading/tools
./auto_grade_mp.sh --mp mpX [--students ../mpX/result/students_mpX.json | --repo <owner/repo>] [--prefix ntuos2026]
```

*(Tip: CI execution usually takes 5-10 minutes. If some students haven't finished, the script will display a "Pending" list and export a partial score snapshot. You can run the exact same command later to collect the remaining scores. Furthermore, if a student's code and the Payload remain unchanged, the system defaults to **skipping the CI trigger (idempotency)** and fetches the previous score. To forcefully re-trigger everyone, append `--force`.)*

**What does this do?**
This is an orchestrator script that seamlessly connects `trigger_grading` and `grading_crawler` in parallel:

1. **Parallel Payload Injection**: Using multithreading, it iterates through every student in the list and forcefully commits the contents of `mpX/payload/` directly into the root of their repository using the TA's identity. This forcefully overwrites the student's CI configurations and guarantees the latest Sanitizer environment. Since the payload lacks the "skip on TA commit" logic found in the student template, the grading CI will correctly proceed.
2. **Parallel CI Triggers**: Because this constitutes an official Git Push, the student's GitHub Actions will wake up and execute the official compiler and test suite (which now includes the Private Tests). The SHA of this injected commit acts as a unique, unforgeable fingerprint.
3. **Stateless Single Crawl & Backup**: The script immediately calls the crawler to extract a real-time snapshot of the scores. When it detects that the Action for that specific fingerprint has passed successfully (turned green), it downloads the pristine `report.json`. **Every raw student `report.json` is preserved individually within `../mpX/result/reports/` for auditing.** For students still in progress, their names will be reported, allowing you to seamlessly sync them by re-running the command later.
4. **Report Output**: Finally, it generates the `final_grades.csv` and `.json` files inside the `mpX/result/` directory.

```csv
Repository,Status,Final Score,Run URL
anon-chihaya/ntuos2026-mpX,Success,100,https://github.com/anon-chihaya/ntuos2026-mpX/actions/runs/223...
```

**Grading Deliverables:**

* `../mpX/result/final_grades.csv`: Ready for direct opening or uploading for translation against NTU COOL.
* `../mpX/result/final_grades.json`: Full, structured per-student grading records (score, SHA fingerprint, test-case breakdown, deadline/penalty metadata). This is the canonical input for `ntu_combine_grade.sh`.
* `../mpX/result/reports/`: Contains individual execution logs and `report.json` for the entire class.

You can now use `final_grades.csv` to directly grade on NTU COOL!

### Step 4 (Optional): Fold grades back into the NTU COOL gradebook

`final_grades.csv` is keyed by `<github-owner>/ntuos2026-mpX`, which is not the format NTU COOL expects for bulk upload. Use `ntu_combine_grade.sh` to translate the raw grading output into a gradebook CSV that COOL will accept:

```bash
cd xv6-ntu-mp-grading/tools
./ntu_combine_grade.sh \
    --cool  <cool_gradebook.csv> \
    --grade ../mpX/result/final_grades.json \
    --map   student-github-accounts.csv \
    --mp    mpX \
    --output ../mpX/result/gradebook.csv
```

**What you need to prepare:**

* `--cool` — download the **full grade sheet** from the course's NTU COOL Grades page (Export → CSV). The script reuses it as both the template (to preserve unrelated columns) and the identity source (`SIS Login ID` → student ID, `Student` → name). BOM and line endings of the original file are preserved on output.
* `--grade` — the `final_grades.json` produced by `auto_grade_mp.sh` in the previous step. This is the score source, keyed by GitHub username inside `detail.student_info.github_username`.
* `--map` — the `Name, StudentID, GithubUsername` mapping (3 columns). `.tsv` and `.csv` are both accepted; the delimiter is auto-detected from the extension, with a `csv.Sniffer` fallback for other extensions. The `student-github-accounts.csv` generated in Step 1 works as-is.
* `--mp` — case-insensitive keyword that selects the destination COOL column (e.g. `mp0` matches columns like `MP0 (377381)` or `mp0 - Boot Loader (…)`).
* `--output` — destination CSV. It mirrors the input COOL layout with only the matched MP column updated.

**Cross-checks the script performs:**

1. Matches COOL rows to grades by **student ID** (from `SIS Login ID`), not by name.
2. After ID match, verifies the names align (every token in the map's name must appear in the COOL row's `Student` field; CJK characters are compared per-codepoint, punctuation is ignored). A mismatch is logged as a `Ghost …` warning to stderr and the row is skipped rather than silently mis-graded.
3. Reads `Points Possible` from row 3 (the COOL convention) and rescales the JSON percentage accordingly, so a `100` in the JSON becomes `10.00` in a `10`-point column.
4. Any COOL row that ends up without a matched grade is filled with `0` / `0.00` and printed as a warning — no student is left blank by accident.

### Step 3.x (Recovery): Repair a broken payload push

If you accidentally deployed a wrong payload (e.g. shipped reference solutions, or an incomplete `tests/` set) and every student's CI now reports a useless score, do **not** rewrite history on student remotes. Instead, fix the payload locally, then run:

```bash
./auto_grade_mp.sh --mp mpX --students ../mpX/result/students_mpX.json --repair
```

The `--repair` flag changes Phase 1 behavior:

1. Clone each student's grading branch with enough history (depth 50) to look past the bad TA commits.
2. Walk `git log` and pick the most recent commit whose committer email is **not** listed in `<payload>/mp.conf TA_EMAILS`. That commit represents the student's last real state.
3. `git checkout <student_sha> -- .` restores the working tree to that state — **history is preserved**, no force-push, no branch divergence.
4. Overlay the now-correct `mpX/payload/` on top.
5. Commit as `fix(grading): restore student code and redeploy correct grading payload` and push, which re-triggers CI.

Because the TA whitelist is read directly from `mpX/payload/mp.conf` (the `TA_EMAILS` line), there is no separate flag to keep in sync — update `mp.conf` and `--repair` follows. You can rehearse on one student first via `--repo <owner>/<repo> --repair` before fanning out to the whole class.

---

## Appendix: API Documentation for Grading Tools

The `tools/` directory encapsulates the zero-submission grading engine. These scripts are highly decoupled, idempotent, and designed to perform flawlessly regardless of environmental interruptions.

### `accept_invite.sh`

A shell script designed for robust repository discovery and inventory management.

* **Mechanism**: Utilizes a dual-track scanning strategy. It first queries the GitHub API `user/repository_invitations` to accept pending collaborator invitations. Then, it queries `user/repos?affiliation=collaborator` to enumerate the TA's connected repositories, performing a strict intersection against a supplied whitelist and naming keyword.
* **Idempotency**: Execution is stateless and strictly reflects the authoritative data from GitHub's servers. Re-running the script will perfectly recreate the complete student JSON roster without omission or duplication.
* **Usage**: `./accept_invite.sh -f <whitelist_txt> -r <repo_keyword> -o <output_json> [-d]`
  * `-f`: Path to the line-delimited list of allowed GitHub usernames.
  * `-r`: The required substring that must be present in the repository name (e.g., `ntuos2026-mpX`).
  * `-o`: The target JSON file for the compiled repository array (e.g., `students_mpX.json`).
  * `-d`: Dry-run mode. Previews API hits and matching logic without executing PATCH requests.

### `auto_grade_mp.sh`

The overarching orchestration shell script. It manages the entire grading lifecycle by invoking Python sub-modules sequentially.

* **Mechanism**: Dispatches `trigger_grading.py` to push payloads and spawn CI workflows. It subsequently performs a stateless single crawl via `grading_crawler.py` to capture the current progress and aggregate results.
* **Usage**: `./auto_grade_mp.sh --mp <mp_id> [--students <roster_json> | --repo <owner/repo>] [--prefix <course_prefix>] [--force-push] [--force-fetch] [--repair] [--exclude-repo <repo1,repo2>]`
* **`--repair`**: Switches Phase 1 into recovery mode. Restores each student's working tree to their last non-TA commit (TA emails sourced from `<payload>/mp.conf TA_EMAILS`), overlays the current payload, and pushes a single corrective commit. Use this when an earlier payload push contaminated all students' CI results. History is preserved — no force-push, no branch divergence.

### `trigger_grading.py`

A multi-threaded Python executor responsible for payload injection and CI initiation.

* **Mechanism**: Using `concurrent.futures`, it concurrently accesses listed student repositories via `gh api`. It commits the designated `mpX/payload/` structure directly to the student's root tree on the target branch (inherited from `--prefix`), establishing an official TA benchmark environment.
* **Idempotency (Caching Focus)**: Prior to committing, it compares the payload against the student's latest tree. If the payload is identical to the current HEAD, the system infers no meaningful updates occurred and gracefully skips the redundant commit, significantly conserving GitHub Action minutes. Forced overriding is achieved via the `--force-push` flag.
* **Repair Mode (`--repair`)**: Replaces the normal payload-push behavior with a forward-only undo. For each repo, it clones with depth 50, scans `git log` for the most recent commit whose committer email is **not** in the payload's `mp.conf TA_EMAILS` list, then `git checkout <student_sha> -- .` to roll the working tree back to that state without touching history. The current payload is overlaid on top and committed as `fix(grading): restore student code and redeploy correct grading payload`. The TA whitelist is intentionally sourced from `mp.conf` (single source of truth) rather than a CLI flag.
* **Usage**: `python3 trigger_grading.py --mp <mp_id> [--students <json> | --repo <owner/repo>] --grading-dir <path> [--prefix <course>] [--branch <branch>] [--force-push] [--repair] [--exclude-repo <repo1,repo2>]`

### `grading_crawler.py`

A robust Python crawler designed for asynchronous artifact retrieval and data serialization.

* **Mechanism**: Exploits the unforgeable nature of Git SHAs. For each student, it scans workflow runs on their repository for the exact commit SHA injected by the `trigger_grading.py` script. It intelligently waits (polls) for the `in_progress` workflow to `completed`. Once finalized, it downloads the run artifacts, strictly extracts `report.json` authored by the CI test suite, and digests the data.
* **Anti-Cheating (Visibility Check)**: Before acknowledging any score, it executes a live API call against the repository. If the repository is currently `Public` (e.g. the student turned it public after CI finished), a relentless `0` score is enforced under `Public Repo Penalty`.
* **Resilience**: Features automatic exponential backoffs and handles partial successes (e.g., missing artifacts, compilation failures are safely logged with zeroed scores rather than crashing).

### `broadcast_update.sh`

The Hot-Sync broadcast tool for TAs to securely map and push updates to student private repositories in parallel.

* **Mechanism**: A Bash wrapper for `broadcast_update.py` that utilizes `concurrent.futures` to concurrently clone each student's private repository, switch to the target assignment branch (`ntuos2026/mpX`), and exclusively sync contents from `mpX/public/` (e.g., docs, specs, public tests). This creates an isolated TA commit directly on the student's remote without causing non-fast-forward conflicts, allowing them to trivially merge changes natively via `mp.sh sync`.
* **Safety Restriction**: Strictly avoid placing private test cases or official grading configs in `public/`. Official grading assets (like `grading.conf`) must be stored in `payload/`.
* **Usage**: `./broadcast_update.sh --mp <mp_id> --message <commit_message> [--repos-list <json_file>] [--workers <int>] [--dry-run]`
  * `--mp`: Assignment identifier (e.g., `mp0`). Assets must be in `mpX/public/`.
  * `--message`: Commit message. This is what students see in their git log.
  * `--repos-list`: JSON file containing the array of target repository URLs (generated by `accept_invite.sh`).
  * `--workers`: (Optional) Number of parallel threads to use. Default is 4.
  * `--repo`: (Optional) Single target repository URL, used primarily for testing. Mutually exclusive with `--repos-list`.
  * `--dry-run`: Preview mode. Stages changes and creates a local commit in independent `.tmp/` directories without pushing to the remotes.

### `ntu_combine_grade.sh`

A thin shell wrapper around `ntu_combine_grade.py` that merges `auto_grade_mp`'s `final_grades.json` into an NTU COOL gradebook CSV, producing a drop-in upload.

* **Mechanism**: Joins three data sources — the COOL gradebook CSV (template + identity), the grading JSON (scores keyed by GitHub username), and a Name/StudentID/GithubUsername mapping — by first looking up each COOL row's student ID in the mapping, then verifying the names agree. Scores are rescaled against `Points Possible` (row 3 of the COOL export) before being written into the MP column. BOM and line endings of the original COOL CSV are preserved byte-faithfully so that re-uploading to COOL does not trip the server's strict parser.
* **Safety Nets**: Mismatched name → skipped with a `Ghost …` warning. Unmatched COOL rows → filled with `0` and reported. No silent overwrites.
* **Usage**: `./ntu_combine_grade.sh --cool <cool_gradebook.csv> --grade <final_grades.json> --map <accounts.tsv|accounts.csv> --mp <keyword> [--output <out.csv>]`
  * `--cool`: Full grade sheet exported from the course's NTU COOL Grades page (Export → CSV). Acts as both template and identity source (`SIS Login ID`, `Student`).
  * `--grade`: `final_grades.json` produced by `auto_grade_mp.sh` (array of records with `score` and `detail.student_info.github_username`).
  * `--map`: Three-column mapping (Name, StudentID, GithubUsername). Both TSV and CSV are accepted; the delimiter is auto-detected from the file extension, with a `csv.Sniffer` fallback for ambiguous extensions. Quoted fields and UTF-8 BOM are handled.
  * `--mp`: Case-insensitive keyword matching the target COOL column name prefix (e.g. `mp0` → `MP0 (377381)`, `mp1` → `MP1 - Thread Operation (…)`).
  * `--output`: Destination CSV. Defaults to `combined_grade.csv`.
