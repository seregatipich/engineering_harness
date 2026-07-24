# Hooks

A paired **loop-until-done** gate for Claude Code. Together the two scripts keep a turn from
ending until the work is verifiably complete — or until you record an honest block.

| Script | Hook event | Role |
| --- | --- | --- |
| `loop-protocol-context.sh` | `SessionStart` | Arms a per-session baseline and injects the loop-protocol briefing into context. |
| `loop-until-done.sh` | `Stop` | The gate. Refuses to stop until tests pass, lint/format is clean, work is committed and pushed, and `.claude/.done` is attested — or `.claude/.blocked` is written. |

Install **both or neither** — the Stop gate reads the baseline the SessionStart hook writes.

## What you are opting into

- The Stop hook **blocks turns from ending** until its definition of done holds. Expect Claude to
  keep working (or ask you to unblock it) rather than stopping early.
- It enforces the **direct-merge git flow** from `rules/CLAUDE_global.md`: `feature/<name>` off
  `dev`, merge into `dev`, promote `dev` → `main`; never commit to or branch from `main`/`master`.
- It auto-detects and runs project checks (`ruff`/`pytest` for Python, `npm run lint`/`npm test`
  for Node, or an executable `.claude/verify.sh` / `scripts/verify.sh` when present).
- Loop state lives under `~/.claude/loop-state/` and is auto-pruned after 30 days. The markers
  `.claude/.done` and `.claude/.blocked` are added to each repo's `.git/info/exclude`
  automatically, so they never touch the tracked tree.
- A couple of user-facing messages are in Russian — edit the strings in `loop-until-done.sh` if
  you want them in another language.

Needs `git`, plus `jq` **or** `python3` for reliable JSON parsing (the scripts fall back to a
minimal parser without either, but installing one is strongly recommended).

## Install

Two parts: symlink the scripts to a stable path (so editing them here changes behaviour
everywhere, matching the rest of this repo), then register those paths in `settings.json`.

### 1. Symlink the scripts

```sh
REPO="$(git rev-parse --show-toplevel)"
mkdir -p ~/.claude/hooks
ln -sfn "$REPO/hooks/loop-protocol-context.sh" ~/.claude/hooks/loop-protocol-context.sh
ln -sfn "$REPO/hooks/loop-until-done.sh"       ~/.claude/hooks/loop-until-done.sh
```

`ln -sfn` replaces an existing link, so the block is safe to re-run. The links store absolute
paths — re-run it after relocating the clone.

### 2. Register them in `settings.json`

Unlike rules and skills, `settings.json` cannot be a whole-file symlink — it holds your other
settings too — so **merge** this `hooks` block into `~/.claude/settings.json` (create the file
with just this object if it does not exist; if a `hooks` key is already there, add these two
events to it):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "$HOME/.claude/hooks/loop-protocol-context.sh" }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "$HOME/.claude/hooks/loop-until-done.sh" }
        ]
      }
    ]
  }
}
```

The commands reference the stable `~/.claude/hooks/` symlinks, so edits to the scripts in this
repo take effect with no further changes.

## Verify

```sh
ls -l ~/.claude/hooks/                        # → symlinks into …/engineering_harness/hooks/
jq '.hooks | keys' ~/.claude/settings.json    # → ["SessionStart","Stop"]
```

Hooks load at startup, so **restart Claude Code**. Then, in a git repo, make a change and confirm
the turn will not end until checks pass and you create `.claude/.done` (or write `.claude/.blocked`
to exit honestly).

## Tuning

`loop-until-done.sh` reads these environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `CLAUDE_LOOP_MAX_ITERS` | `12` | Consecutive blocks before the backstop lets the turn end. |
| `CLAUDE_LOOP_LINT_TIMEOUT` | `120` | Seconds allowed for lint. |
| `CLAUDE_LOOP_TEST_TIMEOUT` | `300` | Seconds allowed for tests. |
| `CLAUDE_LOOP_VERIFY_TIMEOUT` | `480` | Seconds allowed for a custom `verify.sh`. |
| `CLAUDE_LOOP_GIT_TIMEOUT` | `20` | Seconds allowed for each git call. |

To control verification per repository, add an executable `.claude/verify.sh` (or
`scripts/verify.sh`); the gate runs it instead of the language auto-detection.

## Uninstall

```sh
rm ~/.claude/hooks/loop-protocol-context.sh ~/.claude/hooks/loop-until-done.sh
```

Then remove the `SessionStart` and `Stop` entries from `~/.claude/settings.json`. The scripts
themselves stay in this repo.
