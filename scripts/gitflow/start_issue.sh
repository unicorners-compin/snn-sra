#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <issue_id> <slug> [feature|hotfix]"
  exit 1
fi

ISSUE_ID="$1"
SLUG="$2"
KIND="${3:-feature}"

if [[ "$KIND" != "feature" && "$KIND" != "hotfix" ]]; then
  echo "KIND must be feature or hotfix"
  exit 1
fi

if [[ "$KIND" == "feature" ]]; then
  BASE="develop"
else
  BASE="main"
fi

BRANCH="${KIND}/issue-${ISSUE_ID}-${SLUG}"

git fetch origin
git checkout "$BASE"
git pull --ff-only origin "$BASE" || true
git checkout -b "$BRANCH"

echo "Created branch: $BRANCH (from $BASE)"
