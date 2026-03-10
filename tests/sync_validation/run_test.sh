#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Dynamic path resolution (Portable)
TEST_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$TEST_DIR/../.." && pwd)
SANDBOX="$TEST_DIR/sandbox"

info() { echo -e "${GREEN}[INFO] $1${NC}"; }
warn() { echo -e "${YELLOW}[WARN] $1${NC}"; }
error() { echo -e "${RED}[ERROR] $1${NC}"; exit 1; }

info "0. Initializing portable sandbox environment..."
rm -rf "$SANDBOX"
mkdir -p "$SANDBOX"
cd "$SANDBOX"

# Official Template base
TEMPLATE_URL="https://github.com/Shiritai/xv6-ntu-mp.git"
TEMPLATE_BRANCH="ntuos2026/mp-template"
TEST_MP="mp-test"

REMOTE_REPO_1="$SANDBOX/remote_student_1.git"
REMOTE_REPO_2="$SANDBOX/remote_student_2.git"

info "1. Fetching official template base from GitHub..."
git clone -b "$TEMPLATE_BRANCH" "$TEMPLATE_URL" template_base

# Prepare Mock Remotes
git init --bare "$REMOTE_REPO_1"
git init --bare "$REMOTE_REPO_2"

cd template_base
git checkout -b "ntuos2026/$TEST_MP"
# Inject TA Email for sync detection
sed -i 's/TA_EMAILS=.*/TA_EMAILS="ntu-ta@example.com"/' mp.conf
git add mp.conf
git commit -m "Initialize test branch from official template" --no-verify

# Push template to both students' private bare remotes
git remote add mock_origin_1 "$REMOTE_REPO_1"
git push mock_origin_1 "ntuos2026/$TEST_MP"

git remote add mock_origin_2 "$REMOTE_REPO_2"
git push mock_origin_2 "ntuos2026/$TEST_MP"
cd ..

# 2. Setup Mock Student Repos
info "2. Setting up mock student repositories..."

# Student 1
git clone "$REMOTE_REPO_1" -b "ntuos2026/$TEST_MP" student_repo_1
cd student_repo_1
echo "// Student 1 specific code" >> user/student_logic.c
git add .
git commit -m "feat: student 1 starting $TEST_MP" --no-verify
git push origin "ntuos2026/$TEST_MP"
cd ..

# Student 2
git clone "$REMOTE_REPO_2" -b "ntuos2026/$TEST_MP" student_repo_2
cd student_repo_2
echo "// Student 2 specific code" >> user/student_logic.c
git add .
git commit -m "feat: student 2 starting $TEST_MP" --no-verify
git push origin "ntuos2026/$TEST_MP"
cd ..

# 3. Setup Mock Grading Repo (Syncing from current project root)
info "3. Preparing mock grading tools..."
mkdir -p "grading/$TEST_MP/public/doc"
mkdir -p "grading/$TEST_MP/public/tests"
echo "Official Spec v1.1 - Portable Test" >> "grading/$TEST_MP/public/doc/spec.md"
echo "def test_sync(): assert True" >> "grading/$TEST_MP/public/tests/test_sync_public.py"

# Copy tools from current project
cp -r "$REPO_ROOT/tools" "grading/"
chmod +x "grading/tools/"*

# Generate mock students JSON
# We use absolute paths to local bare repos to avoid network during test
echo '["'"$REMOTE_REPO_1"'", "'"$REMOTE_REPO_2"'"]' > "grading/mock_students.json"


# 4. TA Broadcast simulation
info "4. Simulating TA Parallel Broadcast..."
cd "grading"
export GIT_AUTHOR_NAME="NTU TA"
export GIT_AUTHOR_EMAIL="ntu-ta@example.com"
export GIT_COMMITTER_NAME="NTU TA"
export GIT_COMMITTER_EMAIL="ntu-ta@example.com"

# Broadcase to all JSON targets
./tools/broadcast_update.sh --mp "$TEST_MP" --repos-list "mock_students.json" --message "Hot-fix: update spec via portable test"
cd ..

# 5. Student Sync simulation
info "5. Simulating Student Sync (Blocking prompt handling)..."
for i in 1 2; do
    info "  -> Syncing student $i"
    cd "student_repo_$i"
    export SIMULATION_MODE=1
    export IGNORE_TTY_CHECK=1
    unset GITHUB_ACTIONS
    unset OFFICIAL_GRADING
    echo "y" | ./mp.sh sync
    cd ..
done

# 6. Verification
info "6. Verifying synchronization results..."

for i in 1 2; do
    cd "student_repo_$i"
    
    # Check asset propagation
    if [ ! -f "doc/spec.md" ] || ! grep -q "Portable Test" doc/spec.md; then
        error "FAIL: doc/spec.md not correctly updated in student $i."
    fi

    # Check student work preservation
    if ! grep -q "Student $i specific code" user/student_logic.c; then
        error "FAIL: Student $i's local file 'user/student_logic.c' was lost!"
    fi

    # Check snapshot existence
    SNAPSHOT_COUNT=$(git branch --list "snapshot-*" | wc -l)
    if [ "$SNAPSHOT_COUNT" -eq 0 ]; then
        error "FAIL: No snapshot branch was created during sync in student $i."
    fi
    cd ..
    info "  -> Verification passed for student $i."
done

info "7. Git Graph Verification (Student 1):"
cd student_repo_1
git log --oneline --graph --all -n 10
cd ..

info "🎉 PARALLEL BROADCAST AND PIPELINE WHITE-BOX TEST PASSED!"

