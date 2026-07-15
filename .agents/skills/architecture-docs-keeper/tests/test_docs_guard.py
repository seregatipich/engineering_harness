"""Regression tests for the stdlib-only architecture documentation guard."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = SKILL_ROOT / "scripts" / "docs_guard.py"
MODULE_SPEC = importlib.util.spec_from_file_location("architecture_docs_guard", GUARD_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load docs guard from {GUARD_PATH}")
docs_guard = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = docs_guard
MODULE_SPEC.loader.exec_module(docs_guard)


def front_matter(
    *,
    doc_id: str,
    doc_type: str,
    title: str,
    status: str = "active",
    parent_id: str | None = None,
    relations: tuple[tuple[str, str, str | None], ...] = (),
    profile: str | None = None,
    redirect_to: str | None = None,
) -> str:
    """Render canonical fixture front matter."""
    lines = [
        "---",
        f"doc_id: {doc_id}",
        f"doc_type: {doc_type}",
        f"title: {title}",
        f"status: {status}",
    ]
    if parent_id is not None:
        lines.append(f"parent_id: {parent_id}")
    if profile is not None:
        lines.append(f"profile: {profile}")
    if redirect_to is not None:
        lines.append(f"redirect_to: {redirect_to}")
    lines.append("relations:")
    for relation_type, target_id, anchor in relations:
        lines.extend([f"  - type: {relation_type}", f"    target_id: {target_id}"])
        if anchor:
            lines.append(f"    anchor: {anchor}")
    lines.extend(["---", ""])
    return "\n".join(lines)


COMPONENT_BODY = """# Authentication component

## Summary

Provides the documented authentication boundary for this fixture.

## Responsibility

Owns the authenticated entry flow and deliberately excludes persistence.

## Boundaries

Owns request authentication while callers own presentation and persistence.

## Entry points and public interfaces

Exports the authenticate function to the application container.

## Dependencies

Uses only interfaces represented in the architecture relationship graph.

## Data and control flow

Receives credentials, validates them, and returns an authenticated result.

## State and side effects

Does not persist state; callers own any session side effects.

## Failure modes and recovery

Rejects invalid credentials and allows the caller to retry safely.

## Security and permissions

Validates untrusted credential input before granting authenticated access.

## Observability and operations

Exposes failures through the caller's structured logging boundary.

## Tests and evidence

The catalog owns the implementation file and its integration test evidence.

## Change impact

Callers, authentication contracts, and access-control tests require review.

## Profile requirements

Documents rendering, interaction, accessibility, and user-visible failure.

## Related documentation
"""

AREA_BODY = """# Frontend

## Responsibility

Owns browser-facing behavior represented by this fixture.

## Boundaries

The area ends at the typed authentication interface.

## Entry points

The authentication component exposes the fixture entry point.

## Components

The authored catalog is the component inventory source of truth.

## Dependencies

Dependencies are declared through document and component relationships.

## Data and control flow

Input enters through authentication and returns a deterministic result.

## Security and operations

Untrusted input is validated and failures are observable by callers.

## Related documentation
"""

COMPONENT_JOURNAL_BODY = """# Authentication journal

## Component

Records append-only evidence for the authentication component.

## Timeline

2026-01-01T00:00:00Z — Baseline implementation and tests were verified.

## Current operational notes

The component has no persistent state and is exercised by its owned test.

## Related documentation
"""


class DocsGuardTestCase(unittest.TestCase):
    """Exercise graph, links, ownership, generation, bootstrap, and migration."""

    def setUp(self) -> None:
        """Create an isolated Git repository with one valid v2 architecture map."""
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.repository = Path(self.temporary_directory.name) / "repository"
        self.repository.mkdir()
        self._git("init", "--quiet")
        self._git("config", "user.email", "docs-guard@example.invalid")
        self._git("config", "user.name", "Docs Guard Test")
        self._write("src/auth.py", "def authenticate():\n    return True\n")
        self._write("tests/auth_test.py", "def test_authenticate():\n    assert True\n")
        bootstrap_issues, _ = docs_guard.bootstrap_repository(
            self.repository, apply=True
        )
        self.assertEqual([], [issue for issue in bootstrap_issues if issue.severity == "error"])
        self._write(
            "docs/architecture/areas/frontend/README.md",
            front_matter(
                doc_id="architecture.area.frontend",
                doc_type="architecture-area",
                title="Frontend",
                parent_id="architecture.areas.index",
            )
            + AREA_BODY,
        )
        self._write(
            "docs/architecture/areas/frontend/components/auth.md",
            front_matter(
                doc_id="architecture.component.auth",
                doc_type="architecture-component",
                title="Authentication",
                parent_id="architecture.area.frontend",
                profile="frontend-ui",
            )
            + COMPONENT_BODY,
        )
        self._write(
            "docs/journals/components/auth.md",
            front_matter(
                doc_id="journal.component.auth",
                doc_type="journal-component",
                title="Authentication journal",
                parent_id="journals.components.index",
            )
            + COMPONENT_JOURNAL_BODY,
        )
        self._write_catalog(
            components=[
                {
                    "id": "auth",
                    "doc_id": "architecture.component.auth",
                    "name": "Authentication",
                    "kind": "ui-component",
                    "profile": "frontend-ui",
                    "status": "active",
                    "area": "frontend",
                    "sources": ["src/auth.py"],
                    "tests": ["tests/auth_test.py"],
                }
            ]
        )
        issues, _ = docs_guard.generate_repository(self.repository, write=True)
        self.assertEqual([], issues)

    def _git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        """Run a successful Git command in the test repository."""
        return subprocess.run(
            ["git", "-C", str(self.repository), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    def _write(self, relative_path: str, content: str) -> Path:
        """Write one UTF-8 fixture file."""
        path = self.repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _write_catalog(
        self,
        *,
        components: list[dict[str, object]],
        include: list[str] | None = None,
        exclude: list[dict[str, str]] | None = None,
        relationships: list[dict[str, str]] | None = None,
    ) -> None:
        """Write the reviewed architecture ownership catalog."""
        payload = {
            "schema_version": 2,
            "inventory": {
                "include": include
                if include is not None
                else ["src/**/*.py", "tests/**/*.py"],
                "exclude": exclude if exclude is not None else [],
            },
            "areas": [
                {
                    "id": "frontend",
                    "name": "Frontend",
                    "doc_id": "architecture.area.frontend",
                }
            ],
            "components": components,
            "relationships": relationships if relationships is not None else [],
        }
        self._write(
            "docs/architecture/catalog.json",
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
        )

    def _reload_documents(self):
        """Load documents and their validated identity maps."""
        documents, parse_issues = docs_guard.load_documents(self.repository)
        graph_issues, by_id, aliases = docs_guard.validate_document_graph(documents)
        self.assertEqual([], parse_issues)
        return documents, graph_issues, by_id, aliases

    def _add_component(
        self,
        slug: str,
        *,
        relations: tuple[tuple[str, str, str | None], ...] = (),
        body: str = COMPONENT_BODY,
    ) -> dict[str, object]:
        """Add a sibling component page/source and return its catalog record."""
        doc_id = f"architecture.component.{slug}"
        source = f"src/{slug}.py"
        test = f"tests/{slug}_test.py"
        self._write(source, f"NAME = {slug!r}\n")
        self._write(test, "def test_component():\n    assert True\n")
        self._write(
            f"docs/architecture/areas/frontend/components/{slug}.md",
            front_matter(
                doc_id=doc_id,
                doc_type="architecture-component",
                title=slug.title(),
                parent_id="architecture.area.frontend",
                relations=relations,
                profile="frontend-ui",
            )
            + body,
        )
        self._write(
            f"docs/journals/components/{slug}.md",
            front_matter(
                doc_id=f"journal.component.{slug}",
                doc_type="journal-component",
                title=f"{slug.title()} journal",
                parent_id="journals.components.index",
            )
            + COMPONENT_JOURNAL_BODY.replace("Authentication", slug.title()).replace("authentication", slug),
        )
        return {
            "id": slug,
            "doc_id": doc_id,
            "name": slug.title(),
            "kind": "ui-component",
            "profile": "frontend-ui",
            "status": "active",
            "area": "frontend",
            "sources": [source],
            "tests": [test],
        }

    def test_valid_graph_catalog_links_and_generated_files_pass(self) -> None:
        """A complete minimal v2 map passes every audit layer."""
        issues, summary = docs_guard.audit_repository(self.repository)
        self.assertEqual([], issues)
        self.assertEqual(len(docs_guard.CANONICAL_DOCUMENTS) + 3, summary["documents"])
        self.assertEqual(1, summary["owned_sources"])
        self.assertEqual("not-machine-verifiable", summary["semantic_accuracy"])

    def test_broken_inline_target_is_reported(self) -> None:
        """Visible inline links must resolve to a regular file."""
        component = self.repository / "docs/architecture/areas/frontend/components/auth.md"
        component.write_text(component.read_text() + "\n[Missing](missing.md)\n")
        documents, graph_issues, by_id, aliases = self._reload_documents()
        self.assertEqual([], graph_issues)
        codes = {
            issue.code
            for issue in docs_guard.validate_internal_links(
                self.repository, documents, by_id, aliases
            )
        }
        self.assertIn("link_target_missing", codes)

    def test_link_without_doc_relation_is_reported(self) -> None:
        """A non-hierarchical architecture link needs a declared relation."""
        other = self._add_component("profile")
        original = {
            "id": "auth",
            "doc_id": "architecture.component.auth",
            "name": "Authentication",
            "kind": "ui-component",
            "profile": "frontend-ui",
            "status": "active",
            "area": "frontend",
            "sources": ["src/auth.py"],
            "tests": ["tests/auth_test.py"],
        }
        self._write_catalog(components=[original, other])
        auth = self.repository / "docs/architecture/areas/frontend/components/auth.md"
        auth.write_text(
            auth.read_text().replace(
                docs_guard.MANAGED_LINKS_END,
                "- Unexpected: [Profile](profile.md)\n" + docs_guard.MANAGED_LINKS_END,
            )
        )
        documents, graph_issues, by_id, aliases = self._reload_documents()
        self.assertEqual([], graph_issues)
        codes = {
            issue.code
            for issue in docs_guard.validate_internal_links(
                self.repository, documents, by_id, aliases
            )
        }
        self.assertIn("link_relation_missing", codes)

    def test_bad_anchor_and_path_case_are_reported(self) -> None:
        """Link checks are anchor- and case-sensitive on every platform."""
        self._add_component("profile")
        lower_path = self.repository / "docs/architecture/areas/frontend/components/profile.md"
        target_path = lower_path.with_name("Profile.md")
        lower_path.rename(target_path)
        auth = self.repository / "docs/architecture/areas/frontend/components/auth.md"
        auth_text = docs_guard._without_managed_links(auth.read_text())
        auth_text = auth_text.replace(
            "relations:\n",
            "relations:\n  - type: related\n    target_id: architecture.component.profile\n",
            1,
        )
        auth.write_text(auth_text.rstrip() + "\n\n[Profile](profile.md#Missing-Anchor)\n")
        documents, _, by_id, aliases = self._reload_documents()
        codes = {
            issue.code
            for issue in docs_guard.validate_internal_links(
                self.repository, documents, by_id, aliases
            )
        }
        self.assertIn("link_path_case", codes)
        self.assertIn("link_anchor_missing", codes)

    def test_fenced_link_is_ignored_and_reference_link_is_validated(self) -> None:
        """Fenced examples are ignored while reference links remain active."""
        auth = self.repository / "docs/architecture/areas/frontend/components/auth.md"
        clean = docs_guard._without_managed_links(auth.read_text())
        auth.write_text(
            clean.rstrip()
            + "\n\n```md\n[Ignored](missing-in-fence.md)\n```\n"
            + "\n[Missing reference][missing-ref]\n\n[missing-ref]: absent.md\n"
        )
        documents, _, by_id, aliases = self._reload_documents()
        issues = docs_guard.validate_internal_links(
            self.repository, documents, by_id, aliases
        )
        missing_messages = [issue.message for issue in issues if issue.code == "link_target_missing"]
        self.assertEqual(1, len(missing_messages))
        self.assertIn("absent.md", missing_messages[0])

    def test_duplicate_orphan_and_parent_cycle_are_reported(self) -> None:
        """Identity and topology corruption produce separate graph diagnostics."""
        self._write(
            "docs/architecture/duplicate.md",
            front_matter(
                doc_id="architecture.component.auth",
                doc_type="architecture-component",
                title="Duplicate",
                parent_id="missing.parent",
                profile="frontend-ui",
            )
            + COMPONENT_BODY,
        )
        self._write(
            "docs/architecture/orphan.md",
            front_matter(
                doc_id="architecture.component.orphan",
                doc_type="architecture-component",
                title="Orphan",
                parent_id="missing.parent",
                profile="frontend-ui",
            )
            + COMPONENT_BODY,
        )
        area = self.repository / "docs/architecture/areas/frontend/README.md"
        area.write_text(
            area.read_text().replace(
                "parent_id: architecture.areas.index",
                "parent_id: architecture.component.auth",
            )
        )
        documents, parse_issues = docs_guard.load_documents(self.repository)
        graph_issues, _, _ = docs_guard.validate_document_graph(documents)
        codes = {issue.code for issue in (*parse_issues, *graph_issues)}
        self.assertIn("doc_id_duplicate", codes)
        self.assertIn("parent_orphan", codes)
        self.assertIn("parent_cycle", codes)

    def test_relation_target_and_relation_anchor_are_validated(self) -> None:
        """Typed relation targets and optional anchors resolve through doc IDs."""
        auth = self.repository / "docs/architecture/areas/frontend/components/auth.md"
        clean = docs_guard._without_managed_links(auth.read_text())
        clean = clean.replace(
            "relations:\n",
            "relations:\n  - type: related\n    target_id: architecture.missing\n"
            "  - type: related\n    target_id: architecture.area.frontend\n"
            "    anchor: absent-anchor\n",
            1,
        )
        auth.write_text(clean)
        documents, parse_issues = docs_guard.load_documents(self.repository)
        graph_issues, _, _ = docs_guard.validate_document_graph(documents)
        codes = {issue.code for issue in (*parse_issues, *graph_issues)}
        self.assertIn("relation_orphan", codes)
        self.assertIn("relation_anchor_missing", codes)

    def test_source_traversal_uncovered_and_duplicate_ownership_are_reported(self) -> None:
        """Inventory ownership rejects traversal, omissions, and multiple owners."""
        profile = self._add_component("profile")
        self._write("src/unowned.py", "UNOWNED = True\n")
        original = {
            "id": "auth",
            "doc_id": "architecture.component.auth",
            "name": "Authentication",
            "kind": "ui-component",
            "profile": "frontend-ui",
            "status": "active",
            "area": "frontend",
            "sources": ["src/auth.py", "../outside.py"],
            "tests": ["tests/auth_test.py"],
        }
        profile["sources"] = ["src/auth.py", "src/profile.py"]
        self._write_catalog(components=[original, profile])
        documents, _, by_id, aliases = self._reload_documents()
        issues, _, _ = docs_guard.validate_architecture_catalog(
            self.repository, by_id, aliases
        )
        codes = {issue.code for issue in issues}
        self.assertIn("source_path_traversal", codes)
        self.assertIn("source_duplicate_owner", codes)
        self.assertIn("source_uncovered", codes)

    def test_justified_inventory_exclusion_removes_source_from_coverage(self) -> None:
        """Explicit exclusions require reasons and are excluded from ownership."""
        self._write("src/generated/output.py", "GENERATED = True\n")
        component = {
            "id": "auth",
            "doc_id": "architecture.component.auth",
            "name": "Authentication",
            "kind": "ui-component",
            "profile": "frontend-ui",
            "status": "active",
            "area": "frontend",
            "sources": ["src/auth.py"],
            "tests": ["tests/auth_test.py"],
        }
        self._write_catalog(
            components=[component],
            exclude=[{"glob": "src/generated/**", "reason": "generated output"}],
        )
        documents, _, by_id, aliases = self._reload_documents()
        issues, _, _ = docs_guard.validate_architecture_catalog(
            self.repository, by_id, aliases
        )
        self.assertNotIn("source_uncovered", {issue.code for issue in issues})

    def test_empty_and_placeholder_component_sections_are_rejected(self) -> None:
        """Section headings alone or template prose cannot satisfy the contract."""
        component = self.repository / "docs/architecture/areas/frontend/components/auth.md"
        text = docs_guard._without_managed_links(component.read_text())
        text = text.replace(
            "Owns the authenticated entry flow and deliberately excludes persistence.",
            "TBD",
        ).replace(
            "Exports the authenticate function to the application container.",
            "",
        )
        component.write_text(text)
        documents, _ = docs_guard.load_documents(self.repository)
        codes = {issue.code for issue in docs_guard.lint_component_sections(documents)}
        self.assertIn("component_section_placeholder", codes)
        self.assertIn("component_section_empty", codes)

    def test_generate_check_detects_and_write_repairs_drift_idempotently(self) -> None:
        """Generated projections have a byte-stable check/write contract."""
        root = self.repository / "docs/architecture/README.md"
        root.write_text(root.read_text().replace("- Children:", "- Children changed:"))
        issues, changed = docs_guard.generate_repository(self.repository, write=False)
        self.assertIn("managed_links_drift", {issue.code for issue in issues})
        self.assertEqual([], changed)
        issues, changed = docs_guard.generate_repository(self.repository, write=True)
        self.assertEqual([], issues)
        self.assertIn("docs/architecture/README.md", changed)
        issues, changed = docs_guard.generate_repository(self.repository, write=True)
        self.assertEqual(([], []), (issues, changed))

    def test_bootstrap_dry_run_apply_and_repeat_are_idempotent(self) -> None:
        """Dry-run is read-only and repeated apply produces no further actions."""
        empty_repository = Path(self.temporary_directory.name) / "empty-repository"
        empty_repository.mkdir()
        (empty_repository / "lefthook.yml").write_text(
            "pre-push:\n  commands:\n    existing-check:\n      run: echo existing\n",
            encoding="utf-8",
        )

        issues, dry_run_actions = docs_guard.bootstrap_repository(
            empty_repository, apply=False
        )
        self.assertEqual([], [issue for issue in issues if issue.severity == "error"])
        self.assertGreater(len(dry_run_actions), 10)
        self.assertFalse((empty_repository / "docs").exists())

        issues, apply_actions = docs_guard.bootstrap_repository(
            empty_repository, apply=True
        )
        self.assertEqual([], [issue for issue in issues if issue.severity == "error"])
        self.assertTrue((empty_repository / "docs/README.md").is_file())
        self.assertTrue(
            (empty_repository / "docs/architecture/system/deployments/README.md").is_file()
        )
        self.assertTrue((empty_repository / ".codex/scripts/docs_guard.py").is_file())
        project_hooks = json.loads(
            (empty_repository / ".codex/hooks.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            {"SessionStart", "SubagentStart", "UserPromptSubmit", "Stop"},
            set(project_hooks["hooks"]),
        )
        self.assertIn(
            ".agents/skills/architecture-docs-keeper/scripts/docs_hook.py",
            project_hooks["hooks"]["Stop"][0]["hooks"][0]["command"],
        )
        merged_lefthook = (empty_repository / "lefthook.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("existing-check", merged_lefthook)
        self.assertIn(docs_guard.LEFTHOOK_START, merged_lefthook)
        self.assertGreater(len(apply_actions), 10)

        issues, repeated_actions = docs_guard.bootstrap_repository(
            empty_repository, apply=True
        )
        self.assertEqual([], [issue for issue in issues if issue.severity == "error"])
        self.assertEqual([], repeated_actions)

    def test_migration_preserves_legacy_content_redirects_links_and_is_idempotent(self) -> None:
        """Every accepted legacy mapping preserves content and stabilizes after apply."""
        legacy_repository = Path(self.temporary_directory.name) / "legacy-repository"
        legacy_repository.mkdir()

        def legacy_write(relative_path: str, content: str) -> None:
            path = legacy_repository / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        legacy_write("src/auth.py", "def authenticate():\n    return True\n")
        legacy_write("tests/auth_test.py", "def test_authenticate():\n    assert True\n")
        legacy_write("docs/architecture/README.md", "# Legacy architecture\n\nRoot evidence survives.\n")
        legacy_write(
            "docs/architecture/frontend/README.md",
            "# Legacy frontend\n\n[Authentication](components/auth.md)\n",
        )
        legacy_write(
            "docs/architecture/frontend/components/auth.md",
            "---\ncomponent_id: authentication.auth\narea: frontend\nstatus: active\n"
            "sources:\n  - src/auth.py\n  - tests/auth_test.py\n---\n"
            + COMPONENT_BODY
            + "\nLegacy component evidence survives byte-for-byte in the body.\n",
        )
        legacy_write(
            "docs/superpowers/plans/session-plan.md",
            "# Session plan\n\nLegacy plan evidence survives.\n",
        )
        legacy_write(
            "docs/superpowers/specs/session-spec.md",
            "# Session specification\n\nLegacy specification evidence survives.\n",
        )
        legacy_write(
            "docs/components/authentication.auth/changelog.md",
            "# Authentication history\n\nLegacy changelog evidence survives.\n",
        )
        legacy_write(
            "docs/architecture/decisions.md",
            "# Decisions\n\nLegacy decision evidence survives.\n",
        )

        issues, plan = docs_guard.migrate_repository(legacy_repository, apply=False)
        self.assertEqual([], [issue for issue in issues if issue.severity == "error"])
        self.assertGreater(len(plan), 10)
        self.assertFalse((legacy_repository / "docs/README.md").exists())

        issues, actions = docs_guard.migrate_repository(legacy_repository, apply=True)
        self.assertEqual([], [issue for issue in issues if issue.severity == "error"])
        self.assertGreater(len(actions), 10)
        expected_phrases = {
            "docs/architecture/areas/frontend/components/authentication.auth.md": "Legacy component evidence survives",
            "docs/plans/session-plan.md": "Legacy plan evidence survives",
            "docs/specifications/session-spec.md": "Legacy specification evidence survives",
            "docs/journals/components/authentication.auth.md": "Legacy changelog evidence survives",
            "docs/decisions/0001-legacy-decisions.md": "Legacy decision evidence survives",
        }
        for relative_path, phrase in expected_phrases.items():
            self.assertIn(
                phrase,
                (legacy_repository / relative_path).read_text(encoding="utf-8"),
            )
        redirect_text = (
            legacy_repository / "docs/architecture/frontend/components/auth.md"
        ).read_text(encoding="utf-8")
        self.assertIn("doc_type: redirect", redirect_text)
        self.assertIn(
            "redirect_to: architecture.component.authentication.auth",
            redirect_text,
        )
        migrated_area = (
            legacy_repository / "docs/architecture/areas/frontend/README.md"
        ).read_text(encoding="utf-8")
        self.assertIn("components/authentication.auth.md", migrated_area)
        generated_catalog = json.loads(
            (legacy_repository / "docs/catalog.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(generated_catalog["aliases"]), 6)

        issues, repeated_actions = docs_guard.migrate_repository(
            legacy_repository, apply=True
        )
        self.assertEqual([], [issue for issue in issues if issue.severity == "error"])
        self.assertEqual([], repeated_actions)

    def test_migration_refuses_destination_collision(self) -> None:
        """Migration never overwrites a conflicting canonical destination."""
        legacy_repository = Path(self.temporary_directory.name) / "collision-repository"
        source = legacy_repository / "docs/superpowers/plans/example.md"
        destination = legacy_repository / "docs/plans/example.md"
        source.parent.mkdir(parents=True)
        destination.parent.mkdir(parents=True)
        source.write_text("# Original legacy plan\n", encoding="utf-8")
        destination.write_text("# Existing canonical plan\n", encoding="utf-8")
        issues, _ = docs_guard.migrate_repository(legacy_repository, apply=True)
        self.assertIn(
            "migration_destination_exists", {issue.code for issue in issues}
        )
        self.assertEqual(
            "# Existing canonical plan\n", destination.read_text(encoding="utf-8")
        )

    def test_cli_audit_json_and_internal_links_are_runnable(self) -> None:
        """Public audit and links subcommands expose stable machine behavior."""
        audit = subprocess.run(
            [
                sys.executable,
                str(GUARD_PATH),
                "audit",
                str(self.repository),
                "--format",
                "json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, audit.returncode, audit.stderr)
        self.assertTrue(json.loads(audit.stdout)["ok"])
        links = subprocess.run(
            [
                sys.executable,
                str(GUARD_PATH),
                "links",
                str(self.repository),
                "--internal",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, links.returncode, links.stderr)


if __name__ == "__main__":
    unittest.main()
