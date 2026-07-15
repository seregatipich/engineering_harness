---
doc_id: specification.architecture-documentation-system-v2
doc_type: specification
title: Architecture documentation system v2
status: approved
parent_id: specifications.root
relations:
  - type: decided-by
    target_id: decision.0001.stdlib-validator
  - type: decided-by
    target_id: decision.0002.layered-enforcement
  - type: decided-by
    target_id: decision.0003.project-scoped-skill
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
---

# Architecture documentation system v2

## Problem

Repository documentation drifts when architecture prose, source ownership, work history, decisions, and generated navigation are maintained independently or only when a contributor remembers to update them.

## Requirements

The system shall maintain the exact schema-v2 tree, globally unique document IDs, valid parents and typed relations, exhaustive ownership for selected inventory, complete required sections, one task journal per editable task, one append-only journal per component, immutable approved specifications and terminal decisions, and deterministic generated navigation and catalog output. Local and CI gates shall run the same guard implementation. CI shall run unit and contract tests plus full and real-base change-aware audits.

## Non-requirements

The system does not infer semantic truth from source code, host a documentation server, replace Git history, install third-party Python dependencies, cover files outside the explicitly reviewed inventory, require a user-level skill copy, or publish a separately installed package.

## Design

Authored Markdown front matter forms a typed document graph. An authored JSON catalog maps exact repository files to four stable components. A standard-library guard validates and projects that state. A lifecycle adapter attributes turn changes and requires journals. The checked-in skill defines agent behavior. Project configuration supplies discovery, hook, policy, local, and CI gates.

## Interfaces and data

The guard interface consists of `bootstrap`, `migrate`, `generate`, `links`, and `audit`. Hook input and output are JSON. Document metadata uses the allowed scalar fields plus relation objects. The architecture catalog uses schema version 2 with `inventory`, `areas`, `components`, and `relationships`. Generated catalog records map IDs to paths and graph metadata.

## Failure and security behavior

Unsafe paths, globs, symlinks, malformed schemas, unresolved graph edges, missing ownership, stale output, absent journals, and protected-history rewrites fail closed in the guard. Hook failures block Stop when attribution is reliable. Subprocesses avoid shell execution and use bounded timeouts; state filenames derive from hashed opaque IDs.

## Compatibility and migration

Stable component and document IDs survive path moves. Established legacy paths use redirect records when retained. The project skill and its contracts are versioned with the repository revision; no user-level installation state participates in compatibility. Migration preflights collisions and preserves unmatched factual content.

## Acceptance criteria

Exactly four active components own all 19 selected sources and tests once. The three architecture areas, complete component pages and journals, requested plan, task, flow, concept, deployment, operation, development guide, and decisions resolve in one graph. Project-skill and `.codex` guards are byte-identical. All skill suites, repository contract tests, links, generation check, full audit, and audit against the feature-branch base pass.

## Verification

Guard unit and adversarial tests cover parser, graph, catalog, safety, history, migration, generation, and CLI behavior. Hook tests cover lifecycle adaptation. Skill contract tests cover project discovery, runtime resources, hook wiring, command contracts, CLI availability, and standard-library imports. Repository contract tests cover project scope, exact ownership, wrapper execution, guard parity, and workflow base enforcement.

## Related documentation

<!-- docs:links:start -->
- Parent: [Specifications](README.md)
- Children: None.
- Related:
  - decided-by: [Use a standard-library documentation validator](../decisions/0001-stdlib-validator.md)
  - decided-by: [Enforce documentation at layered lifecycle gates](../decisions/0002-layered-enforcement.md)
  - decided-by: [Keep the documentation skill project-scoped](../decisions/0003-project-scoped-skill.md)
  - verified-by: [Dogfood architecture-docs-keeper v2](../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks:
  - changes: [Dogfood architecture-docs-keeper v2](../journals/tasks/20260715-architecture-docs-keeper-v2.md)
  - changes: [Dogfood architecture-docs-keeper v2](../plans/20260715-architecture-docs-keeper-v2.md)
  - specified-by: [Enforcement](../architecture/areas/enforcement/README.md)
  - specified-by: [Guidance](../architecture/areas/guidance/README.md)
  - specified-by: [Project integration](../architecture/areas/integration/README.md)
  - specified-by: [Documentation guard](../architecture/areas/enforcement/components/documentation.guard.md)
  - specified-by: [Documentation lifecycle hooks](../architecture/areas/enforcement/components/documentation.lifecycle-hooks.md)
  - specified-by: [Documentation project integration](../architecture/areas/integration/components/documentation.project-integration.md)
  - specified-by: [Documentation workflow skill](../architecture/areas/guidance/components/documentation.workflow-skill.md)
  - specified-by: [Document graph](../architecture/concepts/document-graph.md)
  - specified-by: [Local documentation lifecycle](../architecture/flows/local-documentation-lifecycle.md)
  - specified-by: [Architecture](../architecture/README.md)
<!-- docs:links:end -->
