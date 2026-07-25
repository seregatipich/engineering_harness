# Promotion — integration branch to production

Promotion is a defined phase, not an improvisation. It runs **only** on an explicit user request naming it,
and that request authorises the whole procedure below as one unit. Do not re-litigate it mid-phase, and do
not stop halfway to confirm a step that step 1 already gated.

Pushing to the default branch is usually a production deploy. That is exactly why the pre-flight is
mechanical and the abort conditions are stated up front, rather than reasoned about under time pressure.

## Procedure

**1. Pre-flight.** All three must hold. If any fails, stop and report which one, with the command output.

```bash
git fetch origin
git merge-base --is-ancestor origin/<default> origin/dev   # must pass: promotion is fast-forward only
git rev-list --count origin/<default>..origin/dev          # what will ship
git log --oneline origin/<default>..origin/dev
```

Then: the CI run **for the exact current `origin/dev` SHA** must be green —
`bash scripts/wait_ci.sh <owner/repo> "$(git rev-parse origin/dev)"`. A green run on an older SHA does not
count, and matching by branch or by "latest run" silently accepts one.

If `dev` does not fast-forward, stop. Reconciling a diverged production branch is not part of this phase.

**2. Promote.**

```bash
git push origin origin/dev:<default>
```

Fast-forward only. Never a merge commit, never `--force`.

**3. Wait for everything the push triggered** — CI and any deploy workflow — via `wait_ci.sh` against the
new default-branch SHA. Promotion is not done when the push returns; it is done when the deploy concludes.

**4. On green, close out each issue.** Post the completion-evidence comment — the delivery chain, the CI and
deploy run links, the quality gates with their real output, and the verification provenance. Remove the
`awaiting-release` label. Close each issue **whose acceptance criteria were fully exercised**.

**5. An issue with any deferred criterion stays open.** Post a progress comment naming the criterion, why it
could not be exercised, and the exact command that would exercise it on a capable host. An acceptance
criterion that was written and guarded but never run cannot carry a "verified" claim, and closing it anyway
converts an honest limitation into a false record. This is the same rule as the run-deferred branch in
`handoff.md`, applied at the last possible moment to change it.

## If the deploy fails

Report it with the run link and stop. Do not roll back, revert, or re-push without an explicit instruction:
a failed deploy on production is a decision the user makes, not a cleanup the run performs.
