#!/usr/bin/env bash
# Deterministic issue selection for the work-next-issue skill.
#
# The working set is whatever the user's request scopes to — explicit issues
# and/or filters (milestone, priority floor, labels), optionally capped at an
# exact count. There is no default size and no rounding: the scope is the user's;
# this script just resolves it deterministically.
#
# Usage: bash select_batch.sh <owner/repo> [args...]
#   <n>  (a bare number)     -> exact cap: work AT MOST this many issues. No
#                              rounding, no minimum, no default — omit it to work
#                              the whole scoped set. A cap is a ceiling, never a
#                              target: if fewer eligible issues exist, you get
#                              fewer, and the script never invents work to fill it.
#   #<n>  or  issue <n>...    -> explicit issue numbers, selected first, in the
#                              order given, even if assigned or in-progress; the
#                              filters below do not apply to them. Explicit issues
#                              with no filter means "exactly these" — nothing is
#                              added beyond them (a cap only trims the list).
#   --milestone <title>      -> restrict selection to one milestone
#   --priority <critical|high|medium|low>
#                            -> floor: keep only issues at that priority or more urgent
#   --label <name>           -> require this label; repeat the flag to require several
#
# The caller (SKILL.md Step 1) translates a natural-language request into these
# flags before invoking; this script never parses prose.
#
# Fill order for the non-explicit remainder — open issues that are unassigned,
# not in-progress, and match the priority floor and required labels:
#   * --milestone set        -> only that milestone.
#   * a priority/label filter -> nearest-due open milestones, then all open
#                              issues, so every matching issue is covered.
#   * no filter but a cap    -> same broad sweep (nearest-due milestones, then
#                              all open), bounded by the cap rather than by scope.
#   * no filter, no cap, no explicit (a fully unscoped request)
#                            -> only the nearest-due open milestone that has
#                              eligible work — a bounded default, not the backlog.
#   * explicit issues, no filter -> no fill at all.
#   Within any sweep, order is priority (critical>high>medium>low>none) then
#   lowest number.
#
# Output: single JSON object
#   { "cap": N|null, "filters": {milestone,priority,labels}, "assumptions": [...],
#     "batch": [ {number,title,milestone,priority,source,order} ] }
set -euo pipefail

for c in gh jq; do
  command -v "$c" >/dev/null 2>&1 || { echo "select_batch.sh: required CLI '$c' not found on PATH" >&2; exit 127; }
done

REPO="${1:?usage: select_batch.sh <owner/repo> [N] [#issue ...] [--milestone T] [--priority P] [--label L]}"
shift || true

CAP=""            # empty = no cap (work the whole scoped set)
EXPLICIT=()
ASSUMPTIONS=()
MILESTONE=""
PRIORITY=""
LABELS=()
expect_issue=0

while (( $# )); do
  tok="$1"; shift || true
  case "$tok" in
    --milestone|-m) MILESTONE="${1-}"; shift || true; expect_issue=0 ;;
    --priority|-p)  PRIORITY="${1-}";  shift || true; expect_issue=0 ;;
    --label|-l)     LABELS+=("${1-}"); shift || true; expect_issue=0 ;;
    *)
      t="${tok#\#}"
      low="$(printf '%s' "$tok" | tr '[:upper:]' '[:lower:]')"
      if [[ "$tok" == \#* && "$t" =~ ^[0-9]+$ ]]; then
        EXPLICIT+=("$t"); expect_issue=0
      elif [[ "$low" == "issue" || "$low" == "issues" ]]; then
        expect_issue=1
      elif [[ "$t" =~ ^[0-9]+$ ]]; then
        # After an `issue`/`issues` keyword every following number is explicit,
        # so `issue 5 6 7` claims all three; otherwise a bare number is the cap.
        if (( expect_issue == 1 )); then EXPLICIT+=("$t"); else CAP="$t"; fi
      else
        expect_issue=0
      fi
      ;;
  esac
done

PRIO_FLOOR=99
if [[ -n "$PRIORITY" ]]; then
  PRIORITY="$(printf '%s' "$PRIORITY" | tr '[:upper:]' '[:lower:]')"
  case "$PRIORITY" in
    critical) PRIO_FLOOR=0 ;;
    high)     PRIO_FLOOR=1 ;;
    medium)   PRIO_FLOOR=2 ;;
    low)      PRIO_FLOOR=3 ;;
    *) ASSUMPTIONS+=("Priority '$PRIORITY' unrecognized; no priority floor applied.")
       PRIORITY="" ;;
  esac
fi

labels_json="$(printf '%s\n' ${LABELS[@]+"${LABELS[@]}"} | jq -R . | jq -s 'map(select(length > 0))')"

HAS_FILTER=0
[[ -n "$MILESTONE" || -n "$PRIORITY" || ${#LABELS[@]} -gt 0 ]] && HAS_FILTER=1

JQ_PRIO='def prio: ([.labels[].name]) as $l
  | if   $l | index("priority:critical") then "critical"
    elif $l | index("priority:high")     then "high"
    elif $l | index("priority:medium")   then "medium"
    elif $l | index("priority:low")      then "low"
    else "none" end;
  def prio_rank: {"critical":0,"high":1,"medium":2,"low":3,"none":4}[prio];'

declare -A seen
BATCH=()

# True once a cap is set and reached; every source checks it before adding more.
at_cap() { [[ -n "$CAP" ]] && (( ${#BATCH[@]} >= CAP )); }

add() { # $1 = compact JSON object with .number
  local obj="$1" num
  num="$(jq -r '.number' <<<"$obj")"
  [[ -n "${seen[$num]:-}" ]] && return 0
  seen[$num]=1
  BATCH+=("$obj")
}

# 1. Explicit issues first, in the order given. Filters do not apply to them.
for n in ${EXPLICIT[@]+"${EXPLICIT[@]}"}; do
  at_cap && break
  if ! obj="$(gh issue view "$n" --repo "$REPO" --json number,title,labels,milestone,state 2>/dev/null)"; then
    ASSUMPTIONS+=("Explicit issue #$n not found; skipped.")
    continue
  fi
  state="$(jq -r '.state' <<<"$obj")"
  if [[ "$state" != "OPEN" ]]; then
    ASSUMPTIONS+=("Explicit issue #$n is $state; skipped.")
    continue
  fi
  add "$(jq -c "$JQ_PRIO"'{number,title,milestone:(.milestone.title // null),priority:prio,source:"explicit"}' <<<"$obj")"
done

fill_from_list() { # $1 = JSON array of open issues, $2 = source tag
  local arr="$1" src="$2" obj
  while IFS= read -r obj; do
    [[ -z "$obj" ]] && continue
    at_cap && break
    add "$obj"
  done < <(jq -c --arg src "$src" --argjson floor "$PRIO_FLOOR" --argjson req "$labels_json" "$JQ_PRIO"'
      map(select(([.labels[].name] | index("in-progress")) | not))
      | map(select(prio_rank <= $floor))
      | map(select(
          ($req | length) == 0
          or (([.labels[].name]) as $l | ($req | map(. as $r | $l | index($r)) | all))
        ))
      | sort_by([prio_rank, .number])
      | .[]
      | {number,title,milestone:(.milestone.title // null),priority:prio,source:$src}' <<<"$arr")
}

# Nearest-due open milestones (by due date), then every open issue. The priority
# floor and label filters are applied inside fill_from_list, so this same sweep
# serves both a scoped filter request and a bare cap.
broad_sweep() {
  local mtitle issues
  while IFS= read -r mtitle; do
    [[ -z "$mtitle" ]] && continue
    at_cap && break
    issues="$(gh issue list --repo "$REPO" --milestone "$mtitle" --state open \
      --search "no:assignee" --limit 100 --json number,title,labels,milestone)"
    fill_from_list "$issues" "milestone:$mtitle"
  done < <(gh api "repos/$REPO/milestones" \
    --jq 'map(select(.state=="open" and .open_issues>0)) | sort_by(.due_on // "9999-12-31") | .[].title')
  if ! at_cap; then
    issues="$(gh issue list --repo "$REPO" --state open \
      --search "no:assignee" --limit 200 --json number,title,labels,milestone)"
    fill_from_list "$issues" "backlog"
  fi
}

# 2. Fill the remainder according to the request's scope.
if ! at_cap; then
  if [[ -n "$MILESTONE" ]]; then
    if gh api "repos/$REPO/milestones" --jq '.[].title' 2>/dev/null | grep -qxF "$MILESTONE"; then
      issues="$(gh issue list --repo "$REPO" --milestone "$MILESTONE" --state open \
        --search "no:assignee" --limit 100 --json number,title,labels,milestone)"
      fill_from_list "$issues" "milestone:$MILESTONE"
    else
      ASSUMPTIONS+=("Milestone '$MILESTONE' not found on $REPO; no issues selected from it.")
    fi
  elif (( HAS_FILTER == 1 )); then
    broad_sweep
  elif (( ${#EXPLICIT[@]} == 0 )); then
    if [[ -n "$CAP" ]]; then
      broad_sweep
    else
      # Fully unscoped: just the nearest-due open milestone that has eligible
      # work — a bounded default so a bare run never sweeps the whole backlog.
      while IFS= read -r mtitle; do
        [[ -z "$mtitle" ]] && continue
        before=${#BATCH[@]}
        issues="$(gh issue list --repo "$REPO" --milestone "$mtitle" --state open \
          --search "no:assignee" --limit 100 --json number,title,labels,milestone)"
        fill_from_list "$issues" "milestone:$mtitle"
        (( ${#BATCH[@]} > before )) && break
      done < <(gh api "repos/$REPO/milestones" \
        --jq 'map(select(.state=="open" and .open_issues>0)) | sort_by(.due_on // "9999-12-31") | .[].title')
      if (( ${#BATCH[@]} == 0 )); then
        ASSUMPTIONS+=("No open milestone has eligible work; nothing selected. Name a priority, label, or issue numbers to scope the run.")
      fi
    fi
  fi
  # Explicit issues with no filter: the batch is exactly those issues, no fill.
fi

# A shortfall only means something against an explicit cap; without one there is
# no target to fall short of.
if [[ -n "$CAP" ]] && (( ${#BATCH[@]} < CAP )); then
  ASSUMPTIONS+=("Only ${#BATCH[@]} eligible issue(s) matched the request; fewer than the cap of $CAP (report it).")
fi

assumptions_json="$(printf '%s\n' ${ASSUMPTIONS[@]+"${ASSUMPTIONS[@]}"} | jq -R . | jq -s 'map(select(length > 0))')"
filters_json="$(jq -n --arg m "$MILESTONE" --arg p "$PRIORITY" --argjson l "$labels_json" \
  '{milestone:(if $m == "" then null else $m end), priority:(if $p == "" then null else $p end), labels:$l}')"
if [[ -n "$CAP" ]]; then cap_json="$CAP"; else cap_json="null"; fi

if (( ${#BATCH[@]} == 0 )); then
  jq -n --argjson cap "$cap_json" --argjson f "$filters_json" --argjson a "$assumptions_json" \
    '{cap:$cap, filters:$f, assumptions:$a, batch:[]}'
else
  printf '%s\n' "${BATCH[@]}" | jq -s --argjson cap "$cap_json" --argjson f "$filters_json" --argjson a "$assumptions_json" \
    '{cap:$cap, filters:$f, assumptions:$a, batch:(to_entries | map(.value + {order:(.key + 1)}))}'
fi
