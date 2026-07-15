---
doc_id: architecture.area.guidance
doc_type: architecture-area
title: Guidance
status: active
parent_id: architecture.areas.index
relations:
  - type: specified-by
    target_id: specification.architecture-documentation-system-v2
---

# Guidance

## Responsibility

The guidance area owns the project-discoverable workflow skill, model-facing metadata, and the normative schema-v2 documentation standard.

## Boundaries

It defines commands, sequencing, document schemas, required records, and completion criteria. It contains no executable validation logic; enforcement remains authoritative when prose and repository state disagree.

## Entry points

Codex discovers `.agents/skills/architecture-docs-keeper/SKILL.md` at project scope and uses `agents/openai.yaml` to expose implicit invocation and the default prompt.

## Components

`documentation.workflow-skill` is the only guidance component. Its three owned sources form one project contract consumed by agents and validated by the skill contract suite.

## Dependencies

The skill resolves its own root from the repository and calls the guard's public CLI. Project hook discovery remains separately declared in `.codex/hooks.json`.

## Data and control flow

Project discovery selects the skill, the skill directs the agent to inspect or create the documentation graph, and the standard supplies exact tree, front-matter, relation, ownership, content, and audit rules.

## Security and operations

Guidance forbids user-level copies, absolute catalog paths, traversal, speculative facts, placeholders, manual generated links, and destructive migration. Contract tests verify project discovery, required resources, command forms, hook wiring, and standard-library runtime imports.

## Related documentation

<!-- docs:links:start -->
- Parent: [Architecture areas](../README.md)
- Children:
  - [Documentation workflow skill](components/documentation.workflow-skill.md)
- Related:
  - specified-by: [Architecture documentation system v2](../../../specifications/architecture-documentation-system-v2.md)
- Backlinks: None.
<!-- docs:links:end -->
