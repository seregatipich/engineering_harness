#!/usr/bin/env bash
# Tests for hooks/loop-until-done.sh (the done-loop Stop gate), exercised
# together with hooks/loop-protocol-context.sh (the SessionStart baseline
# arming). Each case builds an isolated temp HOME + git repo, arms the
# baseline, mutates git state, then runs the Stop hook and asserts on its exit
# code and stderr. exit 2 == the gate blocked the stop; exit 0 == it allowed.
#
# Kept portable to bash 3.2 (macOS system bash): no associative arrays, no
# mapfile. Run: bash hooks/tests/loop-until-done_test.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STOP_HOOK="$HERE/../loop-until-done.sh"
START_HOOK="$HERE/../loop-protocol-context.sh"
SESSION="test-session"

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT
MKN=0

FAILED=0
assert_eq() { # desc expected actual
  if [[ "$2" == "$3" ]]; then printf '  PASS  %s\n' "$1"
  else printf '  FAIL  %s\n    expected: %s\n    actual:   %s\n' "$1" "$2" "$3"; FAILED=1; fi
}
assert_contains() { # desc needle haystack
  case "$3" in
    *"$2"*) printf '  PASS  %s\n' "$1" ;;
    *) printf '  FAIL  %s\n    expected substring: %s\n    in: %s\n' "$1" "$2" "$3"; FAILED=1 ;;
  esac
}

# Fresh isolated HOME + git repo with one seed commit on `main`.
new_repo() {
  MKN=$((MKN + 1))
  THOME="$TMPROOT/home$MKN"; REPO="$TMPROOT/repo$MKN"
  mkdir -p "$THOME" "$REPO"
  git -C "$REPO" init -q
  git -C "$REPO" symbolic-ref HEAD refs/heads/main
  git -C "$REPO" config core.hooksPath /dev/null
  git -C "$REPO" config user.email t@t
  git -C "$REPO" config user.name t
  printf 'seed\n' > "$REPO/seed.txt"
  git -C "$REPO" add -A
  git -C "$REPO" commit -qm seed
}

arm()      { printf '{"cwd":"%s","session_id":"%s"}' "$REPO" "$SESSION" | HOME="$THOME" bash "$START_HOOK" >/dev/null 2>&1; }
commit()   { printf '%s\n' "$1" >> "$REPO/seed.txt"; git -C "$REPO" add -A; git -C "$REPO" commit -qm "$1"; }
dirty()    { printf 'x\n' >> "$REPO/seed.txt"; }
mark_done(){ mkdir -p "$REPO/.claude"; printf 'done\n' > "$REPO/.claude/.done"; }
feature()  { git -C "$REPO" checkout -q -b "feature/$1"; }
done_state(){ [[ -f "$REPO/.claude/.done" ]] && echo present || echo absent; }

# Runs the Stop hook; sets EXIT_CODE and STDERR.
run_stop() {
  local err; err="$(mktemp)"
  printf '{"cwd":"%s","session_id":"%s","stop_hook_active":false}' "$REPO" "$SESSION" \
    | HOME="$THOME" bash "$STOP_HOOK" 2>"$err" >/dev/null
  EXIT_CODE=$?
  STDERR="$(cat "$err")"; rm -f "$err"
}

echo "loop-until-done.sh"

# 1. The session's own scenario: housekeeping on main leaves HEAD unchanged and
#    a clean tree. .done must be accepted (exit 0), NOT bounced for being on main.
new_repo; arm; mark_done; run_stop
assert_eq "no-op on main (HEAD unchanged, clean) is allowed" 0 "$EXIT_CODE"

# 2. Real commits on main are still blocked -- the short-circuit is scoped to
#    no-op turns only, so a moved HEAD falls through to the protected-branch guard.
new_repo; arm; commit c1; mark_done; run_stop
assert_eq "committed work on main is blocked" 2 "$EXIT_CODE"
assert_contains "block names the protected branch" "main" "$STDERR"

# 3. A dirty tree with .done is blocked before the short-circuit is ever reached.
new_repo; arm; dirty; mark_done; run_stop
assert_eq "dirty tree with .done is blocked" 2 "$EXIT_CODE"
assert_contains "block cites uncommitted changes" "uncommitted changes" "$STDERR"

# 4. Without a baseline the state is unknown, so .done on main is NOT
#    short-circuited -- the strict protected-branch guard still fires.
new_repo; mark_done; run_stop
assert_eq "missing baseline: .done on main is not short-circuited" 2 "$EXIT_CODE"

# 5. A no-op turn on a feature branch is allowed too (branch-agnostic).
new_repo; feature x; arm; mark_done; run_stop
assert_eq "no-op on a feature branch is allowed" 0 "$EXIT_CODE"

# 6. The gate still does its job: committed-but-unattested work blocks with a
#    prompt to attest (proves the short-circuit did not loosen the real path).
new_repo; feature y; arm; commit c2; run_stop
assert_eq "committed, unattested work on a feature branch is blocked" 2 "$EXIT_CODE"
assert_contains "block asks to attest completion" "attest" "$STDERR"

# 7. Runaway backstop: after MAX_ITERS consecutive blocks the gate gives up,
#    allows the stop, and clears the stale .done. Forced via the env override.
export CLAUDE_LOOP_MAX_ITERS=1
new_repo; arm; commit c3; mark_done
run_stop
assert_eq "backstop: first block (loop count -> 1)" 2 "$EXIT_CODE"
run_stop
assert_eq "backstop: allows once the threshold is reached" 0 "$EXIT_CODE"
assert_eq "backstop: stale .done is cleared" "absent" "$(done_state)"
unset CLAUDE_LOOP_MAX_ITERS

if (( FAILED )); then
  echo "FAILED"
  exit 1
fi
echo "All tests passed."
