#!/bin/bash
# One-time setup for results publishing: creates the orphan results branch in a
# dedicated worktree (.results-worktree) that the supervisor commits+pushes to
# after each project. Safe to rerun; no-op if the worktree already exists.
set -euo pipefail
cd "$(dirname "$0")/.."

BRANCH="${1:-results}"
WT=".results-worktree"

if [ -e "$WT/.git" ]; then
    echo "$WT already set up"
    exit 0
fi

if git show-ref --quiet "refs/heads/$BRANCH" || git show-ref --quiet "refs/remotes/origin/$BRANCH"; then
    # Branch exists (e.g. cloned on a new machine): just add the worktree.
    git fetch origin "$BRANCH" 2>/dev/null || true
    git worktree add "$WT" "$BRANCH"
else
    git worktree add --detach "$WT" HEAD
    (
        cd "$WT"
        git checkout --orphan "$BRANCH" -q
        git rm -rfq .
        find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
        printf '# researchAI — results\n\nAuto-published research outputs from the autonomous harness. Code lives on `main`.\n' > README.md
        git add README.md
        git commit -qm "results branch: research outputs live here"
        git push -u origin "$BRANCH"
    )
fi
echo "results branch '$BRANCH' ready in $WT"
