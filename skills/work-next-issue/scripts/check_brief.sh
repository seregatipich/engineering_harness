#!/usr/bin/env bash
# Conformance gate for a Brief before it is posted or dispatched.
#
# The Brief contract lives in references/handoff.md: required headings, a *Where
# things are* table whose paths and anchors are real, a test plan that names
# tests, steps that account for every path, and no delegated decisions. Nothing
# checked that contract, so Briefs shipped with "Optionally add X", with
# "backup.ts (or host-backup.ts)", and with test paths naming zero tests — each
# one a decision handed to an executor that has no licence to make it. A
# contract nothing checks is a suggestion.
#
# Usage: bash check_brief.sh <repo-root> <brief.md>
#   <repo-root>  the git work tree the Brief's paths are relative to (the
#                worktree the executor will run in, not necessarily this repo)
#   <brief.md>   the Brief as it will be posted, in Markdown
#
# Exit 0  -> dispatchable, no output.
# Exit 1  -> one line per problem on stdout: `LINE <n>: <CODE> <detail>`
#            (LINE 0 = a whole-document problem, e.g. a missing heading).
# Exit 2  -> misuse: bad arguments, unreadable Brief, repo root is not a git
#            work tree. A malformed invocation is never a passing Brief.
#
# Codes:
#   SECTIONS  a required heading is missing or has no content
#   PATH      a *Where things are* path that cannot be edited as written
#   ANCHOR    an anchor literal that is not unique, or a range past end of file
#   TESTNAME  a test path with no `:: <literal test name>` after it
#   STEPS     steps not numbered 1..n, a numbered step without a `[ ]` checkbox,
#             or a path in the table and not the steps (or the reverse) — an
#             unplanned edit, or a forgotten step
#   HEDGE     wording that delegates a decision to the executor
#
# An inline `#conformance-ok:<CODE>` comment on a line suppresses exactly that
# code on exactly that line, so one legitimate exception never becomes a reason
# to skip the gate wholesale.
set -euo pipefail

for c in git sort; do
  command -v "$c" >/dev/null 2>&1 || { echo "check_brief.sh: required CLI '$c' not found on PATH" >&2; exit 127; }
done

if (( $# != 2 )); then
  echo "check_brief.sh: expected 2 arguments, got $#" >&2
  echo "usage: check_brief.sh <repo-root> <brief.md>" >&2
  exit 2
fi

REPO_ROOT="$1"
BRIEF="$2"

[[ -d "$REPO_ROOT" ]] || { echo "check_brief.sh: repo root '$REPO_ROOT' is not a directory" >&2; exit 2; }
[[ -r "$BRIEF" && -f "$BRIEF" ]] || { echo "check_brief.sh: brief '$BRIEF' is not a readable file" >&2; exit 2; }
git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || { echo "check_brief.sh: repo root '$REPO_ROOT' is not a git work tree" >&2; exit 2; }
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"

# Headings the Brief must carry, from references/handoff.md. "Brief" is the H2
# title line; the rest are its H3 sections.
REQUIRED_SECTIONS=(
  "Brief"
  "Objective and acceptance criteria"
  "Where things are"
  "Mirror"
  "Contracts (bind exactly)"
  "Repo invariants"
  "Do NOT touch"
  "Test plan"
  "Test matrix"
  "Docs to update"
  "Implementation steps"
  "Finish checklist"
  "Progress reporting"
  "Commit plan"
  "Assumptions"
  "Return contract"
)

# Each of these turns one plan into two deliverables. `follow the ... pattern`
# is the same delegation wearing a reference's clothes: the sibling path plus
# the quoted lines is the compliant form.
HEDGE_TOKENS=(
  "optionally"
  "if unclear"
  "TBD"
  "UNRESOLVED"
  "and/or"
  "either"
  "decide whether"
  "something like"
)
HEDGE_PHRASE_RE='follow(s|ed|ing)? the [^.]{0,60}pattern'

# --- input -------------------------------------------------------------------

RAW=()
mapfile -t RAW < "$BRIEF"
LINES=()
for l in ${RAW[@]+"${RAW[@]}"}; do LINES+=("${l%$'\r'}"); done
NLINES=${#LINES[@]}

declare -A TRACKED=()
while IFS= read -r f; do
  [[ -n "$f" ]] && TRACKED["$f"]=1
done < <(git -C "$REPO_ROOT" ls-files)

# --- helpers -----------------------------------------------------------------

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

# Backticked substrings of $1, in order, into the BT array.
BT=()
extract_backticked() {
  local s="$1" m
  BT=()
  while [[ "$s" =~ \`([^\`]*)\` ]]; do
    m="${BASH_REMATCH[1]}"
    [[ -n "$m" ]] && BT+=("$m")
    s="${s#*\`"$m"\`}"
  done
}

# What is left of $1 once every backticked span is removed — a path cell's prose.
strip_backticked() {
  local s="$1" out="" m
  while [[ "$s" =~ \`([^\`]*)\` ]]; do
    m="${BASH_REMATCH[1]}"
    out+="${s%%\`"$m"\`*} "
    s="${s#*\`"$m"\`}"
  done
  printf '%s' "$out$s"
}

# A token names a file when it has no whitespace, uses path characters only,
# carries a separator or an extension, and its basename says something.
is_path_like() {
  local t="$1" base
  [[ -n "$t" ]] || return 1
  [[ "$t" == *[[:space:]]* ]] && return 1
  [[ "$t" =~ ^[A-Za-z0-9._/@+-]+$ ]] || return 1
  [[ "$t" == */* || "$t" =~ \.[A-Za-z][A-Za-z0-9]*$ ]] || return 1
  base="${t##*/}"
  [[ "$base" =~ [A-Za-z0-9] ]] || return 1
  return 0
}

is_placeholder_cell() {
  local s
  s="$(trim "$1")"
  [[ -z "$s" || "$s" == "—" || "$s" == "–" || "$s" == "-" || "$s" == "n/a" || "$s" == "N/A" ]]
}

# grep -c counts matching lines, which is the uniqueness question an Edit asks.
count_literal() {
  local needle="$1" file="$2" n
  n="$(grep -c -F -e "$needle" -- "$file" 2>/dev/null || true)"
  printf '%s' "${n:-0}"
}

file_lines() { # counts a final line with no trailing newline, which wc -l drops
  grep -c '' -- "$1" 2>/dev/null || true
}

# --- fences, suppressions, headings ------------------------------------------

# A Brief quotes code, and quoted code contains `#` comments and `|` characters.
# Structure is only ever read outside fences.
IN_FENCE=()
fence=0
for ((i = 0; i < NLINES; i++)); do
  if [[ "$(trim "${LINES[i]}")" == '```'* ]]; then
    IN_FENCE[i]=1
    fence=$((1 - fence))
  else
    IN_FENCE[i]=$fence
  fi
done

declare -A SUPPRESSED=()
for ((i = 0; i < NLINES; i++)); do
  s="${LINES[i]}"
  while [[ "$s" =~ \#conformance-ok:([A-Za-z]+) ]]; do
    SUPPRESSED["$((i + 1)):${BASH_REMATCH[1]^^}"]=1
    s="${s#*\#conformance-ok:}"
  done
done

HEAD_IDX=()
HEAD_NORM=()
for ((i = 0; i < NLINES; i++)); do
  (( IN_FENCE[i] )) && continue
  line="${LINES[i]}"
  [[ "$line" =~ ^\#{1,6}[[:space:]]+ ]] || continue
  t="$(trim "${line#"${line%%[![:space:]#]*}"}")"
  HEAD_IDX+=("$i")
  HEAD_NORM+=("${t,,}")
done

PROBLEMS=()
declare -A EMITTED=()
problem() { # $1 line (1-based, 0 = whole document)  $2 code  $3 detail
  [[ -n "${SUPPRESSED["$1:$2"]:-}" ]] && return 0
  [[ -n "${EMITTED["$1:$2:$3"]:-}" ]] && return 0
  EMITTED["$1:$2:$3"]=1
  PROBLEMS+=("$1"$'\t'"$2"$'\t'"$3")
  return 0
}

# Content range of a section, exclusive of its heading, up to the next heading.
SEC_HEAD_LINE=0
SEC_START=0
SEC_END=-1
find_section() {
  local want="${1,,}" want_short="${1%% (*}" h n
  want_short="${want_short,,}"
  for ((h = 0; h < ${#HEAD_IDX[@]}; h++)); do
    n="${HEAD_NORM[h]}"
    if [[ "$n" == "$want" || "$n" == "$want_short" || ( "$want" == "brief" && "$n" == brief* ) ]]; then
      SEC_HEAD_LINE=$(( HEAD_IDX[h] + 1 ))
      SEC_START=$(( HEAD_IDX[h] + 1 ))
      if (( h + 1 < ${#HEAD_IDX[@]} )); then SEC_END=$(( HEAD_IDX[h + 1] - 1 )); else SEC_END=$(( NLINES - 1 )); fi
      return 0
    fi
  done
  return 1
}

# --- SECTIONS ----------------------------------------------------------------

for want in "${REQUIRED_SECTIONS[@]}"; do
  if ! find_section "$want"; then
    problem 0 SECTIONS "required heading \"$want\" is missing"
    continue
  fi
  filled=0
  for ((i = SEC_START; i <= SEC_END; i++)); do
    [[ -n "$(trim "${LINES[i]}")" ]] && { filled=1; break; }
  done
  (( filled )) || problem "$SEC_HEAD_LINE" SECTIONS "section \"$want\" has no content"
done

# --- PATH / ANCHOR: the *Where things are* table -----------------------------

TABLE_PATHS=()
declare -A TABLE_PATH_LINE=()
declare -A REPORTED_MISSING=()

check_ranges() { # $1 cell  $2 line  — every `path:La-Lb` must fit inside the file
  local cell="$1" ln="$2" tok p a b total
  local toks=()
  cell="${cell//\`/ }"
  read -r -a toks <<<"$cell"
  for tok in ${toks[@]+"${toks[@]}"}; do
    tok="${tok%,}"
    [[ "$tok" =~ ^(.+):L?([0-9]+)-L?([0-9]+)$ ]] || continue
    p="${BASH_REMATCH[1]}"; a="${BASH_REMATCH[2]}"; b="${BASH_REMATCH[3]}"
    [[ -n "${REPORTED_MISSING["$p"]:-}" ]] && continue
    if [[ -z "${TRACKED["$p"]:-}" || ! -r "$REPO_ROOT/$p" ]]; then
      problem "$ln" ANCHOR "range \`$tok\` points at \`$p\`, which is not tracked in this repo"
      continue
    fi
    total="$(file_lines "$REPO_ROOT/$p")"
    if (( a < 1 || a > b )); then
      problem "$ln" ANCHOR "range \`$tok\` is inverted or starts before line 1"
    elif (( b > total )); then
      problem "$ln" ANCHOR "range \`$tok\` runs past end of \`$p\` ($total lines)"
    fi
  done
}

if find_section "Where things are"; then
  for ((i = SEC_START; i <= SEC_END; i++)); do
    (( IN_FENCE[i] )) && continue
    ln=$((i + 1))
    row="$(trim "${LINES[i]}")"
    [[ "$row" == \|* ]] || continue
    [[ "$row" =~ ^\|[[:space:]:|-]*\|$ ]] && continue   # the |---|---| separator
    row="${row#|}"
    row="${row%|}"
    IFS='|' read -r -a cells <<<"$row"
    (( ${#cells[@]} >= 2 )) || continue
    path_cell="$(trim "${cells[0]}")"
    action="$(trim "${cells[1]}")"
    action="${action^^}"
    [[ "${path_cell,,}" == 'path' || "$action" == "ACTION" ]] && continue   # the header row

    range_cell="$(trim "${cells[2]:-}")"
    anchor_cell="$(trim "${cells[3]:-}")"
    mirror_cell="$(trim "${cells[5]:-}")"

    # "backup.ts (or host-backup.ts)" is a choice too, so the alternative is
    # caught by a standalone `or` outside the backticks, not by a literal
    # " or ". A cell offering one still gets checked against its first option,
    # so one ambiguous path does not silence the rest of the row.
    prose="$(strip_backticked "$path_cell")"
    if [[ "${prose,,}" =~ (^|[^[:alnum:]])or([^[:alnum:]]|$) ]]; then
      problem "$ln" PATH "path cell offers a choice (\"$path_cell\"); name exactly one file"
    fi
    extract_backticked "$path_cell"
    if (( ${#BT[@]} )); then path="${BT[0]}"; else path="$path_cell"; fi
    path="$(trim "$path")"

    case "$action" in
      CREATE|MODIFY|REGISTER) ;;
      *) problem "$ln" PATH "action \"${action:-<empty>}\" for \`$path\` is not CREATE, MODIFY or REGISTER"
         continue ;;
    esac

    if [[ -z "$path" ]]; then
      problem "$ln" PATH "row has an action but no path"
      continue
    fi
    if [[ "$path" == *[*?\[]* ]]; then
      problem "$ln" PATH "\`$path\` is a glob; an Edit binds to one file"
      continue
    fi
    if [[ "$path" == */ ]]; then
      problem "$ln" PATH "\`$path\` has a trailing slash; a directory is not an edit target"
      continue
    fi

    TABLE_PATHS+=("$path")
    [[ -z "${TABLE_PATH_LINE["$path"]:-}" ]] && TABLE_PATH_LINE["$path"]=$ln

    if [[ "$action" == "CREATE" ]]; then
      if [[ -e "$REPO_ROOT/$path" ]]; then
        problem "$ln" PATH "CREATE \`$path\` already exists; it is a MODIFY"
      fi
    else
      if [[ -z "${TRACKED["$path"]:-}" ]]; then
        problem "$ln" PATH "$action \`$path\` is not in git ls-files"
        REPORTED_MISSING["$path"]=1
      elif is_placeholder_cell "$anchor_cell"; then
        problem "$ln" ANCHOR "$action \`$path\` has no anchor literal; line numbers rot, the literal does not"
      else
        extract_backticked "$anchor_cell"
        if (( ${#BT[@]} )); then anchor="${BT[0]}"; else anchor="$anchor_cell"; fi
        hits="$(count_literal "$anchor" "$REPO_ROOT/$path")"
        if (( hits != 1 )); then
          problem "$ln" ANCHOR "anchor \`$anchor\` matches $hits line(s) in \`$path\`; an Edit needs exactly 1"
        fi
      fi
    fi

    is_placeholder_cell "$range_cell"  || check_ranges "$range_cell" "$ln"
    is_placeholder_cell "$mirror_cell" || check_ranges "$mirror_cell" "$ln"
  done
fi

# --- TESTNAME: the *Test plan* section ---------------------------------------

named_a_test=0
if find_section "Test plan"; then
  test_head_line=$SEC_HEAD_LINE
  block_path=""
  block_line=0
  block_text=""
  saw_path=0

  close_block() {
    [[ -z "$block_path" ]] && return 0
    saw_path=1
    if [[ "$block_text" =~ ::[[:space:]]*\`?([^\`]*) ]] && [[ -n "$(trim "${BASH_REMATCH[1]}")" ]]; then
      named_a_test=1
    else
      problem "$block_line" TESTNAME "\`$block_path\` names no test; add \`:: <literal test name>\` per test"
    fi
    block_path=""
    return 0
  }

  for ((i = SEC_START; i <= SEC_END; i++)); do
    (( IN_FENCE[i] )) && continue
    ln=$((i + 1))
    line="${LINES[i]}"
    t="$(trim "$line")"
    if [[ "$t" =~ ^([-*+][[:space:]]|[0-9]+\.[[:space:]]) ]]; then
      close_block
      block_text="$t"
      block_line=$ln
      extract_backticked "$t"
      for tok in ${BT[@]+"${BT[@]}"}; do
        if is_path_like "$tok"; then block_path="$tok"; break; fi
      done
    elif [[ -n "$t" && -n "$block_path" ]]; then
      block_text+=" $t"
    elif [[ -z "$t" ]]; then
      close_block
    fi
  done
  close_block

  if (( saw_path == 0 )); then
    problem "$test_head_line" TESTNAME "*Test plan* names no test file; a section with no test path is not a test plan"
  fi
fi

# --- STEPS: the *Implementation steps* section -------------------------------

if find_section "Implementation steps"; then
  steps_head_line=$SEC_HEAD_LINE
  steps_text=""
  expected=1
  saw_step=0
  numbering_reported=0

  for ((i = SEC_START; i <= SEC_END; i++)); do
    ln=$((i + 1))
    steps_text+="${LINES[i]}"$'\n'
    (( IN_FENCE[i] )) && continue
    t="$(trim "${LINES[i]}")"
    if [[ "${LINES[i]}" =~ ^[[:space:]]{0,3}([0-9]+)\.[[:space:]] ]]; then
      n="${BASH_REMATCH[1]}"
      saw_step=1
      if (( n != expected )); then
        (( numbering_reported )) || problem "$ln" STEPS "steps must run 1..n contiguously; expected step $expected, found $n"
        numbering_reported=1
        expected=$((n + 1))
      else
        expected=$((n + 1))
      fi
      # The steps double as the executor's checklist; a step it cannot tick is
      # a step whose completion nothing tracks.
      [[ "${LINES[i]}" =~ ^[[:space:]]{0,3}[0-9]+\.[[:space:]]+\[[[:space:]xX]\] ]] \
        || problem "$ln" STEPS "step $n is not a checklist item; write \`$n. [ ] <step>\`"
    fi
    # A path cited only inside a step is an edit the table never declared.
    extract_backticked "$t"
    for tok in ${BT[@]+"${BT[@]}"}; do
      tok="${tok%%:L*}"
      is_path_like "$tok" || continue
      hit=0
      for p in ${TABLE_PATHS[@]+"${TABLE_PATHS[@]}"}; do
        [[ "$p" == "$tok" ]] && { hit=1; break; }
      done
      (( hit )) || problem "$ln" STEPS "step cites \`$tok\`, which is absent from *Where things are*"
    done
  done

  (( saw_step )) || problem "$steps_head_line" STEPS "no numbered steps found"

  for p in ${TABLE_PATHS[@]+"${TABLE_PATHS[@]}"}; do
    [[ "$steps_text" == *"$p"* ]] && continue
    problem "${TABLE_PATH_LINE["$p"]}" STEPS "\`$p\` is in *Where things are* but no step touches it"
  done
fi

# --- HEDGE -------------------------------------------------------------------

shopt -s nocasematch
for ((i = 0; i < NLINES; i++)); do
  line="${LINES[i]}"
  [[ -n "$line" ]] || continue
  ln=$((i + 1))
  for tok in "${HEDGE_TOKENS[@]}"; do
    if [[ "$line" =~ (^|[^[:alnum:]_])${tok}([^[:alnum:]_]|$) ]]; then
      problem "$ln" HEDGE "\"$tok\" delegates the decision; decide it now and record it as a numbered assumption"
    fi
  done
  if [[ "$line" =~ $HEDGE_PHRASE_RE ]]; then
    problem "$ln" HEDGE "\"follow the ... pattern\" describes a convention; give the sibling path and quote its lines instead"
  fi
done
shopt -u nocasematch

# --- report ------------------------------------------------------------------

(( ${#PROBLEMS[@]} )) || exit 0

printf '%s\n' "${PROBLEMS[@]}" | sort -s -n -t$'\t' -k1,1 | while IFS=$'\t' read -r ln code detail; do
  printf 'LINE %s: %s %s\n' "$ln" "$code" "$detail"
done
exit 1
