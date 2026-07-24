---
name: work-next-issue
description: >-
  Work a scoped set of GitHub issues end to end with zero mid-run questions:
  resolve the scope from the request (issues, milestone, priority, labels),
  provision whatever the verification environment is missing (deps, env files,
  services, toolchains) instead of stopping at the gap, research via subagents,
  partition the work by dependencies and file overlap, post plans on the
  issues, implement test-first (parallel worktrees where the partition allows),
  verify independently, and merge to dev serially.
when_to_use: >-
  Manual only: /work-next-issue then plain English (e.g. "the critical bugs in
  v2", "do 3 of them", "#42 #43"). Creates branches, posts issue comments, and
  merges to dev, so it is never model-invoked.
argument-hint: "plain English (milestone/priority/label/count understood), or [#issue ...] [count]"
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent, WebFetch, WebSearch
disallowed-tools: AskUserQuestion
---

# Work a scoped set of GitHub issues

Arguments: $ARGUMENTS

Preloaded environment:

* gh auth: !`gh auth status 2>&1 | head -4`
* Repo: !`gh repo view --json nameWithOwner -q .nameWithOwner 2>&1`
* Tooling: !`missing=""; for c in gh jq git; do command -v "$c" >/dev/null 2>&1 || missing="$missing $c"; done; [ -z "$missing" ] && echo "gh, jq, git all present" || echo "MISSING:$missing"`

One run takes the scoped set of issues zero to hero: select → provision the environment and baseline → research (subagents) → partition (parallel / pipelined / serialized) → one Master Plan → per-issue plans posted on GitHub → implement test-first (one worktree-isolated subagent per issue, concurrent where the partition allows) → verify and merge to `dev` serially.

## Prerequisites

* A git repo with a GitHub `origin` remote, and the `gh`, `jq`, and `git` CLIs on `PATH` (the `jq` dependency is what `scripts/select_batch.sh` uses to build the batch). If the preloaded Tooling line reports anything `MISSING`, try a user-space install first (static binary into `~/.local/bin`); it is a hard stop only if that attempt fails.
* This skill assumes this machine's engineering harness is installed: the git policy in `rules/CLAUDE_global.md` (`main` production, `dev` integration) and the loop-until-done `Stop` hook (`~/.claude/hooks/loop-until-done.sh`). Where a step below folds in that harness (git flow in Step 2, attestation in Step 6), it degrades gracefully when a piece is absent — the note on each step says how.

This skill's contract supersedes the general "ask when ambiguous" rule in this machine's global instructions (`~/.claude/CLAUDE.md`): a skill's explicit procedure is the more specific instruction for its own run. Ambiguity here is resolved by `references/decision-rules.md`, never by asking.

## Operating contract

* **Zero mid-run questions.** All thinking happens in the Master Plan; execution is mechanical. Ambiguity is resolved by `references/decision-rules.md` and recorded as a numbered assumption — never asked. `AskUserQuestion` is blocked for the run via `disallowed-tools`. This covers the final message too: a run that hits a blocker still ends with the most work achievable and a factual report of what the user must do — never with a menu of options awaiting a choice.
* **The repo is a literal.** Resolve `owner/repo` once from the preloaded environment above, then substitute the literal string into every command and every subagent prompt. Never rely on a shell variable — subagents start fresh shells and don't inherit it.
* **User interjections don't reopen questions.** Tool grants/blocks reset with any new user message. If the user interjects mid-run, reply briefly, never use it to ask anything, and resume the plan.
* **State lives on GitHub.** If context is compacted, do not reconstruct from memory: re-read the canonical Master Plan comment (Step 4) and per-issue comments (`gh issue view <n> --comments`), then resume from the checklist state.
* **This machine's loop-until-done gate, when installed, is active.** A `Stop` hook (`~/.claude/hooks/loop-until-done.sh`) blocks the turn from ending once real work (commits) has happened this session, until tests/lint are clean, everything is committed and pushed, and `.claude/.done` is attested — or `.claude/.blocked` is written. Step 6 folds this attestation in; don't skip it or the turn will hang blocked. If the hook is not installed, Step 6's attestation is a no-op and is skipped.

## Hard stops (failures, not questions)

* `gh` unauthenticated, or repo unresolvable → report it and stop. A `MISSING` CLI on the Tooling line (`gh`/`jq`/`git`) → try a user-space install first (static binary into `~/.local/bin`); a hard stop only if that fails. If no work occurred, nothing needs attesting.
* Selection returns no eligible issues → say so and stop. Never invent work.
* A missing tool, dependency, service, or config file is **never by itself a hard stop** — Step 2 provisions it. Only a provisioning attempt that actually failed (Step 2's definition) can block, and it blocks only the issues that need that piece.
* Per issue: unimplementable as written (references nonexistent code, self-contradictory, needs credentials or external access that Step 2's provisioning attempts could not obtain), acceptance criteria unverifiable in every tier the environment can run, or 3 full verification cycles fail with no progress → post findings on the issue, mark it skipped, remove its `in-progress` label, keep `dev` clean, continue the batch.
* Whole run: if a repo-level failure — or Step 2 ending with no issue verifiable — makes every remaining issue impossible, stop the batch early, write `.claude/.blocked` at the repo root with 1-5 lines on what's blocked and what the user must do, and repeat the same note in the final reply. A blocker note states what was attempted, what failed, and the exact commands that unblock it — even a fully blocked run ends with a factual report, never an options menu or a question.

## Step 1 — Select and claim the batch

1. `bash "${CLAUDE_SKILL_DIR}/scripts/setup_labels.sh" <owner/repo>` (idempotent — creates `priority:*`, `in-progress`, `awaiting-release` labels if missing).
2. **Interpret the request into selector flags.** `$ARGUMENTS` is free-form — it may be empty, explicit `#numbers`, or a sentence like "the critical bugs in the v2 milestone" or "do 3 of them." The scope is the user's: work exactly what they describe, no more. The selector script parses flags, never prose, so translate the request here in this context — by the decision rules, never by asking:
   * explicit issue references ("#42", "issue 42 and 43") → `#42 #43`
   * a named milestone ("v2 milestone", "the 1.0 release") → `--milestone "<exact title>"`, matched against `gh api repos/<owner/repo>/milestones --jq '.[].title'`
   * a priority ("critical", "high priority") → `--priority <critical|high|medium|low>` (a floor: that level and everything more urgent)
   * an issue type or label ("bugs", "docs") → `--label <name>` for each, matched against an existing repo label (`gh label list`); if nothing matches, drop the filter and record it rather than inventing a label
   * an explicit count ("do 3", "a couple", "the top five") → a bare trailing number, an exact ceiling. Pass it only when the user names a quantity; there is no default. No count → work the whole scoped set. Do not turn an open-ended request ("fix the critical bugs") into a number.

   Record every word→flag mapping as a numbered assumption for the Master Plan, citing Rule 1 (the request text wins). Empty `$ARGUMENTS` → no flags: the fully unscoped default.
3. `bash "${CLAUDE_SKILL_DIR}/scripts/select_batch.sh" <owner/repo> <the flags you derived>` → JSON with `cap` (the count ceiling or `null`), `filters` (echoing what you passed — confirm it matches your intent), `assumptions`, and the ordered `batch`. Selection: explicit `#<n>` issues first (even if assigned/in-progress, filters don't apply to them), then — among open issues that are unassigned, not `in-progress`, and match the priority floor and required labels — filled by nearest-due open milestone then priority (`critical→high→medium→low`, then lowest number). Scope decides how wide that fill reaches: `--milestone` sweeps only that milestone; a priority/label filter sweeps every matching issue across the repo; a bare count sweeps the same broad way but stops at the cap; a fully unscoped run (no filter, no count, no explicit issues) takes only the nearest-due milestone that has eligible work — a bounded default, never the whole backlog. Explicit issues with no filter are worked exactly as given. A cap is a ceiling, never a target: fewer eligible issues means a smaller batch, never invented work.
4. **Claim immediately:** `gh issue edit <n> --repo <owner/repo> --add-label in-progress` for every selected issue — this is what stops a concurrent run from picking up the same work.
5. Report the batch as a table (#, title, milestone, priority, order), carry the script's `assumptions` into the Master Plan, and proceed without waiting for acknowledgment.

## Step 2 — Provision the environment, then baseline on clean `dev`

* Create `dev` from the default branch if it doesn't exist (per this machine's git policy in `rules/CLAUDE_global.md`: `main`/`master` is production, `dev` is integration, working branches start from and merge back into `dev`); sync it.

An incomplete environment is the normal starting state of a run, not an exception. A fresh clone has no installed dependencies, no `.env`, maybe no services — the run builds what it needs before it judges what it can do. Discovering a gap and reporting it as a blocker without an attempt to close it is the one failure mode this step exists to prevent.

1. **Discover what a full verification run needs.** The repo states its own requirements: README / CONTRIBUTING / AGENTS.md, the CI workflows (what CI installs and starts is the authoritative list — local verification needs the same), `docker-compose*` / devcontainer files, lockfiles, `.env.example`, setup scripts in `scripts/` or a Makefile. Turn this into a checklist: runtimes and toolchains, dependency installs, services (DB, cache), config files, provisioned test data.
2. **Probe what's present and close the gap — provisioning is the run's work, not a blocker.** Classify each item *present and current* / *present but stale* / *absent*, then act:
   * **Stale → bring it up to date:** install/refresh dependencies from the lockfile, sync `.env` against `.env.example` for new keys, pull or rebuild images, run migrations or the repo's test-DB script.
   * **Absent → set it up from zero,** preferring the repo's own bootstrap path (devcontainer, compose files, Makefile or package-script setup targets, `scripts/*.sh`) over improvised installs.
   * **Root unavailable?** Check `sudo -n true` once. Without root, use user-space routes: toolchain tarballs or version managers into `$HOME` (Go tarball, corepack/nvm), rootless container runtimes, service alternatives the repo already supports. Config files: derive `.env` from `.env.example` and docs with dev-safe values — real third-party secrets are the one thing that can never be invented.
   * **Prove each piece by using it** — start the service and hit its healthcheck, run one real test — not by `--version`.
3. **"Unprovisionable" is a verdict earned by a failed attempt,** never by observation alone: the fetch was actually tried and there is no network or registry access, root is genuinely required and there is no passwordless sudo *and* no user-space alternative, or the missing piece is a credential only the user holds. Record each such item in the Master Plan with the failed attempt and the exact commands the user must run. Its consequence is **per-issue, not per-run**: it excludes only the issues whose acceptance criteria cannot be exercised without it (skip those per hard stops); every other issue proceeds. The whole run stops only when nothing in the batch remains verifiable.

* Detect the toolchain once: test runner, formatter, linter, type checker, and their exact invocations in this repo (`package.json`, `Makefile`, `pyproject.toml`, CI config, or an executable `.claude/verify.sh` / `scripts/verify.sh` if present — the same script the loop-until-done gate itself runs). If a run recipe exists at `.claude/skills/run-*/`, read it — it documents how to build and launch the app.
* Run the full verification suite once on clean `dev` — full meaning every tier the now-provisioned environment can run — and record every pre-existing failure, plus every tier that still could not run and why. This baseline goes in the Master Plan. Pass criterion for the whole run: **no new failures versus this baseline** — the batch is not responsible for making a previously red suite green. An issue whose acceptance criteria live entirely in a tier the baseline could not run is unverifiable — it gets skipped per the hard stops, never merged on the strength of checks that don't exercise it.

## Step 3 — Research via subagents

* Dispatch one Explore subagent per issue (or per cluster of related issues) via the Agent tool, all in a single message so they run in parallel. Each prompt must inline: the literal `owner/repo`, the issue number, an instruction to read the issue and all comments (`gh issue view <n> --repo <owner/repo> --comments`), the full content of `references/decision-rules.md`, and the required return format: one-paragraph problem restatement; root cause and affected files with real paths and line references (exhaustive — the partition below is computed from these file sets); proposed approach; ambiguities pre-resolved with the decision rule number cited.
* For any third-party API or SDK, verify against the installed version's official docs, not memory.
* In the main context, build the conflict/dependency map from the research returns: which issues touch which files, which build on which (Rule 8). The batch arrives mixed, with unknown dependencies — independence is discovered here, from the map, never assumed from the request or asked of the user. Partition the batch:
  * **Parallel group** — disjoint file sets, no ordering constraint → implemented concurrently in isolated worktrees.
  * **Pipeline** — B builds on A's change → B waits for A's merge (Rule 8).
  * **Serialized** — overlapping file sets, even when logically independent → one at a time, because concurrent edits to the same files collide at merge.

  An issue in a pipeline can still run parallel to unrelated issues. When research can't pin down an issue's file set, serialize it: misclassifying toward serial costs minutes, toward parallel costs a broken merge. The partition also fixes the single total **merge order** across the whole batch — integration is always serial (Step 5).

## Step 4 — Master Plan (before any code)

* Write the complete plan for the whole batch using `references/master-plan-template.md`: every remaining action across all issues in the batch, detailed enough that execution requires no further decisions. Anything that would have been a question appears as a numbered assumption citing its decision rule.
* Post the full Master Plan **once, as a single comment on the first issue in merge order**. That comment is the canonical plan — recovery after compaction re-reads this one comment, not the scattered per-issue ones.
* Post each issue's slice on that issue (format: `references/comment-templates.md`), linking back to the canonical plan comment. Then continue directly into execution.

## Step 5 — Execute per the partition; integrate serially

Every issue is implemented by a general-purpose subagent in its own git worktree: dispatch via the Agent tool with `isolation: "worktree"`. A subagent worktree is cut from the repo's **default branch** (`main`), never from `dev`, and no setting can point it at a branch — so every subagent pins its own base as its first command: `git checkout -B feature/issue-<n>-<slug> dev` (worktrees share the repo's refs, so local `dev` resolves and the working tree resets onto its tip — `dev` exactly as it stands at dispatch time). The partition controls only *when* each subagent launches:

* **Parallel group:** all of the group's subagents in a single message, concurrently.
* **Pipeline:** each successor only after its predecessor has merged to `dev` — it builds on that change.
* **Serialized issues:** one at a time, each after the previous merge, so the later worktree already contains the earlier edits it overlaps with.

Each subagent's prompt must inline: the literal repo, the branch to create (`feature/issue-<n>-<slug>`, via the base-pinning first command above), the issue's posted plan comment (fetch it and paste it), the full decision rules, the toolchain commands, the worktree bootstrap from Step 2 (a fresh worktree shares the repo's refs but not its installed dependencies — give the exact commands that make the toolchain runnable there, e.g. the dependency install), the baseline failures, and the TDD contract — write the plan's failing tests first, then implement the numbered steps until they pass; cover happy path, edge cases, and failure paths; prefer integration tests over mocks; never skip a test, suppress a warning, disable a lint rule, or loosen a type to get green; commit to the branch per the plan's commit plan (worktrees share the repo's object store, so committed branches outlive the worktree — uncommitted work does not); no scope beyond the issue; no questions; never touch `dev`, never push, never merge.

**Integration runs strictly serially in the main context, in the Master Plan's merge order — whatever the bucket, this phase never parallelizes.** As each subagent finishes:

1. **Reclaim the branch.** The subagent's worktree survives (it holds unpushed commits) with the branch still checked out, and git refuses a second checkout of a branch another worktree holds. Confirm the commits landed (`git log --oneline dev..feature/issue-<n>-<slug>`), then remove that worktree (`git worktree list` to find it, `git worktree remove <path>`; `--force` only for a failed agent's dirty tree). The committed branch survives removal; now it can be checked out, merged, or deleted normally.
2. **Verify — never take the subagent's word.** Check out the branch and run the full verification suite yourself (tests, formatter, linter, type checker), compare against the baseline, and drive the behavior end to end: the run recipe if one exists, or for libraries/CLIs a realistic invocation of the changed interface.
3. **Merge:** push the branch, then `git checkout dev && git merge --no-ff feature/issue-<n>-<slug>`. If the branch was developed concurrently (its base predates other merges), re-run the verification suite on merged `dev` before pushing — the isolation that made parallelism safe means the merge is the first time these changes meet; new failures here reset the un-pushed merge and count as a failed verification cycle. Push `dev` when clean.
4. **Ship:** post the closing comment (`references/comment-templates.md`), swap labels: `gh issue edit <n> --remove-label in-progress --add-label awaiting-release`. Do **not** close the issue — closing happens at promotion to `main`, which only occurs on explicit user request. Tick the batch checklist.
5. **On failure** (per hard stops): comment findings, mark skipped, remove `in-progress`, leave `dev` clean (never merge partial work), continue with the rest of the partition. A skipped issue also skips everything pipelined behind it — post each dependent's skip comment citing the broken dependency and remove its `in-progress` label too, so it returns to the eligible pool for a future run.

## Step 6 — Report and attest completion

* Per issue as each finishes, and a batch report at the end — formats in `references/comment-templates.md`. Report only validation that actually ran, with its real output. Include the shortfall note if a cap was given and fewer eligible issues matched it, plus the combined follow-ups deferred by Rules 6–7.
* **Attest for the loop-until-done gate** *(only when this machine's Stop hook is installed — skip this bullet entirely if `~/.claude/hooks/loop-until-done.sh` does not exist, since writing `.claude/.done` into a repo with no gate just litters a stray file).* Once the batch report is posted and `dev` is pushed: if any commit happened this session, create `.claude/.done` at the repo root before ending the turn — the Stop hook re-verifies tests/lint/push independently and revokes `.done`, blocking again, if anything is actually unclean, so this is a request-to-verify, not a shortcut. If the whole run ended via the repo-level hard stop with no commits made, no attestation is needed.
* The run ends at `dev`. Never commit to `main`/`master` directly, never merge a working branch into it, never force-push a shared branch, and never promote to `main` unless the user explicitly asked in this run's instructions or a later message.

## Guardrails

* One batch per run. Implementation fans out only as far as the partition allows; integration never does — one merge into `dev` at a time, always in the main context. Never interleave two issues' changes on one branch or worktree.
* Never fabricate results — a test "passed" only if it was run and observed passing in the main context.
* The plan is binding. Deviations must be minimal, forced by reality, and reported in the plan-vs-actual sections.
* A failed issue never poisons the batch; skipped work stays off `dev`.
* Leave files the batch didn't need untouched.
