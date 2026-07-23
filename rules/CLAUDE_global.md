# Global Claude Rules
 
Applies to every repository. A project's own `CLAUDE.md` wins on any conflict.
 
---
 
## Scope
 
* Do what was asked, nothing more. No unrequested features, no unrelated refactors, no architecture redesigns.
* Prefer editing existing code over adding abstractions, and existing project patterns over new ones.
* If the requirements are ambiguous, ask before implementing.

## Unrelated problems found along the way
 
1. If it blocks the requested work, fix it as part of the task.
2. If it does not, open a GitHub Issue with reproduction steps, observed vs. expected behavior, suspected cause, affected files, and suggested next steps, then reference it in the final summary.
3. If GitHub Issues are unavailable, use the project's own tracker and note the limitation.
Investigate far enough to write a useful report, not further.
 
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

## Testing and validation
 
* Every behavioral change needs automated tests covering the happy path, the edge cases, and the failure paths.
* Prefer integration tests over mocks where practical.
* Never route around a failing check: no skipped tests, suppressed warnings, disabled lint rules, or loosened types. Fix the cause, or stop and say why you cannot.
* Report only validation that actually ran. Show the command and its output; never state that a suite passed without running it.

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