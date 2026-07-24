---
name: work-next-issue
description: >-
  Work a batch of GitHub issues end to end with zero mid-run questions: select N
  by milestone/priority, research via subagents, post plans on the issues,
  implement test-first, verify independently, and merge to dev.
when_to_use: >-
  Manual only: /work-next-issue then plain English (e.g. "the 3 critical bugs in
  v2") or [N] [#issue ...]. Creates branches, posts issue comments, and merges to
  dev, so it is never model-invoked.
argument-hint: "plain English, or [N] [#issue ...] (milestone/priority/label understood)"
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Task, WebFetch, WebSearch, TodoWrite
disallowed-tools: AskUserQuestion
---

# Work the next N GitHub issues

Arguments: $ARGUMENTS

Preloaded environment:

* gh auth: !`gh auth status 2>&1 | head -4`
* Repo: !`gh repo view --json nameWithOwner -q .nameWithOwner 2>&1`
* Tooling: !`missing=""; for c in gh jq git; do command -v "$c" >/dev/null 2>&1 || missing="$missing $c"; done; [ -z "$missing" ] && echo "gh, jq, git all present" || echo "MISSING:$missing"`

One run takes a batch of N issues zero to hero: select → research (subagents) → one Master Plan → per-issue plans posted on GitHub → implement test-first (one subagent per issue) → verify independently → merge to `dev`.

## Prerequisites

* A git repo with a GitHub `origin` remote, and the `gh`, `jq`, and `git` CLIs on `PATH` (the `jq` dependency is what `scripts/select_batch.sh` uses to build the batch). If the preloaded Tooling line reports anything `MISSING`, that is a repo-level hard stop — report it and stop before touching any issue.
* This skill assumes this machine's engineering harness is installed: the git policy in `rules/CLAUDE_global.md` (`main` production, `dev` integration) and the loop-until-done `Stop` hook (`~/.claude/hooks/loop-until-done.sh`). Where a step below folds in that harness (git flow in Step 2, attestation in Step 6), it degrades gracefully when a piece is absent — the note on each step says how.

This skill's contract supersedes the general "ask when ambiguous" rule in this machine's global instructions (`~/.claude/CLAUDE.md`): a skill's explicit procedure is the more specific instruction for its own run. Ambiguity here is resolved by `references/decision-rules.md`, never by asking.

## Operating contract

* **Zero mid-run questions.** All thinking happens in the Master Plan; execution is mechanical. Ambiguity is resolved by `references/decision-rules.md` and recorded as a numbered assumption — never asked. `AskUserQuestion` is blocked for the run via `disallowed-tools`.
* **The repo is a literal.** Resolve `owner/repo` once from the preloaded environment above, then substitute the literal string into every command and every subagent prompt. Never rely on a shell variable — subagents start fresh shells and don't inherit it.
* **User interjections don't reopen questions.** Tool grants/blocks reset with any new user message. If the user interjects mid-run, reply briefly, never use it to ask anything, and resume the plan.
* **State lives on GitHub.** If context is compacted, do not reconstruct from memory: re-read the canonical Master Plan comment (Step 4) and per-issue comments (`gh issue view <n> --comments`), then resume from the checklist state.
* **This machine's loop-until-done gate, when installed, is active.** A `Stop` hook (`~/.claude/hooks/loop-until-done.sh`) blocks the turn from ending once real work (commits) has happened this session, until tests/lint are clean, everything is committed and pushed, and `.claude/.done` is attested — or `.claude/.blocked` is written. Step 6 folds this attestation in; don't skip it or the turn will hang blocked. If the hook is not installed, Step 6's attestation is a no-op and is skipped.

## Hard stops (failures, not questions)

* `gh` unauthenticated, repo unresolvable, or the Tooling line reports a `MISSING` CLI (`gh`/`jq`/`git`) — see preloaded environment → report it and stop. No work occurred, so nothing needs attesting.
* Selection returns no eligible issues → say so and stop. Never invent work.
* Per issue: unimplementable as written (references nonexistent code, self-contradictory, needs credentials/infra the environment lacks), or 3 full verification cycles fail with no progress → post findings on the issue, mark it skipped, remove its `in-progress` label, keep `dev` clean, continue the batch.
* Whole run: if a repo-level failure makes every remaining issue impossible, stop the batch early, write `.claude/.blocked` at the repo root with 1-5 lines on what's blocked and what the user must do, and repeat the same note in the final reply.

## Step 1 — Select and claim the batch

1. `bash "${CLAUDE_SKILL_DIR}/scripts/setup_labels.sh" <owner/repo>` (idempotent — creates `priority:*`, `in-progress`, `awaiting-release` labels if missing).
2. **Interpret the request into selector flags.** `$ARGUMENTS` is free-form — it may be empty, a bare count, explicit `#numbers`, or a sentence like "the 3 critical bugs in the v2 milestone." The selector script parses flags, never prose, so translate the request here in this context — by the decision rules, never by asking:
   * a count ("3", "a couple", "the top five") → the positional `N`
   * explicit issue references ("#42", "issue 42 and 43") → `#42 #43`
   * a named milestone ("v2 milestone", "the 1.0 release") → `--milestone "<exact title>"`, matched against `gh api repos/<owner/repo>/milestones --jq '.[].title'`
   * a priority ("critical", "high priority") → `--priority <critical|high|medium|low>` (a floor: that level and everything more urgent)
   * an issue type or label ("bugs", "docs") → `--label <name>` for each, matched against an existing repo label (`gh label list`); if nothing matches, drop the filter and record it rather than inventing a label

   Record every word→flag mapping as a numbered assumption for the Master Plan, citing Rule 1 (the request text wins). Empty `$ARGUMENTS` → no flags, the default batch.
3. `bash "${CLAUDE_SKILL_DIR}/scripts/select_batch.sh" <owner/repo> <the flags you derived>` → JSON with `n`, `filters` (echoing what you passed — confirm it matches your intent), `assumptions`, and the ordered `batch`. Selection: explicit `#<n>` issues first (even if assigned/in-progress, filters don't apply to them), then — among open issues that are unassigned, not `in-progress`, and match the priority floor and required labels — the nearest-due open milestone by priority (`critical→high→medium→low`, then lowest number), continuing through milestones, then priority across all open issues. With `--milestone` set, only that milestone is swept (no all-open fallback). N is rounded up to a multiple of 5 (default 10).
4. **Claim immediately:** `gh issue edit <n> --repo <owner/repo> --add-label in-progress` for every selected issue — this is what stops a concurrent run from picking up the same work.
5. Report the batch as a table (#, title, milestone, priority, order), carry the script's `assumptions` into the Master Plan, and proceed without waiting for acknowledgment.

## Step 2 — Baseline on clean `dev`

* Create `dev` from the default branch if it doesn't exist (per this machine's git policy in `rules/CLAUDE_global.md`: `main`/`master` is production, `dev` is integration, working branches start from and merge back into `dev`); sync it.
* Detect the toolchain once: test runner, formatter, linter, type checker, and their exact invocations in this repo (`package.json`, `Makefile`, `pyproject.toml`, CI config, or an executable `.claude/verify.sh` / `scripts/verify.sh` if present — the same script the loop-until-done gate itself runs). If a run recipe exists at `.claude/skills/run-*/`, read it — it documents how to build and launch the app.
* Run the full verification suite once on clean `dev` and record every pre-existing failure. This baseline goes in the Master Plan. Pass criterion for the whole run: **no new failures versus this baseline** — the batch is not responsible for making a previously red suite green.

## Step 3 — Research via subagents

* Dispatch one Explore subagent per issue (or per cluster of related issues) via the Task tool, in parallel. Each prompt must inline: the literal `owner/repo`, the issue number, an instruction to read the issue and all comments (`gh issue view <n> --repo <owner/repo> --comments`), the full content of `references/decision-rules.md`, and the required return format: one-paragraph problem restatement; root cause and affected files with real paths and line references; proposed approach; ambiguities pre-resolved with the decision rule number cited.
* For any third-party API or SDK, verify against the installed version's official docs, not memory.
* In the main context, build the batch view: a conflict/dependency map (which issues touch the same files, which must precede which — Rule 8) and the final execution order.

## Step 4 — Master Plan (before any code)

* Write the complete plan for the whole batch using `references/master-plan-template.md`: every remaining action across all N issues, detailed enough that execution requires no further decisions. Anything that would have been a question appears as a numbered assumption citing its decision rule.
* Post the full Master Plan **once, as a single comment on the first issue in execution order**. That comment is the canonical plan — recovery after compaction re-reads this one comment, not N scattered ones.
* Post each issue's slice on that issue (format: `references/comment-templates.md`), linking back to the canonical plan comment. Then continue directly into execution.

## Step 5 — Execute: one implementation subagent per issue, strict order

For each issue, in planned order:

1. **Branch off current `dev`** (so each issue builds on the batch's prior merges): `git checkout dev && git pull && git checkout -b feature/issue-<n>-<slug>`.
2. **Dispatch a general-purpose subagent** via the Task tool to implement. Its prompt must inline: the literal repo, the branch name, the issue's posted plan comment (fetch it and paste it), the full decision rules, the toolchain commands, the baseline failures, and the TDD contract — write the plan's failing tests first, then implement the numbered steps until they pass; cover happy path, edge cases, and failure paths; prefer integration tests over mocks; never skip a test, suppress a warning, disable a lint rule, or loosen a type to get green; no scope beyond the issue; no questions.
3. **Verify in the main context — never take the subagent's word.** Run the full verification suite yourself (tests, formatter, linter, type checker), compare against the baseline, and drive the behavior end to end: the run recipe if one exists, or for libraries/CLIs a realistic invocation of the changed interface.
4. **Ship:** commit per the plan's commit plan, push the branch, post the closing comment (`references/comment-templates.md`), then `git checkout dev && git merge --no-ff feature/issue-<n>-<slug> && git push`, then swap labels: `gh issue edit <n> --remove-label in-progress --add-label awaiting-release`. Do **not** close the issue — closing happens at promotion to `main`, which only occurs on explicit user request. Tick the batch checklist.
5. **On failure** (per hard stops): comment findings, mark skipped, remove `in-progress`, leave `dev` clean (never merge partial work), continue with the next issue.

## Step 6 — Report and attest completion

* Per issue as each finishes, and a batch report at the end — formats in `references/comment-templates.md`. Report only validation that actually ran, with its real output. Include the shortfall note if fewer than N were eligible and the combined follow-ups deferred by Rules 6–7.
* **Attest for the loop-until-done gate** *(only when this machine's Stop hook is installed — skip this bullet entirely if `~/.claude/hooks/loop-until-done.sh` does not exist, since writing `.claude/.done` into a repo with no gate just litters a stray file).* Once the batch report is posted and `dev` is pushed: if any commit happened this session, create `.claude/.done` at the repo root before ending the turn — the Stop hook re-verifies tests/lint/push independently and revokes `.done`, blocking again, if anything is actually unclean, so this is a request-to-verify, not a shortcut. If the whole run ended via the repo-level hard stop with no commits made, no attestation is needed.
* The run ends at `dev`. Never commit to `main`/`master` directly, never merge a working branch into it, never force-push a shared branch, and never promote to `main` unless the user explicitly asked in this run's instructions or a later message.

## Guardrails

* One batch per run; one issue at a time; never interleave two issues' changes on one branch.
* Never fabricate results — a test "passed" only if it was run and observed passing in the main context.
* The plan is binding. Deviations must be minimal, forced by reality, and reported in the plan-vs-actual sections.
* A failed issue never poisons the batch; skipped work stays off `dev`.
* Leave files the batch didn't need untouched.
