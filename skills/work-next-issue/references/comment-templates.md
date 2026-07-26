# GitHub comment templates

Post comments with a temp file: `gh issue comment <n> --repo <owner/repo> --body-file <tmpfile>`.
There is never an "open questions" section — anything that would have been a question appears as a resolved
assumption citing its decision rule.

## 1. The per-issue plan comment

This is the **Brief**, and its template lives in `references/handoff.md`. It is not summarised here because
it is not a summary: it is the document the executor runs, fetched back verbatim as the dispatch prompt.
Post it, record its comment id, and gate it on `scripts/check_brief.sh` before dispatching.

## 2. Progress report (posted by the executor, per checkpoint)

The executor posts one of these on its issue at every checkpoint its Brief's *Progress reporting* section
names: **red** (tests written, observed failing), **green** (implementation complete, suite observed
passing), **final** (self-report before returning), and immediately on any `PLAN-WRONG` or blocker.
Evidence is real output only — a checkpoint that reports what did not run is a fabrication.

```
## Progress — <red | green | final | plan-wrong | blocked>

- Branch: `feature/issue-<n>-<slug>` @ `<short sha>`
- Checklist: <k>/<m> steps done — <the boxes closed since the last report, by step number>
- Evidence: `<command>` → <exit code and the counts/lines that matter>
- <plan-wrong/blocked only> Detail: <the quoted claim and observed output | what is blocked and why>
- Next: <the next step by number, or "returning">
```

## 3. Implementation report (as each issue merges — the final, structured record)

Posted by the orchestrator after its own verification, at merge. This is the accountability document for
the issue: everything below is filled from observed state, never from the executor's word alone.

```
## Implementation report — merged to <integration branch>

### Summary
<what was delivered, in 2-4 sentences: the problem, the approach, the outcome>

### What changed
- Branch: `feature/issue-<n>-<slug>` (merged --no-ff), integration SHA `<sha>`
- Files: <from `git diff --name-only`, grouped created / modified>
- Commits: <the logical commits, one line each>

### Checklist state
<the Brief's implementation steps, every box ticked or its skip explained>

### Tests
- Test matrix outcome: <each row — the named tests that now cover it, or the N/A reason re-confirmed>
- Tests added: <file :: literal test name, per test>
- Red-before evidence: <the failing run that preceded the implementation>

### Verification (real output, only what actually ran)
- `<VERIFY path>` → <result summary>
- New failures vs baseline: none | <list>
- End-to-end check: <what was driven and observed>

### Deviations and plan corrections
- Brief vs actual: <"as briefed" | each deviation and why>
- PLAN-WRONG: <list, or "none">

### Accountability trail
- Brief: <comment URL> · Progress reports: <red URL>, <green URL>, <final URL>

### Follow-ups deferred (Rules 6–7)
<list, or "none">

Issue stays open with `<awaiting-release role label>` until promotion.
```

## 4. Skip comment (hard stop on one issue)

```
## Skipped this run

Reason: <unimplementable as written: what was found | 3 failed verification cycles: what was tried | unprovisionable infra <item>: provisioning attempted via <what was tried>, failed because <why>; unblock with `<commands>` | pipelined behind skipped #<n>: this issue builds on its change>
State: no changes merged; the integration branch is clean; branch <deleted | left at <ref> for reference>
Suggested next step for a human: <concrete pointer>
```

## 5. Batch report (to the user, end of run)

```
Batch progress:
- [x] #<n1> — brief posted / tests written / implemented / verified / merged
- [ ] #<n2> — skipped (<reason>)

| # | Title | Status | Branch | Tests added | Deviations |
|---|-------|--------|--------|-------------|------------|

Verification: `<VERIFY path>` — <what it runs>
Environment: <"already current" | provisioned: <items>>; unprovisionable: <"none" | <items> — unblock with `<commands>`>
Label roles resolved: <role → the repo's actual label, or "no match — guard inert">
Shortfall: <"none" | the user named a count but only X eligible issues matched — why>
Ledger: <corrections discovered mid-run and which Briefs were patched, or "none">
Follow-ups (combined, Rules 6–7): <list>
Run ends at <integration branch>. Promotion to the default branch only on explicit request.
```

## 6. Completion evidence (promotion only)

Posted at promotion, per `references/promotion.md`. Only on issues whose acceptance criteria were **fully
exercised**; an issue with a deferred criterion gets a progress comment naming the criterion instead, and
stays open.

```
## Verified complete

- Delivered on <integration branch> and promoted to `<default>` (`<sha>`).
- CI: <run link> — all jobs success. Deploy: <run link> — success.
- Quality gates at `<sha>`: `<VERIFY path>` → <real output>
- Acceptance criteria: <each, with the evidence that exercised it>
- Verification provenance: <who/what ran it, when, and how>
- Risks, skips, limitations: <honest list, or "none">
```
