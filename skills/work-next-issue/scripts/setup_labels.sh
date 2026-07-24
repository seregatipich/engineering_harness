#!/usr/bin/env bash
# Idempotently ensure the labels the work-next-issue skill relies on.
# Usage: bash setup_labels.sh <owner/repo>
set -euo pipefail

REPO="${1:?usage: setup_labels.sh <owner/repo>}"

gh label create "priority:critical" -c b60205 -R "$REPO" 2>/dev/null || true
gh label create "priority:high"     -c d93f0b -R "$REPO" 2>/dev/null || true
gh label create "priority:medium"   -c fbca04 -R "$REPO" 2>/dev/null || true
gh label create "priority:low"      -c 0e8a16 -R "$REPO" 2>/dev/null || true
gh label create "in-progress"       -c 1d76db -R "$REPO" 2>/dev/null || true
gh label create "awaiting-release"  -c 5319e7 -R "$REPO" 2>/dev/null || true

echo "labels ensured on $REPO"
