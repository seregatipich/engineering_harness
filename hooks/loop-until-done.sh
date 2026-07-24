#!/usr/bin/env bash
# Stop hook: the done-loop gate. Refuses to let the turn end until the work is
# verifiably complete (tests, lint, committed, pushed, .claude/.done attested),
# or until an honest exit via .claude/.blocked.
#
# Blocking uses the canonical Stop mechanism: exit 2 with the reason on stderr.
# Allowing uses exit 0; user-facing notes use JSON {systemMessage}.
# Pairs with loop-protocol-context.sh (SessionStart hook), which arms the
# per-session baseline used by session_is_armed.
set -uo pipefail

JQ_BIN="$(command -v jq || true)"
PY_BIN="$(command -v python3 || true)"
TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"

MAX_ITERS="${CLAUDE_LOOP_MAX_ITERS:-12}"
[[ "$MAX_ITERS" =~ ^[0-9]+$ ]] || MAX_ITERS=12
LINT_TIMEOUT="${CLAUDE_LOOP_LINT_TIMEOUT:-120}"
TEST_TIMEOUT="${CLAUDE_LOOP_TEST_TIMEOUT:-300}"
VERIFY_TIMEOUT="${CLAUDE_LOOP_VERIFY_TIMEOUT:-480}"
GIT_TIMEOUT="${CLAUDE_LOOP_GIT_TIMEOUT:-20}"

VERIFY_FAIL_DETAIL=""
GIT_REPO=0
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

json_escape() {
  local raw="$1"
  if [[ -n "$PY_BIN" ]]; then
    printf '%s' "$raw" | "$PY_BIN" -c 'import sys, json; sys.stdout.write(json.dumps(sys.stdin.read()))'
    return
  fi
  raw="${raw//\\/\\\\}"; raw="${raw//\"/\\\"}"; raw="${raw//$'\n'/\\n}"; raw="${raw//$'\t'/\\t}"
  printf '"%s"' "$raw"
}

hash_key() {
  if command -v shasum >/dev/null 2>&1; then printf '%s' "$1" | shasum | cut -d' ' -f1
  else printf '%s' "$1" | cksum | cut -d' ' -f1; fi
}

run_with_timeout() {
  local seconds="$1"; shift
  if [[ -n "$TIMEOUT_BIN" ]]; then
    "$TIMEOUT_BIN" "$seconds" "$@"
    return $?
  fi
  "$@" &
  local cmd_pid=$!
  ( sleep "$seconds"; kill -TERM "$cmd_pid" 2>/dev/null; sleep 2; kill -KILL "$cmd_pid" 2>/dev/null ) >/dev/null 2>&1 &
  local watch_pid=$!
  local exit_code=0
  wait "$cmd_pid" 2>/dev/null || exit_code=$?
  kill -TERM "$watch_pid" 2>/dev/null || true
  wait "$watch_pid" 2>/dev/null || true
  [[ "$exit_code" -eq 143 || "$exit_code" -eq 137 ]] && return 124
  return "$exit_code"
}

git_safe() { run_with_timeout "$GIT_TIMEOUT" git "$@"; }

ensure_state_dir() { mkdir -p "$STATE_HOME" 2>/dev/null || true; }

read_loop_count() {
  local count_value=0
  [[ -f "$LOOP_COUNT_FILE" ]] && count_value="$(cat "$LOOP_COUNT_FILE" 2>/dev/null)"
  [[ "$count_value" =~ ^[0-9]+$ ]] || count_value=0
  printf '%s' "$count_value"
}
increment_loop_count() { ensure_state_dir; printf '%s' "$(( $(read_loop_count) + 1 ))" > "$LOOP_COUNT_FILE" 2>/dev/null || true; }
clear_loop_count() { rm -f "$LOOP_COUNT_FILE" 2>/dev/null || true; }

can_manage_markers() {
  mkdir -p "$MARKER_DIR" 2>/dev/null || return 1
  local probe="$MARKER_DIR/.write_probe.$$"
  ( : > "$probe" ) 2>/dev/null || return 1
  rm -f "$probe" 2>/dev/null
  return 0
}

allow_stop() { clear_loop_count; exit 0; }

allow_with_system_message() {
  clear_loop_count
  if [[ -n "$JQ_BIN" ]]; then
    "$JQ_BIN" -n --arg message "$1" '{systemMessage: $message}'
  else
    printf '{"systemMessage":%s}\n' "$(json_escape "$1")"
  fi
  exit 0
}

# Canonical Stop blocking: exit 2, reason on stderr (fed back to Claude).
block_stop() {
  increment_loop_count
  printf '%s\n\n%s\n' "$1" "$(done_protocol_block)" >&2
  exit 2
}

done_protocol_block() {
  cat <<'PROTOCOL'
Definition of done (all four must hold before you stop):
  1. All tests are written and old + new tests pass.
  2. Lint and format are 100% clean and passing.
  3. Work is committed AND pushed (if remote exists).
  4. You have attested completion by creating .claude/.done at the repository root.

How to get there:
  - Write tests first.
  - Diagnose failures methodically.
  - Prove every claim with real output before saying it works.
  - Git flow is DIRECT MERGE, no pull requests: work on feature/<name> off dev, commit AND push each logical chunk, merge into dev, and promote dev -> main only when fully done. Do not commit to or branch from main/master unless specifically asked.
  - Run a thorough review before merging.
  - When every criterion is genuinely met, create .claude/.done at the repo root.
  - HONEST EXIT: if you genuinely cannot make further progress -- blocked on the user (credentials, a decision, or access) OR stuck on a technical dead end you cannot resolve (a check that will not pass, a hang, a missing tool, an environment you cannot fix) -- write .claude/.blocked at the repo root and stop. The file must NOT be empty: put 1-5 short lines in the user's language stating what you are blocked on and exactly what the USER must do next (the gate shows this text to the user). Repeat the same explanation at the END OF YOUR OUTPUT. Do not commit or push changes the user did not ask you to make.
  - ALWAYS end your final reply with a short section addressed to the user: what was done, and "What you need to do" -- the concrete next action required from them (or state explicitly that nothing is required).
PROTOCOL
}

worktree_signature() {
  local porcelain
  porcelain="$(git_safe status --porcelain -- ':(exclude).claude/' 2>/dev/null | LC_ALL=C sort)"
  hash_key "$porcelain"
}
worktree_is_dirty() { [[ -n "$(git_safe status --porcelain -- ':(exclude).claude/' 2>/dev/null)" ]]; }
current_branch() { git_safe rev-parse --abbrev-ref HEAD 2>/dev/null; }
branch_is_protected() { local b; b="$(current_branch)"; [[ "$b" == "main" || "$b" == "master" ]]; }
has_remote() { [[ -n "$(git_safe remote 2>/dev/null)" ]]; }
has_upstream() { git_safe rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; }
has_unpushed_commits() {
  has_upstream || return 1
  local ahead; ahead="$(git_safe rev-list --count '@{u}..HEAD' 2>/dev/null)"
  [[ "$ahead" =~ ^[0-9]+$ ]] && [[ "$ahead" -gt 0 ]]
}

# The gate only engages ("armed") when real work happened this session:
# HEAD moved or the worktree signature diverged from the SessionStart baseline.
session_is_armed() {
  [[ -f "$DONE_MARKER" ]] && return 0
  [[ "$GIT_REPO" -eq 1 ]] || return 1
  [[ -f "$BASELINE_FILE" ]] || return 1
  local base_head base_sig cur_head cur_sig
  base_head="$(sed -n '1p' "$BASELINE_FILE" 2>/dev/null)"
  base_sig="$(sed -n '2p' "$BASELINE_FILE" 2>/dev/null)"
  cur_head="$(git_safe rev-parse HEAD 2>/dev/null)"
  cur_sig="$(worktree_signature)"
  [[ "$cur_head" != "$base_head" ]] && return 0
  [[ "$cur_sig" != "$base_sig" ]] && return 0
  return 1
}

guarded_check() {
  local timeout_secs="$1" fail_detail="$2"; shift 2
  local exit_code=0
  run_with_timeout "$timeout_secs" "$@" || exit_code=$?
  if [[ "$exit_code" -eq 124 ]]; then
    VERIFY_FAIL_DETAIL="$fail_detail (timed out after ${timeout_secs}s; if it cannot be made to pass, write .claude/.blocked)"
    return 1
  fi
  if [[ "$exit_code" -ne 0 ]]; then VERIFY_FAIL_DETAIL="$fail_detail"; return 1; fi
  return 0
}

is_python_project() { [[ -f pyproject.toml || -f setup.cfg || -f setup.py || -f ruff.toml || -f .ruff.toml ]]; }

python_in_venv() {
  local python_path; python_path="$(command -v python || true)"
  [[ -n "$python_path" && "$python_path" == "$PWD"/* ]]
}
python_has_tests() {
  [[ -d tests || -f pytest.ini || -f tox.ini ]] && return 0
  [[ -f pyproject.toml ]] && grep -q '\[tool.pytest' pyproject.toml 2>/dev/null && return 0
  [[ -f setup.cfg ]] && grep -q '\[tool:pytest\]' setup.cfg 2>/dev/null && return 0
  return 1
}
run_python_checks() {
  # uv-managed projects: run tools through `uv run` -- no activated venv needed.
  local runner=()
  if [[ -f uv.lock ]] && command -v uv >/dev/null 2>&1; then
    runner=(uv run --no-sync)
  elif [[ -f .venv/bin/activate ]]; then set +u; source .venv/bin/activate 2>/dev/null || true; set -u
  elif [[ -f venv/bin/activate ]]; then set +u; source venv/bin/activate 2>/dev/null || true; set -u
  else
    VERIFY_FAIL_DETAIL="Python project has no local environment: no uv.lock (with uv installed) and no .venv/venv. Create a local venv or use uv (never the global interpreter), then re-verify."
    return 1
  fi
  if [[ ${#runner[@]} -eq 0 ]] && ! python_in_venv; then
    VERIFY_FAIL_DETAIL="active python is not inside the project virtualenv; activate the local venv before verifying."
    return 1
  fi
  if [[ ${#runner[@]} -gt 0 ]] || command -v ruff >/dev/null 2>&1; then
    guarded_check "$LINT_TIMEOUT" "ruff check . reported lint errors" "${runner[@]}" ruff check . || return 1
  fi
  if python_has_tests; then
    if [[ ${#runner[@]} -gt 0 ]] || command -v pytest >/dev/null 2>&1; then
      local exit_code=0
      run_with_timeout "$TEST_TIMEOUT" "${runner[@]}" pytest -q || exit_code=$?
      if [[ "$exit_code" -eq 124 ]]; then VERIFY_FAIL_DETAIL="pytest timed out after ${TEST_TIMEOUT}s (write .claude/.blocked if it cannot pass)"; return 1; fi
      if [[ "$exit_code" -ne 0 && "$exit_code" -ne 5 ]]; then VERIFY_FAIL_DETAIL="pytest reported failing tests"; return 1; fi
    fi
  fi
  return 0
}

node_script_defined() {
  local script_name="$1"
  if [[ -n "$JQ_BIN" ]]; then "$JQ_BIN" -e --arg name "$script_name" '.scripts[$name] // empty' package.json >/dev/null 2>&1; return $?; fi
  if [[ -n "$PY_BIN" ]]; then "$PY_BIN" -c 'import sys, json
try:
    manifest = json.load(open("package.json"))
except Exception:
    sys.exit(1)
sys.exit(0 if manifest.get("scripts", {}).get(sys.argv[1]) else 1)' "$script_name" 2>/dev/null; return $?; fi
  grep -q "\"$script_name\"[[:space:]]*:" package.json 2>/dev/null
}
node_test_is_stub() {
  local test_script=""
  if [[ -n "$JQ_BIN" ]]; then test_script="$("$JQ_BIN" -r '.scripts.test // ""' package.json 2>/dev/null)"
  elif [[ -n "$PY_BIN" ]]; then test_script="$("$PY_BIN" -c 'import json
try:
    print(json.load(open("package.json")).get("scripts", {}).get("test", ""))
except Exception:
    pass' 2>/dev/null)"; fi
  [[ "$test_script" == *"no test specified"* ]]
}
has_eslint_config() { compgen -G '.eslintrc*' >/dev/null 2>&1 || compgen -G 'eslint.config.*' >/dev/null 2>&1; }
run_node_checks() {
  command -v npm >/dev/null 2>&1 || return 0
  if node_script_defined lint; then guarded_check "$LINT_TIMEOUT" "npm run lint failed" npm run lint --silent || return 1
  elif has_eslint_config && command -v npx >/dev/null 2>&1; then guarded_check "$LINT_TIMEOUT" "eslint reported errors" npx --no-install eslint . || return 1; fi
  if node_script_defined test && ! node_test_is_stub; then guarded_check "$TEST_TIMEOUT" "npm test failed or did not exit (watch mode?); write .claude/.blocked if it cannot pass" npm test --silent || return 1; fi
  return 0
}

has_test_signals() {
  [[ -d tests ]] && return 0
  compgen -G '*.test.sh' >/dev/null 2>&1 && return 0
  compgen -G 'tests/*.test.sh' >/dev/null 2>&1 && return 0
  compgen -G '*_test.go' >/dev/null 2>&1 && return 0
  return 1
}

detect_and_run_checks() {
  if [[ -x "$MARKER_DIR/verify.sh" ]]; then guarded_check "$VERIFY_TIMEOUT" ".claude/verify.sh failed" "$MARKER_DIR/verify.sh"; return $?; fi
  if [[ -x scripts/verify.sh ]]; then guarded_check "$VERIFY_TIMEOUT" "scripts/verify.sh failed" ./scripts/verify.sh; return $?; fi
  if is_python_project; then run_python_checks; return $?; fi
  if [[ -f package.json ]]; then run_node_checks; return $?; fi
  if has_test_signals; then VERIFY_FAIL_DETAIL="this repo has a test suite but no recognized verifier; add scripts/verify.sh that runs it (and lint), then attest .done"; return 1; fi
  return 0
}

# ---------------------------------------------------------------------------

HOOK_CWD="$(read_hook_field cwd)"
STOP_HOOK_ACTIVE="$(read_hook_field stop_hook_active)"
SESSION_ID="$(read_hook_field session_id)"

TARGET_DIR="${HOOK_CWD:-${CLAUDE_PROJECT_DIR:-$PWD}}"
[[ -d "$TARGET_DIR" ]] && cd "$TARGET_DIR" 2>/dev/null || exit 0

REPO_ROOT="$(git_safe rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$REPO_ROOT" ]]; then GIT_REPO=1; cd "$REPO_ROOT" 2>/dev/null || exit 0; fi
ANCHOR_DIR="$PWD"

SAFE_SESSION="${SESSION_ID//[^A-Za-z0-9_-]/_}"
[[ -z "$SAFE_SESSION" ]] && SAFE_SESSION="default"

STATE_HOME="$HOME/.claude/loop-state/$(hash_key "$ANCHOR_DIR")"
ensure_state_dir
LOOP_COUNT_FILE="$STATE_HOME/loop_count.$SAFE_SESSION"
VERIFIED_SHA_FILE="$STATE_HOME/verified_sha.$SAFE_SESSION"
BASELINE_FILE="$STATE_HOME/baseline.$SAFE_SESSION"

MARKER_DIR="$ANCHOR_DIR/.claude"
DONE_MARKER="$MARKER_DIR/.done"
BLOCKED_MARKER="$MARKER_DIR/.blocked"

can_manage_markers || allow_with_system_message "loop-until-done is inert: cannot write ${MARKER_DIR}. The gate cannot verify or be escaped here; allowing the stop."

# Runaway-loop backstop: after MAX_ITERS consecutive blocks, let the turn end.
LOOP_COUNT="$(read_loop_count)"
if [[ "$LOOP_COUNT" -ge "$MAX_ITERS" ]]; then
  rm -f "$DONE_MARKER" "$VERIFIED_SHA_FILE" 2>/dev/null || true
  allow_with_system_message "loop-until-done backstop reached after ${LOOP_COUNT} consecutive blocks (CLAUDE_LOOP_MAX_ITERS=${MAX_ITERS}; stop_hook_active=${STOP_HOOK_ACTIVE:-false}). Allowing the turn to end and clearing the .done attestation. Review the working tree and re-engage manually if work remains."
fi

# Honest exit: .blocked lets the turn end so the user can act. Consumed on use.
# The file must CONTAIN a note for the user (what is blocked + what they must do);
# an empty marker is bounced back once so the user is never left guessing.
if [[ -f "$BLOCKED_MARKER" ]]; then
  BLOCKED_NOTE="$(tr -d '\r\000' < "$BLOCKED_MARKER" 2>/dev/null | head -c 1500)"
  if [[ -z "${BLOCKED_NOTE//[[:space:]]/}" ]]; then
    block_stop ".claude/.blocked is empty. Before stopping, write INTO .claude/.blocked 1-5 short lines in the user's language: (1) what you are blocked on, (2) exactly what the USER must do next. Repeat the same explanation at the end of your reply. Then stop again."
  fi
  rm -f "$BLOCKED_MARKER" "$DONE_MARKER" 2>/dev/null || true
  allow_with_system_message "⏸ Claude остановился, требуется ваше действие:
${BLOCKED_NOTE}
(Маркер .claude/.blocked поглощён; гейт снова включится на следующем ходе.)"
fi

DONE_PRESENT=0
[[ -f "$DONE_MARKER" ]] && DONE_PRESENT=1

# Outside a git repo the gate only acts on an explicit .done attestation.
if [[ "$GIT_REPO" -eq 0 ]]; then
  if [[ "$DONE_PRESENT" -eq 1 ]]; then
    VERIFY_FAIL_DETAIL=""
    if ! detect_and_run_checks; then
      rm -f "$DONE_MARKER" 2>/dev/null || true
      block_stop "Verification failed: ${VERIFY_FAIL_DETAIL}. I removed the premature .claude/.done."
    fi
    rm -f "$DONE_MARKER" 2>/dev/null || true
    allow_with_system_message "✅ Done-gate пройден: проверки чисты. От вас ничего не требуется."
  fi
  allow_stop
fi

# No attestation yet: block only if real work happened this session.
if [[ "$DONE_PRESENT" -eq 0 ]]; then
  session_is_armed || allow_stop
  if worktree_is_dirty && branch_is_protected; then
    block_stop "You are on $(current_branch) with uncommitted changes. Do not commit to main/master unless the user specifically asked for that; otherwise move your work onto feature/<name> created off dev. If the user did ask, or there is no work to finish, write .claude/.blocked (with a note for the user) and stop."
  fi
  if worktree_is_dirty; then
    block_stop "You still have uncommitted changes, so the work is not finished. Commit (and later push) the work you did. Do NOT commit changes the user did not ask for. If the user only asked a question, write .claude/.blocked (with a note for the user) and stop."
  fi
  block_stop "You committed work this session but have not attested completion. Verify tests and lint pass, push your commits, then create .claude/.done -- or write .claude/.blocked if you cannot proceed."
fi

# .done is present: cheap structural checks first, expensive verification after.
if worktree_is_dirty; then
  block_stop ".claude/.done is present but the tree still has uncommitted changes. Commit every change before attesting completion."
fi
if branch_is_protected; then
  block_stop ".claude/.done is present but you are on $(current_branch). Unless the user specifically asked for work on main/master, move the commits onto feature/<name> off dev. If the user did ask (e.g. a dev -> main promotion), write .claude/.blocked explaining that and hand it to the user."
fi

HEAD_SHA="$(git_safe rev-parse HEAD 2>/dev/null || true)"
VERIFIED_SHA=""
[[ -f "$VERIFIED_SHA_FILE" ]] && VERIFIED_SHA="$(cat "$VERIFIED_SHA_FILE" 2>/dev/null)"

if [[ -z "$HEAD_SHA" || "$HEAD_SHA" != "$VERIFIED_SHA" ]]; then
  VERIFY_FAIL_DETAIL=""
  if ! detect_and_run_checks; then
    rm -f "$DONE_MARKER" 2>/dev/null || true
    block_stop "Verification failed: ${VERIFY_FAIL_DETAIL}. I removed the premature .claude/.done."
  fi
  [[ -n "$HEAD_SHA" ]] && { ensure_state_dir; printf '%s' "$HEAD_SHA" > "$VERIFIED_SHA_FILE" 2>/dev/null || true; }
fi

if has_remote; then
  if ! has_upstream; then
    block_stop ".claude/.done is present and verification passed, but this branch has no upstream. Push it: git push -u origin $(current_branch)."
  fi
  if has_unpushed_commits; then
    block_stop ".claude/.done is present and the tree is clean, but local commits are not pushed. Push them."
  fi
fi

rm -f "$DONE_MARKER" 2>/dev/null || true
allow_with_system_message "✅ Done-gate пройден: проверки чисты, всё закоммичено$(has_remote && printf ' и запушено'). От вас ничего не требуется."
~Z