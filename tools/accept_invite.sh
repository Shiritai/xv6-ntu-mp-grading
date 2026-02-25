#!/bin/bash

# --- Default values ---
WHITELIST_FILE=""
REPO_KEYWORD=""
DRY_RUN=false

# --- Usage ---
usage() {
    echo "Usage: $0 -f <whitelist_file> -r <repo_keyword> [-o <output_file>] [-d]"
    echo "Parameters:"
    echo "  -f    Specify the file containing inviter accounts (one name per line)"
    echo "  -r    Specify the required keyword in the repository name"
    echo "  -o    [Optional] Output successfully accepted Repos to a JSON file (e.g., students.json)"
    echo "  -d    Enable Dry-run mode (preview only, no actual execution)"
    exit 1
}

# --- Parse arguments ---
while getopts "f:r:o:d" opt; do
    case "$opt" in
        f) WHITELIST_FILE=$OPTARG ;;
        r) REPO_KEYWORD=$OPTARG ;;
        o) OUTPUT_FILE=$OPTARG ;;
        d) DRY_RUN=true ;;
        *) usage ;;
    esac
done

# --- Basic checks ---
if [[ -z "$WHITELIST_FILE" || -z "$REPO_KEYWORD" ]]; then
    usage
fi

if [[ ! -f "$WHITELIST_FILE" ]]; then
    echo "Error: File not found $WHITELIST_FILE"
    exit 1
fi

# --- Read whitelist and convert to JSON array ---
USER_LIST_JSON=$(grep -v '^$' "$WHITELIST_FILE" | jq -R . | jq -s -c .)

echo "--------------------------------------------------"
echo "Phase 1: Accept Invitations"
echo "Starting filtering task..."
echo "Whitelist file: $WHITELIST_FILE"
echo "Repo keyword: $REPO_KEYWORD"
[[ "$DRY_RUN" == true ]] && echo "Mode: [DRY-RUN]" || echo "Mode: [EXECUTION]"
echo "--------------------------------------------------"

# --- Key fix: call gh api first, then pipe to jq ---
INVITATIONS=$(gh api user/repository_invitations --paginate | jq -c --argjson list "$USER_LIST_JSON" --arg kw "$REPO_KEYWORD" '
  .[] | select(
    (.inviter.login as $u | $list | index($u) != null) and 
    (.repository.name | contains($kw))
  ) | {id: .id, repo: .repository.full_name, inviter: .inviter.login}
')

if [[ -z "$INVITATIONS" ]]; then
    echo "  ⚪ No new invitations to accept."
else
    # --- Execution Phase ---
    echo "$INVITATIONS" | while read -r item; do
    ID=$(echo "$item" | jq -r '.id')
    REPO=$(echo "$item" | jq -r '.repo')
    USER=$(echo "$item" | jq -r '.inviter')

    if [[ "$DRY_RUN" == true ]]; then
        echo "[Preview] Found matching invitation: $REPO (Inviter: $USER) | ID: $ID"
    else
        echo "Accepting: $REPO (From: $USER)..."
        gh api -X PATCH "user/repository_invitations/$ID" --silent
        if [[ $? -eq 0 ]]; then
            echo "  ✅ Successfully accepted"
            if [[ -n "$OUTPUT_FILE" ]]; then
                echo "  📝 Will be written globally in the final phase"
            fi
        else
            echo "  ❌ Error occurred"
        fi
    fi
done
fi

echo "--------------------------------------------------"
echo "Phase 2: Automatically aggregate and output all eligible repository lists"

if [[ -n "$OUTPUT_FILE" && "$DRY_RUN" == false ]]; then
    mkdir -p "${OUTPUT_FILE%/*}" || echo "  ⚠️ Warning: Failed to create directory ${OUTPUT_FILE%/*}"
    echo "Syncing all repositories containing keyword [$REPO_KEYWORD] and present in whitelist from GitHub API..."
    
    gh api "user/repos?affiliation=collaborator&per_page=100" --paginate | jq -r \
      --argjson list "$USER_LIST_JSON" \
      --arg kw "$REPO_KEYWORD" \
      '[.[] | select((.owner.login as $u | $list | index($u) != null) and (.name | contains($kw))) | .full_name]' \
      > "$OUTPUT_FILE"
      
    if [[ $? -eq 0 ]]; then
        echo "  ✅ Successfully retrieved global list! Overwritten to: $OUTPUT_FILE"
    else
        echo "  ❌ Failed to retrieve global list. Please check API permissions or network status."
    fi
fi

echo "--------------------------------------------------"
echo "Task complete!"
