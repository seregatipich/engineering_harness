# GitHub comment templates

Post comments with a temp file: `gh issue comment <n> --repo <owner/repo> --body-file <tmpfile>`. There is never an "open questions" section — anything that would have been a question appears as a resolved assumption citing its decision rule.

## 1. Per-issue plan comment (Step 4)

```
## Plan (batch run <date>, issue <k> of <total>)

Canonical Master Plan: <link to the canonical plan comment>

### Research
<one-paragraph restatement of the problem>
<root cause>

### Affected files
- `path/to/file.ext:L10-L42` — <why>

### Assumptions
1. <assumption> (Rule <r>)

### Test plan (written before code)
- `path/to/test_file` :: <test name> — asserts <what> (happy path | edge | failure)

### Implementation steps
1. <file(s)> — <change> → makes <test(s)> pass

### Verification
- <exact commands>
- End to end: <how the behavior will be driven>

### Scheduling note
Bucket: <parallel group | pipeline after #<m> | serialized — overlaps #<m> on <files>>. Merge position <k> of <total>.
```

## 2. Closing comment (Step 5, as each issue finishes)

```
## Done — merged to dev

- Branch: `feature/issue-<n>-<slug>` (merged --no-ff into dev)
- What changed: <succinct summary, files touched>
- Plan vs actual: <"as planned" | deviations and why>
- Validation run (real output, only what actually ran):
  - `<test command>` → <result summary>
  - `<lint / format / typecheck commands>` → <result summary>
  - New failures vs baseline: none | <list>
- End-to-end check: <what was driven and observed>
- Follow-ups deferred (Rules 6–7): <list or "none">

Issue stays open with `awaiting-release` until promotion to main.
```

## 3. Skip comment (hard stop on one issue)

```
## Skipped this run

Reason: <unimplementable as written: what was found | 3 failed verification cycles: what was tried | unprovisionable infra <item>: provisioning attempted via <what was tried>, failed because <why>; unblock with `<commands>` | pipelined behind skipped #<n>: this issue builds on its change>
State: no changes merged; dev is clean; branch <deleted | left at <ref> for reference>
Suggested next step for a human: <concrete pointer>
```

## 4. Batch report (to the user, end of run)

```
Batch progress:
- [x] #<n1> — plan posted / tests written / implemented / verified / merged to dev
- [ ] #<n2> — skipped (<reason>)

| # | Title | Status | Branch | Tests added | Deviations |
|---|-------|--------|--------|-------------|------------|

Environment: <"already current" | provisioned: <items>>; unprovisionable: <"none" | <items> — unblock with `<commands>`>
Shortfall: <"none" | a cap was given but only X eligible issues matched — why>
Follow-ups (combined, Rules 6–7): <list>
Run ends at dev. Promotion to main only on explicit request.
```
