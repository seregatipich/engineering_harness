---
doc_id: decision.0001.stdlib-validator
doc_type: decision
title: Use a standard-library documentation validator
status: accepted
parent_id: decisions.root
relations:
  - type: verified-by
    target_id: journal.task.20260715-architecture-docs-keeper-v2
---

# Use a standard-library documentation validator

## Context

The documentation gate runs in local repositories, Codex hooks, and GitHub Actions. Requiring a package installation before validation would add bootstrap ordering, version, availability, and supply-chain failure modes.

## Decision drivers

The validator must run with the Python interpreter already used by hooks, remain portable across local and CI environments, start without dependency installation, expose deterministic behavior, and permit direct repository copying with byte parity.

## Considered options

A standard-library Python executable, a Python package with YAML and Markdown dependencies, a shell implementation, and a JavaScript package were considered. External parser libraries would simplify some syntax handling but introduce installation state; shell would make safe parsing and cross-platform behavior harder; JavaScript would add a separate runtime contract.

## Decision

Implement the validator, hook, tests, and contract inspection with Python's standard library. Parse the deliberately constrained front-matter and catalog schemas explicitly and execute Git through argument-array subprocess calls.

## Consequences

The project skill is self-contained and CI requires only Python 3 and Git. The accepted Markdown and YAML subsets remain intentionally constrained. Parser and safety behavior require thorough unit and adversarial coverage because a third-party parser does not supply validation semantics.

## Verification

The skill contract test parses runtime imports and rejects modules outside `sys.stdlib_module_names`. Guard and hook tests execute directly with Python, and the repository contract verifies byte parity between the project-skill and `.codex` guard scripts.

## Amendments

This accepted record has no amendment. Future clarification will be appended under a UTC timestamp without changing the sections above.

## Related documentation

<!-- docs:links:start -->
- Parent: [Decisions](README.md)
- Children: None.
- Related:
  - verified-by: [Dogfood architecture-docs-keeper v2](../journals/tasks/20260715-architecture-docs-keeper-v2.md)
- Backlinks:
  - decided-by: [Documentation guard](../architecture/areas/enforcement/components/documentation.guard.md)
  - decided-by: [Document graph](../architecture/concepts/document-graph.md)
  - decided-by: [Dogfood architecture-docs-keeper v2](../plans/20260715-architecture-docs-keeper-v2.md)
  - decided-by: [Architecture documentation system v2](../specifications/architecture-documentation-system-v2.md)
<!-- docs:links:end -->
