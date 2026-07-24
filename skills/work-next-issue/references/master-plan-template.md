# Master Plan template

The plan is the contract for the rest of the run. Every step must be executable without a decision — if writing a step requires choosing, make the choice now via the decision rules and log it as a numbered assumption. Concise per step, exhaustive in coverage: no phase of the run and no issue in the batch may be missing.

Post the completed plan as ONE comment on the first issue in execution order (the canonical plan comment). Link every per-issue comment back to it.

## Batch-level sections

1. **Objective** — one sentence: what "done" means for this batch of N.
2. **Execution order** — the N issues in the order they will be worked, with the reason wherever it differs from priority order (dependency, shared files — Rule 8).
3. **Baseline** — toolchain detection results (exact test/format/lint/typecheck commands, run recipe if any) and every pre-existing failure found on clean `dev`. Pass criterion for the run: no NEW failures versus this baseline.
4. **Global assumptions** — numbered: N rounding, selection shortfalls, toolchain choices, integration path, anything spanning issues; each cites its decision rule.
5. **Out of scope** — what will deliberately not be done batch-wide, with follow-ups.
6. **Integration path** — base branch, per-issue branch scheme `feature/issue-<n>-<short-slug>`, merge target `dev`, `--no-ff` merges, merge order, label flow (`in-progress` → `awaiting-release`, issues stay open until promotion).
7. **Batch progress checklist** — one line per issue, copied into responses and ticked as the run advances:

```
Batch progress:
- [ ] #<n1> — plan posted / tests written / implemented / verified / merged to dev
- [ ] #<n2> — plan posted / tests written / implemented / verified / merged to dev
```

## Per-issue sections (repeated for each of the N, in execution order)

8. **Issue objective** and the resolved assumptions specific to it.
9. **Test plan (written before code)** — every test with file path, test name, what it asserts, and whether it covers happy path / edge case / failure path.
10. **Implementation steps** — numbered; each names the files to create or modify (real paths), the change in one or two sentences, and which tests it should make pass.
11. **Verification steps** — the exact commands for tests, formatter, linter, type checker, plus how the behavior will be driven end to end (run recipe, or realistic invocation of the changed interface).
12. **Commit plan** — intended logical commits and their messages.
13. **Subagent handoff** — confirmation that the issue's plan comment plus decision rules plus baseline is a complete, self-sufficient prompt for the implementation subagent.

## Wrap-up section

14. Per-issue closing comments, `--no-ff` merges `feature → dev` in order, label swaps, and the final batch report.

## Deviation rule

If reality forces a deviation (a file moved, a framework quirk, an earlier issue's change altering a later one's plan), deviate minimally, record the deviation for the plan-vs-actual sections — still without asking.
