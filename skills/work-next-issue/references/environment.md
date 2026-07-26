# Environment — provisioning and the verification command

Step 2 answers two questions: *what can this machine actually run*, and *what command decides whether the
work is good*. Both get recorded in the Master Plan so nothing re-derives them.

## Probing

Run `scripts/probe_env.sh <repo-root> > <scratch>/probe.json` and read from the file. It is read-only: it
never installs and never chooses the verification command.

**Record the conclusions in the Master Plan, never the dump.** The probe reports every toolchain it found in
every search directory, every listening socket and the whole repo scan; on a monorepo that is several KB of
JSON. The plan comment is re-read on every compaction recovery and by every human who opens the issue, so a
pasted probe is paid for on each recovery and skimmed past by every reader. What belongs in the plan is the
classification below — found current / brought up to date / set up from zero / unprovisionable — plus the
scratch path, which is what later steps consult when they need a detail back.

Two rules follow from what it returns:

* **An item is `absent` only if it appears in none of the searched directories.** The probe deliberately
  looks beyond `$PATH` — `$HOME/.local/bin`, `$HOME/bin`, version-manager roots. A perfectly usable
  toolchain sitting outside `$PATH` has been mistaken for a missing one, turning a five-minute provision
  into a reported blocker.
* **Provision every toolchain the repo's manifests declare**, not only what this batch appears to need.
  Which tiers you can run is a property of the environment, and you decide it once — discovering a missing
  compiler at merge time costs far more than installing it at baseline.

## Provisioning

An incomplete environment is the normal starting state of a run. Classify each item *present and current* /
*present but stale* / *absent*, then act (Rule 10):

* **Stale** → bring it up to date: install or refresh dependencies from the lockfile, sync config against
  its example for new keys, pull or rebuild images, run migrations.
* **Absent** → set it up from zero, preferring the repo's own bootstrap path (devcontainer, compose files,
  Makefile or package-script setup targets, `scripts/*.sh`) over improvised installs.
* **No root?** The probe already answered that. Without it, use user-space routes: toolchain tarballs or
  version managers into `$HOME`, rootless container runtimes, service alternatives the repo already
  supports.
* **Config values** — take dev-safe credentials from CI's `env:` blocks, which `scripts/ci_recipe.sh`
  extracts. CI is the authoritative statement of what values the test suite expects; inventing your own is
  guesswork that ages badly. Real third-party secrets are the one thing that can never be synthesised.
* **Prove each piece by using it** — start the service and hit its healthcheck, run one real test — never
  by `--version`. A version string has passed for a database with no accessible socket and an encryption
  key that decoded to the wrong length.

**"Unprovisionable" is a verdict earned by a failed attempt,** never by observation alone: the fetch was
actually tried and there is no network or registry access, root is genuinely required and there is no
passwordless sudo *and* no user-space alternative, or the missing piece is a credential only the user holds.
Record each with the failed attempt and the exact commands the user must run. The consequence is
**per-issue, not per-run**: it excludes only the issues whose acceptance criteria cannot be exercised
without it. The whole run stops only when nothing in the batch remains verifiable.

## The verification command

Run `scripts/ci_recipe.sh <repo-root> > <scratch>/ci-recipe.txt` and read from the file — it prints every
run body of every job of every workflow, twice (once rendered, once as JSON), which is a lot of context for
the handful of lines that turn out to be the gate. **The gate is CI's, not the repo's convenience scripts.**
Where CI runs a stricter variant of a local command — coverage thresholds, race detection, a frozen
lockfile, `CI=1` — the stricter variant is this run's verification command.

This is the single most expensive thing to get wrong. A local suite that is weaker than CI's lets a
subagent report green, the orchestrator confirm green, and the integration branch go red after the merge —
after which the failure has to be diagnosed against a tree that now contains several issues' changes.

Step 2 ends by writing `<scratch>/verify.sh` — the literal command set, in one executable file — and
recording its absolute path as `VERIFY` in the Master Plan. Every Brief's finish checklist names that path.
Where the repo already ships such a script (`.claude/verify.sh`, `scripts/verify*.sh`), use it and extend it
rather than writing a competing one.

## The baseline, and the probe worktree

Enumerate the gated units once into a two-column TSV (`unit<TAB>command`) and run them with
`scripts/run_units.sh`. Never judge pass/fail through a pager or a truncating pipe — a baseline piped
through `tail` has reported exit 0 for a failing run, which is worse than having no baseline at all.
Classify every failure in the Master Plan's units table.

Then cut a **throwaway worktree at `BASELINE_SHA`** and rehearse there, before any issue is dispatched:

1. Run the candidate bootstrap commands.
2. Run `verify.sh`.
3. Iterate until the result matches the baseline taken in the main checkout.
4. Discard the worktree.

Two artifacts survive into every Brief: the **ordered bootstrap command list** that actually worked, and the
list of **commands that lie in a fresh worktree** — anything whose output is misleading before the tree is
built, paired with the aggregate to use instead. A fresh worktree shares the repository's refs but not its
build output, so per-package checks routinely report errors that belong to unbuilt siblings. An executor
that cannot tell those apart will either silence them with casts or report them as its own regression.

Rehearsing also settles the plan's provenance: any generator, scaffold or bootstrap command the plan intends
to prescribe gets run once, here, and its real behaviour recorded in the Master Plan's *Verified facts*
table. A command that goes interactive, or that a repo has quietly stopped using, is discovered now — at a
cost of one throwaway worktree — rather than at implementation time in a tree that already has changes in it.

## The Stop-hook attestation

This machine's loop-until-done gate, when installed, blocks the turn from ending once commits have happened
until tests and lint are clean, everything is committed and pushed, and `.claude/.done` is attested — or
`.claude/.blocked` is written. Step 6 folds this in.

If `~/.claude/hooks/loop-until-done.sh` does not exist, skip the attestation entirely rather than writing a
marker file into a repo that has no gate to read it.
