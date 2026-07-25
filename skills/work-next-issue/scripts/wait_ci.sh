#!/usr/bin/env bash
# Wait for every GitHub Actions run at an EXACT commit to conclude.
#
# "Done" for this skill means CI is green at the tip that was actually pushed.
# The two ways that check goes wrong are both about matching the wrong run:
# selecting by branch (which returns whatever ran last, possibly an older commit)
# or prefix-matching a short SHA. This script matches headSha exactly, and treats
# "no run exists yet" as "keep waiting" rather than as success — a push takes a
# few seconds to register a workflow run, and an early poll otherwise reports a
# clean slate.
#
# Usage: bash wait_ci.sh <owner/repo> <full-40-char-sha> [--timeout <seconds>] [--interval <seconds>]
#
# Output: one line per run as it concludes, then a summary.
# Exit: 0 all concluded successfully (or nothing is configured to run)
#       1 at least one run failed, was cancelled, or timed out on GitHub's side
#       2 usage error
#       3 local timeout waiting for runs to conclude
set -euo pipefail

command -v gh >/dev/null 2>&1 || { echo "wait_ci.sh: required CLI 'gh' not found on PATH" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "wait_ci.sh: required CLI 'jq' not found on PATH" >&2; exit 2; }

REPO="${1:-}"; SHA="${2:-}"
shift 2 2>/dev/null || { echo "usage: wait_ci.sh <owner/repo> <full-sha> [--timeout N] [--interval N]" >&2; exit 2; }
[[ -n "$REPO" && -n "$SHA" ]] || { echo "usage: wait_ci.sh <owner/repo> <full-sha> [--timeout N] [--interval N]" >&2; exit 2; }

# A short SHA would silently match the wrong commit through GitHub's prefix
# handling, so require the full form rather than trying to expand it here.
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "wait_ci.sh: need a full 40-character SHA, got '$SHA'" >&2; exit 2; }

TIMEOUT=3600
INTERVAL=30
GRACE=120   # how long to keep waiting when no run has appeared for this SHA yet

while (( $# )); do
  case "$1" in
    --timeout)  TIMEOUT="${2:-}"; shift 2 || true ;;
    --interval) INTERVAL="${2:-}"; shift 2 || true ;;
    *) echo "wait_ci.sh: unknown argument '$1'" >&2; exit 2 ;;
  esac
done
[[ "$TIMEOUT" =~ ^[0-9]+$ && "$INTERVAL" =~ ^[0-9]+$ ]] || { echo "wait_ci.sh: --timeout and --interval take integers" >&2; exit 2; }

runs_at_sha() {
  # --json headSha is the only field that identifies the commit unambiguously;
  # filtering client-side keeps this correct even as gh's flags change.
  gh run list --repo "$REPO" --limit 100 \
    --json headSha,databaseId,name,status,conclusion,url 2>/dev/null \
    | jq -c --arg sha "$SHA" '[.[] | select(.headSha == $sha)]' 2>/dev/null \
    || echo '[]'
}

started=$(date +%s)
reported=""
seen_any=0

printf 'wait_ci: %s @ %s (timeout %ss, poll %ss)\n' "$REPO" "${SHA:0:12}" "$TIMEOUT" "$INTERVAL"

while :; do
  now=$(date +%s)
  elapsed=$(( now - started ))
  if (( elapsed > TIMEOUT )); then
    echo "wait_ci: TIMEOUT after ${elapsed}s — runs still in progress" >&2
    exit 3
  fi

  runs="$(runs_at_sha)"
  count="$(jq 'length' <<<"$runs")"

  if (( count == 0 )); then
    if (( seen_any == 0 && elapsed < GRACE )); then
      sleep "$INTERVAL"; continue
    fi
    if (( seen_any == 0 )); then
      # Nothing ever appeared. A repo with no workflows is a legitimate state,
      # so this is success — but say so plainly rather than implying a green run.
      echo "wait_ci: no workflow runs are configured for this commit — nothing to wait for"
      exit 0
    fi
  fi
  seen_any=1

  # Report each run once, as it concludes, so a long wait shows progress.
  while IFS=$'\t' read -r id name concl url; do
    [[ -z "$id" ]] && continue
    case "$reported" in *"|$id|"*) continue ;; esac
    reported="${reported}|$id|"
    printf '  %-12s %-28s %s\n' "$concl" "$name" "$url"
  done < <(jq -r '.[] | select(.status == "completed") | [.databaseId, .name, .conclusion, .url] | @tsv' <<<"$runs")

  pending="$(jq '[.[] | select(.status != "completed")] | length' <<<"$runs")"
  if (( pending == 0 )); then
    # skipped and neutral are not failures; anything else that is not success is.
    bad="$(jq -r '[.[] | select(.conclusion != "success" and .conclusion != "skipped" and .conclusion != "neutral")] | length' <<<"$runs")"
    total="$(jq 'length' <<<"$runs")"
    if (( bad > 0 )); then
      echo "wait_ci: FAILED — $bad of $total run(s) did not succeed at ${SHA:0:12}" >&2
      exit 1
    fi
    echo "wait_ci: GREEN — $total run(s) succeeded at ${SHA:0:12}"
    exit 0
  fi

  sleep "$INTERVAL"
done
