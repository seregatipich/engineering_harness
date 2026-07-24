# Decision rules — resolve, never ask

Include this file's full content verbatim in every subagent prompt (research and implementation). Apply the rules in order. Record every application as a numbered assumption in the Master Plan or plan comment, citing the rule number.

1. **Issue text wins.** If the issue or its comments state a preference, follow it.
2. **Repo convention wins next.** Match existing patterns: test framework already in use, naming style, error-handling style, directory layout, existing similar features.
3. **Smallest correct change.** When two designs both satisfy the issue, pick the one that touches fewer files and adds no new dependencies.
4. **Backwards compatible by default.** Do not change public interfaces, CLI flags, config keys, or API response shapes unless the issue explicitly asks for it.
5. **New dependency only if unavoidable.** Prefer stdlib / already-installed packages. If truly required, pick the most widely used maintained option and record it as an assumption.
6. **Scope stays inside the issue.** Adjacent bugs or refactors get noted in the closing comment as follow-up suggestions, not implemented.
7. **Safety over completeness.** If a sub-task would be destructive or irreversible (data migration on real data, deleting user content, force-push, rewriting history), implement the non-destructive portion and list the destructive step as a documented follow-up for the user — do not execute it and do not ask.
8. **Batch order is dependency order.** If issue B builds on issue A's change, A goes first regardless of priority; record the reordering as an assumption.
9. **No convention exists at all?** Choose the dominant, current ecosystem default for the project's language/framework (verify against current docs, not memory) and log it as an assumption.
10. **An environment gap is work, not a blocker.** A missing dependency install, toolchain, service, or config file gets provisioned, not reported: bring stale infra up to date, set absent infra up from zero — the repo's own setup scripts first, user-space installs (tarballs, version managers, rootless runtimes into `$HOME`) when root is unavailable. Only an attempt that actually failed for a cause outside your control (no network access, root required with no alternative, a credential only the user holds) blocks — and it blocks only the work that needs that piece. Log what was provisioned as an assumption.

## Hard-stop recap (failures, not questions)

Unimplementable as written, or 3 failed verification cycles with no progress → post findings, skip, keep `dev` clean, continue the batch. Missing infra → provision it (Rule 10); only a failed provisioning attempt blocks, and only the issues that need that piece. Repo-level failure (auth, unresolvable repo) → stop the run and report. Everything else is covered by the rules above.
