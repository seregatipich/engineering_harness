---
doc_id: operations.installation
doc_type: operations
title: Use the project-local architecture documentation skill
status: active
parent_id: operations.root
relations:
  - type: documents
    target_id: architecture.component.documentation.project-integration
  - type: decided-by
    target_id: decision.0003.project-scoped-skill
  - type: related
    target_id: architecture.deployment.local-codex
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
---

# Use the project-local architecture documentation skill

## Procedure

1. Use a checkout containing `.agents/skills/architecture-docs-keeper` and `.codex/hooks.json`.
2. Open the checkout in Codex so project-scope skill discovery can load `$architecture-docs-keeper`.
3. Trust the repository, inspect `.codex/hooks.json` with `/hooks`, and enable the declared project hooks.
4. Confirm that the skill metadata names `architecture-docs-keeper` and that startup context states the documentation invariant.
5. Run the skill tests, repository contract, links, generated check, full audit, and change-aware audit from the repository root.

## Prerequisites

The checkout requires Python 3, Git, readable project files, and a Codex installation that supports project skills and hooks. Local pre-commit and pre-push execution additionally requires Lefthook in the contributor's Git workflow.

## Safety boundaries

Use the checked-in project skill directly. Do not create a marketplace entry, plugin installation, or user-level copy as a substitute. Review project hooks before trusting them, and keep `.codex/scripts/docs_guard.py` byte-identical to `.agents/skills/architecture-docs-keeper/scripts/docs_guard.py`.

## Verification

Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .agents/skills/architecture-docs-keeper/tests -v` and `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_repository_contract.py -v`. Then run `python3 .codex/scripts/docs_guard.py links . --internal`, `generate --check .`, `audit . --format human`, and `scripts/docs-guard .`. A startup event should emit project documentation context, and the hook suite should prove that an attributable change without required journals is blocked.

## Rollback

Disable the project hooks in Codex if immediate containment is required, then restore the previous tracked skill and enforcement revision. There is no marketplace or user-level installation to remove. Do not delete repository documentation records merely to roll back execution.

## Escalation

If project discovery fails, inspect the skill front matter and `.agents/skills/architecture-docs-keeper/agents/openai.yaml`. If hooks fail, inspect `.codex/hooks.json`, the Git-root command, `<absolute-git-dir>/codex-project-hook-state`, and hook stderr. If guard parity or contracts fail, restore the project-skill and `.codex` guard from the same revision before retrying validation.

## Related documentation

<!-- docs:links:start -->
- Parent: [Operations](README.md)
- Children: None.
- Related:
  - decided-by: [Keep the documentation skill project-scoped](../decisions/0003-project-scoped-skill.md)
  - documents: [Documentation project integration](../architecture/areas/integration/components/documentation.project-integration.md)
  - related: [Local Codex deployment](../architecture/system/deployments/local-codex.md)
  - verified-by: [Dogfood architecture-docs-keeper v2](../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks: None.
<!-- docs:links:end -->
