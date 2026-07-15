---
doc_id: architecture.component.documentation.workflow-skill
doc_type: architecture-component
title: Documentation workflow skill
status: active
parent_id: architecture.area.guidance
profile: shared-library
relations:
  - type: depends-on
    target_id: architecture.component.documentation.guard
  - type: specified-by
    target_id: specification.architecture-documentation-system-v2
  - type: decided-by
    target_id: decision.0002.layered-enforcement
  - type: decided-by
    target_id: decision.0003.project-scoped-skill
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
  - type: related
    target_id: architecture.concept.document-graph
---

# Documentation workflow skill

## Summary

The workflow skill is the agent-facing contract for creating, migrating, reading, updating, and validating the complete repository documentation system.

## Responsibility

It owns project-skill discovery, implicit invocation metadata, exact guard command forms, task sequencing, the normative v2 tree and schema, reconciliation rules, and the completion gate presented to Codex.

## Boundaries

The component owns `.agents/skills/architecture-docs-keeper/SKILL.md`, `agents/openai.yaml`, and `references/architecture-standard.md`. It specifies behavior but does not execute validation, lifecycle state capture, or project integration.

## Entry points and public interfaces

Codex discovers `$architecture-docs-keeper` directly from `.agents/skills/architecture-docs-keeper`. The public interface consists of the skill description, implicit invocation policy, default prompt, exact CLI commands, schema tables, required document headings, and completion conditions.

## Dependencies

The workflow component depends on `documentation.guard` for every prescribed bootstrap, migration, generation, link, and audit command. It resolves `SKILL_ROOT` from the Git repository, and change audit requires a Git base object. Agents consume the skill and standard; Codex consumes the model metadata.

## Data and control flow

Project discovery exposes the checked-in skill, and model metadata makes it implicitly invocable. The skill routes an editable task through discovery, bootstrap or migration when necessary, authored updates, links, generation, full audit, and base audit. The standard supplies the exact records validated by the guard.

## State and side effects

The guidance files retain versioned declarative state and have no runtime side effect by themselves. Their commands may direct an agent to invoke explicit guard write modes after inspecting repository evidence.

## Failure modes and recovery

Malformed front matter or model metadata can prevent discovery. Stale commands or schema prose can direct invalid work even when Python remains correct. The skill contract suite detects missing resources and locked command drift; recovery synchronizes the project contract with verified implementation behavior.

## Security and permissions

Guidance requires repository-derived roots and forbids user-level copies, traversal, absolute catalog paths, speculative records, and destructive migration without preflight.

## Observability and operations

Discovery exposes the display name, short description, implicit invocation policy, and default prompt. Agents report generated, authored, migrated, and verified documents together with exact guard results.

## Tests and evidence

`test_skill_contract.py` validates project discovery, required runtime resources, project hook wiring, skill and standard command contracts, runnable CLI subcommands, and the absence of third-party runtime imports.

## Change impact

Changing the skill, model metadata, or standard affects every agent consumer. Review must cover guard schema parity, hook instructions, project discovery, documentation examples, and approved specification compatibility.

## Profile requirements

The public API is the skill-plus-standard documentation contract. Compatibility is tied to schema version 2, the listed CLI forms, and stable document semantics. Consumers are Codex agents and repository contributors. The contract is versioned with the project revision rather than a separately installed package. Invalid guidance propagates as agent workflow failure, so skill contracts and the approved specification are release gates.

## Related documentation

<!-- docs:links:start -->
- Parent: [Guidance](../README.md)
- Children: None.
- Related:
  - decided-by: [Enforce documentation at layered lifecycle gates](../../../../decisions/0002-layered-enforcement.md)
  - decided-by: [Keep the documentation skill project-scoped](../../../../decisions/0003-project-scoped-skill.md)
  - depends-on: [Documentation guard](../../enforcement/components/documentation.guard.md)
  - related: [Document graph](../../../concepts/document-graph.md)
  - specified-by: [Architecture documentation system v2](../../../../specifications/architecture-documentation-system-v2.md)
  - verified-by: [Dogfood architecture-docs-keeper v2](../../../../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks:
  - changes: [Dogfood architecture-docs-keeper v2](../../../../journals/tasks/20260715-architecture-docs-keeper-v2.md)
  - changes: [Dogfood architecture-docs-keeper v2](../../../../plans/20260715-architecture-docs-keeper-v2.md)
  - documents: [Document graph](../../../concepts/document-graph.md)
  - documents: [Local documentation lifecycle](../../../flows/local-documentation-lifecycle.md)
  - documents: [Documentation workflow skill journal](../../../../journals/components/documentation.workflow-skill.md)
<!-- docs:links:end -->
