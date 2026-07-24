# engineering_harness

This repository is a [Claude Code](https://code.claude.com/docs/en/) configuration.
Implemented to make my agent harness easily accessible across multiple machines & users.

Users {ask agents to | manually} install the hooks, skills and rules according to the scope of their choice.

Repository structure:
```text
engineering_harness/
├── rules/                  # global instructions loaded in every session, in every project
│   └── CLAUDE_global.md
├── skills/                 # one directory per skill, each with a SKILL.md
│   ├── work-next-issue/
│   └── ...
└── hooks/                  # shell hooks (e.g. the loop-until-done gate)
    ├── loop-until-done.sh
    └── ...
```

| This repo | Installs to | Scope |
| --- | --- | --- |
| `rules/CLAUDE_global.md` | `~/.claude/CLAUDE.md` | User instructions — all your projects |
| `skills/<name>/` | `~/.claude/skills/<name>/` | Personal skills — all your projects |
| `hooks/*.sh` | `~/.claude/hooks/` + `~/.claude/settings.json` | The loop-until-done gate — all your projects |