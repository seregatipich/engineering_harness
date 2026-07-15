---
name: architecture-docs-keeper
description: Maintain the complete project documentation system for every editable repository task. Use for source, configuration, schema, dependency, runtime, infrastructure, test, or documentation changes; architecture discovery; planning; specifications; task or component journals; decision records; migrations; onboarding; and documentation audits. Bootstrap missing docs, safely migrate legacy docs, and reconcile every indexed component and internal documentation link before completion.
---

# Maintain Project Documentation

Treat documentation as implementation state. Maintain an evidence-backed document graph under `docs/` covering architecture, plans, specifications, task and component journals, decisions, operations, and development guidance.

## Resolve the tools

Resolve the project-local skill from the Git root. Do not install or copy it into a user-level skill directory.

```bash
REPOSITORY_ROOT="$(git rev-parse --show-toplevel)"
SKILL_ROOT="$REPOSITORY_ROOT/.agents/skills/architecture-docs-keeper"
```

Use these exact commands:

```bash
python3 "$SKILL_ROOT/scripts/docs_guard.py" bootstrap --dry-run "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" bootstrap --apply "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" migrate --plan "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" migrate --apply "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" links "$REPOSITORY_ROOT" --internal
python3 "$SKILL_ROOT/scripts/docs_guard.py" generate --write "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" generate --check "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" audit "$REPOSITORY_ROOT" --base "$BASE_SHA" --format human
```

## Before an editable task

1. Read project instructions and existing documentation.
2. Record the pre-task Git revision for the final change audit.
3. Read [the documentation system standard](references/architecture-standard.md) completely when schema v2 is absent, requires migration, has audit failures, or the task changes documentation structure.
4. Run `audit`. If documentation is absent, run `bootstrap --dry-run`, inspect the plan, then run `bootstrap --apply`. If legacy or partial documentation exists, run `migrate --plan`, inspect every move and redirect, then run `migrate --apply`. Never bootstrap over unmanaged documentation.
5. After bootstrap or migration, run `links --internal`, `generate --write`, and `audit`. Replace scaffold prose with verified facts before changing implementation.
6. Read the root catalog, affected architecture documents, active specifications, relevant plans and decisions, and current task and component journals.

For read-only work, do not bootstrap, migrate, generate, or edit. Run read-only checks when permitted and report missing, stale, or invalid documentation.

## During the task

- Maintain one `journal-task` document for every editable task. Append timestamped evidence; never rewrite history.
- Append an entry to every affected `journal-component` document.
- Update `docs/architecture/catalog.json` and affected architecture pages for every source, configuration, schema, dependency, runtime, deployment, or test change.
- Create or update a plan for multi-step, cross-component, migration, rollout, or recovery work.
- Create or update a specification when behavior, an interface, schema, permission, compatibility contract, or acceptance criterion changes.
- Create a decision record when choosing among material alternatives with durable consequences.
- Express every cross-document relationship in front matter. Do not hand-author generated links or backlinks.
- Preserve stable IDs across moves and renames. Use redirects when an established document path or ID changes.
- Use only verified project facts. Do not leave placeholders, speculative claims, empty required sections, or stale paths.
- Preserve append-only journals and terminal decision history defined by the standard.

## Before completion

1. Reconcile the complete task diff with component ownership, tests, specifications, plans, decisions, and both journal classes.
2. Run `links <repository> --internal`.
3. Run `generate --write <repository>`, then `generate --check <repository>`.
4. Run `audit <repository> --base <pre-task-sha> --format human` and resolve every error.
5. Inspect all generated and authored documentation diffs. Do not edit marker-delimited generated content.
6. Report created, migrated, updated, and verified documents with repository-relative paths.

Do not report completion while a relevant file is unowned, a document-graph edge is invalid, generated content is stale, a required journal entry is absent, or a required check is unavailable or failing.

The standard is normative. Project instructions may add stricter requirements but must not weaken it.
