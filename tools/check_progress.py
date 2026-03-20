# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Check crawl progress: output pending repo names, count, and estimated API calls needed."""
import json
import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: check_progress.py <results_json>", file=sys.stderr)
        sys.exit(1)

    try:
        with open(sys.argv[1]) as f:
            results = json.load(f)
    except Exception as e:
        print(f"Error reading {sys.argv[1]}: {e}", file=sys.stderr)
        sys.exit(1)

    pending = [e["repo"] for e in results if e.get("status") == "In Progress"]
    # Output as tab-separated: count \t needed_api_calls \t comma-separated names
    print(f"{len(pending)}\t{len(pending) * 4}\t{', '.join(pending)}")

if __name__ == "__main__":
    main()
