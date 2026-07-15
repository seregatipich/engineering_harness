---
doc_id: architecture.concept.document-graph
doc_type: architecture-concept
title: Document graph
status: active
parent_id: architecture.concepts.index
relations:
  - type: documents
    target_id: architecture.component.documentation.guard
  - type: documents
    target_id: architecture.component.documentation.workflow-skill
  - type: specified-by
    target_id: specification.architecture-documentation-system-v2
  - type: decided-by
    target_id: decision.0001.stdlib-validator
---

# Document graph

## Definition

The document graph is the set of schema-v2 Markdown records identified by stable `doc_id` values and connected through one parent plus typed relations. Paths locate records; identities and relations define meaning.

## Invariants

Every Markdown document has one unique ID, valid type and status, required parent except `docs.root`, allowed front-matter fields, one final Related documentation heading, and one generated navigation block. Targets resolve, parent and redirect cycles are forbidden, and architecture component relations agree with the ownership catalog.

## Ownership

Authored front matter owns identity and graph edges. Authored prose owns technical facts. `docs/architecture/catalog.json` owns areas, components, source and test paths, and component dependencies. The guard owns generated navigation and `docs/catalog.json`.

## Lifecycle

Agents author or migrate records, preserve stable IDs, update relations and catalogs, append history, and run generation. Terminal plans, decisions, specifications, journals, and removed components remain indexed. Base audit protects immutable and append-only content after it enters Git history.

## Implementations

`docs_guard.py` parses, validates, and projects the graph using standard-library Python. `docs_hook.py` enforces per-turn journal and guard requirements. The skill and standard define how agents maintain the same graph.

## Misuse and failure

Manual cross-document links, hand-edited generated blocks, path IDs, reverse-edge duplication, unresolved targets, duplicate IDs, unknown metadata, stale catalogs, placeholders, and destructive history rewrites violate the graph contract and produce audit errors.

## Related documentation

<!-- docs:links:start -->
- Parent: [Architecture concepts](README.md)
- Children: None.
- Related:
  - decided-by: [Use a standard-library documentation validator](../../decisions/0001-stdlib-validator.md)
  - documents: [Documentation guard](../areas/enforcement/components/documentation.guard.md)
  - documents: [Documentation workflow skill](../areas/guidance/components/documentation.workflow-skill.md)
  - specified-by: [Architecture documentation system v2](../../specifications/architecture-documentation-system-v2.md)
- Backlinks:
  - related: [Documentation guard](../areas/enforcement/components/documentation.guard.md)
  - related: [Documentation workflow skill](../areas/guidance/components/documentation.workflow-skill.md)
  - related: [Engineering harness system context](../system/context.md)
<!-- docs:links:end -->
