---
doc_id: architecture.component.documentation.lifecycle-hooks
doc_type: architecture-component
title: Documentation lifecycle hooks
status: active
parent_id: architecture.area.enforcement
profile: integration-adapter
relations:
  - type: depends-on
    target_id: architecture.component.documentation.guard
  - type: specified-by
    target_id: specification.architecture-documentation-system-v2
  - type: decided-by
    target_id: decision.0002.layered-enforcement
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
  - type: related
    target_id: architecture.flow.local-documentation-lifecycle
---

# Documentation lifecycle hooks

## Summary

The lifecycle adapter converts Codex hook events into concise policy context, per-turn Git baselines, journal requirements, guard commands, and a blocking Stop response when checks fail.

## Responsibility

It owns lifecycle JSON dispatch, Git snapshot capture, safe state persistence, net-change classification, catalog ownership matching, required task and component journal checks, guard subprocess execution, and Codex-compatible output.

## Boundaries

The component owns `.agents/skills/architecture-docs-keeper/scripts/docs_hook.py`, `.codex/hooks.json`, and `.agents/skills/architecture-docs-keeper/tests/test_docs_hook.py`. It delegates documentation semantics to the guard and does not modify repository documentation itself.

## Entry points and public interfaces

`.codex/hooks.json` resolves the checked-in hook through the Git root for `SessionStart`, `SubagentStart`, `UserPromptSubmit`, and `Stop`. Each invocation receives one JSON object on standard input. Context events emit additional developer context. Prompt submission records a baseline. Stop emits no block when attributable changes pass and emits `continue: false`, a stop reason, and a system message when they fail.

## Dependencies

The adapter depends on its sibling project-skill guard and local Git. `ARCHITECTURE_DOCS_KEEPER_GUARD` can replace the sibling path only for isolated test execution. By default, baselines use `codex-project-hook-state` under the repository's absolute Git metadata directory; `ARCHITECTURE_DOCS_KEEPER_STATE_DIR` provides a controlled test override. Catalog component patterns determine which changed source or test paths require component journals.

## Data and control flow

Prompt submission hashes modified, staged, and untracked paths plus their kinds and modes. Stop captures a second snapshot, subtracts the baseline, classifies relevant changes as docs-only or full, validates required journals, and runs the same locked full-audit and generated-state commands for either class.

## State and side effects

State is one atomic JSON baseline whose filename hashes session, turn, and working-directory identity beneath the project Git metadata or controlled override root. Files use restricted permissions. Stop deletes the snapshot after no changes or successful checks, preserves it after a blocking failure so the corrected turn can retry, and leaves repository mutation to the agent and explicit guard write commands.

## Failure modes and recovery

Malformed hook input returns a nonzero status on standard error. Missing repository or reliable baseline is non-blocking because attribution is unavailable. A missing adjacent guard, timeout, nonzero guard result, or journal gap becomes an actionable Stop failure; rerunning after correction recovers.

## Security and permissions

Opaque lifecycle identifiers are SHA-256 hashed before becoming filenames. Git paths reject traversal. Symlink and regular-file hashes include kind and mode. State writes use a temporary file and restrictive permissions. Guard commands use argument arrays and bounded output.

## Observability and operations

Blocking output lists attributable paths, omitted-path count when capped, every missing journal, exact failed commands, exit statuses, and bounded stderr or stdout. Context output is compact JSON suitable for Codex hook processing.

## Tests and evidence

`test_docs_hook.py` contains 24 cases covering lifecycle context, dirty baseline attribution, read-only turns, docs and full modes, journal ownership, segment-aware globs, configuration changes, missing state, opaque IDs, Git-metadata state isolation, snapshot cleanup and retry, project-local guard fallback, descriptor wiring, and full audit enforcement for documentation-only changes.

## Change impact

Hook changes can alter task attribution or completion blocking. They require the hook suite, catalog ownership review, hook descriptor review, timeout review, and validation that the guard command interface remains compatible.

## Profile requirements

The external contract is local Codex hook JSON rather than a network API. Authentication is inherited from the trusted project process; no remote credential is transmitted. Descriptor timeouts are 30 seconds for context events, 60 seconds for prompt baseline capture, and 300 seconds for Stop; each guard subprocess is bounded at 120 seconds. Remote rate limiting is inapplicable because every call is local and finite. Degradation is conservative for known failures but intentionally non-blocking when a baseline cannot distinguish user work. Reconciliation compares two Git snapshots and reports only net attributable paths.

## Related documentation

<!-- docs:links:start -->
- Parent: [Enforcement](../README.md)
- Children: None.
- Related:
  - decided-by: [Enforce documentation at layered lifecycle gates](../../../../decisions/0002-layered-enforcement.md)
  - depends-on: [Documentation guard](documentation.guard.md)
  - related: [Local documentation lifecycle](../../../flows/local-documentation-lifecycle.md)
  - specified-by: [Architecture documentation system v2](../../../../specifications/architecture-documentation-system-v2.md)
  - verified-by: [Dogfood architecture-docs-keeper v2](../../../../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks:
  - changes: [Dogfood architecture-docs-keeper v2](../../../../journals/tasks/20260715-architecture-docs-keeper-v2.md)
  - changes: [Dogfood architecture-docs-keeper v2](../../../../plans/20260715-architecture-docs-keeper-v2.md)
  - documents: [Runtime containers](../../../system/containers.md)
  - documents: [Local Codex deployment](../../../system/deployments/local-codex.md)
  - documents: [Local documentation lifecycle](../../../flows/local-documentation-lifecycle.md)
  - documents: [Validate the project skill and repository integration](../../../../development/validation.md)
  - documents: [Documentation lifecycle hooks journal](../../../../journals/components/documentation.lifecycle-hooks.md)
<!-- docs:links:end -->
