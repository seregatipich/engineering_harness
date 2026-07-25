#!/usr/bin/env bash
# Tests for scripts/check_brief.sh. Builds a throwaway git repo whose tracked
# files the fixture Brief points at, then mutates one clean Brief into one
# Brief per failure code — so each assertion names the single defect it injected
# and the clean Brief proves the gate stays quiet on a conformant document.
#
# Run: bash tests/check_brief_test.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$HERE/../scripts/check_brief.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
REPO="$WORK/repo"

# --- fixture repo ------------------------------------------------------------
mkdir -p "$REPO/src/a" "$REPO/tests"

{
  echo "// b.ts"
  for i in $(seq 2 18); do echo "const line$i = $i;"; done
  echo "const shared = 1;"
  echo "export function handleConnect(evt: Event) {"
  for i in $(seq 22 39); do echo "  // body $i"; done
  echo "}"
  echo "const shared = 2;"
} >"$REPO/src/a/b.ts"

{
  echo "// c.ts — the mirror sibling"
  for i in $(seq 2 30); do echo "  // c body $i"; done
} >"$REPO/src/a/c.ts"

{
  echo "// registry.ts"
  echo "import { alpha } from './a/alpha';"
  echo "import { beta } from './a/beta';"
  echo ""
  echo "export const HANDLERS = ["
  echo "  alpha,"
  echo "  beta,"
  echo "];"
  for i in $(seq 9 20); do echo "// tail $i"; done
} >"$REPO/src/registry.ts"

echo "// existing b tests" >"$REPO/tests/b_test.ts"
echo "// existing registry parity guard" >"$REPO/tests/registry_test.ts"

git -C "$REPO" init -q
git -C "$REPO" add -A

# --- clean brief -------------------------------------------------------------
cat >"$WORK/clean.md" <<'MD'
## Brief — #42 Handle connect events (issue 1 of 2, merge position 1)

Canonical Master Plan: https://github.com/acme/app/issues/42#issuecomment-1

### Objective and acceptance criteria

Deliver the connect handler so a connect event reaches the registry.

> - A connect event invokes the new handler.
> - An unknown event is rejected.

### Where things are

| path | action | read range | anchor literal | change | mirror |
|---|---|---|---|---|---|
| `src/a/b.ts` | MODIFY | `src/a/b.ts:L20-40` | `export function handleConnect(` | Call the new handler. | `src/a/c.ts:L10-20` |
| `src/a/new.ts` | CREATE | — | — | Holds the new handler. | `src/a/c.ts` |
| `src/registry.ts` | REGISTER | `src/registry.ts:L1-12` | `export const HANDLERS = [` | append `connect` | — |
| `tests/new_test.ts` | CREATE | — | — | The failing test, written first. | `tests/b_test.ts` |

### Mirror

`src/a/new.ts` copies `src/a/c.ts` lines 1-6:

```ts
// c.ts — the mirror sibling
  // c body 2
```

### Contracts (bind exactly)

```ts
export function connect(evt: Event): void
```

### Repo invariants

Registry parity: every handler is listed in HANDLERS -> `tests/registry_test.ts` -> `src/registry.ts`.
MUST-PASS-UNMODIFIED.

### Do NOT touch

- The transport layer.
- The existing b tests.

### Test plan

- `tests/new_test.ts` :: `handles a connect event` — asserts the handler runs on connect (happy)
- `tests/new_test.ts` :: `rejects an unknown event` — asserts it throws (failure)
- `tests/registry_test.ts` :: `registry lists every handler` — asserts parity holds (edge)

### Docs to update

`docs/handlers.md`, heading "Handlers", one table row per handler. Exhaustive: `grep -c '^|' docs/handlers.md` printed 4.

### Implementation steps

1. Write `tests/new_test.ts` from the *Mirror* sibling -> makes `handles a connect event` fail for the right reason
   verify: `npm test -- tests/new_test.ts` -> expect `1 failing`
   if it doesn't match: stop that step, then record PLAN-WRONG
2. Add `src/a/new.ts` with the signature from *Contracts* -> makes the import resolve
   verify: `npx tsc --noEmit` -> expect exit 0
   if it doesn't match: bind the signature to *Contracts*, then record PLAN-WRONG
3. Edit `src/a/b.ts` at its anchor to call the handler -> makes `handles a connect event` pass
   verify: `npm test -- tests/new_test.ts` -> expect `2 passing`
   if it doesn't match: re-read the anchor line, then record PLAN-WRONG
4. Append the handler in `src/registry.ts` at its anchor -> keeps `registry lists every handler` green
   verify: `npm test -- tests/registry_test.ts` -> expect `1 passing`
   if it doesn't match: re-read the anchor line, then record PLAN-WRONG

### Finish checklist

`npm test` -> green except the baseline failures: `tests/legacy_test.ts` (3 failing, pre-existing on dev).

### Commit plan

1. `test(handlers): cover connect events`
2. `feat(handlers): route connect events to the registry`

### Assumptions

1. The handler name is `connect`, matching the event string (Rule 2).

### Return contract

STATUS / BRANCH / COMMITS / FILES / STEPS / TESTS ADDED / VERIFICATION / RED-BEFORE / DEVIATIONS /
PLAN-WRONG / UNVERIFIABLE / ASSUMPTIONS.

- Never skip, disable or `.skip` a test, suppress a warning, disable a lint rule, or loosen a type.
- Never fabricate a result. If something cannot run here, say so and say why.
- Stay inside the issue. Adjacent bugs go in the return as follow-ups, not in the diff.
MD

# --- fixture mutation --------------------------------------------------------
mutate() { # $1 name, then sed expressions -> prints the new brief's path
  local name="$1"; shift
  local f="$WORK/$name.md" e
  cp "$WORK/clean.md" "$f"
  for e in "$@"; do sed "$e" "$f" >"$f.tmp" && mv "$f.tmp" "$f"; done
  printf '%s' "$f"
}

drop_section() { # $1 name  $2 exact heading line
  local f="$WORK/$1.md"
  awk -v h="$2" '$0==h {skip=1; next} /^#/ {skip=0} !skip' "$WORK/clean.md" >"$f"
  printf '%s' "$f"
}

empty_section() { # $1 name  $2 exact heading line
  local f="$WORK/$1.md"
  awk -v h="$2" '$0==h {print; print ""; skip=1; next} /^#/ {skip=0} !skip' "$WORK/clean.md" >"$f"
  printf '%s' "$f"
}

replace_section_body() { # $1 name  $2 exact heading line  $3 replacement body
  local f="$WORK/$1.md"
  awk -v h="$2" -v b="$3" '$0==h {print; print ""; print b; print ""; skip=1; next} /^#/ {skip=0} !skip' \
    "$WORK/clean.md" >"$f"
  printf '%s' "$f"
}

# --- assertions --------------------------------------------------------------
FAILED=0
OUT=""
RC=0
run_check() {
  set +e
  OUT="$(bash "$CHECK" "$REPO" "$1" 2>&1)"
  RC=$?
  set -e
}
codes_of() { awk '$1=="LINE" {print $3}' <<<"$OUT" | sort -u | tr '\n' ' ' | sed 's/ $//'; }
count_of() { awk -v c="$1" '$1=="LINE" && $3==c' <<<"$OUT" | grep -c '' || true; }

assert_eq() { # $1 desc  $2 expected  $3 actual
  if [[ "$2" == "$3" ]]; then
    printf '  PASS  %s\n' "$1"
  else
    printf '  FAIL  %s\n    expected: %s\n    actual:   %s\n' "$1" "$2" "$3"
    FAILED=1
  fi
}
assert_case() { # $1 desc  $2 brief path  $3 expected code set ("" = clean)
  run_check "$2"
  if [[ -z "$3" ]]; then
    assert_eq "$1 (exit 0, silent)" "0|" "$RC|$OUT"
  else
    assert_eq "$1" "1|$3" "$RC|$(codes_of)"
  fi
}

echo "check_brief.sh"

# A conformant Brief passes silently — the gate is only credible if it does.
assert_case "clean brief is dispatchable" "$WORK/clean.md" ""

# --- SECTIONS ---
assert_case "missing required heading" "$(drop_section missing_mirror '### Mirror')" "SECTIONS"
run_check "$(drop_section missing_mirror '### Mirror')"
assert_eq "missing heading is a whole-document problem (LINE 0) naming the heading" "1" \
  "$(grep -c '^LINE 0: SECTIONS required heading "Mirror" is missing$' <<<"$OUT" || true)"
assert_case "heading present but empty" "$(empty_section empty_commits '### Commit plan')" "SECTIONS"

# --- PATH ---
assert_case "CREATE path that already exists" \
  "$(mutate path_create_exists 's|src/a/new.ts|src/a/c.ts|g')" "PATH"
assert_case "MODIFY path absent from git ls-files" \
  "$(mutate path_untracked 's|src/a/b.ts|src/a/ghost.ts|g')" "PATH"
assert_case "glob instead of a file" \
  "$(mutate path_glob 's|src/a/new.ts|src/a/*.ts|g')" "PATH"
assert_case "trailing slash instead of a file" \
  "$(mutate path_dir 's|src/a/new.ts|src/a/new/|g')" "PATH"
assert_case "path cell offering a parenthesised alternative" \
  "$(mutate path_choice 's#`src/a/new.ts` | CREATE#`src/a/new.ts` (or `src/a/alt.ts`) | CREATE#')" "PATH"
assert_case "path cell offering two files" \
  "$(mutate path_choice2 's#`src/a/new.ts` | CREATE#`src/a/new.ts` or `src/a/alt.ts` | CREATE#')" "PATH"
assert_case "a path segment spelled 'or' is not a choice" \
  "$(mutate path_or_segment 's|src/a/new.ts|src/or/new.ts|g')" ""

# --- ANCHOR ---
assert_case "anchor literal that is not unique" \
  "$(mutate anchor_dup 's#`export function handleConnect(`#`const shared =`#')" "ANCHOR"
assert_case "read range past end of file" \
  "$(mutate anchor_range 's#src/a/b.ts:L20-40#src/a/b.ts:L20-999#')" "ANCHOR"
assert_case "MODIFY row with no anchor literal" \
  "$(mutate anchor_missing 's#`export function handleConnect(`#—#')" "ANCHOR"

# --- TESTNAME ---
assert_case "test path with no :: test name" \
  "$(mutate testname_bare 's# :: `handles a connect event` — asserts the handler runs on connect (happy)##')" \
  "TESTNAME"
assert_case "test plan naming no test file at all" \
  "$(replace_section_body testname_none '### Test plan' 'The existing suite must stay green.')" \
  "TESTNAME"

# --- STEPS ---
assert_case "steps not numbered contiguously" \
  "$(mutate steps_gap 's|^3\. Edit|5. Edit|')" "STEPS"
run_check "$(mutate steps_paths 's|Append the handler in `src/registry.ts`|Append the handler in `src/other.ts`|')"
assert_eq "path swap in a step fires STEPS twice: unplanned edit and forgotten step" "1|STEPS|2" \
  "$RC|$(codes_of)|$(count_of STEPS)"

# --- HEDGE ---
assert_case "hedge word delegates the decision" \
  "$(mutate hedge_word 's|^Deliver the connect handler|Optionally deliver the connect handler|')" "HEDGE"
assert_case "hedge phrase pointing at a convention instead of a sibling" \
  "$(mutate hedge_phrase 's|from the \*Mirror\* sibling|following the alerts pattern|')" "HEDGE"

# --- suppression -------------------------------------------------------------
assert_case "inline #conformance-ok suppresses that code on that line" \
  "$(mutate ok_hedge \
     's|^Deliver the connect handler|Optionally deliver the connect handler <!-- #conformance-ok:HEDGE -->|')" ""
assert_case "suppression is per code: a different code on the same line still fires" \
  "$(mutate ok_wrong_code \
     's|^Deliver the connect handler|Optionally deliver the connect handler <!-- #conformance-ok:PATH -->|')" \
  "HEDGE"
assert_case "suppression works on a table row" \
  "$(mutate ok_path 's|src/a/new.ts|src/a/*.ts|g' \
     's|Holds the new handler.|Holds the new handler. <!-- #conformance-ok:PATH -->|')" ""

# --- misuse ------------------------------------------------------------------
set +e
OUT="$(bash "$CHECK" "$REPO" 2>&1)"; RC=$?
set -e
assert_eq "too few arguments exits 2, not 0" "2" "$RC"
set +e
OUT="$(bash "$CHECK" "$REPO" "$WORK/nope.md" 2>&1)"; RC=$?
set -e
assert_eq "unreadable brief exits 2, not 0" "2" "$RC"
set +e
OUT="$(bash "$CHECK" "$WORK" "$WORK/clean.md" 2>&1)"; RC=$?
set -e
assert_eq "repo root that is not a git work tree exits 2" "2" "$RC"

if (( FAILED )); then
  echo "FAILED"
  exit 1
fi
echo "All tests passed."
