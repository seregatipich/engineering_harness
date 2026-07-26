---
name: work-next-issue
description: >-
  Work a scoped set of GitHub issues end to end with zero mid-run questions:
  read the scope straight from the user's wording, provision whatever the
  verification environment is missing (deps, env files, services, toolchains)
  instead of stopping at the gap, research via subagents, partition the work by
  dependencies and file overlap, post one very detailed executable Brief per
  issue (checklist steps, full test matrix), implement test-first via Sonnet
  executors that post progress reports on the issue, verify independently,
  merge to the integration branch serially, and leave a structured
  implementation report per issue.
when_to_use: >-
  Manual only: /work-next-issue then plain English (e.g. "the critical bugs in
  v2", "do 3 of them", "#42 #43"). Creates branches, posts issue comments, and
  merges to the integration branch, so it is never model-invoked.
argument-hint: "plain English — issue numbers, milestone, priority, label, count, or nothing"
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
* Executor tier: !`echo "${CLAUDE_CODE_SUBAGENT_MODEL:-unset}"`

One run takes the scoped set of issues zero to hero: select → provision the environment and baseline → research (subagents) → partition (parallel / pipelined / serialized) → one Master Plan → one executable Brief posted per issue → implement test-first (one worktree-isolated Sonnet executor per issue, concurrent where the partition allows, posting progress reports on its issue) → verify, merge serially, and post a structured implementation report per issue.

## Prerequisites

* A git repo with a GitHub `origin` remote, and `gh`, `jq`, `git` on `PATH`. If the Tooling line reports anything `MISSING`, try a user-space install first (static binary into `~/.local/bin`); a hard stop only if that fails.
* This machine's harness — the git policy in `rules/CLAUDE_global.md` (production branch / integration branch `dev`) and the loop-until-done `Stop` hook — is assumed but optional. Every step that folds it in degrades gracefully when a piece is absent; `references/environment.md` says how.
* This skill's contract supersedes the general "ask when ambiguous" rule in `~/.claude/CLAUDE.md`. Ambiguity here is resolved by `references/decision-rules.md`, never by asking.

## Operating contract

* **Zero mid-run questions.** All thinking happens before dispatch; execution is mechanical. Ambiguity is resolved by the decision rules and recorded as a numbered assumption. `AskUserQuestion` is blocked for the run. This covers the final message: a run that hits a blocker still ends with the most work achievable and a factual report — never a menu of options.
* **The repo and `VERIFY` are literals.** Resolve `owner/repo` once from the preloaded environment and the verification script path once in Step 2, then substitute the literal strings into every command and every subagent prompt. Subagents start fresh shells and inherit no variables.
* **User interjections don't reopen questions.** If the user interjects mid-run, reply briefly, never use it to ask anything, and resume.
* **State lives on GitHub.** After compaction, do not reconstruct from memory: re-read the canonical Master Plan comment (Step 4) and each issue's Brief (`gh issue view <n> --comments`), then resume from the checklist and the run ledger.

## Hard stops (failures, not questions)

* `gh` unauthenticated, or repo unresolvable → report it and stop.
* Selection returns no eligible issues → say so and stop. Never invent work.
* A missing tool, dependency, service, or config file is **never by itself a hard stop** — Step 2 provisions it. Only a provisioning attempt that actually failed can block, and it blocks only the issues that need that piece.
* Per issue: unimplementable as written, acceptance criteria unverifiable in every tier the environment can run, or 3 full verification cycles fail with no progress → post findings, mark skipped, drop the in-progress label, keep the integration branch clean, continue the batch.
* Whole run: if a repo-level failure — or Step 2 leaving no issue verifiable — makes every remaining issue impossible, stop early, write `.claude/.blocked` at the repo root with 1-5 lines on what's blocked and what the user must do, and repeat it in the final reply.

## Step 1 — Select and claim the batch

1. **Read the scope straight from the user's wording.** `$ARGUMENTS` is plain English — issue numbers, milestones, a priority, a label, a theme, a count, or nothing — and you resolve it yourself with `gh` (`gh issue list`, `gh issue view`, `gh api repos/<owner/repo>/milestones`, `gh search issues`), composing whatever query the wording implies. There is no flag grammar to translate into and no selector script to satisfy. The boundaries still hold:
   * The scope is the user's: work exactly what they describe, no more. Never invent work to fill a batch.
   * Explicit issue numbers mean exactly those issues, in the order given, even if assigned.
   * A count is an exact ceiling, and only when the user names one — an open-ended request has no default size.
   * Skip issues already carrying the in-progress role label; they belong to another run.
   * Empty arguments → the nearest-due open milestone that has eligible work, never the whole backlog.
   * Order the batch by milestone due date, then priority, then issue number; Step 3's dependency map may reorder it.
   * Record how the wording was read — what it matched, what it didn't, anything dropped — as numbered assumptions for the Master Plan.
2. **Resolve the repo's label vocabulary once:** `gh label list --repo <owner/repo> --limit 200`, then map which of this repo's real labels play the priority ranks, in-progress and awaiting-release roles (`priority:p0`, `status:in-progress` and friends count; read the repo's names, don't impose canonical ones). A role with no match means that guard is inert — create the missing role's label with `bash "${CLAUDE_SKILL_DIR}/scripts/setup_labels.sh" <owner/repo> --map <file>` (a `{role: label|null}` JSON map; it creates only the `null` roles, so it never imposes a second vocabulary). Record the resolved map in the Master Plan.
3. **Claim immediately:** add the in-progress role label to every selected issue. This is what stops a concurrent run picking up the same work.
4. Report the batch as a table (#, title, milestone, priority, order) and proceed without waiting for acknowledgment.

## Step 2 — Provision, baseline, and fix the verification command

Full procedure in **`references/environment.md`**. An incomplete environment is the normal starting state of a run, not an exception — discovering a gap and reporting it as a blocker without an attempt to close it is the one failure mode this step exists to prevent (Rule 10). In outline:

1. Create the integration branch from the default branch if it doesn't exist; sync it. Probe `git worktree list --porcelain` and record which worktree holds it — that decides the base pin in Step 5.
2. `bash "${CLAUDE_SKILL_DIR}/scripts/probe_env.sh"` → the environment profile. Provision what's missing, preferring the repo's own bootstrap path; prove each piece by using it, never by `--version`.
3. `bash "${CLAUDE_SKILL_DIR}/scripts/ci_recipe.sh"` → **the gate is CI's, not the repo's convenience scripts.** Where CI runs a stricter variant, that variant is this run's verification command. Write it to `<scratch>/verify.sh` and record the absolute path as `VERIFY`.
4. Enumerate the gated units into a TSV and baseline them with `bash "${CLAUDE_SKILL_DIR}/scripts/run_units.sh"`. Classify every failure in the Master Plan's units table. Pass criterion for the run: **no NEW failures versus this baseline.**
5. Rehearse in a throwaway worktree at the baseline SHA: run the candidate bootstrap and `verify.sh` there until they match the checkout baseline, then discard it. This is also where any command the plan intends to prescribe gets run once, so the Master Plan's *Verified facts* table states only what was observed.
6. Read the repo's own agent contract (`AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`) and record the definition of done, and how it reconciles with this skill's sequence, as **one** numbered assumption — decided once, not re-litigated per issue.

## Step 3 — Research via subagents, in two passes

Paste `references/research-contract.md` in full into every research prompt; it is the return format. Dispatch Explore subagents via the Agent tool, all in a single message so they run in parallel, one per issue or per cluster of related issues — clustering issues that share a substrate finds a cross-cutting constraint once instead of three times. Each prompt inlines the literal `owner/repo`, the issue number, an instruction to read the issue and all comments, and the full decision rules.

* **Pass 1 — map.** Problem restatement, root cause, and the exhaustive create/modify file set. In the main context, build the conflict/dependency map from these file sets and partition the batch: **parallel** (disjoint files), **pipeline** (B builds on A's merge, Rule 8), **serialized** (overlapping files despite logical independence). When a file set can't be pinned down, serialize: misclassifying toward serial costs minutes, toward parallel costs a broken merge. The partition also fixes the single total merge order.
* **Pass 2 — mechanics.** Dispatched after the partition, with pass 1's file list inlined. This fills the research contract's fields and is what each Brief is built from. Research is the cheap place to buy detail: the researcher already has the file open when the fact matters.

## Step 4 — Master Plan, then one Brief per issue

* Write the batch-level plan with `references/master-plan-template.md` and post it as ONE comment on the first issue in merge order — the canonical plan comment.
* Write each issue's **Brief** with `references/handoff.md`, post it on its issue, and record its comment id. The Brief is the whole per-issue contract; there is no second, richer document. It is written for a Sonnet executor, so it is *very* detailed by design: checklist implementation steps (`1. [ ] …`) each with a verify command, a test matrix covering every applicable kind of verification with implemented tests or a grounded N/A, and the progress-report checkpoints the executor must post.
* Gate every Brief on `bash "${CLAUDE_SKILL_DIR}/scripts/check_brief.sh" <repo-root> <brief.md>` and dispatch only on exit 0. A contract nothing checks is a suggestion.

## Step 5 — Execute per the partition; integrate serially

Each issue is implemented by a general-purpose subagent in its own git worktree (`isolation: "worktree"`). The worktree starts on the repository's default branch, so every subagent pins its base as its first command: `git fetch origin && git checkout -B feature/issue-<n>-<slug> origin/<integration>`. A remote-tracking ref is used deliberately — no worktree can hold it, and it is the exact object Step 5.3 pushes to. The partition controls only *when* each subagent launches: the parallel group all in one message; a pipeline successor only after its predecessor merges; serialized issues one at a time.

**The dispatch prompt is the posted Brief, fetched verbatim, plus the machine block from `scripts/agent_env.sh <n> <worktree>` — nothing else is authored.** To tell an executor something the Brief lacks, PATCH the comment and re-fetch. Implementation dispatches pass `model: "sonnet"` — the executor tier is the latest Sonnet, deliberately smaller than the orchestrator; the Brief's detail is what makes that tier sufficient. Research subagents get no `model` and inherit the orchestrator. If the preloaded Executor tier line is set, that env var outranks the parameter — record the effective tier as an assumption and pass no conflicting `model`. Beyond 20 concurrent subagents, dispatches queue; that is not an error.

While an executor runs, its progress lives on the issue: the Brief obliges it to post checkpoint comments (red / green / final, plus any PLAN-WRONG or blocker) as it works, so the issue is readable in real time without interrogating the subagent.

**Integration runs strictly serially in the main context, in merge order — this phase never parallelizes.** As each subagent finishes:

1. **Verify in place, and never take the subagent's word.** The subagent's worktree already has the dependencies and the resource slot, so verify there: run `VERIFY`, compare against the baseline with `run_units.sh --baseline`, read the diff adversarially, check every Brief checklist box and every test-matrix row against the committed tests, and drive the behaviour end to end. The end-to-end drive belongs to this context; the executor's obligation was to turn any e2e path the Brief named into a committed test, not a throwaway probe. Confirm the executor's progress reports were actually posted (`REPORTS` in its return, cross-checked on the issue) — a missing checkpoint is a deviation to record.
2. **Merge concurrent work first.** In that same worktree, `git fetch && git merge origin/<integration>` and re-run `VERIFY`. If the branch was developed concurrently, this is the first time these changes meet; new failures here reset the merge and count as a failed verification cycle (`git merge --abort` or `git reset --merge ORIG_HEAD`, never `git reset --hard`).
3. **Merge and push:** `git checkout --detach origin/<integration> && git merge --no-ff <branch> && git push origin HEAD:<integration>`. A detached HEAD has no upstream, so confirm the push landed by comparing `git rev-parse HEAD` against `origin/<integration>` after a fetch, and record that SHA — Step 6 needs it. Only now remove the worktree.
4. **Fold in what was learned.** Every `PLAN-WRONG` the executor returned goes into the Master Plan's run ledger, and any Brief it affects gets PATCHed before that issue dispatches. A correction that lives only in this context dies with the next compaction.
5. **Ship:** post the structured **implementation report** (`references/comment-templates.md` §3) — summary, files, checklist state, test-matrix outcome, verification output, deviations, and the accountability trail linking the Brief and every progress report — then swap the in-progress role label for awaiting-release. Do **not** close the issue — closing happens at promotion. Tick the checklist.
6. **On failure** (per hard stops): comment findings, mark skipped, keep the integration branch clean, continue. A skipped issue also skips everything pipelined behind it. A gate failure discovered *after* a merge is a new work item — cut `fix/<slug>`, dispatch an executor, verify and merge it like any batch item. The orchestrator never writes production code.

## Step 6 — Report and attest

* Per issue as each finishes (the implementation report of Step 5.5), and a batch report at the end — formats in `references/comment-templates.md`. Report only validation that actually ran, with its real output. Accountability lives on GitHub: every issue ends the run carrying its Brief, the executor's progress reports, and the final implementation report.
* Done means the repo's own definition of done is satisfied **and** CI for the current integration tip concludes green (`scripts/wait_ci.sh <owner/repo> <sha>`). A green run on an older SHA does not count.
* **Attest for the loop-until-done gate** *(only when `~/.claude/hooks/loop-until-done.sh` exists)*: once the batch report is posted and the integration branch is pushed, if any commit happened this session, create `.claude/.done` at the repo root. The hook re-verifies independently and revokes it if anything is unclean, so this is a request-to-verify, not a shortcut.
* The run ends at the integration branch. Never commit to the default branch directly, never merge a working branch into it, never force-push a shared branch.

## Step 7 — Promote (only on explicit request)

Promotion is a defined phase — **`references/promotion.md`**. Entered only on an explicit user request naming it; that request authorises the whole procedure as one unit and is never re-litigated mid-phase.

## Guardrails

* One batch per run. Implementation fans out only as far as the partition allows; integration never does.
* Never fabricate results — a test "passed" only if it was run and observed passing in this context.
* The Brief is binding until reality contradicts it; then Rule 11 applies. Deviations are minimal, recorded, and reported.
* A failed issue never poisons the batch; skipped work stays off the integration branch.
* Leave files the batch didn't need untouched.
