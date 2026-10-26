#!/usr/bin/env bash
# Publish only after the Checks workflow succeeds for this exact pushed commit.
set -euo pipefail
cd "$(dirname "$0")/.."
git diff --exit-code
git diff --cached --exit-code
release_commit=$(git rev-parse HEAD)
remote_commit=$(gh api repos/ScottiBYTE/ha-scottibyte-incus/commits/main --jq .sha)
if [ "$release_commit" != "$remote_commit" ]; then
  echo "Push the prepared commit to main before publishing."
  exit 1
fi
python3 - <<'CHECK'
import json
from pathlib import Path
assert json.loads(Path("custom_components/scottibyte_incus/manifest.json").read_text())["version"] == "0.1.9"
CHECK
run_id=""
for attempt in {1..20}; do
  run_id=$(gh run list --workflow Checks --commit "$release_commit" --event push --limit 1 --json databaseId --jq '.[0].databaseId // empty')
  if [ -n "$run_id" ]; then break; fi
  sleep 3
done
if [ -z "$run_id" ]; then
  echo "No Checks run found for this commit; no release created."
  exit 1
fi
if ! gh run watch "$run_id" --exit-status; then
  gh run view "$run_id" --log-failed
  exit 1
fi
if gh release view v0.1.9 >/dev/null 2>&1; then
  echo "v0.1.9 already exists; leaving it unchanged."
  exit 0
fi
if gh api repos/ScottiBYTE/ha-scottibyte-incus/git/ref/tags/v0.1.9 >/dev/null 2>&1; then
  tagged_commit=$(gh api repos/ScottiBYTE/ha-scottibyte-incus/commits/v0.1.9 --jq .sha)
  if [ "$tagged_commit" != "$release_commit" ]; then
    echo "Existing v0.1.9 tag points to another commit; no release created."
    exit 1
  fi
fi
gh release create v0.1.9 --target "$release_commit" --prerelease   --title "ScottiBYTE Incus v0.1.9 — readable mobile instance actions"   --notes-file RELEASE_NOTES_0.1.9.md
