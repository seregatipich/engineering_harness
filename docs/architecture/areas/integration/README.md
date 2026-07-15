---
doc_id: architecture.area.integration
doc_type: architecture-area
title: Project integration
status: active
parent_id: architecture.areas.index
relations:
  - type: specified-by
    target_id: specification.architecture-documentation-system-v2
---

# Project integration

## Responsibility

The integration area owns the repository policy, contributor entry points, local Git gates, CI gate, licensing, and generated-file hygiene that make the checked-in documentation skill part of this project.

## Boundaries

It does not implement document validation or Codex lifecycle attribution. Those executable concerns remain in enforcement, while the skill workflow and normative standard remain in guidance.

## Entry points

`README.md` introduces project-scoped use, `AGENTS.md` requires the workflow for editable tasks, `lefthook.yml` runs local checks, and `.github/workflows/docs-guard.yml` runs delivery checks. `LICENSE` and `.gitignore` define redistribution terms and local artifact hygiene.

## Components

`documentation.project-integration` owns the six project-level source files and the repository contract that verifies scope, exact ownership, wrapper execution, guard parity, and CI wiring.

## Dependencies

Project integration depends on `documentation.guard`: local and CI commands execute the repository guard copy, which remains byte-identical to the project skill's canonical guard.

## Data and control flow

Codex discovers the checked-in skill from `.agents/skills`. Contributor policy points editable tasks at that skill. Lefthook checks links and generated state before commit, then runs the change-aware wrapper before push. GitHub Actions executes all skill tests, the repository contract, link and generation checks, a full audit, and a base-aware audit.

## Security and operations

All tracked paths are repository-relative and contain no credential. CI validates event SHAs before using them, falls back to the remote default-branch merge base, and finally uses the empty-tree object so change auditing remains active for initial history.

## Related documentation

<!-- docs:links:start -->
- Parent: [Architecture areas](../README.md)
- Children:
  - [Documentation project integration](components/documentation.project-integration.md)
- Related:
  - specified-by: [Architecture documentation system v2](../../../specifications/architecture-documentation-system-v2.md)
- Backlinks: None.
<!-- docs:links:end -->
