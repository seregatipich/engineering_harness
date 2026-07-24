#!/usr/bin/env bash
# Deterministic batch selection for the work-next-issue skill.
#
# Usage: bash select_batch.sh <owner/repo> [args...]
#   bare number          -> N (rounded UP to a multiple of 5; default 10)
#   #<n>  or  issue <n>  -> explicit issue numbers, selected first, in given order,
#                           even if assigned or labeled in-progress
#
# Selection order for remaining slots:
#   1. nearest-due open milestone with open issues: open, unassigned, not
#      in-progress, by priority (critical>high>medium>low>none) then lowest number
#   2. next-nearest qualifying milestones, same ordering
#   3. all open issues (no milestone requirement), same ordering
#
# Output: single JSON object
#   { "n": N, "assumptions": [...], "batch": [ {number,title,milestone,priority,source,order} ] }
set -euo pipefail

REPO="${1:?usage: select_batch.sh <owner/repo> [N | #issue ...]}"
shift || true

N=10
EXPLICIT=()
ASSUMPTIONS=()
expect_issue=0

for tok in "$@"; do
  t="${tok#\#}"
  low="$(printf '%s' "$tok" | tr '[:upper:]' '[:lower:]')"
  if [[ "$tok" == \#* && "$t" =~ ^[0-9]+$ ]]; then
    EXPLICIT+=("$t")
    expect_issue=0
  elif [[ "$low" == "issue" || "$low" == "issues" ]]; then
    expect_issue=1
  elif [[ "$t" =~ ^[0-9]+$ ]]; then
    if (( expect_issue == 1 )); then EXPLICIT+=("$t"); else N="$t"; fi
    expect_issue=0
  fi
done

if (( N < 5 )); then
  ASSUMPTIONS+=("N=$N below minimum; raised to 5.")
  N=5
elif (( N % 5 != 0 )); then
  ORIG=$N
  N=$(( (N + 4) / 5 * 5 ))
  ASSUMPTIONS+=("N=$ORIG is not a multiple of 5; rounded up to $N.")
fi

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

# 1. Explicit issues first, in the order given.
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
  done < <(jq -c --arg src "$src" "$JQ_PRIO"'
      map(select(([.labels[].name] | index("in-progress")) | not))
      | sort_by([prio_rank, .number])
      | .[]
      | {number,title,milestone:(.milestone.title // null),priority:prio,source:$src}' <<<"$arr")
}

# 2. Milestones, nearest due date first.
if (( ${#BATCH[@]} < N )); then
  while IFS= read -r mtitle; do
    [[ -z "$mtitle" ]] && continue
    (( ${#BATCH[@]} >= N )) && break
    issues="$(gh issue list --repo "$REPO" --milestone "$mtitle" --state open \
      --search "no:assignee" --limit 100 --json number,title,labels,milestone)"
    fill_from_list "$issues" "milestone:$mtitle"
  done < <(gh api "repos/$REPO/milestones" \
    --jq 'map(select(.state=="open" and .open_issues>0)) | sort_by(.due_on // "9999-12-31") | .[].title')
fi

# 3. Priority fallback across all open issues.
if (( ${#BATCH[@]} < N )); then
  issues="$(gh issue list --repo "$REPO" --state open \
    --search "no:assignee" --limit 200 --json number,title,labels,milestone)"
  fill_from_list "$issues" "priority-fallback"
fi

if (( ${#BATCH[@]} < N )); then
  ASSUMPTIONS+=("Only ${#BATCH[@]} eligible issue(s) found for N=$N; working the shortfall (report it).")
fi

assumptions_json="$(printf '%s\n' ${ASSUMPTIONS[@]+"${ASSUMPTIONS[@]}"} | jq -R . | jq -s 'map(select(length > 0))')"

if (( ${#BATCH[@]} == 0 )); then
  jq -n --argjson n "$N" --argjson a "$assumptions_json" '{n:$n, assumptions:$a, batch:[]}'
else
  printf '%s\n' "${BATCH[@]}" | jq -s --argjson n "$N" --argjson a "$assumptions_json" \
    '{n:$n, assumptions:$a, batch:(to_entries | map(.value + {order:(.key + 1)}))}'
fi
