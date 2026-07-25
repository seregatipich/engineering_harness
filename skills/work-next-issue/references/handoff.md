# The Brief — the one artifact the executor runs

Each issue gets exactly **one** executable document, the **Brief**. It is posted as that issue's plan
comment, and the implementation subagent's prompt is that comment fetched back verbatim plus a generated
machine block. Nothing else is authored.

That constraint is the point. When the posted comment and the dispatch prompt are two different documents,
the richer one lives only in the orchestrator's context: compaction loses it, a re-dispatch can't reproduce
it, and the skill's own "state lives on GitHub" recovery contract restores a document that isn't the one
execution used. One artifact, one source of truth.

```
brief=$(gh api "/repos/<owner/repo>/issues/comments/<comment-id>" --jq .body)
machine=$(bash "${CLAUDE_SKILL_DIR}/scripts/agent_env.sh" <n> <worktree-abs-path>)
# dispatch prompt = "$brief" then "$machine"
```

Record each Brief's comment id at post time — that id is how you re-fetch it, and how you correct it.

**Nothing may appear in the dispatch prompt that is absent from the comment, except the machine block.**
The machine block is the only exception because it carries host paths, dev credentials and per-issue
resource slots, which must never be published to an issue that may be public. It is regenerated, never
remembered, so it never needs storing anywhere.

**To tell the executor something the Brief lacks:** PATCH the comment, re-fetch, dispatch. Never append a
correction to the prompt — that recreates the split this design exists to close.

## Writing the Brief

The executor may be a cheaper model than the one writing this. It cannot re-derive the codebase, and it
will not doubt a confident statement. So the Brief transcribes rather than describes, and every claim about
a gate, guard or generator carries the command that proved it (see `master-plan-template.md`, *Verified
facts*). A confidently wrong instruction costs far more than a missing one, because the executor has no
licence to disbelieve it.

Use these headings, in this order. `scripts/check_brief.sh` refuses to let the run dispatch without them.

```markdown
## Brief — #<n> <title> (issue <k> of <total>, merge position <k>)

Canonical Master Plan: <link to the canonical plan comment>

### Objective and acceptance criteria
<one paragraph: what "done" means>
<the acceptance criteria, quoted verbatim from the issue or spec — never paraphrased>

### Where things are
| path | action | read range | anchor literal | change | mirror |
|---|---|---|---|---|---|
| `src/a/b.ts` | MODIFY | `src/a/b.ts:L120-160` | `export function handleConnect(` | <one sentence> | `src/a/c.ts:L40-88` |
| `src/a/new.ts` | CREATE | — | — | <one sentence> | `src/a/c.ts` |
| `src/registry.ts` | REGISTER | `src/registry.ts:L12-30` | `HANDLERS = [` | append `<literal>` | — |

### Mirror
<per new file and per new test: one sibling path plus <= 40 quoted lines>

### Contracts (bind exactly)
<every identifier that appears in more than one file, as literal code — types, function signatures,
 enum members, event names, response shapes, audit action strings, test ids>

### Repo invariants
<rule -> the test that enforces it -> the files it binds; each marked MUST-PASS-UNMODIFIED>

### Do NOT touch
<anti-targets and near-misses, one line each>

### Test plan
- `path/to/test_file` :: `<literal test name>` — asserts <what> (happy | edge | failure)

### Docs to update
<exact file + heading + row format + whether that list is exhaustive, with the evidence>

### Implementation steps
1. <cites rows from *Where things are*> — <the change> -> makes `<test name>` pass
   verify: `<command>` -> expect `<observable>`
   if it doesn't match: <what to do>, then record PLAN-WRONG

### Finish checklist
<the literal verification command, then the allowed baseline failures BY TEST NAME>

### Commit plan
<intended logical commits and their messages>

### Assumptions
1. <assumption> (Rule <r>)

### Return contract
<the envelope below>
```

### What each section is for

**Where things are** is the highest-leverage block in the whole document, so it gets two anchor columns
that do different jobs:

* the **read range** (`path:L120-160`) is the Read hint. Where a prompt gave a range, the executor opened
  the file in one call; where it gave only a filename, it cost three to ten. An oversized whole-file Read
  can also return a silently partial view, so a path without a range is not merely slower, it is unreliable.
* the **anchor literal** is a verbatim substring that occurs exactly once in the file — what an Edit binds
  to. Line numbers rot: in a serialized batch, `dev` moves under every issue after the first, so by the
  fourth Brief the ranges written at planning time are stale. The literal survives. Give both, and expect
  the executor to trust the literal over the range when they disagree.

**Mirror** beats describing a convention. Naming the sibling to copy — and quoting it — turns invention
into transcription. "Model it on the alerts feature" is not compliant; the path plus the lines is.

**Repo invariants** are the rules a change can silently break: parity between two registries, a guard test
that enumerates every member of a list, an isolation rule about how test data is scoped. Mark them
MUST-PASS-UNMODIFIED, because the cheap way out of a failing guard is to weaken its assertion, and that is
exactly what the prohibition list exists to prevent.

**Do NOT touch** earns its place: every negative instruction in the analysed run was obeyed, each cost one
line, and each closed off an expensive wrong path before it opened. Scope creep is the usual cause of a
300-turn implementation.

**Finish checklist** names the allowed baseline failures by exact test file. "Some tests may fail" makes an
executor chase ambient red or, worse, revert good work believing it caused the failure. The named list
means it never starts.

### Steps must be verifiable and falsifiable

Every step carries a **verify** command, its expected observable, and what to do when reality disagrees.
This is what makes a hyper-detailed plan safe rather than brittle: the detail tells the executor what to do,
and the check tells it when the detail is wrong.

Never delegate a decision. `optionally`, `if unclear`, `A or B`, `search for X and decide` — each of these
turns one plan into two different deliverables and makes the orchestrator's verification non-reproducible.
Decide it now, by the decision rules, and record it as a numbered assumption; or put it in *Out of scope*.

## The machine block

Generated by `scripts/agent_env.sh <n> <worktree>`; appended to the prompt, never posted. It carries the
literal first command, the ordered bootstrap, the per-issue resource slot (test database, cache index,
ports, scratchpad path), and this reminder, which matters because every Bash call starts a fresh shell:

```
set -a; . <abs path to env file>; set +a
```

Prefix every later command with it. The env file lives inside the worktree's `.git/` directory, so it is
per-worktree, never committed, and never shared with a sibling subagent running another issue concurrently.

## The return envelope

The executor's final message is data for the orchestrator, not a human summary. Requiring this shape is what
lets Step 5's verification be a *check* rather than a re-derivation.

```
STATUS: COMPLETE | STOPPED_EARLY | BLOCKED
BRANCH: feature/issue-<n>-<slug>
COMMITS: <git log --oneline <base>..HEAD>
FILES: <git diff --name-only <base>..HEAD>
STEPS: <each numbered step: done | skipped, with why>
TESTS ADDED: <file :: literal test name, per test>
VERIFICATION: <each command, its real exit code, and the counts it printed>
RED-BEFORE: <the evidence: the test run before the implementation file existed>
DEVIATIONS: <what differed from the Brief and why> | none
PLAN-WRONG: <see below> | none
UNVERIFIABLE: <what could not be checked here, and why> | none
ASSUMPTIONS: <numbered, each citing a decision rule>
```

Report only what actually ran, with its real output. A test "passed" only if it was observed passing.

### PLAN-WRONG

When observed reality contradicts something the Brief states as fact, the executor does not guess and does
not push on. It stops that step, records the contradiction, and continues with the steps that don't depend
on it:

```
PLAN-WRONG step=<k> claim="<the Brief's text, quoted>" observed=<command> -> <output head>
```

A `PLAN-WRONG` is only valid with both the quote and the pasted output — that bar is what stops it becoming
a general-purpose excuse. The orchestrator folds every one into the run ledger and PATCHes the affected
Briefs before the next dispatch, so a correction discovered on issue 2 reaches issue 5 rather than living
in one context until compaction eats it.

## The executor's standing rules

Inline these in every Brief's *Return contract* section — they held under real pressure at every point where
a cheap escape was available and visible:

* Never skip, disable or `.skip` a test, suppress a warning, disable a lint rule, or loosen a type to get
  green. Fix the cause.
* Never fabricate a result. If something cannot run here, say so and say why.
* When an acceptance criterion cannot be exercised in this environment: write the check completely, guard it
  so it only runs where it can, document it as **run-deferred** — and do not fake a pass. All three parts.
* Stay inside the issue. Adjacent bugs and refactors go in the return as follow-ups, not in the diff.
* You are the executor. Execute the numbered steps yourself; do not dispatch subagents.
* Never push, never merge, never touch the integration branch. Commit to your feature branch only.
