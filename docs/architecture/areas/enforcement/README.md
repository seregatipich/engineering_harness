---
doc_id: architecture.area.enforcement
doc_type: architecture-area
title: Enforcement
status: active
parent_id: architecture.areas.index
relations:
  - type: specified-by
    target_id: specification.architecture-documentation-system-v2
---

# Enforcement

## Responsibility

The enforcement area owns executable validation and the Codex lifecycle adapter that decides when repository work may complete.

## Boundaries

It accepts repository paths, Git state, Markdown, JSON catalogs, and Codex hook payloads. It emits deterministic files, process diagnostics, exit statuses, or hook responses; agent guidance and project integration remain separate areas.

## Entry points

The public entry points are the project skill's `docs_guard.py` subcommands, the `scripts/docs-guard` audit wrapper, and the lifecycle commands declared in `.codex/hooks.json`.

## Components

`documentation.guard` implements the schema, graph, generator, migration, and audit CLI. `documentation.lifecycle-hooks` captures per-turn state and adapts lifecycle events to journal and guard checks.

## Dependencies

The lifecycle adapter depends on the guard. Both use Python's standard library and local Git; neither imports a third-party runtime package.

## Data and control flow

The hook records a Git snapshot on `UserPromptSubmit`, computes attributable changes on `Stop`, requires journals, then runs full audit and generated-state checks for either documentation-only or full changes. Direct CLI callers bypass hook state and invoke guard subcommands against an explicit repository.

## Security and operations

Path traversal, unsafe glob forms, symlink escapes, malformed input, and unresolved graph targets are rejected. Subprocesses avoid shell interpolation and use bounded timeouts; failures contain actionable commands and capped output.

## Related documentation

<!-- docs:links:start -->
- Parent: [Architecture areas](../README.md)
- Children:
  - [Documentation guard](components/documentation.guard.md)
  - [Documentation lifecycle hooks](components/documentation.lifecycle-hooks.md)
- Related:
  - specified-by: [Architecture documentation system v2](../../../specifications/architecture-documentation-system-v2.md)
- Backlinks: None.
<!-- docs:links:end -->
