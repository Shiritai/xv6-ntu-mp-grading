import os
import re
import sys
import json
import shutil
import subprocess
import tempfile
import argparse
import concurrent.futures

TA_GRADING_COMMIT_MSG = 'chore(grading): deploy private tests and trigger grading'
TA_REPAIR_COMMIT_MSG = 'fix(grading): restore student code and redeploy correct grading payload'


def parse_ta_emails(mp_conf_path):
    """Extract TA_EMAILS (space-separated) from a payload mp.conf file."""
    if not os.path.isfile(mp_conf_path):
        return []
    with open(mp_conf_path, "r") as f:
        for line in f:
            m = re.match(r'^\s*TA_EMAILS\s*=\s*"([^"]*)"', line)
            if m:
                return [e for e in m.group(1).split() if e]
    return []

def run_cmd(cmd, cwd=None):
    res = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        return False, res.stderr
    return True, res.stdout.strip()

def pr_error(msg):
    print(f"\033[91m[ERROR]\033[0m {msg}", file=sys.stderr)

def pr_info(msg):
    print(f"\033[94m[INFO]\033[0m {msg}")

def pr_success(msg):
    print(f"\033[92m[SUCCESS]\033[0m {msg}")

def pr_warn(msg):
    print(f"\033[93m[WARN]\033[0m {msg}")

def repair_repo(repo_full_name, payload_dir, branch, ta_emails):
    """Restore student files to their last commit, then overlay the correct payload."""
    pr_info(f"Repairing {repo_full_name} on branch '{branch}'...")

    with tempfile.TemporaryDirectory() as tmpdir:
        clone_dir = os.path.join(tmpdir, "repo")

        ok, err = run_cmd(f"gh repo clone {repo_full_name} {clone_dir} -- -b {branch} --depth 50")
        if not ok:
            pr_error(f"Failed to clone {repo_full_name}:\n{err}")
            return None

        # Find the last commit NOT by any TA listed in mp.conf TA_EMAILS
        ok, log_out = run_cmd("git log --format='%H %ae'", cwd=clone_dir)
        if not ok:
            pr_error(f"Failed to read git log in {repo_full_name}:\n{log_out}")
            return None

        ta_set = set(ta_emails)
        student_sha = None
        for line in log_out.splitlines():
            sha, _, email = line.partition(" ")
            if email and email not in ta_set:
                student_sha = sha
                break

        if not student_sha:
            pr_error(f"Could not find a non-TA commit in {repo_full_name} (TA_EMAILS={sorted(ta_set)})")
            return None

        pr_info(f"  Last student commit: {student_sha[:8]} in {repo_full_name}")

        # Restore working tree to the student's state (history unchanged)
        ok, err = run_cmd(f"git checkout {student_sha} -- .", cwd=clone_dir)
        if not ok:
            pr_error(f"Failed to restore student files in {repo_full_name}:\n{err}")
            return None

        # Overlay the correct payload
        if payload_dir and os.path.isdir(payload_dir):
            try:
                for item in os.listdir(payload_dir):
                    s = os.path.join(payload_dir, item)
                    d = os.path.join(clone_dir, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d, dirs_exist_ok=True)
                    else:
                        shutil.copy2(s, d)
            except Exception as e:
                pr_error(f"Failed to copy payload to {repo_full_name}: {e}")
                return None

        run_cmd("git add -A", cwd=clone_dir)
        ok, status = run_cmd("git status --porcelain", cwd=clone_dir)
        if not status:
            pr_warn(f"No changes needed for {repo_full_name} (already correct)")
            ok, sha = run_cmd("git rev-parse HEAD", cwd=clone_dir)
            return (sha, False) if ok else None

        ok, err = run_cmd(f"git commit -m '{TA_REPAIR_COMMIT_MSG}'", cwd=clone_dir)
        if not ok:
            pr_error(f"Failed to commit repair in {repo_full_name}:\n{err}")
            return None

        ok, err = run_cmd("git push origin HEAD", cwd=clone_dir)
        if not ok:
            pr_error(f"Failed to push repair to {repo_full_name}:\n{err}")
            return None

        ok, sha = run_cmd("git rev-parse HEAD", cwd=clone_dir)
        if not ok or not sha:
            pr_error(f"Failed to retrieve HEAD SHA for {repo_full_name}.")
            return None

        pr_success(f"Repaired {repo_full_name} (Commit: {sha})")
        return sha, True


def process_repo(repo_full_name, payload_dir, branch, force=False):
    pr_info(f"Processing {repo_full_name} on branch '{branch}'...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_dir = os.path.join(tmpdir, "repo")
        
        # Clone the repository using gh CLI (uses TA's native auth configuration)
        ok, err = run_cmd(f"gh repo clone {repo_full_name} {clone_dir} -- -b {branch} --depth 1")
        if not ok:
            pr_error(f"Failed to clone {repo_full_name}:\n{err}")
            return None
            
        # Copy payload contents to the root of the repository
        if payload_dir and os.path.isdir(payload_dir):
            try:
                # Copy everything inside payload_dir to clone_dir
                for item in os.listdir(payload_dir):
                    s = os.path.join(payload_dir, item)
                    d = os.path.join(clone_dir, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d, dirs_exist_ok=True)
                    else:
                        shutil.copy2(s, d)
            except Exception as e:
                pr_error(f"Failed to copy payload to {repo_full_name}: {e}")
                return None
                
        # Add and commit
        run_cmd("git add -A", cwd=clone_dir)
        
        # Check if there is anything to commit
        ok, status = run_cmd("git status --porcelain", cwd=clone_dir)
        if not ok:
            pr_error(f"Failed to run git status in {repo_full_name}:\n{status}")
            return None
        if not status:
            if force:
                pr_warn(f"No changes for {repo_full_name}, but --force-push is set. Triggering CI via workflow_dispatch.")
                # We use 'grading.yml' as it's the filename in .github/workflows/
                ok, err = run_cmd(f"gh workflow run grading.yml --repo {repo_full_name} --ref {branch}", cwd=clone_dir)
                if not ok:
                    pr_error(f"Failed to trigger workflow_dispatch for {repo_full_name}:\n{err}")
                    return None
                
                # Retrieve the current SHA (since no new commit was made)
                ok, sha = run_cmd("git rev-parse HEAD", cwd=clone_dir)
                return (sha, True) if ok else (None, False)
            else:
                pr_info(f"No changes (payload already matches) for {repo_full_name}. Retrieving HEAD commit...")
                ok, sha = run_cmd("git rev-parse HEAD", cwd=clone_dir)
                if not ok:
                    pr_error(f"Failed to retrieve HEAD SHA for {repo_full_name}.")
                    return None
                ok, msg = run_cmd("git log -1 --format=%s", cwd=clone_dir)
                if ok and TA_GRADING_COMMIT_MSG in msg:
                    pr_info(f"HEAD is the TA grading commit {sha[:8]} for {repo_full_name}.")
                else:
                    pr_warn(f"HEAD {sha[:8]} is not the TA grading commit for {repo_full_name}. Using it anyway.")
                return sha, False
        else:
            ok, err = run_cmd(f"git commit -m '{TA_GRADING_COMMIT_MSG}'", cwd=clone_dir)
            if not ok:
                pr_error(f"Failed to commit in {repo_full_name}:\n{err}")
                return None
                
        # Push only if a commit was made
        pr_info(f"Pushing updates to {repo_full_name}...")
        ok, err = run_cmd("git push origin HEAD", cwd=clone_dir)
        if not ok:
            pr_error(f"Failed to push {repo_full_name}:\n{err}")
            return None
            
        # Get new HEAD SHA
        ok, sha = run_cmd("git rev-parse HEAD", cwd=clone_dir)
        if not ok or not sha:
            pr_error(f"Failed to retrieve HEAD SHA for {repo_full_name}.")
            return None
            
        pr_success(f"Successfully triggered grading for {repo_full_name} (Commit: {sha})")
        # If we made a commit or used workflow_dispatch, a "push/trigger" occurred.
        return sha, True

def main():
    parser = argparse.ArgumentParser(description="TA Script to deploy private tests and trigger grading.")
    parser.add_argument("--mp", required=True, help="Machine Problem identifier (e.g., mp0, mp1).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--students", help="Path to JSON file containing list of 'owner/repo'.")
    group.add_argument("--repo", help="Target 'owner/repo' of a single repository.")
    parser.add_argument("--grading-dir", required=True, help="Path to xv6-ntu-mp-grading workspace.")
    parser.add_argument("--branch", help="Target branch in student repositories (overrides prefix).")
    parser.add_argument("--prefix", default="ntuos2026", help="Course prefix for branch.")
    parser.add_argument("--force-push", action="store_true", help="Force an empty commit to trigger CI even if there are no payload changes.")
    parser.add_argument("--repair", action="store_true", help="Repair mode: restore student code to their last commit, then redeploy the correct payload. TA emails are read from <payload>/mp.conf TA_EMAILS.")
    parser.add_argument("--exclude-repo", help="Comma-separated list of 'owner/repo' to exclude from grading.")
    args = parser.parse_args()

    # Automatically derive the default branch if not explicitly provided
    target_branch = args.branch if args.branch else f"{args.prefix}/{args.mp}"

    # Note: Authentication is handled transparently by the `gh` CLI or underlying `git` config (SSH/HTTPS)

    if args.students:
        try:
            with open(args.students, "r") as f:
                student_repos = json.load(f)
        except Exception as e:
            pr_error(f"Failed to read students list: {e}")
            sys.exit(1)
    else:
        student_repos = [args.repo]

    if args.exclude_repo:
        exclude_list = [r.strip() for r in args.exclude_repo.split(",") if r.strip()]
        before_count = len(student_repos)
        student_repos = [r for r in student_repos if r not in exclude_list]
        pr_info(f"Excluded {before_count - len(student_repos)} repositories. Remaining: {len(student_repos)}")

    payload_dir = os.path.join(args.grading_dir, args.mp, "payload")
    if not os.path.isdir(payload_dir):
        pr_warn(f"Payload directory {payload_dir} not found. Will trigger grading with empty commits.")

    ta_emails = []
    if args.repair:
        ta_emails = parse_ta_emails(os.path.join(payload_dir, "mp.conf"))
        if not ta_emails:
            pr_error(f"--repair requires TA_EMAILS in {payload_dir}/mp.conf, none found. Aborting.")
            sys.exit(1)
        pr_info(f"Repair mode: TA_EMAILS = {ta_emails}")
        
    # We output grading_targets.json inside the MP result directory
    mp_out_dir = os.path.join(args.grading_dir, args.mp, "result")
    os.makedirs(mp_out_dir, exist_ok=True)
    output_target_file = os.path.join(mp_out_dir, f"grading_targets.json")
    
    mode = "repair" if args.repair else "trigger"
    pr_info(f"Starting grading {mode} for {len(student_repos)} repositories for {args.mp}...")

    targets = []

    push_occurred = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        if args.repair:
            future_to_repo = {executor.submit(repair_repo, repo, payload_dir, target_branch, ta_emails): repo for repo in student_repos}
        else:
            future_to_repo = {executor.submit(process_repo, repo, payload_dir, target_branch, args.force_push): repo for repo in student_repos}
        for future in concurrent.futures.as_completed(future_to_repo):
            repo_full_name = future_to_repo[future]
            try:
                result = future.result()
                if result:
                    commit_sha, pushed = result
                    if commit_sha:
                        targets.append({
                            "repo": repo_full_name,
                            "commit_sha": commit_sha
                        })
                    if pushed:
                        push_occurred = True
            except Exception as exc:
                pr_error(f"Repository {repo_full_name} generated an exception: {exc}")
            print("-" * 40)

    pr_success(f"Trigger Phase finished. Saving {len(targets)} target SHAs to {output_target_file}")
    try:
        with open(output_target_file, "w") as f:
            json.dump(targets, f, indent=2)
    except Exception as e:
        pr_error(f"Failed to save targets: {e}")

    if push_occurred:
        push_signal_file = os.path.join(mp_out_dir, ".push_occurred")
        try:
            with open(push_signal_file, "w") as f:
                f.write("true")
            pr_info(f"Push detected. Signal file created at {push_signal_file}")
        except Exception as e:
            pr_error(f"Failed to create push signal file: {e}")

if __name__ == "__main__":
    main()
