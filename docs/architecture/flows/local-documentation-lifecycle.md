---
doc_id: architecture.flow.local-documentation-lifecycle
doc_type: architecture-flow
title: Local documentation lifecycle
status: active
parent_id: architecture.flows.index
relations:
  - type: documents
    target_id: architecture.component.documentation.guard
  - type: documents
    target_id: architecture.component.documentation.lifecycle-hooks
  - type: documents
    target_id: architecture.component.documentation.workflow-skill
  - type: documents
    target_id: architecture.component.documentation.project-integration
  - type: specified-by
    target_id: specification.architecture-documentation-system-v2
  - type: decided-by
    target_id: decision.0002.layered-enforcement
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
---

# Local documentation lifecycle

## Trigger

Codex session and subagent startup request policy context. `UserPromptSubmit` begins attributable work by capturing a baseline. `Stop`, local validation, pre-push, pull requests, and pushes trigger enforcement at progressively broader boundaries.

## Participants

The workflow skill instructs the agent, the lifecycle hook attributes the current turn, the guard validates repository truth, and project-integration configuration invokes those checks locally and in GitHub Actions.

## Preconditions

Codex supplies a valid hook event and working directory for lifecycle attribution. Editable repository work has a Git root. Guard execution has Python 3, readable repository files, and Git when base-aware validation is requested.

## Sequence

1. Startup events inject the documentation invariant.
2. Prompt submission hashes the current dirty and untracked Git state into a turn baseline.
3. The agent reads affected maps, updates source ownership and authored records, appends task and component evidence, and regenerates derived files.
4. Stop compares baseline and current snapshots, filters generated noise, classifies docs-only or full changes, and checks required journals.
5. For both documentation-only and full changes, the hook runs a full audit followed by a generated-state check and blocks completion on any failure.
6. Stop deletes the baseline after no changes or successful checks and preserves it after a blocking failure so the same turn can retry after correction.
7. Local wrapper, pre-push, and CI repeat generated, full, and change-aware validation independently of the interactive turn.

## Data transformations

Git porcelain records become normalized path, status, kind, mode, and SHA-256 snapshot entries. Net paths become a change class and affected component IDs through architecture catalog patterns. Markdown front matter becomes a document graph; the graph becomes `docs/catalog.json` and marker-delimited navigation.

## Failure paths

Malformed hook input fails the hook process. Missing attribution state skips Stop enforcement rather than assigning pre-existing work to the turn. Missing journals, unsafe catalog data, failed guard commands, or stale generated output produce a blocking Stop response. Local and CI command failures stop their respective gates.

## Security boundaries

Lifecycle IDs are hashed before filesystem use, default snapshot state stays beneath the repository's absolute Git metadata directory, Git paths reject traversal, snapshot writes are atomic and permission-restricted, catalog globs are segment-aware, subprocesses use argument arrays, and the validator rejects repository escapes and unsafe symlinks.

## Verification

The hook suite exercises all lifecycle branches and ownership matching. Guard and adversarial suites exercise repository safety and graph semantics. Skill and repository contract suites verify project discovery, runtime resources, parity, inventory, wrapper, hook, and workflow wiring.

## Related documentation

<!-- docs:links:start -->
- Parent: [Architecture flows](README.md)
- Children: None.
- Related:
  - decided-by: [Enforce documentation at layered lifecycle gates](../../decisions/0002-layered-enforcement.md)
  - documents: [Documentation guard](../areas/enforcement/components/documentation.guard.md)
  - documents: [Documentation lifecycle hooks](../areas/enforcement/components/documentation.lifecycle-hooks.md)
  - documents: [Documentation project integration](../areas/integration/components/documentation.project-integration.md)
  - documents: [Documentation workflow skill](../areas/guidance/components/documentation.workflow-skill.md)
  - specified-by: [Architecture documentation system v2](../../specifications/architecture-documentation-system-v2.md)
  - verified-by: [Dogfood architecture-docs-keeper v2](../../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks:
  - related: [Documentation lifecycle hooks](../areas/enforcement/components/documentation.lifecycle-hooks.md)
  - related: [Validate the project skill and repository integration](../../development/validation.md)
<!-- docs:links:end -->
