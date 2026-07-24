#!/usr/bin/env bash
# Deterministic batch selection for the work-next-issue skill.
#
# Usage: bash select_batch.sh <owner/repo> [args...]
#   bare number             -> N (rounded UP to a multiple of 5; default 10)
#   #<n>  or  issue <n>...   -> explicit issue numbers, selected first, in given
#                              order, even if assigned or in-progress; filters below
#                              do not apply to them
#   --milestone <title>      -> restrict selection to one milestone (skips the
#                              nearest-due sweep and the all-open fallback)
#   --priority <critical|high|medium|low>
#                            -> floor: keep only issues at that priority or more
#                              urgent
#   --label <name>           -> require this label; repeat the flag to require several
#
# The caller (SKILL.md Step 1) translates a natural-language request into these
# flags before invoking; this script never parses prose.
#
# Selection order for remaining slots (after explicit issues):
#   1. nearest-due open milestone with open issues: open, unassigned, not
#      in-progress, matching the priority floor and required labels, by priority
#      (critical>high>medium>low>none) then lowest number
#   2. next-nearest qualifying milestones, same ordering
#   3. all open issues (no milestone requirement), same ordering
#   With --milestone set, only that milestone is swept; steps 2 and 3 are skipped.
#
# Output: single JSON object
#   { "n": N, "filters": {milestone,priority,labels}, "assumptions": [...],
#     "batch": [ {number,title,milestone,priority,source,order} ] }
set -euo pipefail

for c in gh jq; do
  command -v "$c" >/dev/null 2>&1 || { echo "select_batch.sh: required CLI '$c' not found on PATH" >&2; exit 127; }
done

REPO="${1:?usage: select_batch.sh <owner/repo> [N] [#issue ...] [--milestone T] [--priority P] [--label L]}"
shift || true

N=10
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
        # so `issue 5 6 7` claims all three; otherwise a bare number sets N.
        if (( expect_issue == 1 )); then EXPLICIT+=("$t"); else N="$t"; fi
      else
        expect_issue=0
      fi
      ;;
  esac
done

if (( N < 5 )); then
  ASSUMPTIONS+=("N=$N below minimum; raised to 5.")
  N=5
elif (( N % 5 != 0 )); then
  ORIG=$N
  N=$(( (N + 4) / 5 * 5 ))
  ASSUMPTIONS+=("N=$ORIG is not a multiple of 5; rounded up to $N.")
fi

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

JQ_PRIO='def prio: ([.labels[].name]) as $l
  | if   $l | index("priority:critical") then "critical"
    elif $l | index("priority:high")     then "high"
    elif $l | index("priority:medium")   then "medium"
    elif $l | index("priority:low")      then "low"
    else "none" end;
  def prio_rank: {"critical":0,"high":1,"medium":2,"low":3,"none":4}[prio];'

declare -A seen
BATCH=()

add() { # $1 = compact JSON object with .number
  local obj="$1" num
  num="$(jq -r '.number' <<<"$obj")"
  [[ -n "${seen[$num]:-}" ]] && return 0
  seen[$num]=1
  BATCH+=("$obj")
}

# 1. Explicit issues first, in the order given. Filters do not apply to them.
for n in ${EXPLICIT[@]+"${EXPLICIT[@]}"}; do
  (( ${#BATCH[@]} >= N )) && break
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
    (( ${#BATCH[@]} >= N )) && break
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

# 2. Milestone sweep.
if (( ${#BATCH[@]} < N )); then
  if [[ -n "$MILESTONE" ]]; then
    if gh api "repos/$REPO/milestones" --jq '.[].title' 2>/dev/null | grep -qxF "$MILESTONE"; then
      issues="$(gh issue list --repo "$REPO" --milestone "$MILESTONE" --state open \
        --search "no:assignee" --limit 100 --json number,title,labels,milestone)"
      fill_from_list "$issues" "milestone:$MILESTONE"
    else
      ASSUMPTIONS+=("Milestone '$MILESTONE' not found on $REPO; no issues selected from it.")
    fi
  else
    while IFS= read -r mtitle; do
      [[ -z "$mtitle" ]] && continue
      (( ${#BATCH[@]} >= N )) && break
      issues="$(gh issue list --repo "$REPO" --milestone "$mtitle" --state open \
        --search "no:assignee" --limit 100 --json number,title,labels,milestone)"
      fill_from_list "$issues" "milestone:$mtitle"
    done < <(gh api "repos/$REPO/milestones" \
      --jq 'map(select(.state=="open" and .open_issues>0)) | sort_by(.due_on // "9999-12-31") | .[].title')
  fi
fi

# 3. Priority fallback across all open issues (skipped when a milestone was named).
if (( ${#BATCH[@]} < N )) && [[ -z "$MILESTONE" ]]; then
  issues="$(gh issue list --repo "$REPO" --state open \
    --search "no:assignee" --limit 200 --json number,title,labels,milestone)"
  fill_from_list "$issues" "priority-fallback"
fi

if (( ${#BATCH[@]} < N )); then
  ASSUMPTIONS+=("Only ${#BATCH[@]} eligible issue(s) found for N=$N; working the shortfall (report it).")
fi

assumptions_json="$(printf '%s\n' ${ASSUMPTIONS[@]+"${ASSUMPTIONS[@]}"} | jq -R . | jq -s 'map(select(length > 0))')"
filters_json="$(jq -n --arg m "$MILESTONE" --arg p "$PRIORITY" --argjson l "$labels_json" \
  '{milestone:(if $m == "" then null else $m end), priority:(if $p == "" then null else $p end), labels:$l}')"

if (( ${#BATCH[@]} == 0 )); then
  jq -n --argjson n "$N" --argjson f "$filters_json" --argjson a "$assumptions_json" \
    '{n:$n, filters:$f, assumptions:$a, batch:[]}'
else
  printf '%s\n' "${BATCH[@]}" | jq -s --argjson n "$N" --argjson f "$filters_json" --argjson a "$assumptions_json" \
    '{n:$n, filters:$f, assumptions:$a, batch:(to_entries | map(.value + {order:(.key + 1)}))}'
fi
