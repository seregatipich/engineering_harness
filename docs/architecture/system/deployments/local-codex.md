---
doc_id: architecture.deployment.local-codex
doc_type: architecture-deployment
title: Local Codex deployment
status: active
parent_id: architecture.deployments.index
relations:
  - type: documents
    target_id: architecture.component.documentation.lifecycle-hooks
  - type: documents
    target_id: architecture.component.documentation.project-integration
  - type: depends-on
    target_id: architecture.component.documentation.guard
  - type: decided-by
    target_id: decision.0002.layered-enforcement
  - type: decided-by
    target_id: decision.0003.project-scoped-skill
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
---

# Local Codex deployment

## Environment

The deployment is a Git repository consumed by local Codex, local Git hooks, and GitHub-hosted Ubuntu runners. Python 3 and Git are the only runtime tools required by the documentation checks.

## Deployed containers

The skill resides under `.agents/skills/architecture-docs-keeper`. Codex resolves and launches its `scripts/docs_hook.py` through `.codex/hooks.json`; direct and automated gates launch `.codex/scripts/docs_guard.py`. The Python processes are finite command containers, not persistent services.

## Configuration and secrets

The `.agents/skills` path and skill front matter provide project discovery, while `.codex/hooks.json` configures lifecycle execution. `AGENTS.md`, Lefthook, the shell wrapper, and the GitHub workflow configure enforcement. No tracked secret or user-level installation is required. Hook state defaults below the absolute Git metadata directory; `ARCHITECTURE_DOCS_KEEPER_STATE_DIR` is a controlled test override.

## Network and trust boundaries

Local validation needs no network. GitHub Actions checks out repository history and receives event SHAs from GitHub. Repository and event content are untrusted validator input; path and object checks prevent implicit trust in those values.

## Data stores

Tracked files store the skill, policies, tests, and documentation. Git stores historical bases and ephemeral turn snapshots in `codex-project-hook-state` beneath its absolute metadata directory. GitHub Actions keeps resolved base data within the audit step.

## Rollout and rollback

Rollout distributes the repository revision, opens it in Codex, reviews and trusts the project hooks, confirms skill and repository guard parity, then runs contract and guard gates. Rollback restores a prior repository revision; generated documents are recreated from authored records.

## Health and observability

Health is the combined status of skill tests, repository contract tests, internal links, generated check, full audit, and base audit. Hook and guard diagnostics identify the failing path, code, command, or lifecycle requirement.

## Recovery

Restore missing skill or integration files from Git, restore guard-copy parity, regenerate derived documentation, and rerun the complete validation sequence. Corrupt hook baselines can be discarded because prompt submission recreates them.

## Related documentation

<!-- docs:links:start -->
- Parent: [Deployments](README.md)
- Children: None.
- Related:
  - decided-by: [Enforce documentation at layered lifecycle gates](../../../decisions/0002-layered-enforcement.md)
  - decided-by: [Keep the documentation skill project-scoped](../../../decisions/0003-project-scoped-skill.md)
  - depends-on: [Documentation guard](../../areas/enforcement/components/documentation.guard.md)
  - documents: [Documentation lifecycle hooks](../../areas/enforcement/components/documentation.lifecycle-hooks.md)
  - documents: [Documentation project integration](../../areas/integration/components/documentation.project-integration.md)
  - verified-by: [Dogfood architecture-docs-keeper v2](../../../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks:
  - related: [Documentation project integration](../../areas/integration/components/documentation.project-integration.md)
  - related: [Runtime containers](../containers.md)
  - related: [Use the project-local architecture documentation skill](../../../operations/installation.md)
<!-- docs:links:end -->
