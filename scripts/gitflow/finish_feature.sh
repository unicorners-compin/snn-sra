#!/usr/bin/env bash
set -euo pipefail

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [[ "$CURRENT_BRANCH" != feature/* ]]; then
  echo "Current branch is not feature/*: $CURRENT_BRANCH"
  exit 1
fi

echo "Current branch: $CURRENT_BRANCH"
echo
echo "Next steps:"
echo "1) Push branch:"
echo "   git push -u origin $CURRENT_BRANCH"
echo "2) Open PR to develop with template:"
echo "   refs #<issue-id>"
echo "3) Merge after review + checks."
