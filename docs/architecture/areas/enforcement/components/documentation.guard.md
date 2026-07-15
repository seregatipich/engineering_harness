---
doc_id: architecture.component.documentation.guard
doc_type: architecture-component
title: Documentation guard
status: active
parent_id: architecture.area.enforcement
profile: application-runtime
relations:
  - type: specified-by
    target_id: specification.architecture-documentation-system-v2
  - type: decided-by
    target_id: decision.0001.stdlib-validator
  - type: decided-by
    target_id: decision.0002.layered-enforcement
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
  - type: related
    target_id: architecture.concept.document-graph
---

# Documentation guard

## Summary

The documentation guard is a standard-library Python CLI implementing schema-v2 bootstrap, migration, generation, link validation, full audit, and Git-base reconciliation.

## Responsibility

It owns parsing Markdown front matter, validating the document and component graphs, expanding exact inventory patterns, enforcing source ownership and required sections, generating navigation and `docs/catalog.json`, and protecting append-only records during base audits.

## Boundaries

The component owns the canonical guard at `.agents/skills/architecture-docs-keeper/scripts/docs_guard.py`, its byte-identical `.codex/scripts/docs_guard.py` copy, and the executable `scripts/docs-guard` wrapper. It does not own Codex event attribution, skill guidance, or project and CI configuration.

## Entry points and public interfaces

The primary interface is `docs_guard.py` with `bootstrap`, `migrate`, `generate`, `links`, and `audit` subcommands. The audit command accepts an optional `--base` Git object and human or JSON output. `scripts/docs-guard` checks generated state, resolves an explicit, upstream, known default-branch, or empty-tree base, and forwards trailing audit arguments.

## Dependencies

Runtime imports come exclusively from Python's standard library. Git subprocesses provide tracked and untracked paths, changes, historical document bodies, and object content. The filesystem provides authored Markdown and JSON catalogs.

## Data and control flow

The guard loads every Markdown document, builds identity and parent maps, resolves typed relations, validates links and required sections, expands the architecture inventory, and compares generated projections. Write modes preflight safety before changing files; base audit compares current state with Git history and requires changed task and component journals.

## State and side effects

Read-only commands retain no state. `generate --write` replaces only derived catalog and marker blocks. Bootstrap and migration create or transform documented repository files after collision and containment checks. Each invocation terminates after one operation.

## Failure modes and recovery

Schema, graph, link, inventory, path, history, or drift errors produce stable diagnostic codes and a nonzero process status. Repository-not-found and invocation errors use a distinct status. Recovery consists of correcting the cited authored source or restoring safe input, regenerating, and rerunning the same command.

## Security and permissions

Repository patterns reject absolute paths, parent traversal, backslashes, ambiguous glob constructs, and unsafe double-star placement. Source and document symlinks cannot escape the repository. Subprocess calls use argument arrays, bounded timeouts, and no shell.

## Observability and operations

Human diagnostics include path, line when available, issue code, and message. JSON audit output includes issues, an `ok` flag, document and ownership counts, changed-path count, and the explicit statement that semantic accuracy remains human-verifiable.

## Tests and evidence

`test_docs_guard.py` covers graph, catalog, links, generation, bootstrap, migration, and CLI behavior. `test_docs_guard_adversarial.py` covers false-pass, false-fail, unsafe glob, symlink, marker, atomic migration, history, reverse graph, and canonical-schema boundaries.

## Change impact

A guard change requires synchronizing `.codex/scripts/docs_guard.py`, preserving wrapper behavior, running both guard suites, and reviewing schema, standard, generated artifacts, hooks, and project integration for affected contracts.

## Profile requirements

Startup is a direct Python command with an explicit subcommand and repository; shutdown is process exit after validation or generation. Configuration is supplied through CLI arguments and repository files. One invocation operates synchronously without shared in-process concurrency. Deployment consists of the project-skill script, a byte-identical repository gate copy, and the shell wrapper verified by the repository contract test.

## Related documentation

<!-- docs:links:start -->
- Parent: [Enforcement](../README.md)
- Children: None.
- Related:
  - decided-by: [Use a standard-library documentation validator](../../../../decisions/0001-stdlib-validator.md)
  - decided-by: [Enforce documentation at layered lifecycle gates](../../../../decisions/0002-layered-enforcement.md)
  - related: [Document graph](../../../concepts/document-graph.md)
  - specified-by: [Architecture documentation system v2](../../../../specifications/architecture-documentation-system-v2.md)
  - verified-by: [Dogfood architecture-docs-keeper v2](../../../../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks:
  - changes: [Dogfood architecture-docs-keeper v2](../../../../journals/tasks/20260715-architecture-docs-keeper-v2.md)
  - changes: [Dogfood architecture-docs-keeper v2](../../../../plans/20260715-architecture-docs-keeper-v2.md)
  - depends-on: [Documentation lifecycle hooks](documentation.lifecycle-hooks.md)
  - depends-on: [Documentation project integration](../../integration/components/documentation.project-integration.md)
  - depends-on: [Documentation workflow skill](../../guidance/components/documentation.workflow-skill.md)
  - depends-on: [Local Codex deployment](../../../system/deployments/local-codex.md)
  - documents: [Document graph](../../../concepts/document-graph.md)
  - documents: [Runtime containers](../../../system/containers.md)
  - documents: [Local documentation lifecycle](../../../flows/local-documentation-lifecycle.md)
  - documents: [Validate the project skill and repository integration](../../../../development/validation.md)
  - documents: [Documentation guard journal](../../../../journals/components/documentation.guard.md)
<!-- docs:links:end -->
