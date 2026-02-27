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

### B. Prepare Grading Payload & Private Tests (`mpX/payload/`)

📌 **This is the most critical directory.**
The zero-submission model relies on forcefully **overwriting the student's repository** with the `payload/` directory exactly as-is right after the deadline. This ensures:

1. Students cannot tamper with the CI execution process.
2. Private test cases remain strictly hidden until the deadline has concluded.

For `mpX`, your `payload/` directory must contain:

```text
xv6-ntu-mp-grading/mpX/payload/
├── .github/workflows/grading.yml   # Forces reset of Action workflows
├── mp.sh                           # Forces reset of test entry points
├── mp.conf                         # Forces reset of environment
├── tests/grading.conf              # [NEW] Official test list for score isolation
└── tests/test_mpX_private.py       # Private test cases
```

> **⚠️ TA Notice**: Whenever a new assignment is released, ensure that the payload's `mp.sh`, `mp.conf`, and `grading.conf` are fully synchronized with the desired official configuration. **Note that the payload purposely does NOT include Git Hooks (`scripts/pre-commit` etc.) as they are not needed for automated grading.**

---

## 3. Automated Grading SOP

During the assignment period, the student workflow is extremely simple: no Google forms, no uploading to COOL. They just write code and push it to their Private Repositories (ensuring they have invited the TA's GitHub account as a Collaborator).
When the deadline arrives, follow these **3 Steps** to finalize the grades for the entire class.

### Step 1: Prepare Student Whitelist

> 🛑 **Crucial Policy**: All student repositories **MUST be set to Private**. The grading tools naturally enforce this: `accept_invite.sh` will outright reject invitations from public repositories (and warn you), and `grading_crawler.py` will actively check the visibility of the repo at grading time. If a repository is public, the student receives **0 points** regardless of the CI result.

Extract the **GitHub Usernames** submitted by your students from your institution's Learning Management System (LMS like Canvas, Moodle, Blackboard) or a registration form (e.g., Google Forms). Place these usernames line-by-line into a plain text file. Note that this file can be named arbitrarily and placed anywhere, but the root or `tools/` directory are common choices.

* 📂 **Example Path**: `xv6-ntu-mp-grading/whitelist.txt`
* 📝 **Example**:

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
./auto_grade_mp.sh --mp mpX --students ../mpX/result/students_mpX.json
```

*(Tip: If you do not want to wait for the CI to finish running and only want to inject payloads, you can append the `--no-wait` argument. The engine will exit immediately after pushing the payloads. Later, you can run the exact same command without `--no-wait` to cleanly crawl the scores. Furthermore, if a student hasn't changed their code and the Payload remains the same, the system defaults to **skipping the CI trigger (to prevent CI resource waste due to idempotency)** and fetches the previous score. If you must forcefully trigger everyone's CI again, append `--force`.)*

**What does this do?**
This is an orchestrator script that seamlessly connects `trigger_grading` and `grading_crawler` in parallel:

1. **Parallel Payload Injection**: Using multithreading, it iterates through every student in the list and forcefully commits the contents of `mpX/payload/` directly into the root of their repository using the TA's identity. This forcefully overwrites the student's CI configurations and guarantees the latest Sanitizer environment. Since the payload lacks the "skip on TA commit" logic found in the student template, the grading CI will correctly proceed.
2. **Parallel CI Triggers**: Because this constitutes an official Git Push, the student's GitHub Actions will wake up and execute the official compiler and test suite (which now includes the Private Tests). The SHA of this injected commit acts as a unique, unforgeable fingerprint.
3. **Polling & Crawling**: The script seamlessly transitions into a polling wait state. When it detects that the Action for that specific fingerprint has passed successfully (turned green), it downloads and unzips the pristine `report.json`. Most importantly, **every raw student `report.json` is preserved individually within `../mpX/result/reports/` to prevent repository clutter and serve as an immutable audit trail.**
4. **Report Output**: Finally, it generates the `final_grades.csv` and `.json` files inside the `mpX/result/` directory.

```csv
Repository,Status,Final Score,Run URL
anon-chihaya/ntuos2026-mpX,Success,100,https://github.com/anon-chihaya/ntuos2026-mpX/actions/runs/223...
```

**Grading Deliverables:**

* `../mpX/result/final_grades.csv`: Ready for direct opening or uploading for translation against NTU COOL.
* `../mpX/result/reports/`: Contains individual execution logs and `report.json` for the entire class.

You can now use `final_grades.csv` to directly grade on NTU COOL!

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

* **Mechanism**: Dispatches `trigger_grading.py` to push payloads and spawn CI workflows. Unless explicitly overridden with `--no-wait`, it subsequently invokes `grading_crawler.py` to poll completion and aggregate outcomes into `.csv` and `.json` reports.
* **Usage**: `./auto_grade_mp.sh --mp <mp_id> --students <roster_json> [--no-wait] [--force] [--max-attempts <int>] [--wait-interval <int>]`

### `trigger_grading.py`

A multi-threaded Python executor responsible for payload injection and CI initiation.

* **Mechanism**: Using `concurrent.futures`, it concurrently accesses listed student repositories via `gh api`. It commits the designated `mpX/payload/` structure directly to the student's root tree, establishing an official TA benchmark environment.
* **Idempotency (Caching Focus)**: Prior to committing, it compares the payload against the student's latest tree. If the payload is identical to the current HEAD, the system infers no meaningful updates occurred and gracefully skips the redundant commit, significantly conserving GitHub Action minutes. Forced overriding is achieved via the `--force` flag.

### `grading_crawler.py`

A robust Python crawler designed for asynchronous artifact retrieval and data serialization.

* **Mechanism**: Exploits the unforgeable nature of Git SHAs. For each student, it scans workflow runs on their repository for the exact commit SHA injected by the `trigger_grading.py` script. It intelligently waits (polls) for the `in_progress` workflow to `completed`. Once finalized, it downloads the run artifacts, strictly extracts `report.json` authored by the CI test suite, and digests the data.
* **Anti-Cheating (Visibility Check)**: Before acknowledging any score, it executes a live API call against the repository. If the repository is currently `Public` (e.g. the student turned it public after CI finished), a relentless `0` score is enforced under `Public Repo Penalty`.
* **Resilience**: Features automatic exponential backoffs and handles partial successes (e.g., missing artifacts, compilation failures are safely logged with zeroed scores rather than crashing).
