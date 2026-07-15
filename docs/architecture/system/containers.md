---
doc_id: architecture.container.runtime
doc_type: architecture-container
title: Runtime containers
status: active
parent_id: architecture.system.index
relations:
  - type: documents
    target_id: architecture.component.documentation.guard
  - type: documents
    target_id: architecture.component.documentation.lifecycle-hooks
  - type: related
    target_id: architecture.deployment.local-codex
---

# Runtime containers

## Runtime containers

The guard is a finite Python CLI. The lifecycle hook is a separate finite Python process launched by Codex. GitHub Actions and the shell wrapper start the guard as child processes rather than hosting a persistent service.

## Responsibilities

The guard validates and generates repository documentation. The hook attributes a turn's net changes, requires journals, classifies documentation-only or full changes, runs full audit plus generated-state checks for both classes, and converts failures into a blocking Codex response.

## Communication

CLI callers pass subcommands and repository paths through process arguments. The hook consumes one JSON object on standard input, resolves its adjacent project guard, resolves the repository's absolute Git metadata directory for writable state, invokes Git and the guard without a shell, and emits one JSON object on standard output.

## Data stores

The repository filesystem stores authored and generated documentation. Git stores revisions, working-tree status, and the default JSON baseline path under `<absolute-git-dir>/codex-project-hook-state/architecture-docs-keeper/turn-baselines`; successful or no-change Stop processing removes the snapshot, while a blocking failure preserves it for retry. `ARCHITECTURE_DOCS_KEEPER_STATE_DIR` overrides that root for controlled tests.

## Startup and shutdown

Each command starts with Python module initialization, performs one bounded operation, and exits with a conventional status. The hook uses configured timeouts; no daemon, socket, queue, or long-lived worker remains after process exit.

## Deployment mapping

The canonical guard and hook run from `.agents/skills/architecture-docs-keeper/scripts`. Repository gates run the byte-identical `.codex/scripts/docs_guard.py`, and Codex discovers lifecycle commands in `.codex/hooks.json` plus the workflow skill under `.agents/skills`.

## Failure and recovery

Guard validation errors require correcting authored records or source ownership and rerunning checks. Hook failures return actionable command diagnostics. Restoring byte parity and rerunning the contract suites recovers a drifted local deployment.

## Related documentation

<!-- docs:links:start -->
- Parent: [System](README.md)
- Children: None.
- Related:
  - documents: [Documentation guard](../areas/enforcement/components/documentation.guard.md)
  - documents: [Documentation lifecycle hooks](../areas/enforcement/components/documentation.lifecycle-hooks.md)
  - related: [Local Codex deployment](deployments/local-codex.md)
- Backlinks: None.
<!-- docs:links:end -->
