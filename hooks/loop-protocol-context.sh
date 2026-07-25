#!/usr/bin/env bash
# SessionStart hook: arms the done-loop (baseline) and injects the loop protocol briefing.
# Pairs with loop-until-done.sh (Stop hook).
set -uo pipefail

JQ_BIN="$(command -v jq || true)"
PY_BIN="$(command -v python3 || true)"

HOOK_INPUT="$(cat)"

read_hook_field() {
  local field_name="$1"
  if [[ -n "$JQ_BIN" ]]; then
    printf '%s' "$HOOK_INPUT" | "$JQ_BIN" -r --arg key "$field_name" \
      'if .[$key] == null then "" else (.[$key] | tostring) end' 2>/dev/null
    return
  fi
  if [[ -n "$PY_BIN" ]]; then
    printf '%s' "$HOOK_INPUT" | "$PY_BIN" -c 'import sys, json
try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)
value = payload.get(sys.argv[1])
if value is None:
    sys.exit(0)
print("true" if value is True else "false" if value is False else value)' "$field_name" 2>/dev/null
    return
  fi
  # Last-resort fallback for plain string fields only.
  printf '%s' "$HOOK_INPUT" | sed -n "s/.*\"$field_name\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" | head -n1
}

hash_key() {
  if command -v shasum >/dev/null 2>&1; then printf '%s' "$1" | shasum | cut -d' ' -f1
  else printf '%s' "$1" | cksum | cut -d' ' -f1; fi
}

HOOK_CWD="$(read_hook_field cwd)"
SESSION_ID="$(read_hook_field session_id)"
TARGET_DIR="${HOOK_CWD:-${CLAUDE_PROJECT_DIR:-$PWD}}"
[[ -d "$TARGET_DIR" ]] && cd "$TARGET_DIR" 2>/dev/null || true

# Prune loop-state files older than 30 days so state never accumulates forever.
find "$HOME/.claude/loop-state" -type f -mtime +30 -delete 2>/dev/null || true

REPO_ROOT="$(command git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$REPO_ROOT" ]]; then
  cd "$REPO_ROOT" 2>/dev/null || true

  # Keep the gate's marker files out of git without touching the repo's .gitignore.
  EXCLUDE_FILE="$REPO_ROOT/.git/info/exclude"
  if [[ -d "$REPO_ROOT/.git/info" ]] && ! grep -qs '^\.claude/\.done$' "$EXCLUDE_FILE" 2>/dev/null; then
    printf '.claude/.done\n.claude/.blocked\n' >> "$EXCLUDE_FILE" 2>/dev/null || true
  fi

  SAFE_SESSION="${SESSION_ID//[^A-Za-z0-9_-]/_}"; [[ -z "$SAFE_SESSION" ]] && SAFE_SESSION="default"
  STATE_HOME="$HOME/.claude/loop-state/$(hash_key "$REPO_ROOT")"
  BASELINE_FILE="$STATE_HOME/baseline.$SAFE_SESSION"
  if [[ ! -f "$BASELINE_FILE" ]]; then
    mkdir -p "$STATE_HOME" 2>/dev/null || true
    base_head="$(command git rev-parse HEAD 2>/dev/null || true)"
    base_sig="$(hash_key "$(command git status --porcelain -- ':(exclude).claude/' 2>/dev/null | LC_ALL=C sort)")"
    { printf '%s\n%s\n' "$base_head" "$base_sig" > "$BASELINE_FILE"; } 2>/dev/null || true
  fi
fi

read -r -d '' briefing <<'EOF' || true
Loop protocol for this workspace (a policy the user has configured through Claude Code hooks):

A Stop hook (the done-loop gate) checks each turn before it can end. In this repository, work counts as finished only when every Stop-Ship criterion holds AND tests pass AND lint/format is clean AND all work is committed AND pushed (where a remote exists). Completion is attested by creating .claude/.done at the repository root. The gate re-verifies everything independently and revokes .done if any check fails, so .done is a request-to-verify, never proof.

Honest exit: when no further progress is possible -- blocked on the user (login, credentials, a product decision, access) or stuck on a technical dead end that cannot be resolved (a check that will not pass, a hang, a missing tool, an environment that cannot be fixed) -- writing .claude/.blocked at the repository root and stopping is a legitimate, honest end to the turn, not a failure. The .blocked file must not be empty: it carries 1-5 short lines in the user's language saying what is blocked and exactly what the USER must do next; the gate displays this text to the user when the turn ends, and the same explanation is repeated at the end of the reply. Changes the user did not ask for are never committed or pushed.

No-commit turn: a turn that produces no commits -- pure housekeeping (deleting branches, worktrees, or CI runs), a read-only investigation, or a question answered -- needs neither .done nor .blocked. Just stop: the gate detects that HEAD has not moved and the tree is clean, and lets the turn end on any branch.

Every final reply in this workspace ends with a short section addressed to the user: what was done, and "What you need to do" -- the concrete next action required from them, or an explicit note that nothing is required.

Git flow in this workspace is two-tier and uses DIRECT MERGE, not pull requests: branch feature/<name> off dev, commit AND push each logical chunk, merge finished tested work into dev, and promote dev -> main only when fully done. Commits directly to main/master, or branches created from them, are not part of this flow unless the user specifically asks for that. "Done means merged" here means direct-merged (feature -> dev -> promote dev -> main); there are no pull requests to open or wait for.

Quality practices in this workspace: write tests first, diagnose failures methodically, prove every claim with real output before saying it works, and run a thorough review before merging.
EOF

if [[ -n "$JQ_BIN" ]]; then
  "$JQ_BIN" -n --arg ctx "$briefing" \
    '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$ctx}}'
elif [[ -n "$PY_BIN" ]]; then
  "$PY_BIN" -c 'import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))' "$briefing"
else
  # SessionStart plain stdout is added to Claude's context, so degrade gracefully
  # without hand-rolled JSON escaping.
  printf '%s\n' "$briefing"
fi
