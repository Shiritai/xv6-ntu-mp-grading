#!/bin/bash

# --- Default values ---
WHITELIST_FILE=""
REPO_KEYWORD=""
DEADLINE=""
DEADLINE_TS=0
DRY_RUN=false

# --- Usage ---
usage() {
    echo "Usage: $0 -f <whitelist_file> -r <repo_keyword> [-t <deadline>] [-o <output_file>] [-d]"
    echo "Parameters:"
    echo "  -f    Specify the file containing inviter accounts (one name per line)"
    echo "  -r    Specify the required keyword in the repository name"
    echo "  -t    [Optional] Specify a deadline (e.g. \"2026-03-10 23:59:59 +0800\"). Invitations sent after this time will be ignored."
    echo "  -o    [Optional] Output successfully accepted Repos to a JSON file (e.g., students.json)"
    echo "  -d    Enable Dry-run mode (preview only, no actual execution)"
    exit 1
}

# --- Parse arguments ---
while getopts "f:r:t:o:d" opt; do
    case "$opt" in
        f) WHITELIST_FILE=$OPTARG ;;
        r) REPO_KEYWORD=$OPTARG ;;
        t) DEADLINE=$OPTARG ;;
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

if [[ -n "$DEADLINE" ]]; then
    DEADLINE_TS=$(date -d "$DEADLINE" +%s 2>/dev/null)
    if [[ $? -ne 0 ]]; then
        echo "Error: Invalid deadline format. Please use formats like \"2026-03-10 23:59:59\" or \"2026-03-10 23:59:59 +0800\"."
        exit 1
    fi
    echo "Deadline set to: $DEADLINE (UNIX Timestamp: $DEADLINE_TS)"
fi

# --- Read whitelist and convert to JSON array ---
# Robust parsing: Handle 3-column CSV (3rd col) or 1-column plain list (1st col). Remove quotes/spaces.
USER_LIST_JSON=$(awk -F',' '{
    if (NF >= 3) { val=$3 } else { val=$1 }
    gsub(/"/, "", val); gsub(/[[:space:]]/, "", val);
    if (val != "") print val
}' "$WHITELIST_FILE" | grep -v '^$' | jq -R . | jq -s -c .)

[[ "$DRY_RUN" == true ]] && echo "DEBUG: USER_LIST_JSON length: $(echo "$USER_LIST_JSON" | jq 'length')"

echo "--------------------------------------------------"
echo "Phase 1: Accept Invitations"
echo "Starting filtering task..."
echo "Whitelist file: $WHITELIST_FILE"
echo "Repo keyword: $REPO_KEYWORD"
[[ -n "$DEADLINE" ]] && echo "Deadline Threshold: $DEADLINE"
[[ "$DRY_RUN" == true ]] && echo "Mode: [DRY-RUN]" || echo "Mode: [EXECUTION]"
echo "--------------------------------------------------"

# --- Key fix: call gh api first, then pipe to jq ---
# Filter for matching repos and split into private/public lists
ALL_INVITATIONS=$(gh api user/repository_invitations --paginate)

# Valid Private Invitations
INVITATIONS=$(echo "$ALL_INVITATIONS" | jq -c --argjson list "$USER_LIST_JSON" --arg kw "$REPO_KEYWORD" --argjson deadline_ts "$DEADLINE_TS" '
  .[] | select(
    (.inviter.login as $u | $list | index($u) != null) and
    (.repository.name | contains($kw)) and
    (.repository.private == true) and
    (if $deadline_ts > 0 then (.created_at | fromdateiso8601) <= $deadline_ts else true end)
  ) | {id: .id, repo: .repository.full_name, inviter: .inviter.login}
')

# Late Private Invitations
LATE_INVITATIONS=$(echo "$ALL_INVITATIONS" | jq -c --argjson list "$USER_LIST_JSON" --arg kw "$REPO_KEYWORD" --argjson deadline_ts "$DEADLINE_TS" '
  .[] | select(
    (.inviter.login as $u | $list | index($u) != null) and
    (.repository.name | contains($kw)) and
    (.repository.private == true) and
    (if $deadline_ts > 0 then (.created_at | fromdateiso8601) > $deadline_ts else false end)
  ) | {id: .id, repo: .repository.full_name, inviter: .inviter.login, created_at: .created_at}
')

if [[ -n "$LATE_INVITATIONS" ]]; then
    echo "  ⏰ LATE INVITATIONS DETECTED (Sent after the deadline):"
    echo "$LATE_INVITATIONS" | while read -r l_item; do
        L_REPO=$(echo "$l_item" | jq -r '.repo')
        L_USER=$(echo "$l_item" | jq -r '.inviter')
        L_TIME=$(echo "$l_item" | jq -r '.created_at')
        echo "    - $L_REPO (From: $L_USER, At: $L_TIME)"
    done
    echo "  These invitations will NOT be accepted."
    echo "--------------------------------------------------"
fi

PUBLIC_REPOS=$(echo "$ALL_INVITATIONS" | jq -c --argjson list "$USER_LIST_JSON" --arg kw "$REPO_KEYWORD" '
  .[] | select(
    (.inviter.login as $u | $list | index($u) != null) and
    (.repository.name | contains($kw)) and
    (.repository.private == false)
  ) | {repo: .repository.full_name, inviter: .inviter.login}
')

if [[ -n "$PUBLIC_REPOS" ]]; then
    echo "  ⚠️ WARNING: The following matching invitations are PUBLIC repositories and WILL NOT be accepted:"
    echo "$PUBLIC_REPOS" | while read -r p_item; do
        P_REPO=$(echo "$p_item" | jq -r '.repo')
        P_USER=$(echo "$p_item" | jq -r '.inviter')
        echo "    - $P_REPO (From: $P_USER)"
    done
    echo "  Please ask these students to recreate their repositories as Private."
fi

if [[ -z "$INVITATIONS" ]]; then
    echo "  ⚪ No new private invitations to accept."
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
    
    gh api "user/repos?affiliation=collaborator&per_page=100" --paginate | jq -r -s \
      --argjson list "$USER_LIST_JSON" \
      --arg kw "$REPO_KEYWORD" \
      'add | [.[] | select((.owner.login as $u | $list | index($u) != null) and (.name | contains($kw))) | .full_name]' \
      >| "$OUTPUT_FILE"
      
    if [[ $? -eq 0 ]]; then
        echo "  ✅ Successfully retrieved global list! Overwritten to: $OUTPUT_FILE"
    else
        echo "  ❌ Failed to retrieve global list. Please check API permissions or network status."
    fi
fi

echo "--------------------------------------------------"
echo "Task complete!"
