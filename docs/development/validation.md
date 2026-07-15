---
doc_id: development.validation
doc_type: development
title: Validate the project skill and repository integration
status: active
parent_id: development.root
relations:
  - type: documents
    target_id: architecture.component.documentation.guard
  - type: documents
    target_id: architecture.component.documentation.lifecycle-hooks
  - type: related
    target_id: architecture.flow.local-documentation-lifecycle
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
---

# Validate the project skill and repository integration

## Setup

Run commands from the repository root with Python 3 and Git available. Tests use temporary repositories and the standard library; no virtual environment or dependency installation is required. Set `PYTHONDONTWRITEBYTECODE=1` when a clean working tree must remain free of bytecode caches.

## Workflows

During development, run the affected test file first, then all project-skill and repository contract files. After authored documentation changes, run generation once, check links and generated stability, run a full audit, and finish with an audit against the task's pre-change Git object.

## Commands

The validation sequence runs each executable test file directly, refreshes derived graph data once, and then proves that links, generated output, current state, and the feature-branch diff are clean.

```text
python3 .agents/skills/architecture-docs-keeper/tests/test_docs_guard.py -v
python3 .agents/skills/architecture-docs-keeper/tests/test_docs_guard_adversarial.py -v
python3 .agents/skills/architecture-docs-keeper/tests/test_docs_hook.py -v
python3 .agents/skills/architecture-docs-keeper/tests/test_skill_contract.py -v
python3 tests/test_repository_contract.py -v
python3 .codex/scripts/docs_guard.py generate --write .
python3 .codex/scripts/docs_guard.py generate --check .
python3 .codex/scripts/docs_guard.py links . --internal
python3 .codex/scripts/docs_guard.py audit . --format human
python3 .codex/scripts/docs_guard.py audit . --base origin/dev --format human
```

## Test strategy

Guard unit tests cover normal schema and CLI behavior. Adversarial tests target unsafe and historically false-pass states. Hook tests isolate lifecycle behavior with temporary Git repositories and project-local guard fallback. Skill contracts inspect project discovery, self-contained runtime resources, hook wiring, commands, and imports. Repository contracts inspect project scope, exact ownership, wrapper execution, local guard parity, and CI base enforcement.

## Constraints

Accepted decisions and the approved specification are immutable after entering Git history. Journals are append-only. Generated blocks and `docs/catalog.json` are never hand-edited. Tooling copies must be synchronized before parity and workflow assertions are evaluated.

## Troubleshooting

For import failures, run each test file directly rather than importing through the hyphenated skill directory name. For drift, run `generate --write` once and inspect the authored cause. For base-audit failures, confirm the base object resolves and that the task journal plus every affected component journal changed.

## Related documentation

<!-- docs:links:start -->
- Parent: [Development](README.md)
- Children: None.
- Related:
  - documents: [Documentation guard](../architecture/areas/enforcement/components/documentation.guard.md)
  - documents: [Documentation lifecycle hooks](../architecture/areas/enforcement/components/documentation.lifecycle-hooks.md)
  - related: [Local documentation lifecycle](../architecture/flows/local-documentation-lifecycle.md)
  - verified-by: [Dogfood architecture-docs-keeper v2](../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks: None.
<!-- docs:links:end -->
