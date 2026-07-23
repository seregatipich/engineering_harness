# Rules

`CLAUDE_global.md` is the **global Claude Code rule set** for this machine — scope discipline,
code and documentation standards, testing requirements, the git branching policy, and where
working files may live.

Claude Code reads `~/.claude/CLAUDE.md` at the start of every session, in every repository. A
project's own `CLAUDE.md` wins wherever the two conflict.

## Install

Symlink it, so editing the file here takes effect everywhere with no re-install step:

```sh
REPO="$(git rev-parse --show-toplevel)"
ln -sfn "$REPO/rules/CLAUDE_global.md" ~/.claude/CLAUDE.md
```

`ln -sfn` replaces an existing link. If `~/.claude/CLAUDE.md` is a **regular file**, it holds
rules that only exist there — back it up or merge it into `CLAUDE_global.md` before overwriting.

The link stores an absolute path, so moving or deleting this repository silently disables the
global rules. Re-run the command after relocating the clone.

## Verify

```sh
ls -l ~/.claude/CLAUDE.md   # → …/engineering_harness/rules/CLAUDE_global.md
head -1 ~/.claude/CLAUDE.md # → "# Global Claude Rules"
```

Rules load at session start, so start a **new** session to pick up the install. Confirm it is
live by asking Claude what its global rules are — the answer should reflect this file, for
example the `main`/`dev` branching policy or the no-TODO-comments rule.

## Editing

Changes apply to every repository on this machine the next time a session starts. Keep the file
general: anything true of only one project belongs in that project's `CLAUDE.md` instead.
