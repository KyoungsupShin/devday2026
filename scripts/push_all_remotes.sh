#!/usr/bin/env bash

# Push the selected branch to both public GitHub and SAP GitHub.
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

branch=${1:-$(git branch --show-current)}
if [[ -z "$branch" ]]; then
  echo "No branch is checked out. Pass a branch name explicitly." >&2
  exit 1
fi

git push origin "$branch"
git push sap "$branch"
