# Engineering Harness

Project-local Codex skills and enforcement tooling.

## Architecture Docs Keeper

`.agents/skills/architecture-docs-keeper` maintains architecture maps, plans,
specifications, journals, decisions, and their internal document graph.

Open this repository in Codex to load the skill at project scope. No user-level
installation is required. Trust the project and review `.codex/hooks.json` with
`/hooks` before relying on the turn-completion gate.

Run the project skill checks:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s .agents/skills/architecture-docs-keeper/tests -v
scripts/docs-guard .
```
