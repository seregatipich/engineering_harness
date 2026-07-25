#!/usr/bin/env bash
# Find every place a new symbol must be registered, by sweeping an existing sibling.
#
# Central registries and allowlists are invisible from both visible ends of a
# feature: nothing in the caller and nothing in the implementation points at the
# table that must also list it. They are usually guarded by an exact-match test,
# which fails closed — and the cheap way out of a failing guard is to weaken its
# assertion. So this script names the guards as well as the sites.
#
# The insight it encodes: the commit that first introduced an existing sibling
# symbol is the exhaustive registration checklist for adding a new one. Whatever
# that commit had to touch, the new symbol has to touch too — including the files
# that never mention the sibling by name.
#
# Usage: bash sibling_sweep.sh <sibling-literal> [<repo-root>]
#   <sibling-literal>  an existing symbol to imitate, matched as a fixed string
#                      (an enum member, handler name, action string, route id)
#   <repo-root>        defaults to the current directory. Both the grep and the
#                      history search are scoped to this directory's subtree, so
#                      pass the repo root for a whole-repo sweep and a package
#                      directory to scope one package of a monorepo.
#
# Output: the two classified lists, each entry as `path:line` plus the enclosing
# array/list literal quoted with line numbers, so the caller can copy the exact
# line to imitate. Then a machine block:
#
#   --- SWEEP JSON ---
#   { "sibling": "...", "introducing_commit": "<sha>"|null,
#     "registration_sites": [ {path,line,source,context} ],
#     "guard_tests":        [ {path,line,source,context} ],
#     "truncated": false }
#
# `source` is "grep" for a literal hit, "introducing-commit" for a file that
# commit touched without ever naming the sibling — the sites a grep cannot see.
#
# Exit: 2 misuse or not a git repo, 3 the literal has no hits anywhere (the
# caller picked a bad sibling; returning an empty sweep would read as "no
# registration needed"), 127 a required CLI is missing.
set -euo pipefail

for c in git jq awk; do
  command -v "$c" >/dev/null 2>&1 || { echo "sibling_sweep.sh: required CLI '$c' not found on PATH" >&2; exit 127; }
done

SIBLING="${1-}"
ROOT="${2:-.}"
if [[ -z "$SIBLING" ]]; then
  echo "usage: sibling_sweep.sh <sibling-literal> [<repo-root>]" >&2
  exit 2
fi

cd "$ROOT" 2>/dev/null || { echo "sibling_sweep.sh: repo root '$ROOT' is not a directory" >&2; exit 2; }
git rev-parse --show-toplevel >/dev/null 2>&1 || {
  echo "sibling_sweep.sh: '$ROOT' is not inside a git repository (this sweep reads history, not just files)" >&2
  exit 2
}

# A commit this wide is a bulk import or a vendored drop, not a registration
# checklist; its file list would bury the real sites instead of naming them.
BULK_IMPORT_FILES=40

# Path shapes that mean "this hit is a guard, not a site". Kept deliberately
# broad: a guard misfiled as a site costs a wrong edit, the reverse costs a note.
TEST_PATH_RE='(^|/)(__tests__|tests?|specs?)(/|$)|(^|/)test_|[._-](test|spec)\.|(Test|Spec)s?\.[A-Za-z0-9]+$'

# The enclosing literal, found by bracket balance rather than by language: scan
# up for the nearest unmatched opener and down for its close. Works on arrays,
# maps and call lists in every brace language; falls back to a small window when
# the registration is line-oriented (YAML, TOML, a plain table).
quote_literal() { # <path> <line>
  awk -v hit="$2" -v span=40 -v maxout=20 '
    function opens(s,   n, i, c) {
      n = 0
      for (i = 1; i <= length(s); i++) { c = substr(s, i, 1); if (c == "[" || c == "(" || c == "{") n++ }
      return n
    }
    function closes(s,   n, i, c) {
      n = 0
      for (i = 1; i <= length(s); i++) { c = substr(s, i, 1); if (c == "]" || c == ")" || c == "}") n++ }
      return n
    }
    function emit(i) { printf "      %6d: %s\n", i, line[i] }
    { line[NR] = $0 }
    END {
      if (hit < 1 || hit > NR) exit 0
      start = hit; depth = 0
      for (i = hit - 1; i >= 1 && i >= hit - span; i--) {
        depth += closes(line[i]) - opens(line[i])
        if (depth < 0) { start = i; break }
      }
      end = hit; depth = 0
      for (i = hit + 1; i <= NR && i <= hit + span; i++) {
        depth += opens(line[i]) - closes(line[i])
        if (depth < 0) { end = i; break }
      }
      if (start == hit && end == hit) {
        start = (hit - 2 < 1) ? 1 : hit - 2
        end = (hit + 2 > NR) ? NR : hit + 2
      }
      if (end - start + 1 <= maxout) {
        for (i = start; i <= end; i++) emit(i)
      } else {
        emit(start)
        w0 = (hit - 2 < start + 1) ? start + 1 : hit - 2
        w1 = (hit + 2 > end - 1) ? end - 1 : hit + 2
        if (w0 > start + 1) print "           ..."
        for (i = w0; i <= w1; i++) emit(i)
        if (w1 < end - 1) print "           ..."
        emit(end)
      }
    }
  ' "$1"
}

# For a file the introducing commit touched but never names the sibling in, the
# commit's own hunk is the only usable template: it shows what adding the sibling
# had to add here. No line numbers — that commit's are stale by definition.
quote_commit_diff() { # <sha> <path>
  git show --format= --unified=2 "$1" -- "$2" 2>/dev/null |
    awk '/^(diff --git|index |--- |\+\+\+ |new file|deleted file|similarity|rename |old mode|new mode)/ { next }
         { printf "      %s\n", $0 }' |
    head -n 20
}

is_test_path() { [[ "$1" =~ $TEST_PATH_RE ]]; }

REG_HUMAN=()
GUARD_HUMAN=()
REG_JSON=()
GUARD_JSON=()
declare -A hit_files=()

add_entry() { # <path> <line|""> <source> <context>
  local path="$1" line="$2" src="$3" ctx="$4" obj human
  obj="$(jq -nc --arg p "$path" --arg l "$line" --arg s "$src" --arg c "$ctx" \
    '{path:$p, line:(if $l == "" then null else ($l | tonumber) end), source:$s, context:$c}')"
  if [[ -n "$line" ]]; then human="  $path:$line"; else human="  $path"; fi
  if [[ -n "$ctx" ]]; then human="$human"$'\n'"$ctx"; fi
  if is_test_path "$path"; then
    GUARD_JSON+=("$obj"); GUARD_HUMAN+=("$human")
  else
    REG_JSON+=("$obj"); REG_HUMAN+=("$human")
  fi
}

# git grep, so vendored trees, build output and anything else untracked drop out
# with no hand-maintained exclude list. -I keeps binaries from producing hits
# with no quotable line, and -z keeps a path containing a colon parseable.
# Piped rather than captured: command substitution strips the NUL separators.
hit_count=0
while IFS= read -r -d '' path; do
  # Only the path read gates the loop: the final record has no trailing newline
  # after its content, and gating on that read would silently drop the last hit.
  IFS= read -r -d '' lineno || true
  IFS= read -r content || true
  [[ -z "$path" || -z "$lineno" ]] && continue
  hit_files["$path"]=1
  hit_count=$(( hit_count + 1 ))
  ctx=""
  [[ -f "$path" ]] && ctx="$(quote_literal "$path" "$lineno")"
  [[ -z "$ctx" ]] && ctx="$(printf '      %6d: %s' "$lineno" "$content")"
  add_entry "$path" "$lineno" "grep" "$ctx"
done < <(git grep -n -I -z -F -e "$SIBLING" -- 2>/dev/null || true)

if (( hit_count == 0 )); then
  echo "sibling_sweep.sh: no tracked file contains '$SIBLING' — that sibling does not exist in this repo." >&2
  echo "Pick a literal that is really registered somewhere (an existing enum member, handler name or route id) and sweep again." >&2
  exit 3
fi

# --reverse plus head -1 is the first commit whose diff changed the number of
# occurrences of the literal: the one that introduced it.
INTRODUCING_COMMIT="$(git log --format=%H -S"$SIBLING" --reverse -- . 2>/dev/null | head -n 1 || true)"

TRUNCATED=false
commit_files=""
commit_file_count=0
if [[ -n "$INTRODUCING_COMMIT" ]]; then
  commit_files="$(git show --pretty=format: --name-only "$INTRODUCING_COMMIT" 2>/dev/null | awk 'NF' | sort -u || true)"
  [[ -n "$commit_files" ]] && commit_file_count="$(printf '%s\n' "$commit_files" | wc -l | tr -d ' ')"
  if (( commit_file_count > BULK_IMPORT_FILES )); then
    TRUNCATED=true
    commit_files=""
  fi
fi

# Files the introducing commit touched without ever naming the sibling. These are
# the registration sites no grep can reach — a generated table, a docs row, a
# migration, an allowlist keyed by something else.
if [[ -n "$commit_files" ]]; then
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    [[ -n "${hit_files[$f]:-}" ]] && continue
    [[ -f "$f" ]] || continue
    add_entry "$f" "" "introducing-commit" "$(quote_commit_diff "$INTRODUCING_COMMIT" "$f")"
  done <<<"$commit_files"
fi

printf "SIBLING SWEEP: '%s' — %d literal hit(s) in %d file(s)\nswept: %s\n\n" \
  "$SIBLING" "$hit_count" "${#hit_files[@]}" "$PWD"

echo "INTRODUCING COMMIT"
if [[ -z "$INTRODUCING_COMMIT" ]]; then
  echo "  none in this history (shallow clone, or the literal only ever existed uncommitted)."
  echo "  Working from the grep hits alone — treat the site list as a floor, not a checklist."
elif [[ "$TRUNCATED" == true ]]; then
  msg="$INTRODUCING_COMMIT touches $commit_file_count files (over the $BULK_IMPORT_FILES-file threshold) — a bulk import, not a registration checklist."
  echo "  $msg"
  echo "  Falling back to the grep hits alone; the site list is a floor, not a checklist."
  echo "sibling_sweep.sh: WARNING — $msg" >&2
else
  git show --stat --format='  %H%n  %s (%an, %ad)' --date=short "$INTRODUCING_COMMIT" | head -n 60
  echo
  echo "  Every file above had to change for '$SIBLING' to exist. A new sibling needs the same set."
fi
echo

printf 'REGISTRATION SITES (%d) — non-test paths; add the new symbol at each\n' "${#REG_JSON[@]}"
if (( ${#REG_JSON[@]} == 0 )); then
  echo "  none"
else
  printf '%s\n' "${REG_HUMAN[@]}"
fi
echo

printf 'GUARD TESTS (%d) — MUST-PASS-UNMODIFIED; extend the expected set, never weaken the assertion\n' "${#GUARD_JSON[@]}"
if (( ${#GUARD_JSON[@]} == 0 )); then
  echo "  none — no exact-match guard covers this sibling, so nothing will fail closed if a site is missed"
else
  printf '%s\n' "${GUARD_HUMAN[@]}"
fi
echo

reg_json="$(printf '%s\n' ${REG_JSON[@]+"${REG_JSON[@]}"} | jq -s 'map(select(. != null))')"
guard_json="$(printf '%s\n' ${GUARD_JSON[@]+"${GUARD_JSON[@]}"} | jq -s 'map(select(. != null))')"

echo "--- SWEEP JSON ---"
jq -n --arg sib "$SIBLING" --arg sha "$INTRODUCING_COMMIT" \
      --argjson reg "$reg_json" --argjson guards "$guard_json" --argjson truncated "$TRUNCATED" \
  '{sibling:$sib,
    introducing_commit:(if $sha == "" then null else $sha end),
    registration_sites:$reg,
    guard_tests:$guards,
    truncated:$truncated}'
