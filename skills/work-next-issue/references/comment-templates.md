# GitHub comment templates

Post comments with a temp file: `gh issue comment <n> --repo <owner/repo> --body-file <tmpfile>`.
There is never an "open questions" section — anything that would have been a question appears as a resolved
assumption citing its decision rule.

## 1. The per-issue plan comment

This is the **Brief**, and its template lives in `references/handoff.md`. It is not summarised here because
it is not a summary: it is the document the executor runs, fetched back verbatim as the dispatch prompt.
Post it, record its comment id, and gate it on `scripts/check_brief.sh` before dispatching.

## 2. Closing comment (as each issue finishes)

```
## Done — merged to <integration branch>

- Branch: `feature/issue-<n>-<slug>` (merged --no-ff)
- Integration SHA: `<sha>`
- What changed: <succinct summary, files touched>
- Brief vs actual: <"as briefed" | deviations and why>
- Validation run (real output, only what actually ran):
  - `<VERIFY path>` → <result summary>
  - New failures vs baseline: none | <list>
- End-to-end check: <what was driven and observed>
- Plan corrections found (PLAN-WRONG): <list, or "none">
- Follow-ups deferred (Rules 6–7): <list or "none">

Issue stays open with `<awaiting-release role label>` until promotion.
```

## 3. Skip comment (hard stop on one issue)

```
## Skipped this run

Reason: <unimplementable as written: what was found | 3 failed verification cycles: what was tried | unprovisionable infra <item>: provisioning attempted via <what was tried>, failed because <why>; unblock with `<commands>` | pipelined behind skipped #<n>: this issue builds on its change>
State: no changes merged; the integration branch is clean; branch <deleted | left at <ref> for reference>
Suggested next step for a human: <concrete pointer>
```

## 4. Batch report (to the user, end of run)

```
Batch progress:
- [x] #<n1> — brief posted / tests written / implemented / verified / merged
- [ ] #<n2> — skipped (<reason>)

| # | Title | Status | Branch | Tests added | Deviations |
|---|-------|--------|--------|-------------|------------|

Verification: `<VERIFY path>` — <what it runs>
Environment: <"already current" | provisioned: <items>>; unprovisionable: <"none" | <items> — unblock with `<commands>`>
Label roles resolved: <role → the repo's actual label, or "no match — guard inert">
Shortfall: <"none" | a cap was given but only X eligible issues matched — why>
Ledger: <corrections discovered mid-run and which Briefs were patched, or "none">
Follow-ups (combined, Rules 6–7): <list>
Run ends at <integration branch>. Promotion to the default branch only on explicit request.
```

## 5. Completion evidence (promotion only)

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
