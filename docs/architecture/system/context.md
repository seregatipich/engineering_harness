---
doc_id: architecture.context.system
doc_type: architecture-context
title: Engineering harness system context
status: active
parent_id: architecture.system.index
relations:
  - type: related
    target_id: architecture.concept.document-graph
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
---

# Engineering harness system context

## Purpose

The repository contains and verifies a project-local Codex skill that keeps architecture documentation synchronized with selected implementation and configuration files.

## External actors

Codex discovers the skill under `.agents/skills` and loads project hooks from `.codex/hooks.json`. Contributors invoke the repository wrapper or the guard CLI. GitHub Actions executes the same local guard and Python test files on pushes and pull requests.

## Trust boundaries

Repository content and hook JSON are untrusted input to the Python processes. Git object IDs and working-tree paths cross a subprocess boundary. Hook baseline files cross from the working tree into the repository's absolute Git metadata directory, outside normal source ownership.

## System interactions

Project discovery resolves `.agents/skills/architecture-docs-keeper`. Codex lifecycle events invoke its `docs_hook.py`; the hook captures Git state and calls the adjacent `docs_guard.py`. The CLI parses Markdown and JSON, compares the architecture inventory to Git-visible files, and produces diagnostics or deterministic generated artifacts.

## Data ownership

Authored Markdown owns engineering facts and graph relations. `docs/architecture/catalog.json` owns file-to-component assignment. Git owns revision history and change sets. `docs/catalog.json` and marker-delimited navigation are derived projections.

## Failure boundaries

Invalid JSON, unsafe paths, broken graph edges, stale generated output, uncovered inventory, missing journals, and failed subprocesses remain explicit errors. A missing hook baseline is non-blocking because the hook cannot reliably attribute pre-existing changes to the current turn.

## Evidence

The guard, adversarial, hook, skill contract, and repository contract suites exercise schema, graph, safety, lifecycle, project discovery, runtime resources, guard parity, ownership, and workflow behavior.

## Related documentation

<!-- docs:links:start -->
- Parent: [System](README.md)
- Children: None.
- Related:
  - related: [Document graph](../concepts/document-graph.md)
  - verified-by: [Dogfood architecture-docs-keeper v2](../../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks: None.
<!-- docs:links:end -->
