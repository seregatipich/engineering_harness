#!/usr/bin/env bash
# Tests for scripts/select_batch.sh. Stubs the `gh` CLI with a fixed dataset so
# selection logic (scope resolution, priority floor, milestone restriction,
# label filter, exact cap, explicit-first ordering, eligibility) is verified
# without network.
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

# Fully unscoped: only the nearest-due milestone that has eligible work (v1),
# never the whole backlog. No cap, so no shortfall.
out="$(run)"
assert_eq "unscoped: nearest-due milestone only, priority order" \
  '[7,8]' "$(nums "$out")"
assert_eq "unscoped: cap is null" 'null' "$(jq -c '.cap' <<<"$out")"
assert_eq "unscoped: filters are null/empty" \
  '{"milestone":null,"priority":null,"labels":[]}' "$(jq -c '.filters' <<<"$out")"
assert_eq "unscoped: no shortfall assumption (no cap to fall short of)" 'false' \
  "$(jq -c '[.assumptions[] | test("cap of")] | any' <<<"$out")"

out="$(run --priority critical)"
assert_eq "priority floor critical sweeps all milestones + backlog" \
  '[7,20]' "$(nums "$out")"
assert_eq "priority echoed in filters" '"critical"' "$(jq -c '.filters.priority' <<<"$out")"

out="$(run --priority high)"
assert_eq "priority floor high keeps critical+high across repo" \
  '[7,8,20,30]' "$(nums "$out")"

out="$(run --milestone v2)"
assert_eq "milestone v2 restricts and skips the backlog fallback (#30 absent)" \
  '[20,21,22]' "$(nums "$out")"

out="$(run --milestone nope)"
assert_eq "unknown milestone -> empty batch" '[]' "$(nums "$out")"
assert_eq "unknown milestone -> assumption recorded" 'true' \
  "$(jq -c '[.assumptions[] | test("not found")] | any' <<<"$out")"

out="$(run --label bug)"
assert_eq "label bug filter across milestones + backlog" '[7,20,21]' "$(nums "$out")"

out="$(run --milestone v2 --priority critical --label bug)"
assert_eq "combined filters intersect" '[20]' "$(nums "$out")"

out="$(run "#22" "#7")"
assert_eq "explicit issues come first in given order, no fill" \
  '[22,7]' "$(nums "$out")"
assert_eq "explicit issues tagged source=explicit" 'explicit explicit' \
  "$(jq -r '[.batch[0].source, .batch[1].source] | @tsv' <<<"$out" | tr '\t' ' ')"

out="$(run "#31")"
assert_eq "closed explicit issue is skipped with an assumption" 'true' \
  "$(jq -c '[.assumptions[] | test("#31 is CLOSED")] | any' <<<"$out")"

# Bare cap, no filter: bounded broad sweep — crosses from v1 into v2 to honor
# the count, but never invents work beyond what is eligible.
out="$(run 3)"
assert_eq "cap 3 crosses milestones to honor the count" '[7,8,20]' "$(nums "$out")"
assert_eq "cap echoed as a number" '3' "$(jq -c '.cap' <<<"$out")"
assert_eq "cap met exactly -> no shortfall assumption" 'false' \
  "$(jq -c '[.assumptions[] | test("cap of")] | any' <<<"$out")"

# Cap trims a filtered set.
out="$(run 2 --priority high)"
assert_eq "cap 2 trims the filtered sweep" '[7,8]' "$(nums "$out")"

# Cap trims the explicit list (no fill beyond it).
out="$(run 1 "#22" "#7")"
assert_eq "cap 1 trims explicit issues, no fill" '[22]' "$(nums "$out")"

# Cap larger than the eligible pool -> honest shortfall.
out="$(run 99 --priority critical)"
assert_eq "cap above the pool keeps only what is eligible" '[7,20]' "$(nums "$out")"
assert_eq "cap above the pool records a shortfall" 'true' \
  "$(jq -c '[.assumptions[] | test("cap of 99")] | any' <<<"$out")"

# This stub has no `label list`, i.e. the vocabulary could not be probed. That is
# not evidence of absence, so the canonical names are assumed — and said so.
out="$(run)"
assert_eq "unprobeable vocabulary -> canonical assumed, and recorded" 'true' \
  "$(jq -c '[.assumptions[] | test("assumed the canonical vocabulary")] | any' <<<"$out")"
assert_eq "unprobeable vocabulary -> label_map is the canonical identity" \
  '{"priority:critical":"priority:critical","priority:high":"priority:high","priority:medium":"priority:medium","priority:low":"priority:low","in-progress":"in-progress","awaiting-release":"awaiting-release"}' \
  "$(jq -c '.label_map' <<<"$out")"

# --- a repo with its own label vocabulary ------------------------------------
# Same shape of dataset, but the labels are `priority:p0/p1` and
# `status:in-progress`, and the milestones are addressed by number. Everything
# below fails on a hardcoded vocabulary: the priority ordering degrades to issue
# number, and the in-progress exclusion matches nothing.
ALT="$WORK/alt"
mkdir -p "$ALT"
cat >"$ALT/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

DATA='[
 {"number":101,"title":"p0 in alpha",     "labels":[{"name":"priority:p0"}],                                  "milestone":{"title":"alpha"},"state":"OPEN","assignee":null},
 {"number":102,"title":"p1 in alpha",     "labels":[{"name":"priority:p1"},{"name":"bug"}],                   "milestone":{"title":"alpha"},"state":"OPEN","assignee":null},
 {"number":103,"title":"claimed p0",      "labels":[{"name":"priority:p0"},{"name":"status:in-progress"}],     "milestone":{"title":"alpha"},"state":"OPEN","assignee":null},
 {"number":201,"title":"p1 in beta",      "labels":[{"name":"priority:p1"}],                                  "milestone":{"title":"beta"}, "state":"OPEN","assignee":null},
 {"number":202,"title":"p0 in beta",      "labels":[{"name":"priority:p0"}],                                  "milestone":{"title":"beta"}, "state":"OPEN","assignee":null},
 {"number":301,"title":"unlabelled",      "labels":[],                                                        "milestone":{"title":"gamma"},"state":"OPEN","assignee":null}
]'
MILES='[
 {"number":2,"title":"alpha","state":"open","open_issues":3,"due_on":"2026-01-01T00:00:00Z"},
 {"number":6,"title":"beta", "state":"open","open_issues":2,"due_on":"2026-02-01T00:00:00Z"},
 {"number":7,"title":"gamma","state":"open","open_issues":1,"due_on":"2026-03-01T00:00:00Z"}
]'

sub="${1:-}"; shift || true
case "$sub" in
  label)
    printf '%s\t%s\t%s\n' \
      "priority:p0" "urgent" "b60205" \
      "priority:p1" "soon"   "d93f0b" \
      "status:in-progress" "claimed" "1d76db" \
      "bug" "defect" "ee0701"
    ;;
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
chmod +x "$ALT/gh"
run_alt() { PATH="$ALT:$PATH" bash "$SELECT" "$REPO" "$@"; }

out="$(run_alt)"
assert_eq "foreign vocabulary: p0 outranks p1 and in-progress is excluded" \
  '[101,102]' "$(nums "$out")"
assert_eq "foreign vocabulary: label_map reports what resolved and what did not" \
  '{"priority:critical":"priority:p0","priority:high":"priority:p1","priority:medium":null,"priority:low":null,"in-progress":"status:in-progress","awaiting-release":null}' \
  "$(jq -c '.label_map' <<<"$out")"
assert_eq "foreign vocabulary: each resolution is an assumption" 'true' \
  "$(jq -c '[.assumptions[] | test("resolved to this repo.s .status:in-progress.")] | any' <<<"$out")"
assert_eq "unmatched in-progress role would be reported as inert" 'false' \
  "$(jq -c '[.assumptions[] | test("INERT")] | any' <<<"$out")"
assert_eq "unmatched awaiting-release role is reported" 'true' \
  "$(jq -c '[.assumptions[] | test("awaiting-release. role")] | any' <<<"$out")"
assert_eq "priority floor resolves through the map, not the hardcoded names" \
  '[101,202]' "$(nums "$(run_alt --priority critical)")"
assert_eq "label filter still matches label names verbatim" \
  '[102]' "$(nums "$(run_alt --label bug)")"

# Repeatable --milestone: filled in the order given, not the repo's due order.
out="$(run_alt --milestone beta --milestone alpha)"
assert_eq "two --milestone flags fill in the order given, priority within each" \
  '[202,201,101,102]' "$(nums "$out")"
assert_eq "both milestones echoed in filters" '["beta","alpha"]' \
  "$(jq -c '.filters.milestone' <<<"$out")"

out="$(run_alt --milestone 6)"
assert_eq "numeric milestone resolves by number" '[202,201]' "$(nums "$out")"
assert_eq "numeric milestone resolution is recorded as an assumption" 'true' \
  "$(jq -c '[.assumptions[] | test("Milestone .6. resolved by number to .beta.")] | any' <<<"$out")"

out="$(run_alt --milestone 6 --milestone 7)"
assert_eq "several numeric milestones, in the order given" '[202,201,301]' "$(nums "$out")"

out="$(run_alt 3 --milestone 6 --milestone 2)"
assert_eq "cap applies across the union of milestones" '[202,201,101]' "$(nums "$out")"

out="$(run_alt --milestone alpha --milestone 2)"
assert_eq "the same milestone by title and by number is deduped" '[101,102]' "$(nums "$out")"

out="$(run_alt --milestone 99)"
assert_eq "unknown milestone number -> empty batch, assumption recorded" 'true' \
  "$(jq -c '[(.batch | length) == 0, ([.assumptions[] | test("Milestone .99. not found")] | any)] | all' <<<"$out")"

if (( FAILED )); then
  echo "FAILED"
  exit 1
fi
echo "All tests passed."
