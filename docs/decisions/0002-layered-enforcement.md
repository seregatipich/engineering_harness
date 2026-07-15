---
doc_id: decision.0002.layered-enforcement
doc_type: decision
title: Enforce documentation at layered lifecycle gates
status: accepted
parent_id: decisions.root
relations:
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
---

# Enforce documentation at layered lifecycle gates

## Context

Agent guidance alone cannot prove that documentation changed with implementation. A Stop hook can attribute an interactive turn but may lack a reliable baseline, and local checks can be bypassed. CI sees the delivered revision but must receive a real comparison object to enforce journals.

## Decision drivers

Enforcement must guide agents early, catch omissions before interactive completion, provide a fast local gate, verify project behavior with tests, and independently check the delivered Git diff in CI without assigning pre-existing dirty files to a turn.

## Considered options

Skill guidance only, Stop-hook enforcement only, a pre-push command only, CI full audit only, and combined layered enforcement were considered. Each single layer has an attribution or bypass gap. A full audit without `--base` validates current shape but cannot prove task and component journal updates for the delivered change.

## Decision

Use four layers: implicitly invocable project-skill guidance; lifecycle baseline and Stop checks that run full audit plus generated-state validation for both change classes; repository-local wrapper and Git checks; and GitHub Actions running tests, links, generated validation, full audit, and audit against a validated event base, the remote default-branch merge base, or empty tree.

## Consequences

Contributors receive earlier and more specific failures, while CI remains the independent delivery gate. Configuration exists in several owned files and must stay synchronized through repository contract tests and architecture documentation. Base-object handling becomes part of the project-integration contract.

## Verification

Hook tests prove attribution and journal behavior. Repository contracts prove workflow and wrapper wiring. The docs workflow checks generated state and current shape, then passes an event-derived Git object to change-aware audit.

## Amendments

This accepted record has no amendment. Future clarification will be appended under a UTC timestamp without rewriting the rationale.

## Related documentation

<!-- docs:links:start -->
- Parent: [Decisions](README.md)
- Children: None.
- Related:
  - verified-by: [Dogfood architecture-docs-keeper v2](../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks:
  - decided-by: [Documentation guard](../architecture/areas/enforcement/components/documentation.guard.md)
  - decided-by: [Documentation lifecycle hooks](../architecture/areas/enforcement/components/documentation.lifecycle-hooks.md)
  - decided-by: [Documentation project integration](../architecture/areas/integration/components/documentation.project-integration.md)
  - decided-by: [Documentation workflow skill](../architecture/areas/guidance/components/documentation.workflow-skill.md)
  - decided-by: [Local Codex deployment](../architecture/system/deployments/local-codex.md)
  - decided-by: [Local documentation lifecycle](../architecture/flows/local-documentation-lifecycle.md)
  - decided-by: [Architecture](../architecture/README.md)
  - decided-by: [Dogfood architecture-docs-keeper v2](../plans/20260715-architecture-docs-keeper-v2.md)
  - decided-by: [Architecture documentation system v2](../specifications/architecture-documentation-system-v2.md)
<!-- docs:links:end -->
