import json
import zipfile
import requests
import io
import argparse
import csv
import os
import subprocess
import sys
import concurrent.futures

GITHUB_API_URL = "https://api.github.com"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# Default workflow path executed by the student's repository
WORKFLOW_PATH = ".github/workflows/grading.yml"

def pr_error(msg):
    print(f"\033[91m[ERROR]\033[0m {msg}", file=sys.stderr)

def pr_info(msg):
    print(f"\033[94m[INFO]\033[0m {msg}")

def pr_success(msg):
    print(f"\033[92m[SUCCESS]\033[0m {msg}")

def pr_warn(msg):
    print(f"\033[93m[WARN]\033[0m {msg}")

def get_headers():
    token = GITHUB_TOKEN
    
    if not token:
        # Fallback to fetching the token from the gh CLI
        try:
            res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
            token = res.stdout.strip()
        except Exception:
            pass
            
    if not token:
        pr_error("GITHUB_TOKEN environment variable is not set, and 'gh auth token' failed. Please login with gh CLI.")
        sys.exit(1)
        
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

def fetch_run_for_commit(repo_owner, repo_name, commit_sha):
    """Fetches the successful grading workflow run associated with the TA commit."""
    pr_info(f"Querying workflow runs for {repo_owner}/{repo_name} at commit {commit_sha[:8]}...")
    url = f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/actions/runs"
    params = {
        "head_sha": commit_sha,
        "per_page": 100
    }
    
    response = requests.get(url, headers=get_headers(), params=params)
    if response.status_code != 200:
        pr_error(f"Failed to fetch runs API: {response.status_code} - {response.text}")
        return None

    data = response.json()
    valid_runs = []

    for run in data.get("workflow_runs", []):
        if run.get("path") == WORKFLOW_PATH and run.get("status") == "completed":
            valid_runs.append(run)

    if not valid_runs:
         pr_warn(f"No completed grading workflow found for {commit_sha[:8]}. Student hasn't triggered CI or it's still running.")
         return None
         
    success_runs = [r for r in valid_runs if r.get("conclusion") == "success"]
    if success_runs:
        best_run = sorted(success_runs, key=lambda x: x['updated_at'], reverse=True)[0]
        return best_run
        
    best_failed_run = sorted(valid_runs, key=lambda x: x['updated_at'], reverse=True)[0]
    pr_warn(f"Found grading workflow run {best_failed_run['id']} but it failed (conclusion: {best_failed_run.get('conclusion')}). Retrieving artifacts anyway.")
    return best_failed_run

def download_artifact(artifacts_url):
    response = requests.get(artifacts_url, headers=get_headers())
    if response.status_code != 200:
        pr_error(f"Failed to list artifacts: {response.status_code}")
        return None

    artifacts = response.json().get("artifacts", [])
    report_artifact = next((a for a in artifacts if a["name"] == "grading-report"), None)
    
    if not report_artifact:
        pr_warn("No 'grading-report' artifact found in this run.")
        return None
        
    pr_info(f"Found artifact {report_artifact['id']}. Downloading zip (size: {report_artifact['size_in_bytes']} bytes)...")
    download_url = report_artifact["archive_download_url"]
    
    zip_resp = requests.get(download_url, headers=get_headers(), allow_redirects=True)
    if zip_resp.status_code != 200:
        pr_error(f"Failed to download artifact zip: {zip_resp.status_code}")
        return None
        
    return zip_resp.content

def parse_report_from_zip(zip_bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            if "report.json" not in archive.namelist():
                 pr_error("Artifact zip doesn't contain 'report.json'.")
                 return None
            with archive.open("report.json") as f:
                report_data = json.load(f)
                return report_data
    except Exception as e:
        pr_error(f"Failed to unzip and parse report: {e}")
        return None

def process_student_repo(repo_owner, repo_name, ta_commit_sha, reports_dir):
    # FIRST: Check repository visibility to prevent cheating (turning public after action passes)
    url = f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}"
    response = requests.get(url, headers=get_headers())
    if response.status_code == 200:
        repo_data = response.json()
        if not repo_data.get("private", True):
            pr_warn(f"Cheating detected! {repo_owner}/{repo_name} is a PUBLIC repository. Enforcing penalty.")
            return {"repo": f"{repo_owner}/{repo_name}", "score": 0, "status": "Public Repo Penalty", "run_url": repo_data.get("html_url")}

    run = fetch_run_for_commit(repo_owner, repo_name, ta_commit_sha)
    if not run:
        return {"repo": f"{repo_owner}/{repo_name}", "score": 0, "status": "No Run / Missing"}

    run_url = run['html_url']
    artifacts_url = run['artifacts_url']
    
    zip_bytes = download_artifact(artifacts_url)
    if not zip_bytes:
        return {"repo": f"{repo_owner}/{repo_name}", "score": 0, "status": "No Artifact", "run_url": run_url}

    report = parse_report_from_zip(zip_bytes)
    if not report:
         return {"repo": f"{repo_owner}/{repo_name}", "score": 0, "status": "Parse Error", "run_url": run_url}

    final_score = report.get('scores', {}).get('final_score', 0)
    pr_success(f"Parsed final score: {final_score}")
    
    # Preserve the report.json artifact
    try:
        if reports_dir:
            student_report_path = os.path.join(reports_dir, f"{repo_owner}_{repo_name}_report.json")
            with open(student_report_path, "w") as rf:
                json.dump(report, rf, indent=2)
            pr_info(f"Saved artifact to {student_report_path}")
    except Exception as e:
        pr_warn(f"Failed to locally preserve artifact for {repo_owner}: {e}")
    
    return {
        "repo": f"{repo_owner}/{repo_name}", 
        "score": final_score, 
        "status": "Success", 
        "run_url": run_url,
        "detail": report
    }

def main():
    parser = argparse.ArgumentParser(description="Zero-submission CI/CD Crawler for xv6 grading.")
    parser.add_argument("--targets", help="Path to the JSON target mapping generated by trigger_grading.py")
    parser.add_argument("--commit", help="Global commit SHA (fallback if --targets not used)")
    parser.add_argument("--students", help="Global student list if using --commit (JSON list of 'owner/repo').")
    parser.add_argument("--output", default="final_grades.json", help="Output file for aggregated results.")
    parser.add_argument("--reports-dir", help="Directory to save individual student report.json artifacts. (Default: reports)")
    args = parser.parse_args()

    targets = []
    
    if args.targets:
        try:
            with open(args.targets, "r") as f:
                targets = json.load(f)
        except Exception as e:
            pr_error(f"Failed to read targets file: {e}")
            sys.exit(1)
    elif args.commit and args.students:
        try:
            with open(args.students, "r") as f:
                student_repos = json.load(f)
                targets = [{"repo": r, "commit_sha": args.commit} for r in student_repos]
        except Exception as e:
            pr_error(f"Failed to read students list: {e}")
            sys.exit(1)
    else:
        pr_error("You must provide either --targets OR both --commit and --students.")
        sys.exit(1)

    results = []
    pr_info(f"Starting grading crawl for {len(targets)} target repositories...")
    
    reports_dir = args.reports_dir or "reports"
    os.makedirs(reports_dir, exist_ok=True)
    
    valid_targets = []
    for target in targets:
        repo_full_name = target.get("repo")
        commit_sha = target.get("commit_sha")
        
        if not repo_full_name or not commit_sha:
             pr_warn(f"Invalid target entry: {target}. Skipping.")
             continue
             
        parts = repo_full_name.split("/")
        if len(parts) != 2:
             pr_warn(f"Invalid repo format: {repo_full_name}. Skipping.")
             continue
             
        valid_targets.append((repo_full_name, commit_sha, parts[0], parts[1]))
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_target = {
            executor.submit(process_student_repo, owner, name, commit_sha, reports_dir): repo_full_name 
            for repo_full_name, commit_sha, owner, name in valid_targets
        }
        for future in concurrent.futures.as_completed(future_to_target):
            repo_full_name = future_to_target[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                pr_error(f"Repository {repo_full_name} generated an exception during crawl: {exc}")
            print("-" * 40)

    pr_success(f"Grading finished. Saving aggregated results to {args.output}")
    try:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
            
        csv_file = args.output.replace(".json", ".csv")
        if not csv_file.endswith(".csv"):
            csv_file += ".csv"
        
        with open(csv_file, "w", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Repository", "Status", "Final Score", "Run URL"])
            for res in results:
                writer.writerow([res.get("repo", ""), res.get("status", ""), res.get("score", ""), res.get("run_url", "")])
        pr_success(f"CSV exported to {csv_file}")
    except Exception as e:
        pr_error(f"Failed to save output: {e}")

if __name__ == "__main__":
    main()
