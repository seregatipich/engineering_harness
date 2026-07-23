# Skills

Claude Code skills available on this machine. Each subdirectory is one skill, holding a
`SKILL.md` whose frontmatter declares its `name` and the `description` Claude matches against to
decide when the skill applies.

| Skill | What it does |
| --- | --- |
| [`work-next-issue`](work-next-issue/) | Selects the next GitHub issue by milestone or priority, researches it, posts the findings on the issue, then implements it test-first on a branch. |
| [`architecture-blueprint-generator`](architecture-blueprint-generator/) | Analyzes a codebase and writes `Project_Architecture_Blueprint.md` documenting its stack, components, layers, and extension points. |

## Install

Claude Code discovers global skills in `~/.claude/skills/`. Symlink each skill **directory**
(not its `SKILL.md`) so that supporting files added later — `references/`, `scripts/`, assets —
come along automatically:

```sh
REPO="$(git rev-parse --show-toplevel)"
mkdir -p ~/.claude/skills
for skill in "$REPO"/skills/*/; do
  ln -sfn "${skill%/}" ~/.claude/skills/"$(basename "$skill")"
done
```

Re-run it after adding a skill here. `ln -sfn` replaces an existing link, so it is safe to
repeat. The links store absolute paths — moving or deleting this repository disables every
skill, so re-run the loop after relocating the clone.

## Verify

```sh
ls -l ~/.claude/skills/                        # → symlinks into …/engineering_harness/skills/
head -3 ~/.claude/skills/work-next-issue/SKILL.md   # frontmatter reads through the link
```

Skills are discovered at session start. In a **new** session, each one appears in the skill list
and can be invoked by name — `/work-next-issue`, `/architecture-blueprint-generator` — or
triggered automatically when a request matches its `description`.

## Adding a skill

Create `skills/<name>/SKILL.md` with frontmatter:

```yaml
---
name: <name>                     # must match the directory name
description: <what it does, plus the phrasings that should trigger it>
argument-hint: "<optional, shown for slash-command arguments>"
---
```

Write the body as instructions addressed to Claude. Then re-run the install loop above and start
a new session.
