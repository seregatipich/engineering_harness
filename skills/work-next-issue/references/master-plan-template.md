# Master Plan template — the batch-level contract

The Master Plan covers everything that spans issues. Everything specific to *one* issue lives in that
issue's Brief (`references/handoff.md`), which is posted as its own comment and is what the executor runs.
Two artifacts, no overlap: the plan decides, the Brief executes.

Post the completed plan as ONE comment on the first issue in merge order — the canonical plan comment.
Every Brief links back to it. Recovery after compaction re-reads this comment, then the Briefs.

## Sections

1. **Objective** — one sentence: what "done" means for this batch.

2. **Execution partition and merge order** — the output of the conflict/dependency map, never an input
   taken from the request: the parallel groups (disjoint files, no ordering constraint), the pipelines
   (dependency chains — Rule 8), and the serialized issues (overlapping files despite logical
   independence), each non-parallel placement with its reason; plus the single total merge order used for
   serial integration.

3. **Resource allocation** — every scarce sequential resource the batch will contend for, pre-assigned per
   issue: migration numbers, sequence ids, port ranges, fixture namespaces. Assigning these up front
   removes an entire class of merge collision, and a weak executor will otherwise take "the next free one"
   at a moment when its worktree has a stale view of what's free.

4. **Environment & baseline** — the mechanical part of the run, recorded so nothing re-derives it:
   * `BASELINE_SHA` — the integration-branch commit everything is measured against.
   * `VERIFY` — the absolute path to the verification script written at the end of Step 2. This command,
     and no cheaper proxy, is what Step 5 runs and what every Brief's finish checklist names.
   * The units table, from `scripts/run_units.sh`:

     | unit | command | result | class | evidence |
     |---|---|---|---|---|

     `class` is one of `REPO-RED` (fails on clean baseline, the repo's own problem), `ENV-ONLY` (fails
     here for an environmental reason, passes in CI), `FLAKE` (fails non-deterministically; passes in
     isolation), `UNKNOWN`. Classify every failure once, here. Carrying the baseline as prose is what turns
     each later red result into a fresh multi-turn "is this mine?" investigation.
   * What Step 2 provisioned (found current / brought up to date / set up from zero), and any item that
     survived a real provisioning attempt as unprovisionable — the attempt made, why it failed, the exact
     commands the user runs to unblock it.
   * The ordered worktree bootstrap commands, and the *commands that lie in a fresh worktree* — anything
     whose output is misleading before the tree is built, with the aggregate to use instead.

   Pass criterion for the run: **no NEW failures versus this baseline.** The batch is not responsible for
   making a previously red suite green.

5. **Definition of done** — the repo's own completion script if one exists (read it; its checks are the
   contract), plus: the CI run for the current integration tip concludes green. A green run on an older SHA
   does not count. Where the repo ships its own agent contract (`AGENTS.md` and friends), it is **additive**
   — satisfy its extra evidence requirements; where it conflicts on *sequencing*, this skill's sequence
   wins. Record the mapping as one numbered assumption, decided once, so it is not re-litigated per issue.

6. **Verified facts** — the provenance table. Every claim the plan or a Brief states as an imperative about
   a gate, guard, generator or command:

   | claim | command actually run | output digest |
   |---|---|---|

   A fact may be stated as an imperative **only** if it appears here. Anything else is stated as unknown,
   with the command that settles it. This is the counterweight to detail: the costliest failures in this
   skill's history were not omissions but confident assertions that were false — a generator that blocked
   interactively, coverage thresholds off by two orders of magnitude, a parity guard that did not exist.
   A weaker executor trusts a confident wrong statement further than a strong one does.

7. **Global assumptions** — numbered: scope resolution (which flags the request became, and how the repo's
   label vocabulary mapped), selection shortfalls, toolchain choices, integration path, anything spanning
   issues; each cites its decision rule.

8. **Out of scope** — what will deliberately not be done batch-wide, with follow-ups.

9. **Integration path** — base branch, per-issue branch scheme `feature/issue-<n>-<short-slug>`, merge
   target, `--no-ff` merges, merge order, label flow using the roles resolved from the repo's own
   vocabulary, and which worktree (if any) holds the integration branch.

10. **Batch progress checklist** — one line per issue, copied into responses and ticked as the run advances:

```
Batch progress:
- [ ] #<n1> — brief posted / tests written / implemented / verified / merged
- [ ] #<n2> — brief posted / tests written / implemented / verified / merged
```

11. **Run ledger** — appended to as the batch proceeds, by editing this comment. Every `PLAN-WRONG` returned
    by an executor, every correction discovered during integration, every fact that turned out to differ
    from section 6. This is the mechanism that carries a lesson from issue 2 to issue 5: without it a
    correction lives in the orchestrator's context until compaction eats it, and later Briefs repeat the
    mistake. Before each dispatch, check the ledger and PATCH the Brief it affects.

## When the plan turns out to be wrong

It will, somewhere. That is expected, and it is handled rather than prevented: the executor halts the
affected step, returns `PLAN-WRONG` with the quoted claim and the observed output, and continues with the
steps that don't depend on it (`references/handoff.md`). The orchestrator folds it into the ledger above and
corrects the affected Briefs before dispatching them.

A deviation forced by reality is minimal, recorded, and reported — never a question, and never a silent
improvisation.
