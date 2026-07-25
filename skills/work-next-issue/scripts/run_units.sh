#!/usr/bin/env bash
# Run every verification unit of a repo to completion and report against a baseline.
#
# Two failures this replaces. A repo's aggregate test command usually bails at the
# first failing package, so one run surfaces one problem and the next run surfaces
# the next — the orchestrator iterates blind. And a baseline piped through `tail`
# reports the exit status of `tail` (always 0) over a truncated failure list: a
# false green baseline, which is worse than no baseline at all. So: every unit runs,
# nothing is piped for the purpose of deciding pass/fail, and the pass criterion is
# "no new failures versus the baseline", not "green".
#
# Usage: bash run_units.sh <units.tsv> <logdir> [--baseline <results.json>] [--only <unit>]
#   <units.tsv>   two tab-separated columns, `unit_name<TAB>command`, one per line.
#                 Blank lines and lines starting with `#` are ignored. Built in
#                 Step 2 from the repo's own toolchain and recorded in the Master
#                 Plan — this script never guesses a package manager or a runner.
#   <logdir>      created if absent; per-unit logs and the machine summary land here.
#   --baseline <results.json>
#                 a results.json from an earlier run (normally the clean-`dev`
#                 baseline). Turns the report into NEW FAILURES / FIXED / UNCHANGED
#                 and makes the exit code depend on regressions only.
#   --only <unit> run exactly one unit, for an isolation re-run.
#
# Output:
#   stdout        an aligned PASS/FAIL table, a total line, and — with --baseline —
#                 the three diff sections and a verdict line.
#   <logdir>/<unit>.log      combined stdout+stderr of that unit, plus its exit code.
#   <logdir>/results.json    [ {unit, command, exit_code, status, duration_s, log} ]
#                 An --only run writes `results.<unit>.json` instead, so an isolation
#                 re-run can never overwrite the full summary another run baselines against.
#
# Exit: 0 no unit failed (with --baseline: no NEW FAILURES), 1 otherwise, 2 on misuse.
set -euo pipefail

command -v jq >/dev/null 2>&1 || { echo "run_units.sh: required CLI 'jq' not found on PATH" >&2; exit 127; }

usage() { echo "usage: run_units.sh <units.tsv> <logdir> [--baseline <results.json>] [--only <unit>]" >&2; }
die() { echo "run_units.sh: $1" >&2; usage; exit 2; }

UNITS_TSV="${1-}"; [[ -n "$UNITS_TSV" ]] || die "missing <units.tsv>"
LOGDIR="${2-}";    [[ -n "$LOGDIR" ]]    || die "missing <logdir>"
shift 2

BASELINE=""
ONLY=""
while (( $# )); do
  case "$1" in
    --baseline) BASELINE="${2-}"; [[ -n "$BASELINE" ]] || die "--baseline needs a path"; shift 2 ;;
    --only)     ONLY="${2-}";     [[ -n "$ONLY" ]]     || die "--only needs a unit name"; shift 2 ;;
    *) die "unknown argument '$1'" ;;
  esac
done

[[ -f "$UNITS_TSV" ]] || die "units file '$UNITS_TSV' not found"
if [[ -n "$BASELINE" ]]; then
  # A missing or malformed baseline must not degrade into "no baseline": that would
  # silently report zero new failures and merge a regression.
  [[ -f "$BASELINE" ]] || die "baseline '$BASELINE' not found"
  jq -e 'type == "array" and all(.[]; has("unit") and has("status"))' "$BASELINE" >/dev/null 2>&1 \
    || die "baseline '$BASELINE' is not a results.json produced by this script"
fi

NAMES=()
COMMANDS=()
declare -A seen=()
lineno=0
while IFS=$'\t' read -r name cmd || [[ -n "${name-}" ]]; do
  lineno=$(( lineno + 1 ))
  name="${name%$'\r'}"; cmd="${cmd-}"; cmd="${cmd%$'\r'}"
  [[ -z "$name" || "$name" == \#* ]] && continue
  [[ -n "$cmd" ]] || die "$UNITS_TSV line $lineno: unit '$name' has no command (expected 'unit<TAB>command')"
  [[ "$name" != /* && "$name" != *..* ]] || die "$UNITS_TSV line $lineno: unit name '$name' may not be absolute or contain '..'"
  [[ -z "${seen[$name]:-}" ]] || die "$UNITS_TSV line $lineno: duplicate unit '$name'"
  seen[$name]=1
  NAMES+=("$name")
  COMMANDS+=("$cmd")
done < "$UNITS_TSV"

(( ${#NAMES[@]} )) || die "$UNITS_TSV defines no units; a run with nothing to verify is a false green, not a pass"

SELECTED=()
if [[ -n "$ONLY" ]]; then
  [[ -n "${seen[$ONLY]:-}" ]] || die "--only '$ONLY' is not a unit in $UNITS_TSV (have: ${NAMES[*]})"
  for i in "${!NAMES[@]}"; do [[ "${NAMES[$i]}" == "$ONLY" ]] && SELECTED+=("$i"); done
else
  for i in "${!NAMES[@]}"; do SELECTED+=("$i"); done
fi

mkdir -p "$LOGDIR"

RESULTS=()
STATUSES=()
run_started=$(date +%s)
position=0
for i in "${SELECTED[@]}"; do
  name="${NAMES[$i]}"
  cmd="${COMMANDS[$i]}"
  log="$LOGDIR/$name.log"
  mkdir -p "$(dirname "$log")"
  position=$(( position + 1 ))
  printf '[%d/%d] %s\n' "$position" "${#SELECTED[@]}" "$name" >&2

  {
    printf '# unit: %s\n' "$name"
    printf '# command: %s\n' "$cmd"
    printf '# started: %s\n\n' "$(date -Is)"
  } > "$log"

  started=$(date +%s)
  # Redirected straight to the file, never piped: a pipe would report the exit
  # status of the last stage and hide the failure this whole script exists to see.
  bash -c "$cmd" >> "$log" 2>&1 && code=0 || code=$?
  duration=$(( $(date +%s) - started ))

  if (( code == 0 )); then status=pass; else status=fail; fi
  printf '\n# exit: %d (%s) after %ds\n' "$code" "$status" "$duration" >> "$log"

  STATUSES+=("$status")
  RESULTS+=("$(jq -nc --arg unit "$name" --arg command "$cmd" --argjson exit_code "$code" \
    --arg status "$status" --argjson duration_s "$duration" --arg log "$log" \
    '{unit:$unit, command:$command, exit_code:$exit_code, status:$status, duration_s:$duration_s, log:$log}')")
done
run_duration=$(( $(date +%s) - run_started ))

if [[ -n "$ONLY" ]]; then
  SUMMARY="$LOGDIR/results.${ONLY//\//_}.json"
else
  SUMMARY="$LOGDIR/results.json"
fi
mkdir -p "$(dirname "$SUMMARY")"
printf '%s\n' "${RESULTS[@]}" | jq -s . > "$SUMMARY"

width=4
for i in "${SELECTED[@]}"; do (( ${#NAMES[$i]} > width )) && width=${#NAMES[$i]}; done

printf '%-*s  %-6s  %5s  %8s  %s\n' "$width" UNIT STATUS EXIT DURATION LOG
passed=0
failed=0
for n in "${!SELECTED[@]}"; do
  i="${SELECTED[$n]}"
  entry="${RESULTS[$n]}"
  status="${STATUSES[$n]}"
  if [[ "$status" == pass ]]; then passed=$(( passed + 1 )); else failed=$(( failed + 1 )); fi
  printf '%-*s  %-6s  %5s  %7ss  %s\n' "$width" "${NAMES[$i]}" \
    "$(printf '%s' "$status" | tr '[:lower:]' '[:upper:]')" \
    "$(jq -r '.exit_code' <<<"$entry")" \
    "$(jq -r '.duration_s' <<<"$entry")" \
    "$(jq -r '.log' <<<"$entry")"
done
printf '%-*s  %d unit(s)  %d passed  %d failed  in %ds\n' "$width" TOTAL "${#SELECTED[@]}" "$passed" "$failed" "$run_duration"
printf 'summary: %s\n' "$SUMMARY"

if [[ -z "$BASELINE" ]]; then
  (( failed == 0 )) || exit 1
  exit 0
fi

declare -A BASE=()
while IFS=$'\t' read -r bunit bstatus; do
  [[ -n "$bunit" ]] && BASE[$bunit]="$bstatus"
done < <(jq -r '.[] | [.unit, .status] | @tsv' "$BASELINE")

NEW_FAILURES=()
FIXED=()
UNCHANGED=()
for n in "${!SELECTED[@]}"; do
  i="${SELECTED[$n]}"
  name="${NAMES[$i]}"
  status="${STATUSES[$n]}"
  before="${BASE[$name]:-absent}"
  if [[ "$status" == fail ]]; then
    # A unit the baseline never recorded cannot be shown to have been failing
    # before, so it counts as a regression rather than as inherited red.
    if [[ "$before" == fail ]]; then
      UNCHANGED+=("$name (failing in baseline too)")
    else
      NEW_FAILURES+=("$name (baseline: $before)")
    fi
  elif [[ "$before" == fail ]]; then
    FIXED+=("$name (baseline: fail)")
  fi
done

section() { # $1 = heading, rest = lines
  local heading="$1"; shift
  printf '\n%s (%d)\n' "$heading" "$#"
  if (( $# == 0 )); then printf '  none\n'; else printf '  - %s\n' "$@"; fi
}

printf '\nbaseline: %s\n' "$BASELINE"
section "NEW FAILURES — these block" ${NEW_FAILURES[@]+"${NEW_FAILURES[@]}"}
section "FIXED" ${FIXED[@]+"${FIXED[@]}"}
section "UNCHANGED FAILURES" ${UNCHANGED[@]+"${UNCHANGED[@]}"}

if (( ${#NEW_FAILURES[@]} == 0 )); then
  printf '\nVERDICT: pass — no new failures versus baseline (%d pre-existing failure(s) remain)\n' "${#UNCHANGED[@]}"
  exit 0
fi
printf '\nVERDICT: fail — %d new failure(s) versus baseline\n' "${#NEW_FAILURES[@]}"
exit 1
