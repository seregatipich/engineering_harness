# engineering_harness

My [Claude Code](https://code.claude.com/docs/en/) configuration, kept in one repository and
installed onto a machine with symlinks. Editing a file here changes Claude's behaviour
everywhere — there is no copy step to forget.

```text
engineering_harness/
├── rules/
│   ├── CLAUDE_global.md    # instructions loaded in every session, in every project
│   └── README.md
└── skills/
    ├── work-next-issue/SKILL.md
    ├── architecture-blueprint-generator/SKILL.md
    └── README.md
```

| This repo | Installs to | Scope |
| --- | --- | --- |
| `rules/CLAUDE_global.md` | `~/.claude/CLAUDE.md` | User instructions — all your projects |
| `skills/<name>/` | `~/.claude/skills/<name>/` | Personal skills — all your projects |

Both are the *user* scope: personal to you, applied to every repository you open. Nothing here
is committed into the projects you work on.

## Install

Clone the repo somewhere permanent, then run this from inside it:

```sh
REPO="$(git rev-parse --show-toplevel)"

# Rules → ~/.claude/CLAUDE.md
ln -sfn "$REPO/rules/CLAUDE_global.md" ~/.claude/CLAUDE.md

# Skills → ~/.claude/skills/<name>
mkdir -p ~/.claude/skills
for skill in "$REPO"/skills/*/; do
  ln -sfn "${skill%/}" ~/.claude/skills/"$(basename "$skill")"
done
```

Claude Code supports this directly: a skill entry under `~/.claude/skills/` may be a symlink to a
directory elsewhere on disk, and Claude follows it to read `SKILL.md`. Link the skill
**directory**, not the `SKILL.md` inside it, so supporting files added later — `references/`,
`scripts/`, templates — come along without touching the install.

`ln -sfn` replaces an existing link, so the whole block is safe to re-run. Do that after adding a
skill or moving the clone.

**Before you run it**, check whether `~/.claude/CLAUDE.md` already exists as a *regular file*. If
it does, it holds instructions that exist nowhere else — merge them into `rules/CLAUDE_global.md`
first, because the symlink replaces it.

## Verify

```sh
ls -l ~/.claude/CLAUDE.md ~/.claude/skills/
```

Every entry should be a symlink pointing back into this repo. Then, inside a Claude Code session:

- `/context` lists the files actually loaded — `CLAUDE.md` should appear under **Memory files**.
- Type `/` and confirm `work-next-issue` and `architecture-blueprint-generator` are in the menu.

If a skill is listed, it can be invoked as `/work-next-issue`, or Claude loads it on its own when
a request matches its `description`.

## How it loads

**Rules** are read at the start of every session. Claude Code concatenates instruction files from
broadest to most specific: managed policy, then `~/.claude/CLAUDE.md` (this repo), then a
project's own `CLAUDE.md`. The project's file is read last, so it wins where the two disagree.
This is context, not enforcement — keep instructions specific and concrete, and keep the file
short. Under ~200 lines is the guidance; longer files reduce how reliably they're followed.

**Skills** cost nothing until used: only the name and `description` sit in context, and the body
loads when the skill is invoked. That is why long procedures belong in a skill rather than in
`CLAUDE_global.md`.

Claude Code watches `~/.claude/skills/` and picks up added, edited, or removed skills **without a
restart**. The one exception is bootstrapping: if `~/.claude/skills/` did not exist when the
session started, creating it requires restarting Claude Code before the directory is watched. So
on a first-time install, restart once.

Changes to `~/.claude/CLAUDE.md` apply to the next session.

## Adding a skill

Create `skills/<name>/SKILL.md`:

```yaml
---
description: What it does and when to use it — Claude matches against this to decide when to load it. Put the key use case first.
argument-hint: "[optional] shown during autocomplete"
---

Instructions addressed to Claude.
```

All frontmatter fields are optional; `description` is the one that matters. The **directory name**
becomes the command you type (`skills/deploy-staging/` → `/deploy-staging`) — a `name:` field only
sets the label shown in listings, it does not rename the command. Keep `SKILL.md` under ~500 lines
and move reference material into sibling files.

Then re-run the install loop above so the new skill is linked.

## Uninstall

```sh
rm ~/.claude/CLAUDE.md
rm ~/.claude/skills/work-next-issue ~/.claude/skills/architecture-blueprint-generator
```

These remove only the symlinks. The real files stay in this repo.

## Caveats

- **The clone must stay put.** The links store absolute paths, so moving or deleting this
  repository silently disables the rules and every skill. Re-run the install block after
  relocating it.
- **Windows** needs Administrator privileges or Developer Mode to create symlinks. Without those,
  copy instead of linking — and re-copy after every edit.
- **Cloud and Cowork sessions don't read `~/.claude/skills/`.** Scheduled routines and web
  sessions start fresh on a remote machine, so a skill that lives only here is reported as not
  found. Enable it for your account, or ship it as a plugin, if you need it there.
- These are user-scoped personal settings. To share this set with other people, package it as a
  [plugin](https://code.claude.com/docs/en/plugins) and distribute it through a marketplace
  instead of asking them to symlink your repo.

Per-directory detail lives in [`rules/README.md`](rules/README.md) and
[`skills/README.md`](skills/README.md).
