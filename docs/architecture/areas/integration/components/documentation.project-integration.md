---
doc_id: architecture.component.documentation.project-integration
doc_type: architecture-component
title: Documentation project integration
status: active
parent_id: architecture.area.integration
profile: infrastructure
relations:
  - type: depends-on
    target_id: architecture.component.documentation.guard
  - type: specified-by
    target_id: specification.architecture-documentation-system-v2
  - type: decided-by
    target_id: decision.0002.layered-enforcement
  - type: decided-by
    target_id: decision.0003.project-scoped-skill
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
  - type: related
    target_id: architecture.deployment.local-codex
---

# Documentation project integration

## Summary

The project-integration component exposes the checked-in documentation skill to contributors and enforces its contracts in local Git workflows and GitHub Actions without any user-level installation.

## Responsibility

It owns the project README, agent policy, MIT license, ignored local artifacts, Lefthook commands, and docs-guard workflow. The repository contract verifies project scope, exact catalog ownership, executable wrapper behavior, guard-copy parity, and CI commands.

## Boundaries

The component configures discovery, policy, hygiene, and execution but does not implement schema validation, agent guidance, or lifecycle attribution. Generated documentation and the executable wrapper are represented by their owning components rather than this integration component.

## Entry points and public interfaces

`README.md` tells contributors that Codex loads `.agents/skills/architecture-docs-keeper` at project scope and that no user-level installation is required. `AGENTS.md` requires `$architecture-docs-keeper` and `scripts/docs-guard .` for editable tasks. `lefthook.yml` defines pre-commit and pre-push gates. `.github/workflows/docs-guard.yml` defines push and pull-request validation. `LICENSE` exposes MIT terms, and `.gitignore` excludes bytecode caches and local operating-system metadata.

## Dependencies

The component depends on `documentation.guard`. CI also depends on a full Git checkout and GitHub event values for the pull-request base, previous push object, and repository default branch.

## Data and control flow

Project discovery reads the checked-in skill directly. Pre-commit invokes internal-link and generated-state checks; pre-push invokes `scripts/docs-guard`, which checks generated state and audits against an explicit or resolved Git base. CI discovers the skill tests, runs the repository contract, validates links and generated state, performs a full audit, then selects a valid event base, the remote default-branch merge base, or the empty-tree object for change audit.

## State and side effects

All owned files are tracked repository state. Lefthook and CI read the working tree and Git objects; their guard commands do not write authored documentation. CI writes only ephemeral runner state and step output.

## Failure modes and recovery

Missing project files, incorrect scope claims, guard-copy drift, invalid ownership, wrapper failures, stale generated output, broken links, or an audit failure block a contract or gate. Recovery restores the affected tracked file, regenerates projections when authored documents changed, and reruns the repository and documentation gates.

## Security and permissions

No owned file contains a secret. Commands resolve within the repository, CI rejects invalid event objects, and an empty-tree fallback avoids silently dropping base-aware validation when no suitable history exists.

## Observability and operations

The local wrapper prints guard diagnostics. Lefthook reports its named command status. GitHub Actions exposes test, link, generation, full-audit, and change-audit steps independently. Repository-contract failures identify scope, parity, ownership, wrapper, or workflow drift.

## Tests and evidence

`tests/test_repository_contract.py` verifies repository-scoped discovery without marketplace installation, byte-identical guard copies, executable wrapper arguments, exact ownership for all four components, file existence, and workflow test and base-resolution commands.

## Change impact

Changing any owned integration file requires the task journal, this component journal, the repository contract, and full plus base documentation audits. Workflow and Lefthook commands must remain compatible with the canonical project guard.

## Profile requirements

Provisioning is a trusted checkout opened in Codex; no separate package install or credential is required. Rollout consists of distributing the repository revision, trusting the project hooks, and running local and CI gates. Health is the combined contract and audit status. Scaling is one finite process per hook or CI step. Rollback restores the previous tracked revision. Disaster recovery restores the skill and configuration from Git and regenerates derived documentation from authored records.

## Related documentation

<!-- docs:links:start -->
- Parent: [Project integration](../README.md)
- Children: None.
- Related:
  - decided-by: [Enforce documentation at layered lifecycle gates](../../../../decisions/0002-layered-enforcement.md)
  - decided-by: [Keep the documentation skill project-scoped](../../../../decisions/0003-project-scoped-skill.md)
  - depends-on: [Documentation guard](../../enforcement/components/documentation.guard.md)
  - related: [Local Codex deployment](../../../system/deployments/local-codex.md)
  - specified-by: [Architecture documentation system v2](../../../../specifications/architecture-documentation-system-v2.md)
  - verified-by: [Dogfood architecture-docs-keeper v2](../../../../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks:
  - changes: [Dogfood architecture-docs-keeper v2](../../../../journals/tasks/20260715-architecture-docs-keeper-v2.md)
  - changes: [Dogfood architecture-docs-keeper v2](../../../../plans/20260715-architecture-docs-keeper-v2.md)
  - documents: [Local Codex deployment](../../../system/deployments/local-codex.md)
  - documents: [Local documentation lifecycle](../../../flows/local-documentation-lifecycle.md)
  - documents: [Documentation project integration journal](../../../../journals/components/documentation.project-integration.md)
  - documents: [Use the project-local architecture documentation skill](../../../../operations/installation.md)
<!-- docs:links:end -->
