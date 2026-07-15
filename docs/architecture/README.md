---
doc_id: architecture.root
doc_type: architecture-root
title: Architecture
status: active
parent_id: docs.root
relations:
  - type: specified-by
    target_id: specification.architecture-documentation-system-v2
  - type: decided-by
    target_id: decision.0002.layered-enforcement
---

# Architecture

## Scope

The architecture map covers the validator CLI, Codex lifecycle adapter, project-local workflow skill, and repository integration wiring. The authored inventory selects 19 concrete runtime, test, guidance, hook, policy, license, hygiene, and workflow files owned by those four components.

## System summary

`architecture-docs-keeper` is checked into `.agents/skills` and discovered by Codex at project scope. Its Python validator reads repository documentation and Git state, its hook invokes validation at lifecycle boundaries, its skill defines the agent workflow, and project configuration exposes local and CI enforcement gates without a user-level installation.

## Areas

The enforcement area owns runtime validation and lifecycle adaptation. The guidance area owns the skill instructions, model metadata, and normative standard. The integration area owns project policy, contributor entry points, licensing, ignored artifacts, and local or CI gates.

## Runtime boundaries

The guard and hook are finite Python processes using the standard library. The guard reads and, for explicit bootstrap, migration, or generation modes, writes repository files. The hook receives JSON on standard input, persists hashed turn baselines under the repository's absolute Git metadata directory or a controlled test override, and emits Codex hook JSON on standard output.

## Cross-cutting concerns

Stable document IDs, POSIX repository paths, graph-backed navigation, Git-derived change attribution, path containment, append-only history, and deterministic output apply to every component. Validation avoids third-party runtime dependencies.

## Coverage and exclusions

`docs/architecture/catalog.json` lists 19 selected non-documentation files explicitly and has no exclusions. The project README, license, and Git ignore rules are owned by project integration. Generated `docs/catalog.json` and authored documentation remain outside the implementation inventory because the guard validates them through the document graph.

## Maintenance

Changes to selected files require a task journal and the owning component journal. Skill and repository contract tests lock project discovery, required resources, exact ownership, local guard parity, hook wiring, and workflow behavior; generated links and the graph catalog are refreshed with `generate --write`.

## Related documentation

<!-- docs:links:start -->
- Parent: [Documentation](../README.md)
- Children:
  - [Architecture areas](areas/README.md)
  - [Architecture concepts](concepts/README.md)
  - [Architecture flows](flows/README.md)
  - [System](system/README.md)
- Related:
  - decided-by: [Enforce documentation at layered lifecycle gates](../decisions/0002-layered-enforcement.md)
  - specified-by: [Architecture documentation system v2](../specifications/architecture-documentation-system-v2.md)
- Backlinks: None.
<!-- docs:links:end -->
