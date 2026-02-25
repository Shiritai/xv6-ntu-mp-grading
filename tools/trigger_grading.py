import os
import sys
import json
import shutil
import subprocess
import tempfile
import argparse
import concurrent.futures

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

def process_repo(repo_full_name, payload_dir, github_token, branch, force=False):
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
        if not ok or not status:
            if force:
                pr_warn(f"No changes for {repo_full_name}, but --force is set. Forcing an empty commit to trigger CI.")
                run_cmd("git commit --allow-empty -m 'chore(grading): force trigger grading test suite'", cwd=clone_dir)
            else:
                pr_info(f"No changes (payload already matches) for {repo_full_name}. Skipping redundant push.")
                ok, sha = run_cmd("git rev-parse HEAD", cwd=clone_dir)
                return sha if ok else None
        else:
            ok, err = run_cmd("git commit -m 'chore(grading): deploy private tests and trigger grading'", cwd=clone_dir)
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
        return sha

def main():
    parser = argparse.ArgumentParser(description="TA Script to deploy private tests and trigger grading.")
    parser.add_argument("--mp", required=True, help="Machine Problem identifier (e.g., mp0, mp1).")
    parser.add_argument("--students", required=True, help="Path to JSON file containing list of 'owner/repo'.")
    parser.add_argument("--grading-dir", required=True, help="Path to xv6-ntu-mp-grading workspace.")
    parser.add_argument("--branch", help="Target branch in student repositories (default: ntuos2026/mpX).")
    parser.add_argument("--force", action="store_true", help="Force an empty commit to trigger CI even if there are no payload changes.")
    args = parser.parse_args()

    # Automatically derive the default branch if not explicitly provided
    target_branch = args.branch if args.branch else f"ntuos2026/{args.mp}"

    # Note: Authentication is handled transparently by the `gh` CLI or underlying `git` config (SSH/HTTPS)

    try:
        with open(args.students, "r") as f:
            student_repos = json.load(f)
    except Exception as e:
        pr_error(f"Failed to read students list: {e}")
        sys.exit(1)

    payload_dir = os.path.join(args.grading_dir, args.mp, "payload")
    if not os.path.isdir(payload_dir):
        pr_warn(f"Payload directory {payload_dir} not found. Will trigger grading with empty commits.")
        
    # We output grading_targets.json inside the MP result directory
    mp_out_dir = os.path.join(args.grading_dir, args.mp, "result")
    os.makedirs(mp_out_dir, exist_ok=True)
    output_target_file = os.path.join(mp_out_dir, f"grading_targets.json")
    
    pr_info(f"Starting grading trigger for {len(student_repos)} repositories for {args.mp}...")
    
    targets = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_repo = {executor.submit(process_repo, repo, payload_dir, None, target_branch, args.force): repo for repo in student_repos}
        for future in concurrent.futures.as_completed(future_to_repo):
            repo_full_name = future_to_repo[future]
            try:
                commit_sha = future.result()
                if commit_sha:
                    targets.append({
                        "repo": repo_full_name,
                        "commit_sha": commit_sha
                    })
            except Exception as exc:
                pr_error(f"Repository {repo_full_name} generated an exception: {exc}")
            print("-" * 40)

    pr_success(f"Trigger Phase finished. Saving {len(targets)} target SHAs to {output_target_file}")
    try:
        with open(output_target_file, "w") as f:
            json.dump(targets, f, indent=2)
    except Exception as e:
        pr_error(f"Failed to save targets: {e}")

if __name__ == "__main__":
    main()
