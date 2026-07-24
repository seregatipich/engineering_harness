#!/usr/bin/env bash
# Tests for scripts/select_batch.sh. Stubs the `gh` CLI with a fixed dataset so
# selection logic (priority floor, milestone restriction, label filter, N
# rounding, explicit-first ordering, eligibility) is verified without network.
#
# Run: bash tests/select_batch_test.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELECT="$HERE/../scripts/select_batch.sh"
REPO="acme/app"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- gh stub -----------------------------------------------------------------
# Emulates: `issue view <n>`, `issue list [--milestone T] --search no:assignee`
# (open + unassigned), and `api .../milestones --jq EXPR`.
cat >"$WORK/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

DATA='[
 {"number":7, "title":"crit bug v1",    "labels":[{"name":"priority:critical"},{"name":"bug"}],  "milestone":{"title":"v1"}, "state":"OPEN",   "assignee":null},
 {"number":8, "title":"high v1",        "labels":[{"name":"priority:high"}],                       "milestone":{"title":"v1"}, "state":"OPEN",   "assignee":null},
 {"number":9, "title":"assigned crit",  "labels":[{"name":"priority:critical"}],                   "milestone":{"title":"v1"}, "state":"OPEN",   "assignee":{"login":"x"}},
 {"number":10,"title":"in-progress v1", "labels":[{"name":"priority:critical"},{"name":"in-progress"}], "milestone":{"title":"v1"}, "state":"OPEN", "assignee":null},
 {"number":20,"title":"crit bug v2",    "labels":[{"name":"priority:critical"},{"name":"bug"}],  "milestone":{"title":"v2"}, "state":"OPEN",   "assignee":null},
 {"number":21,"title":"medium bug v2",  "labels":[{"name":"priority:medium"},{"name":"bug"}],    "milestone":{"title":"v2"}, "state":"OPEN",   "assignee":null},
 {"number":22,"title":"low doc v2",     "labels":[{"name":"priority:low"},{"name":"docs"}],      "milestone":{"title":"v2"}, "state":"OPEN",   "assignee":null},
 {"number":30,"title":"high no-ms",     "labels":[{"name":"priority:high"}],                       "milestone":null,           "state":"OPEN",   "assignee":null},
 {"number":31,"title":"closed crit v2", "labels":[{"name":"priority:critical"}],                   "milestone":{"title":"v2"}, "state":"CLOSED", "assignee":null}
]'
MILES='[
 {"title":"v1","state":"open","open_issues":3,"due_on":"2025-01-01T00:00:00Z"},
 {"title":"v2","state":"open","open_issues":3,"due_on":"2025-06-01T00:00:00Z"}
]'

sub="${1:-}"; shift || true
case "$sub" in
  issue)
    action="${1:-}"; shift || true
    case "$action" in
      view)
        num="${1:-}"; shift || true
        jq -e --argjson n "$num" '.[] | select(.number==$n) | {number,title,labels,milestone,state}' <<<"$DATA"
        ;;
      list)
        ms=""
        while (( $# )); do case "$1" in --milestone) ms="${2:-}"; shift 2 || true;; *) shift || true;; esac; done
        if [[ -n "$ms" ]]; then
          jq --arg m "$ms" '[.[] | select(.state=="OPEN" and .assignee==null and (.milestone.title==$m)) | {number,title,labels,milestone}]' <<<"$DATA"
        else
          jq '[.[] | select(.state=="OPEN" and .assignee==null) | {number,title,labels,milestone}]' <<<"$DATA"
        fi
        ;;
      *) echo "gh stub: unknown issue action '$action'" >&2; exit 2 ;;
    esac
    ;;
  api)
    jqexpr=""
    while (( $# )); do case "$1" in --jq) jqexpr="${2:-}"; shift 2 || true;; *) shift || true;; esac; done
    jq -r "$jqexpr" <<<"$MILES"
    ;;
  *) echo "gh stub: unknown subcommand '$sub'" >&2; exit 2 ;;
esac
STUB
chmod +x "$WORK/gh"
export PATH="$WORK:$PATH"

# --- assertions --------------------------------------------------------------
FAILED=0
run() { bash "$SELECT" "$REPO" "$@"; }
assert_eq() { # $1 desc  $2 expected  $3 actual
  if [[ "$2" == "$3" ]]; then
    printf '  PASS  %s\n' "$1"
  else
    printf '  FAIL  %s\n    expected: %s\n    actual:   %s\n' "$1" "$2" "$3"
    FAILED=1
  fi
}
nums() { jq -c '[.batch[].number]' <<<"$1"; }

echo "select_batch.sh"

out="$(run)"
assert_eq "default: milestone order, excludes assigned/in-progress/closed" \
  '[7,8,20,21,22,30]' "$(nums "$out")"
assert_eq "default: N stays 10" '10' "$(jq -c '.n' <<<"$out")"
assert_eq "default: filters are null/empty" \
  '{"milestone":null,"priority":null,"labels":[]}' "$(jq -c '.filters' <<<"$out")"
assert_eq "default: shortfall recorded (6 < 10)" 'true' \
  "$(jq -c '[.assumptions[] | test("shortfall")] | any' <<<"$out")"

out="$(run --priority critical)"
assert_eq "priority floor critical keeps only critical, unassigned, open" \
  '[7,20]' "$(nums "$out")"
assert_eq "priority echoed in filters" '"critical"' "$(jq -c '.filters.priority' <<<"$out")"

out="$(run --priority high)"
assert_eq "priority floor high keeps critical+high" \
  '[7,8,20,30]' "$(nums "$out")"

out="$(run --milestone v2)"
assert_eq "milestone v2 restricts and skips all-open fallback (#30 absent)" \
  '[20,21,22]' "$(nums "$out")"

out="$(run --milestone nope)"
assert_eq "unknown milestone -> empty batch" '[]' "$(nums "$out")"
assert_eq "unknown milestone -> assumption recorded" 'true' \
  "$(jq -c '[.assumptions[] | test("not found")] | any' <<<"$out")"

out="$(run --label bug)"
assert_eq "label bug filter" '[7,20,21]' "$(nums "$out")"

out="$(run --milestone v2 --priority critical --label bug)"
assert_eq "combined filters intersect" '[20]' "$(nums "$out")"

out="$(run "#22" "#7")"
assert_eq "explicit issues come first in given order" \
  '22 7' "$(jq -r '[.batch[0].number, .batch[1].number] | @tsv' <<<"$out" | tr '\t' ' ')"
assert_eq "explicit issues tagged source=explicit" 'explicit explicit' \
  "$(jq -r '[.batch[0].source, .batch[1].source] | @tsv' <<<"$out" | tr '\t' ' ')"

out="$(run "#31")"
assert_eq "closed explicit issue is skipped with an assumption" 'true' \
  "$(jq -c '[.assumptions[] | test("#31 is CLOSED")] | any' <<<"$out")"

out="$(run 3)"
assert_eq "N=3 raised to minimum 5" '5' "$(jq -c '.n' <<<"$out")"
assert_eq "sub-minimum N recorded as assumption" 'true' \
  "$(jq -c '[.assumptions[] | test("raised to 5")] | any' <<<"$out")"
assert_eq "N=5 caps the batch" '[7,8,20,21,22]' "$(nums "$out")"

out="$(run 7)"
assert_eq "N=7 rounds up to 10" '10' "$(jq -c '.n' <<<"$out")"
assert_eq "N rounding recorded as assumption" 'true' \
  "$(jq -c '[.assumptions[] | test("rounded up")] | any' <<<"$out")"

if (( FAILED )); then
  echo "FAILED"
  exit 1
fi
echo "All tests passed."
