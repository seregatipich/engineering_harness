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
#   --milestone <title|number>
#                            -> restrict selection to that milestone. Repeatable:
#                              "finish milestones 2, 6 and 7" is one call with
#                              three flags, filled in the order given, deduped,
#                              and capped across the union. A bare integer is
#                              resolved against the repo's milestone numbers
#                              (title match wins if a milestone is literally
#                              titled "6"), and the mapping is recorded as an
#                              assumption so it is auditable.
#   --priority <critical|high|medium|low>
#                            -> floor: keep only issues at that priority or more urgent
#   --label <name>           -> require this label; repeat the flag to require several
#
# The caller (SKILL.md Step 1) translates a natural-language request into these
# flags before invoking; this script never parses prose.
#
# Fill order for the non-explicit remainder — open issues that are unassigned,
# not in-progress, and match the priority floor and required labels:
#   * --milestone set        -> only those milestones, in the order given.
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
# Priority and the in-progress exclusion are read through the repo's OWN label
# vocabulary, probed once with `gh label list`. A repo naming its labels
# `priority:p0` / `status:in-progress` used to score every issue "none" (so
# ordering silently degraded to issue number) and match the in-progress
# exclusion against nothing (so the guard against two concurrent runs claiming
# the same work silently did nothing). Both failures were invisible; label_map
# below makes them visible.
#
# Output: single JSON object
#   { "cap": N|null,
#     "filters": {milestone: null|[requested...], priority, labels},
#     "label_map": {role: this repo's label|null, ...},
#     "assumptions": [...],
#     "batch": [ {number,title,milestone,priority,source,order} ] }
#
#   label_map covers the roles this skill depends on — the four priority ranks
#   plus `in-progress` and `awaiting-release`. A null role has no label on this
#   repo: ordering falls back to issue number where a priority rank is null, and
#   the concurrent-run guard is inert where `in-progress` is null. Pipe the map
#   to scripts/setup_labels.sh to create only what is genuinely missing.
set -euo pipefail

for c in gh jq; do
  command -v "$c" >/dev/null 2>&1 || { echo "select_batch.sh: required CLI '$c' not found on PATH" >&2; exit 127; }
done

REPO="${1:?usage: select_batch.sh <owner/repo> [N] [#issue ...] [--milestone TITLE|NUMBER ...] [--priority P] [--label L ...]}"
shift || true

CAP=""            # empty = no cap (work the whole scoped set)
EXPLICIT=()
ASSUMPTIONS=()
MILESTONE_ARGS=()
PRIORITY=""
LABELS=()
expect_issue=0

while (( $# )); do
  tok="$1"; shift || true
  case "$tok" in
    --milestone|-m) [[ -n "${1-}" ]] && MILESTONE_ARGS+=("$1"); shift || true; expect_issue=0 ;;
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
[[ ${#MILESTONE_ARGS[@]} -gt 0 || -n "$PRIORITY" || ${#LABELS[@]} -gt 0 ]] && HAS_FILTER=1

# --- the repo's label vocabulary --------------------------------------------
# Probed once, then every priority read and the in-progress exclusion go through
# the resolved map instead of a hardcoded name.
ROLES=(priority:critical priority:high priority:medium priority:low in-progress awaiting-release)

role_candidates() { # $1 = role -> candidate label names, most canonical first
  case "$1" in
    priority:critical) printf '%s\n' "priority:critical" "priority:p0" "priority-critical" "priority/critical" "p0" "severity:critical" "severity:s0" ;;
    priority:high)     printf '%s\n' "priority:high"     "priority:p1" "priority-high"     "priority/high"     "p1" "severity:high"     "severity:s1" ;;
    priority:medium)   printf '%s\n' "priority:medium"   "priority:p2" "priority-medium"   "priority/medium"   "p2" "severity:medium"   "severity:s2" ;;
    priority:low)      printf '%s\n' "priority:low"      "priority:p3" "priority-low"      "priority/low"      "p3" "severity:low"      "severity:s3" ;;
    in-progress)       printf '%s\n' "in-progress" "status:in-progress" "status/in-progress" "in progress" "wip" ;;
    awaiting-release)  printf '%s\n' "awaiting-release" "status:awaiting-release" "status/awaiting-release" "awaiting release" ;;
  esac
}

role_miss_note() { # $1 = role -> what the caller loses by this role being absent
  case "$1" in
    priority:*) printf "No label on %s matches the '%s' role; issues at that level score priority 'none', so ordering there falls back to issue number." "$REPO" "$1" ;;
    in-progress) printf "No label on %s matches the 'in-progress' role; the exclusion that stops a concurrent run claiming the same issues is INERT. Create it with setup_labels.sh before relying on it." "$REPO" ;;
    awaiting-release) printf "No label on %s matches the 'awaiting-release' role; the ship step has no label to add. Create it with setup_labels.sh." "$REPO" ;;
  esac
}

declare -A ROLE_LABEL=()
repo_labels="$(gh label list --repo "$REPO" --limit 200 2>/dev/null | cut -f1 || true)"

if [[ -z "${repo_labels//[[:space:]]/}" ]]; then
  # No listing is not evidence of no labels, so assume the canonical vocabulary
  # rather than silently disabling every guard — and say that it was assumed.
  for role in "${ROLES[@]}"; do ROLE_LABEL[$role]="$role"; done
  ASSUMPTIONS+=("Could not list labels on $REPO; assumed the canonical vocabulary (${ROLES[*]}). If this repo names them differently, priority ordering and the in-progress guard are resolving against labels that do not exist.")
else
  verbatim=()
  for role in "${ROLES[@]}"; do
    hit=""
    while IFS= read -r cand; do
      [[ -z "$cand" ]] && continue
      hit="$(grep -ixF -m1 -- "$cand" <<<"$repo_labels" || true)"
      [[ -n "$hit" ]] && break
    done < <(role_candidates "$role")
    ROLE_LABEL[$role]="$hit"
    if [[ -z "$hit" ]]; then
      ASSUMPTIONS+=("$(role_miss_note "$role")")
    elif [[ "$hit" == "$role" ]]; then
      verbatim+=("$hit")
    else
      ASSUMPTIONS+=("Label role '$role' resolved to this repo's '$hit'.")
    fi
  done
  (( ${#verbatim[@]} > 0 )) && ASSUMPTIONS+=("Label roles present on $REPO under their canonical names: ${verbatim[*]}.")
fi

# Ranks 0-3 as a jq array, lowercased for case-insensitive membership tests.
pmap_json="$(printf '%s\n' "${ROLE_LABEL[priority:critical]}" "${ROLE_LABEL[priority:high]}" \
                            "${ROLE_LABEL[priority:medium]}"   "${ROLE_LABEL[priority:low]}" \
  | jq -R 'ascii_downcase | if . == "" then null else . end' | jq -sc .)"
wip_json="$(jq -n --arg w "${ROLE_LABEL[in-progress]}" '$w | ascii_downcase | if . == "" then null else . end')"
label_map_json="$(for role in "${ROLES[@]}"; do printf '%s\t%s\n' "$role" "${ROLE_LABEL[$role]}"; done \
  | jq -Rsc 'split("\n") | map(select(length > 0) | split("\t"))
             | map({(.[0]): (if (.[1] // "") == "" then null else .[1] end)}) | add')"

JQ_PRIO='def prio: ([.labels[].name] | map(ascii_downcase)) as $l
  | ((first($pmap | to_entries[] | select(.value as $n | $n != null and ($l | index($n)) != null) | .key)) // 4) as $rank
  | ["critical","high","medium","low","none"][$rank];
  def prio_rank: {"critical":0,"high":1,"medium":2,"low":3,"none":4}[prio];'

# --- milestones --------------------------------------------------------------
MILESTONES_JSON="$(gh api "repos/$REPO/milestones" --jq '.' 2>/dev/null || true)"
[[ -z "${MILESTONES_JSON//[[:space:]]/}" ]] && MILESTONES_JSON='[]'

nearest_due_titles() { # open milestones with open work, nearest due date first
  jq -r 'map(select(.state=="open" and .open_issues>0)) | sort_by(.due_on // "9999-12-31") | .[].title' <<<"$MILESTONES_JSON"
}

MILESTONE_TITLES=()
declare -A ms_seen=()
for marg in ${MILESTONE_ARGS[@]+"${MILESTONE_ARGS[@]}"}; do
  mtitle="$(jq -r --arg m "$marg" 'map(select(.title == $m)) | .[0].title // ""' <<<"$MILESTONES_JSON")"
  if [[ -z "$mtitle" && "$marg" =~ ^[0-9]+$ ]]; then
    mtitle="$(jq -r --argjson n "$((10#$marg))" 'map(select(.number == $n)) | .[0].title // ""' <<<"$MILESTONES_JSON")"
    [[ -n "$mtitle" ]] && ASSUMPTIONS+=("Milestone '$marg' resolved by number to '$mtitle' on $REPO.")
  fi
  if [[ -z "$mtitle" ]]; then
    ASSUMPTIONS+=("Milestone '$marg' not found on $REPO; no issues selected from it.")
    continue
  fi
  [[ -n "${ms_seen[$mtitle]:-}" ]] && continue
  ms_seen[$mtitle]=1
  MILESTONE_TITLES+=("$mtitle")
done

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
  add "$(jq -c --argjson pmap "$pmap_json" "$JQ_PRIO"'{number,title,milestone:(.milestone.title // null),priority:prio,source:"explicit"}' <<<"$obj")"
done

fill_from_list() { # $1 = JSON array of open issues, $2 = source tag
  local arr="$1" src="$2" obj
  while IFS= read -r obj; do
    [[ -z "$obj" ]] && continue
    at_cap && break
    add "$obj"
  done < <(jq -c --arg src "$src" --argjson floor "$PRIO_FLOOR" --argjson req "$labels_json" \
      --argjson pmap "$pmap_json" --argjson wip "$wip_json" "$JQ_PRIO"'
      map(select($wip == null or (([.labels[].name] | map(ascii_downcase)) | index($wip)) == null))
      | map(select(prio_rank <= $floor))
      | map(select(
          ($req | length) == 0
          or (([.labels[].name]) as $l | ($req | map(. as $r | $l | index($r)) | all))
        ))
      | sort_by([prio_rank, .number])
      | .[]
      | {number,title,milestone:(.milestone.title // null),priority:prio,source:$src}' <<<"$arr")
}

fill_from_milestone() { # $1 = milestone title
  local issues
  issues="$(gh issue list --repo "$REPO" --milestone "$1" --state open \
    --search "no:assignee" --limit 100 --json number,title,labels,milestone)"
  fill_from_list "$issues" "milestone:$1"
}

# Nearest-due open milestones (by due date), then every open issue. The priority
# floor and label filters are applied inside fill_from_list, so this same sweep
# serves both a scoped filter request and a bare cap.
broad_sweep() {
  local mtitle issues
  while IFS= read -r mtitle; do
    [[ -z "$mtitle" ]] && continue
    at_cap && break
    fill_from_milestone "$mtitle"
  done < <(nearest_due_titles)
  if ! at_cap; then
    issues="$(gh issue list --repo "$REPO" --state open \
      --search "no:assignee" --limit 200 --json number,title,labels,milestone)"
    fill_from_list "$issues" "backlog"
  fi
}

# 2. Fill the remainder according to the request's scope.
if ! at_cap; then
  if (( ${#MILESTONE_ARGS[@]} > 0 )); then
    # Each requested milestone in the order given; `add` dedups the overlap and
    # the cap applies across their union, not per milestone.
    for mtitle in ${MILESTONE_TITLES[@]+"${MILESTONE_TITLES[@]}"}; do
      at_cap && break
      fill_from_milestone "$mtitle"
    done
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
        fill_from_milestone "$mtitle"
        (( ${#BATCH[@]} > before )) && break
      done < <(nearest_due_titles)
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
milestones_json="$(printf '%s\n' ${MILESTONE_ARGS[@]+"${MILESTONE_ARGS[@]}"} | jq -R . | jq -s 'map(select(length > 0))')"
filters_json="$(jq -n --argjson m "$milestones_json" --arg p "$PRIORITY" --argjson l "$labels_json" \
  '{milestone:(if ($m | length) == 0 then null else $m end), priority:(if $p == "" then null else $p end), labels:$l}')"
if [[ -n "$CAP" ]]; then cap_json="$CAP"; else cap_json="null"; fi

if (( ${#BATCH[@]} == 0 )); then
  jq -n --argjson cap "$cap_json" --argjson f "$filters_json" --argjson lm "$label_map_json" --argjson a "$assumptions_json" \
    '{cap:$cap, filters:$f, label_map:$lm, assumptions:$a, batch:[]}'
else
  printf '%s\n' "${BATCH[@]}" | jq -s --argjson cap "$cap_json" --argjson f "$filters_json" --argjson lm "$label_map_json" --argjson a "$assumptions_json" \
    '{cap:$cap, filters:$f, label_map:$lm, assumptions:$a, batch:(to_entries | map(.value + {order:(.key + 1)}))}'
fi
