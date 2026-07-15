---
doc_id: decision.0003.project-scoped-skill
doc_type: decision
title: Keep the documentation skill project-scoped
status: accepted
parent_id: decisions.root
relations:
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
---

# Keep the documentation skill project-scoped

## Context

The documentation workflow must accompany each repository and remain reviewable at the same revision as its architecture rules, validator, lifecycle hook, and CI gates. A plugin marketplace or user-level skill installation would add external discovery state that can drift from the checked-in project contract.

## Decision drivers

Discovery must be deterministic from a trusted checkout, updates must be reviewable with the repository diff, local and CI execution must use the same sources, onboarding must avoid a separate installation step, and one user's global configuration must not silently affect another project.

## Considered options

A user-level skill copy, a locally installed plugin exposed through a marketplace, a remote plugin package, and a project-scoped skill under `.agents/skills` were considered. User and marketplace options introduce installation, cache, ordering, and version state outside the repository. A remote package adds publication and availability dependencies.

## Decision

Keep `architecture-docs-keeper` under `.agents/skills/architecture-docs-keeper` as the canonical discovery and runtime source. Declare lifecycle enforcement in `.codex/hooks.json`, resolving the checked-in hook from the Git root. Do not require or document a marketplace entry, plugin install, or user-level skill copy.

## Consequences

The skill, standard, guard, hook, and their tests travel with the project revision. Contributors open and trust the repository rather than installing a separate package. The project retains a `.codex/scripts/docs_guard.py` copy for repository gates, and repository contracts enforce its byte parity with the canonical skill guard. Other repositories must carry their own project-scoped copy if they adopt the workflow.

## Verification

The skill contract verifies `.agents/skills` discovery, required resources, Git-root hook commands, and absence of user-level paths in the skill workflow. The repository contract verifies that no plugin or marketplace tree exists, the README describes project scope and no user-level installation, and local plus CI gates use repository files.

## Amendments

This accepted record has no amendment. Future clarification will be appended under a UTC timestamp without rewriting the rationale.

## Related documentation

<!-- docs:links:start -->
- Parent: [Decisions](README.md)
- Children: None.
- Related:
  - verified-by: [Dogfood architecture-docs-keeper v2](../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks:
  - changes: [Dogfood architecture-docs-keeper v2](../journals/tasks/20260715-architecture-docs-keeper-v2.md)
  - decided-by: [Documentation project integration](../architecture/areas/integration/components/documentation.project-integration.md)
  - decided-by: [Documentation workflow skill](../architecture/areas/guidance/components/documentation.workflow-skill.md)
  - decided-by: [Local Codex deployment](../architecture/system/deployments/local-codex.md)
  - decided-by: [Use the project-local architecture documentation skill](../operations/installation.md)
  - decided-by: [Dogfood architecture-docs-keeper v2](../plans/20260715-architecture-docs-keeper-v2.md)
  - decided-by: [Architecture documentation system v2](../specifications/architecture-documentation-system-v2.md)
<!-- docs:links:end -->
