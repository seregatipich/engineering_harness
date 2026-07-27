# Global Claude Rules
 
Applies to every repository. A project's own `CLAUDE.md` wins on any conflict.
 
---
 
## Scope
 
* Do what was asked, nothing more. No unrequested features, no unrelated refactors, no architecture redesigns.
* Prefer editing existing code over adding abstractions, and existing project patterns over new ones.
* If the requirements are ambiguous, ask before implementing.
* Changes outside the repository — global config, `~/.claude`, installed tooling, system state — are never a silent side effect. Say what you changed and why, and leave no `.bak` or `.orig` copies behind.

## Unrelated problems found along the way
 
1. If it blocks the requested work, fix it as part of the task.
2. If it does not, open a GitHub Issue with reproduction steps, observed vs. expected behavior, suspected cause, affected files, and suggested next steps, then reference it in the final summary.
3. If GitHub Issues are unavailable, use the project's own tracker and note the limitation.
Investigate far enough to write a useful report, not further.

## Environment and infrastructure
 
Provisioning what the requested work needs in order to run and be verified is part of the task, not a separate request. A missing toolchain, dependency, service, socket, container, or config value is a work item; installing what the project's own manifests already declare is not adding a dependency.
 
* Classify each piece as *present and current*, *stale*, or *absent*, then act: refresh from the lockfile, or set it up from zero, preferring the repo's own bootstrap path — devcontainer, compose file, `Makefile` or package-script setup target, `scripts/` — over an improvised install.
* Something is absent only once you have looked for it. Check `$PATH`, `$HOME/.local/bin`, `$HOME/bin`, and version-manager roots, and check whether the repo builds the thing itself, before calling it missing.
* Prefer the unprivileged route: official tarballs or version managers into `$HOME`, rootless container runtimes, configurable socket and port paths. Reach for `sudo` only after the unprivileged route has actually failed.
* Prove each piece by using it — start the service and hit its healthcheck, run one real test. A `--version` string is not proof.
* Never state a constraint you have not tested. "Needs root", "not available here", "cannot work in this environment" require a command and its output. Inferring it from a filename, a `/run/` path, or an installer you did not read is a guess.
* Separate *missing* from *denied*. A sandboxed Bash command writes only to the working directory and `$TMPDIR`, reaches only allowed domains, and cannot run `docker`; those are policy boundaries with their own escape hatches, not absent software. Name the exact boundary.
* "Unprovisionable" is a verdict earned by a failed attempt, never by observation alone. Report the attempt, its output, and the exact commands the user must run.
* Work running in parallel must not share mutable state. Give each worker its own database, port, socket, and temp directory, or serialize access to the shared one — a global teardown in one worker destroys a sibling's in-flight run.

## Blockers and escalation
 
* Stopping is honest when you have hit the dead end, not when you predict one. Before reporting a blocker, list what you tried and what each attempt returned.
* Do not hand back a command you could have run yourself. Escalate only what is genuinely out of reach: a credential, an access grant, a product decision, an approval, a physical action.
* A failure that is pre-existing, outside CI's scope, or not caused by your change is context, not permission to stop. Spend the diagnostic effort on the fix, not on establishing that it is not your fault.
 
## Code
 
* No TODO or FIXME comments, no placeholders. Implement it or leave it out.
* Comments explain *why*, not *what*. Prefer expressive names and types over commentary.
* Do not extract a helper, wrapper, or abstraction for a single call site. Duplication is fine when it reads better; deduplicate only when it clearly improves maintainability.
* Optimize only against a measurement: identify the bottleneck first, verify the improvement after.

## Documentation
 
* Every new or modified public interface gets documentation in the project's existing style: purpose, parameters, return value, raised exceptions, type annotations.
* For private code, document only what reading it will not reveal: algorithms, invariants, side effects, concurrency behavior, assumptions.
* Documentation that contradicts the implementation is a defect. When code changes, update or delete the affected docs, docstrings, types, examples, and links.
* Update project documentation when behavior, APIs, configuration, setup, architecture, or deployment changes, following the existing docs structure.
* Link to related specs, ADRs, RFCs, schemas, and tickets instead of restating them.

## Testing
 
* Every behavioral change needs automated tests covering the happy path, the edge cases, and the failure paths.
* Prefer integration tests over mocks where practical.
* Never satisfy a check with a stub, fake, or stand-in for the real dependency it exists to exercise. Green against a fake certifies nothing. If a bare stub would satisfy the assertions, that is a defect in the test — report it, do not exploit it.
* A test owns the state it asserts on. An absolute count or identity asserted over state shared with other tests is order-dependent by construction; scope the assertion to the rows, files, or keys that test created.

## Validation and reporting
 
* Reproduce what CI runs *and the state it runs in* — a fresh database, container, or tree wherever CI gets one. A failure produced by state you carried over between runs belongs to your process, not to the code.
* Exit status must survive the pipeline. Never read pass/fail from a command that ends in `| tail`, `| grep`, or a pager: that reports the last stage's status, not the check's. Capture the real status and take the verdict from it.
* Never route around a failing check: no skipped tests, suppressed warnings, disabled lint rules, loosened types, and no `--no-verify`, `--force`, or equivalent gate bypass. Fix the cause; if you genuinely cannot, say so and show the evidence that proves it.
* Report only validation that actually ran. Show the command and its output; never state that a suite passed without running it.
* No all-clear while a check is still in flight. "Nothing is broken" is a claim about checks that have concluded and whose output you have read, never about ones you expect to pass.
* A delegate's report is a claim, not evidence. Verify it before building on it, and hold delegated work to the bar you would hold your own — including any gate it bypassed.
* Do not call work complete while a check you know about is red, and do not narrow the claim — "the coverage subset is green" — to keep the red out of the report. State what is failing alongside what is passing.

## Compatibility
 
* Preserve public APIs and backward compatibility unless instructed otherwise.
* When an API does change, update every call site and document the break.

## Dependencies
 
Prefer what the project already depends on. Add a dependency only for clear value, and remove unused ones.
 
## Third-party APIs and SDKs
 
Check the current official documentation for the version the project actually has installed rather than relying on memory.
 
## Git
 
* `main`/`master` is production, `dev` is integration. Working branches start from `dev` and merge back into `dev`. Only `dev` merges into the default branch.
* Name working branches `feature/`, `fix/`, `refactor/`, or `chore/`.
* Never commit to the default branch, never merge a working branch into it directly, and never rename or replace it.
* No destructive Git operations (force push, history rewrite, hard reset on shared branches) unless explicitly instructed.

## Working files
 
The repository holds source, tests, and the project's own documentation. Nothing else.
 
* Plans, task breakdowns, and progress notes stay in the session. Plan files already live in `~/.claude/plans`, outside the repository: no `plans/` directory, no `PLAN.md`.
* Implementation reports, migration summaries, and hand-off notes belong in the final summary, never in a file. No `IMPLEMENTATION_SUMMARY.md`, `CHANGES.md`, or `REFACTOR_NOTES.md`.
* Scratch files, debug scripts, one-off benchmarks, and generated output go to a temp directory outside the repository, or are deleted before the work is called complete.
* New documentation goes where the project's existing structure puts it. No new Markdown files in the repository root except `README.md`, and no second docs tree alongside the real one.