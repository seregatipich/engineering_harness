#!/usr/bin/env bash
# The machine-local half of one implementation dispatch, generated per issue.
#
# Every Bash call starts a fresh shell, so a subagent has to re-establish its
# environment on every single command. Left to invent that themselves, agents
# reach for a shared scratchpad — and a sibling's stale env file, with its `cd`
# pointing at another issue's worktree, is then one `source` away. This script
# ends that: the env file is written inside the worktree's own git directory
# (per-worktree, never committed, invisible to `git status`), and the block it
# prints is the whole of what the dispatch prompt needs to say about the host.
#
# The block is host-local by construction — paths, dev credentials, per-issue
# resource slots — so it is appended to the prompt and never posted to an issue.
# It is regenerated per dispatch rather than remembered, so nothing about it
# needs storing (see references/handoff.md, "The machine block").
#
# Usage: bash agent_env.sh <issue-number> <worktree-abs-path> [KEY=VALUE ...]
#
#   <issue-number>        the GitHub issue this dispatch implements
#   <worktree-abs-path>   the root of the subagent's worktree; must already exist
#   KEY=VALUE             extra variables to export into the subagent's shell.
#                         This is the only way service settings get in: the
#                         script never guesses a stack, because it has no idea
#                         whether this repo wants a Postgres URL, a Redis index,
#                         a devcontainer or nothing at all. Step 2 discovered
#                         those values; pass them here. Injected keys are
#                         written last, so they also override any derived value.
#
#   Two injected keys are read as well as written:
#     WNI_BRANCH=feature/issue-<n>-<slug>
#         the branch the first command pins. Pass the Brief's branch; without
#         it the block falls back to `feature/issue-<n>`.
#     WNI_BASE=origin/<integration>
#         the ref the first command pins onto. Defaults to `origin/dev`: a
#         remote-tracking ref, because no worktree can hold one, so the pin
#         works even when another worktree has local `dev` checked out.
#     WNI_BOOTSTRAP='<cmd>'   (newline-separated for several)
#         the repo's worktree bootstrap from Step 2 — a fresh worktree shares
#         the repo's refs but not its installed dependencies. Omitted when not
#         passed; a bootstrap this script cannot know is absence, not error.
#
# Derived per issue, so two concurrent issues get different resources:
#   slot k          <issue> % 1024. The modulus is what keeps ports in range,
#                   and 1024 is the largest that keeps them there: two issues
#                   share a slot only if their numbers are 1024 apart, which no
#                   single batch does.
#   WNI_LABEL       wni_<issue> — a name for created resources (databases,
#                   containers, volumes, schemas). Unique per issue, always;
#                   prefer it wherever a resource can be named rather than
#                   numbered.
#   WNI_PORT_BASE   20000 + 10*k, reserving ten consecutive ports through
#                   WNI_PORT_LAST. Above the usual dev ports, below the 32768
#                   floor of Linux's ephemeral range, so nothing else claims it.
#   WNI_INDEX       k % 16, for a service indexed rather than named — 16 because
#                   that is how many databases an out-of-the-box Redis has, and
#                   an index has to fit whatever ceiling its service imposes.
#                   This is the one derived value that can repeat across a
#                   batch; where it matters, inject an explicit override.
#   WNI_SCRATCH     a per-issue scratch directory, created here.
#
# Output: the machine block on stdout; the env file at
#   <worktree>/.git/wni-issue-<n>.env
# In a linked worktree `<worktree>/.git` is a file pointing at that worktree's
# private admin directory, so the file lands there instead — same guarantee,
# and the same literal path in a main worktree.
#
# Exit: 2 usage error, 3 not a git worktree, 4 env file would land outside the
# repository's `.git/` tree, 127 missing CLI.
set -euo pipefail

# GIT_DIR/GIT_WORK_TREE inherited from the orchestrator's shell would silently
# retarget every git call below at a different worktree — the exact cross-talk
# this script exists to prevent.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE

USAGE='usage: agent_env.sh <issue-number> <worktree-abs-path> [KEY=VALUE ...]'

die() { printf 'agent_env.sh: %s\n' "$1" >&2; exit "$2"; }

command -v git >/dev/null 2>&1 || die "required CLI 'git' not found on PATH" 127

[[ $# -ge 2 ]] || die "$USAGE" 2

ISSUE="$1"
WORKTREE_ARG="$2"
shift 2

[[ "$ISSUE" =~ ^[1-9][0-9]*$ ]] || die "issue number must be a positive integer, got '$ISSUE'. $USAGE" 2

# Resolve the worktree before anything else: every path this script emits hangs
# off it, and a subagent starts in a different directory than the orchestrator,
# so a relative path here becomes a wrong directory there.
[[ -d "$WORKTREE_ARG" ]] || die "worktree path is not an existing directory: $WORKTREE_ARG" 3
WORKTREE="$(cd "$WORKTREE_ARG" && pwd -P)"

TOPLEVEL="$(git -C "$WORKTREE" rev-parse --show-toplevel 2>/dev/null)" \
  || die "not a git worktree: $WORKTREE" 3
TOPLEVEL="$(cd "$TOPLEVEL" && pwd -P)"
[[ "$TOPLEVEL" == "$WORKTREE" ]] \
  || die "$WORKTREE is inside the worktree $TOPLEVEL, not its root; pass the root" 3

resolve_git_path() { # $1 = a rev-parse path flag; prints the canonical directory
  local raw
  raw="$(git -C "$WORKTREE" rev-parse "$1")"
  [[ "$raw" == /* ]] || raw="$WORKTREE/$raw"
  (cd "$raw" && pwd -P)
}
GIT_PRIVATE_DIR="$(resolve_git_path --git-dir)"
GIT_COMMON_DIR="$(resolve_git_path --git-common-dir)"

# The whole safety story: the env file may carry dev credentials and it must be
# reachable by exactly one subagent, so it is only ever written into this
# worktree's private git directory — the repository's `.git/` itself, or the
# `.git/worktrees/<name>/` that belongs to this worktree alone. Anywhere else
# (a shared scratchpad, a separate-git-dir or bare layout, a redirected GIT_DIR)
# is refused rather than written.
[[ "$GIT_COMMON_DIR" == */.git ]] \
  || die "refusing to write outside a '.git' directory: resolved $GIT_COMMON_DIR" 4
if [[ "$GIT_PRIVATE_DIR" != "$GIT_COMMON_DIR" ]]; then
  [[ "$GIT_PRIVATE_DIR" == "$GIT_COMMON_DIR"/worktrees/* ]] \
    || die "refusing to write outside $GIT_COMMON_DIR: resolved $GIT_PRIVATE_DIR" 4
fi
[[ -w "$GIT_PRIVATE_DIR" ]] || die "git directory is not writable: $GIT_PRIVATE_DIR" 4

ENV_FILE="$GIT_PRIVATE_DIR/wni-issue-$ISSUE.env"
SCRATCH_DIR="$GIT_PRIVATE_DIR/wni-issue-$ISSUE-scratch"

SLOT=$(( ISSUE % 1024 ))
PORT_BASE=$(( 20000 + 10 * SLOT ))
INDEX=$(( SLOT % 16 ))
LABEL="wni_$ISSUE"

BRANCH="feature/issue-$ISSUE"
# A remote-tracking ref, deliberately: no worktree can hold one, so the pin works
# even when another worktree has the local integration branch checked out — and
# it is the same object integration later pushes to.
BASE="origin/dev"
BOOTSTRAP=""
INJECTED_KEYS=()
INJECTED_LINES=()

sq() { # single-quote a value for the env file, escaping embedded quotes
  local v=${1//\'/\'\\\'\'}
  printf "'%s'" "$v"
}

for pair in "$@"; do
  [[ "$pair" == *=* ]] || die "extra arguments must be KEY=VALUE, got '$pair'. $USAGE" 2
  key="${pair%%=*}"
  value="${pair#*=}"
  [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "invalid variable name '$key'. $USAGE" 2
  case "$key" in
    WNI_BRANCH)
      # Absorbed into the derived branch, which is written and reported already.
      BRANCH="$value"
      continue ;;
    WNI_BASE)
      BASE="$value"
      continue ;;
    WNI_BOOTSTRAP)
      # Kept in the env file so the bootstrap can be re-run, but reported as the
      # ordered commands below rather than as an opaque variable name.
      BOOTSTRAP="$value"
      INJECTED_LINES+=("$key=$(sq "$value")")
      continue ;;
  esac
  INJECTED_KEYS+=("$key")
  INJECTED_LINES+=("$key=$(sq "$value")")
done

[[ -n "$BRANCH" ]] || die "WNI_BRANCH was passed empty; omit it or give a branch name" 2

mkdir -p "$SCRATCH_DIR"

# The file is sourced with `set -a`, so it holds assignments only: a `cd` in
# here would run on every command of every later call, which is how an agent
# ends up in the wrong worktree without noticing. Directory changes stay in the
# block below, where they are visible.
(
  umask 077   # dev credentials arrive through KEY=VALUE; keep them off the mode bits
  {
    printf '# Generated by agent_env.sh for issue #%s. Machine-local; never committed.\n' "$ISSUE"
    printf 'WNI_ISSUE=%s\n' "$(sq "$ISSUE")"
    printf 'WNI_LABEL=%s\n' "$(sq "$LABEL")"
    printf 'WNI_SLOT=%s\n' "$(sq "$SLOT")"
    printf 'WNI_INDEX=%s\n' "$(sq "$INDEX")"
    printf 'WNI_PORT_BASE=%s\n' "$(sq "$PORT_BASE")"
    printf 'WNI_PORT_LAST=%s\n' "$(sq "$(( PORT_BASE + 9 ))")"
    printf 'WNI_WORKTREE=%s\n' "$(sq "$WORKTREE")"
    printf 'WNI_SCRATCH=%s\n' "$(sq "$SCRATCH_DIR")"
    printf 'WNI_ENV_FILE=%s\n' "$(sq "$ENV_FILE")"
    printf 'WNI_BRANCH=%s\n' "$(sq "$BRANCH")"
    # Injected last so the caller's discovered values win over the derived ones.
    if (( ${#INJECTED_LINES[@]} > 0 )); then printf '%s\n' "${INJECTED_LINES[@]}"; fi
  } >"$ENV_FILE"
)

PREAMBLE="cd '$WORKTREE' && set -a; . '$ENV_FILE'; set +a"

cat <<BLOCK
## Machine block — host-local, generated for this dispatch. Never post it anywhere.

Worktree: $WORKTREE
Env file: $ENV_FILE

Your first command, before anything else — it pins your base onto \`$BASE\` as it
stands right now:

    cd '$WORKTREE' && git fetch origin && git checkout -B '$BRANCH' '$BASE'

Then bootstrap the worktree, in this order:
BLOCK

step=1
printf '\n    %d. %s\n' "$step" "$PREAMBLE"
if [[ -n "$BOOTSTRAP" ]]; then
  while IFS= read -r cmd; do
    [[ -z "$cmd" ]] && continue
    step=$(( step + 1 ))
    printf '    %d. %s\n' "$step" "$cmd"
  done <<<"$BOOTSTRAP"
fi

cat <<BLOCK

Every Bash call starts a fresh shell. Nothing above survives it — not the
directory, not the variables. Prefix every later command with the preamble:

    $PREAMBLE

Then run your command in the same call.

These resources are yours alone; a sibling subagent working another issue in
parallel has a different slot. Use them instead of a default name, index, port
or temp directory, and write scratch files only under WNI_SCRATCH.
BLOCK

resource() {
  if [[ -n "${2-}" ]]; then printf '    %-24s %s\n' "$1" "$2"; else printf '    %s\n' "$1"; fi
}
printf '\n'
resource "WNI_ISSUE=$ISSUE"
resource "WNI_LABEL=$LABEL" "name anything you create with it: database, container, schema"
resource "WNI_INDEX=$INDEX" "index for a service numbered rather than named"
resource "WNI_PORT_BASE=$PORT_BASE" "yours through $(( PORT_BASE + 9 )), as WNI_PORT_LAST"
resource "WNI_SCRATCH=$SCRATCH_DIR"
resource "WNI_WORKTREE=$WORKTREE"
resource "WNI_BRANCH=$BRANCH"

if (( ${#INJECTED_KEYS[@]} )); then
  # Names only: the values are in the env file already, and some are credentials
  # that have no reason to sit in a prompt.
  printf '\nAlso exported by the preamble, values in the env file: %s\n' \
    "$(printf '%s, ' "${INJECTED_KEYS[@]}" | sed 's/, $//')"
fi
