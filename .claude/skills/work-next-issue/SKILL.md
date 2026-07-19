---
name: work-next-issue
description: Pull the next GitHub issue by milestone or priority, research it against the codebase and docs, post the findings as a comment on the issue, then implement it test-first and verify everything passes. Use when the user wants Claude to pick up tracked GitHub work and take it to a tested, verified state. Triggers include "take the next issue", "work the milestone", "pick up an issue and write tests".
---

# Work the next GitHub issue

Portable skill. Run it inside **any** git repository that has a GitHub `origin` and an
authenticated `gh` CLI — it detects the current repository itself, so nothing here is
tied to a specific repo. One run handles exactly one issue end to end: select it,
document the research on the issue, and deliver tested, verified work on a branch.

## Prerequisites

Verify before doing anything else; stop and tell the user if any fails:

- `gh auth status` succeeds.
- `gh repo view --json nameWithOwner -q .nameWithOwner` returns the target repo. Store it as `$REPO`.
- Priority is expressed with labels `priority:critical | priority:high | priority:medium | priority:low`.
  If none exist, create them once (see Selection → bootstrap).

## 1. Select the issue

Selection order — take the **first** match:

1. **Nearest open milestone** by due date that still has open issues:
   ```
   gh api "repos/$REPO/milestones" \
     --jq 'map(select(.state=="open" and .open_issues>0)) | sort_by(.due_on // "9999-12-31") | .[0] | {number,title}'
   ```
   Within that milestone, order **open, unassigned** issues by priority
   (`critical` → `high` → `medium` → `low`, then lowest issue number):
   ```
   gh issue list --repo "$REPO" --milestone "<title>" --state open \
     --search "no:assignee" --json number,title,labels
   ```
2. If no milestone qualifies, fall back to **priority across all open issues** (same ordering).
3. Skip issues labeled `in-progress` or already assigned, unless the user named one explicitly.

Report the chosen issue (`#<n> — <title>`, milestone, priority) to the user, then proceed.
If selection is empty, say so and stop — do not invent work.

**Bootstrap priority labels (only if missing):**
```
gh label create "priority:critical" -c b60205 -R "$REPO" 2>/dev/null || true
gh label create "priority:high"     -c d93f0b -R "$REPO" 2>/dev/null || true
gh label create "priority:medium"   -c fbca04 -R "$REPO" 2>/dev/null || true
gh label create "priority:low"      -c 0e8a16 -R "$REPO" 2>/dev/null || true
```

## 2. Research

- Read the issue and every comment: `gh issue view <n> --repo "$REPO" --comments`.
- Explore the codebase for each file and behavior the issue touches (Explore/Grep/Read).
- For any third-party API or SDK, check the **installed version's** official docs, not memory.
- Produce, concretely:
  - a one-paragraph restatement of the problem,
  - root cause / affected files with real paths and line references,
  - the proposed approach,
  - an explicit **test plan**: happy path, edge cases, failure paths,
  - open questions that could change the approach.

## 3. Document on the issue

Keep the research artifact on GitHub, not in a repo file. Write it to a temp file and post:
```
gh issue comment <n> --repo "$REPO" --body-file <tmpfile>
```
Structure the comment: **Research**, **Affected files**, **Approach**, **Test plan**,
**Open questions**. If open questions genuinely block the design, stop here and ask the
user rather than guessing.

## 4. Implement, test-first

- Create the branch off the integration branch (create `dev` from the default branch if it
  does not exist): `feature/issue-<n>-<short-slug>`.
- If a TDD skill/workflow is available in the environment, use it. Otherwise follow TDD directly:
  write the failing tests from the test plan **first**, then implement until they pass.
  Cover the happy path, edge cases, and failure paths. Prefer integration tests over mocks.
- Run the full suite: tests, formatter, linter, type checker. Fix everything related to the
  change. Never skip a test, suppress a warning, disable a lint rule, or loosen a type to get
  green — fix the cause or stop and explain why you cannot.
- Verify the behavior **end to end** by driving the real flow, not only via tests. If a
  `verify` skill exists, use it.

## 5. Report back and integrate

- Commit each logical chunk with a descriptive message and push the branch.
- Post a closing comment on the issue: what changed, the branch name, the **exact** commands
  run (tests/lint/types) with their real output, and how the behavior was verified. Report only
  validation that actually ran.
- Merge `feature → dev` and push `dev`. Promote `dev → main` only once the user confirms the
  issue is fully done.
- Never commit to `main`/`master` directly, never merge a working branch into it directly, and
  never force-push a shared branch.

## Guardrails

- **One issue per run.** Finish or hand off cleanly before selecting another.
- **Never fabricate results.** Only claim a test passed if you ran it and saw it pass.
- **Ambiguity stops the run.** If the issue needs a product decision, post the open questions
  as a comment and stop instead of guessing.
- Leave files you did not create untouched unless the issue requires changing them.
