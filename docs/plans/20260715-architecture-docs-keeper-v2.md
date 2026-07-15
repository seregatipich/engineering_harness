---
doc_id: plan.20260715-architecture-docs-keeper-v2
doc_type: plan
title: Dogfood architecture-docs-keeper v2
status: completed
parent_id: plans.root
relations:
  - type: changes
    target_id: architecture.component.documentation.guard
  - type: changes
    target_id: architecture.component.documentation.lifecycle-hooks
  - type: changes
    target_id: architecture.component.documentation.workflow-skill
  - type: changes
    target_id: architecture.component.documentation.project-integration
  - type: changes
    target_id: specification.architecture-documentation-system-v2
  - type: decided-by
    target_id: decision.0001.stdlib-validator
  - type: decided-by
    target_id: decision.0002.layered-enforcement
  - type: decided-by
    target_id: decision.0003.project-scoped-skill
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
---

# Dogfood architecture-docs-keeper v2

## Objective

Replace the repository's generated scaffold with a complete evidence-backed v2 architecture graph for the project-local skill and lock discovery, ownership, local deployment, and CI behavior with executable contracts.

## Scope

The plan covers 17 structural records, three architecture areas, four components and journals, one task journal, the approved v2 specification, one lifecycle flow, one document-graph concept, one local deployment, setup and validation guidance, three decisions, the authored architecture catalog, generated projections, skill contracts, project-integration contracts, and CI test execution.

## Constraints

The canonical surface is the repository-scoped `.agents/skills/architecture-docs-keeper` tree; no plugin, marketplace, or user-level installation belongs to the design. Runtime code, hook configuration, policy, workflow, and local wrappers are documented from repository evidence. Authored facts must have no placeholder or manual graph link.

## Affected documents and components

All four catalog components are affected because their pages, journals, ownership, specification, and verification contracts are established together. The plan also changes the generated document catalog and every structural index through newly derived children, relations, and backlinks.

## Work breakdown

1. Inspect repository rules, project skill, normative standard, runtime files, tests, hooks, wrappers, and workflow.
2. Allocate stable component and document IDs and enumerate exact inventory ownership.
3. Author factual structural, area, component, flow, concept, deployment, specification, decision, operation, development, plan, and journal records.
4. Verify project-skill and repository-integration contract suites.
5. Generate graph projections and correct schema, section, relation, ownership, or link errors.
6. Run every skill and repository test plus generated, link, full, and `origin/dev` base gates.
7. Record fresh command evidence and close the plan and task journal only after all gates pass.

## Verification

All 80 executable tests passed: 15 guard tests in 17.265 seconds, 30 adversarial tests in 67.990 seconds, 24 hook tests in 229.453 seconds, 6 skill-contract tests in 1.505 seconds, and 5 repository-contract tests in 1.046 seconds. `generate --write` exited successfully, `generate --check` reported current output, internal links passed for 39 documents, and both full and `origin/dev` base audits passed for 39 documents and 14 owned sources.

## Rollout and recovery

Rollout distributes the project-local skill with the repository revision, refreshes generated documentation, and relies on local and CI commands tracked by project integration. Recovery restores authored records or managed tooling from Git, reestablishes guard-copy parity, regenerates projections, and reruns all gates; accepted records and journal history are preserved.

## Outcome

The project-local skill is represented by a complete 39-document graph, three areas, four components, 19 exactly owned files with no exclusion, three guard dependencies, and ADR 0003 for project-scoped discovery. All 80 tests and every documentation gate passed, so the plan is completed.

## Related documentation

<!-- docs:links:start -->
- Parent: [Plans](README.md)
- Children: None.
- Related:
  - changes: [Documentation guard](../architecture/areas/enforcement/components/documentation.guard.md)
  - changes: [Documentation lifecycle hooks](../architecture/areas/enforcement/components/documentation.lifecycle-hooks.md)
  - changes: [Documentation project integration](../architecture/areas/integration/components/documentation.project-integration.md)
  - changes: [Documentation workflow skill](../architecture/areas/guidance/components/documentation.workflow-skill.md)
  - changes: [Architecture documentation system v2](../specifications/architecture-documentation-system-v2.md)
  - decided-by: [Use a standard-library documentation validator](../decisions/0001-stdlib-validator.md)
  - decided-by: [Enforce documentation at layered lifecycle gates](../decisions/0002-layered-enforcement.md)
  - decided-by: [Keep the documentation skill project-scoped](../decisions/0003-project-scoped-skill.md)
  - verified-by: [Dogfood architecture-docs-keeper v2](../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks: None.
<!-- docs:links:end -->
