"""Adversarial contract tests for the architecture documentation guard.

The suite intentionally describes safety and completeness requirements that the
guard must satisfy even when repository state is hostile, stale, or partially
migrated.  Fixtures that exercise an existing repository use the public
bootstrap API only to establish an otherwise-valid baseline.  The canonical
schema assertion is deliberately independent from implementation constants.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = SKILL_ROOT / "scripts" / "docs_guard.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "architecture_docs_guard_adversarial", GUARD_PATH
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load docs guard from {GUARD_PATH}")
docs_guard = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = docs_guard
MODULE_SPEC.loader.exec_module(docs_guard)


EXPECTED_CANONICAL_RECORDS = {
    "docs/README.md": ("docs.root", "root", None),
    "docs/architecture/README.md": (
        "architecture.root",
        "architecture-root",
        "docs.root",
    ),
    "docs/architecture/system/README.md": (
        "architecture.system.index",
        "architecture-root",
        "architecture.root",
    ),
    "docs/architecture/system/context.md": (
        "architecture.context.system",
        "architecture-context",
        "architecture.system.index",
    ),
    "docs/architecture/system/containers.md": (
        "architecture.container.runtime",
        "architecture-container",
        "architecture.system.index",
    ),
    "docs/architecture/system/deployments/README.md": (
        "architecture.deployments.index",
        "architecture-root",
        "architecture.system.index",
    ),
    "docs/architecture/areas/README.md": (
        "architecture.areas.index",
        "architecture-root",
        "architecture.root",
    ),
    "docs/architecture/flows/README.md": (
        "architecture.flows.index",
        "architecture-root",
        "architecture.root",
    ),
    "docs/architecture/concepts/README.md": (
        "architecture.concepts.index",
        "architecture-root",
        "architecture.root",
    ),
    "docs/plans/README.md": ("plans.root", "root", "docs.root"),
    "docs/specifications/README.md": (
        "specifications.root",
        "root",
        "docs.root",
    ),
    "docs/journals/README.md": (
        "journals.root",
        "journal-root",
        "docs.root",
    ),
    "docs/journals/tasks/README.md": (
        "journals.tasks.index",
        "journal-root",
        "journals.root",
    ),
    "docs/journals/components/README.md": (
        "journals.components.index",
        "journal-root",
        "journals.root",
    ),
    "docs/decisions/README.md": ("decisions.root", "root", "docs.root"),
    "docs/operations/README.md": ("operations.root", "root", "docs.root"),
    "docs/development/README.md": (
        "development.root",
        "root",
        "docs.root",
    ),
}


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
    """Render one schema-v2 front matter block without guard helpers."""
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
        if anchor is not None:
            lines.append(f"    anchor: {anchor}")
    lines.extend(["---", ""])
    return "\n".join(lines)


def component_body(title: str) -> str:
    """Return substantive content for every required component section."""
    return f"""# {title}

## Summary

Provides the documented {title.lower()} boundary for this fixture.

## Responsibility

Owns its public behavior and delegates unrelated work to explicit dependencies.

## Boundaries

Accepts typed input at its entry point and returns a deterministic result.

## Entry points and public interfaces

Exports one callable interface used by the fixture application.

## Dependencies

Uses only dependencies represented in the architecture graph.

## Data and control flow

Receives input, validates it, and returns the resulting value.

## State and side effects

Does not persist state and performs no hidden external side effects.

## Failure modes and recovery

Rejects invalid input and permits the caller to retry safely.

## Security and permissions

Validates untrusted input before granting access to protected behavior.

## Observability and operations

Reports failures through the caller's structured logging boundary.

## Tests and evidence

The authored catalog identifies implementation and executable test evidence.

## Change impact

Callers, contracts, and integration tests require review after changes.

## Profile requirements

Documents interaction, accessibility, and user-visible failure behavior.

## Related documentation
"""


def area_body(title: str) -> str:
    """Return substantive content for every required architecture-area section."""
    return f"""# {title}

## Responsibility

Owns the {title.lower()} runtime and its component boundaries.

## Boundaries

Accepts requests through documented entry points and delegates persistence.

## Entry points

The application container invokes the area's exported interfaces.

## Components

Catalog component records enumerate the implementation owned by this area.

## Dependencies

Declared graph edges identify every dependency crossing the area boundary.

## Data and control flow

Validated input flows through owned components and returns typed output.

## Security and operations

Authorization, structured logs, and recovery behavior are reviewed together.

## Related documentation

Graph-generated navigation follows this authored area description.
"""


def component_journal_body(title: str, baseline_entry: str) -> str:
    """Return a structured append-only component journal fixture."""
    return f"""# {title} journal

## Component

Tracks architecture.component.{title.lower()} and its owned source evidence.

## Timeline

2026-01-01: {baseline_entry}

## Current operational notes

The component has no unresolved operational exception in this fixture.

## Related documentation

Graph-generated navigation follows this append-only record.
"""


def decision_body(title: str, decision_text: str) -> str:
    """Return substantive content for every required decision section."""
    return f"""# {title}

## Context

The fixture needs one stable architectural boundary and reviewable rationale.

## Decision drivers

Correctness, maintainability, and explicit ownership drive the choice.

## Considered options

Keeping the current boundary and splitting it were both evaluated.

## Decision

{decision_text}

## Consequences

Callers depend on the documented interface and its verification evidence.

## Verification

The adversarial regression suite verifies the invariant mechanically.

## Amendments

No amendments have been accepted for this decision record.

## Related documentation

Graph-generated navigation follows this immutable decision.
"""


def snapshot_tree(root: Path) -> dict[str, tuple[str, object, int]]:
    """Capture repository structure, bytes, link targets, and permission modes."""
    snapshot: dict[str, tuple[str, object, int]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode & 0o7777
        if path.is_symlink():
            snapshot[relative] = ("symlink", os.readlink(path), mode)
        elif path.is_dir():
            snapshot[relative] = ("directory", None, mode)
        else:
            snapshot[relative] = ("file", path.read_bytes(), mode)
    return snapshot


class DocsGuardAdversarialTestCase(unittest.TestCase):
    """Exercise false-pass, false-fail, and destructive-write boundaries."""

    @classmethod
    def setUpClass(cls) -> None:
        """Build one immutable committed baseline reused by isolated test copies."""
        cls.template_directory = tempfile.TemporaryDirectory()
        cls.template_repository = Path(cls.template_directory.name) / "template"
        cls.template_repository.mkdir()

        def write(relative_path: str, content: str) -> None:
            path = cls.template_repository / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        def canonical_id(relative_path: str) -> str:
            for path, doc_id, _, _, _ in docs_guard.CANONICAL_DOCUMENTS:
                if path == relative_path:
                    return doc_id
            raise AssertionError(f"Missing canonical fixture record for {relative_path}")

        subprocess.run(
            ["git", "-C", str(cls.template_repository), "init", "--quiet"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(cls.template_repository),
                "config",
                "user.email",
                "adversarial@example.invalid",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(cls.template_repository),
                "config",
                "user.name",
                "Docs Guard Adversarial Tests",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        write("src/auth.py", "def authenticate():\n    return True\n")
        write("tests/auth_test.py", "def test_authenticate():\n    assert True\n")
        bootstrap_issues, _ = docs_guard.bootstrap_repository(
            cls.template_repository, apply=True
        )
        bootstrap_errors = [
            issue for issue in bootstrap_issues if issue.severity == "error"
        ]
        if bootstrap_errors:
            raise AssertionError(f"Unable to build adversarial baseline: {bootstrap_errors}")
        area_index_id = canonical_id("docs/architecture/areas/README.md")
        component_journal_index_id = canonical_id(
            "docs/journals/components/README.md"
        )
        write(
            "docs/architecture/areas/frontend/README.md",
            front_matter(
                doc_id="architecture.area.frontend",
                doc_type="architecture-area",
                title="Frontend",
                parent_id=area_index_id,
            )
            + area_body("Frontend"),
        )
        write(
            "docs/architecture/areas/frontend/components/auth.md",
            front_matter(
                doc_id="architecture.component.auth",
                doc_type="architecture-component",
                title="Authentication",
                parent_id="architecture.area.frontend",
                profile="frontend-ui",
            )
            + component_body("Authentication"),
        )
        write(
            "docs/journals/components/auth.md",
            front_matter(
                doc_id="journal.component.auth",
                doc_type="journal-component",
                title="Authentication journal",
                parent_id=component_journal_index_id,
            )
            + component_journal_body(
                "Authentication", "Authentication component baseline recorded."
            ),
        )
        auth_component = {
            "id": "auth",
            "doc_id": "architecture.component.auth",
            "name": "Auth",
            "kind": "ui-component",
            "profile": "frontend-ui",
            "status": "active",
            "area": "frontend",
            "sources": ["src/auth.py"],
            "tests": ["tests/auth_test.py"],
        }
        write(
            "docs/architecture/catalog.json",
            json.dumps(
                {
                    "schema_version": 2,
                    "inventory": {
                        "include": ["src/**/*.py", "tests/**/*.py"],
                        "exclude": [],
                    },
                    "areas": [
                        {
                            "id": "frontend",
                            "name": "Frontend",
                            "doc_id": "architecture.area.frontend",
                        }
                    ],
                    "components": [auth_component],
                    "relationships": [],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        generation_issues, _ = docs_guard.generate_repository(
            cls.template_repository, write=True
        )
        if generation_issues:
            raise AssertionError(
                f"Unable to generate adversarial baseline: {generation_issues}"
            )
        audit_issues, _ = docs_guard.audit_repository(cls.template_repository)
        audit_errors = [issue for issue in audit_issues if issue.severity == "error"]
        if audit_errors:
            raise AssertionError(
                f"Adversarial baseline does not pass a full audit: {audit_errors}"
            )
        subprocess.run(
            ["git", "-C", str(cls.template_repository), "add", "-A"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(cls.template_repository),
                "commit",
                "--quiet",
                "-m",
                "valid documentation baseline",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        """Release the shared immutable fixture template."""
        cls.template_directory.cleanup()

    def setUp(self) -> None:
        """Copy the committed template into a private disposable workspace."""
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.workspace = Path(self.temporary_directory.name)
        self.repository = self.workspace / "repository"
        shutil.copytree(self.template_repository, self.repository, symlinks=True)
        self.area_index_id = self._canonical_id(
            "docs/architecture/areas/README.md"
        )
        self.component_journal_index_id = self._canonical_id(
            "docs/journals/components/README.md"
        )
        self.auth_component = self._component_record("auth")
        self.base = self._git("rev-parse", "HEAD").stdout.strip()

    def _git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        """Run Git successfully in the primary fixture repository."""
        return subprocess.run(
            ["git", "-C", str(self.repository), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    def _write(self, relative_path: str, content: str) -> Path:
        """Write one UTF-8 file under the primary fixture repository."""
        path = self.repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _canonical_id(self, relative_path: str) -> str:
        """Resolve the implementation's current ID only for neutral baselines."""
        for path, doc_id, _, _, _ in docs_guard.CANONICAL_DOCUMENTS:
            if path == relative_path:
                return doc_id
        self.fail(f"Missing canonical fixture record for {relative_path}")

    def _component_record(self, slug: str) -> dict[str, object]:
        """Return a catalog component record for a standard fixture component."""
        return {
            "id": slug,
            "doc_id": f"architecture.component.{slug}",
            "name": slug.replace("-", " ").title(),
            "kind": "ui-component",
            "profile": "frontend-ui",
            "status": "active",
            "area": "frontend",
            "sources": [f"src/{slug}.py"],
            "tests": [f"tests/{slug}_test.py"],
        }

    def _write_catalog(
        self,
        components: list[dict[str, object]],
        *,
        include: list[str] | None = None,
        exclude: list[dict[str, str]] | None = None,
        relationships: list[dict[str, str]] | None = None,
        areas: list[dict[str, str]] | None = None,
    ) -> None:
        """Write an authored architecture catalog."""
        payload = {
            "schema_version": 2,
            "inventory": {
                "include": include
                if include is not None
                else ["src/**/*.py", "tests/**/*.py"],
                "exclude": exclude if exclude is not None else [],
            },
            "areas": areas
            if areas is not None
            else [
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

    def _add_component_documents(
        self,
        slug: str,
        *,
        parent_id: str = "architecture.area.frontend",
        relations: tuple[tuple[str, str, str | None], ...] = (),
        include_source: bool = True,
    ) -> dict[str, object]:
        """Add component and journal pages, optionally with source evidence."""
        if include_source:
            self._write(f"src/{slug}.py", f"NAME = {slug!r}\n")
            self._write(f"tests/{slug}_test.py", "def test_component():\n    assert True\n")
        self._write(
            f"docs/architecture/areas/frontend/components/{slug}.md",
            front_matter(
                doc_id=f"architecture.component.{slug}",
                doc_type="architecture-component",
                title=slug.replace("-", " ").title(),
                parent_id=parent_id,
                relations=relations,
                profile="frontend-ui",
            )
            + component_body(slug.replace("-", " ").title()),
        )
        self._write(
            f"docs/journals/components/{slug}.md",
            front_matter(
                doc_id=f"journal.component.{slug}",
                doc_type="journal-component",
                title=f"{slug.title()} journal",
                parent_id=self.component_journal_index_id,
            )
            + component_journal_body(slug.title(), "Component baseline recorded."),
        )
        return self._component_record(slug)

    @staticmethod
    def _issue_text(issues: list[object]) -> str:
        """Join issue fields for readable semantic assertions."""
        return "\n".join(
            " ".join(
                str(value)
                for value in (
                    getattr(issue, "code", ""),
                    getattr(issue, "path", ""),
                    getattr(issue, "message", ""),
                )
                if value is not None
            )
            for issue in issues
        ).casefold()

    def assert_issue_matches(self, issues: list[object], pattern: str) -> None:
        """Require at least one diagnostic matching a semantic regular expression."""
        text = self._issue_text(issues)
        self.assertRegex(text, pattern, msg=f"Issues did not match {pattern!r}:\n{text}")

    def test_source_change_requires_task_and_component_journal_updates(self) -> None:
        """Every source edit requires task evidence and an appended component entry."""
        source = self.repository / "src/auth.py"
        source.write_text(source.read_text() + "\nAUTH_VERSION = 2\n", encoding="utf-8")

        issues, _ = docs_guard.audit_repository(self.repository, base=self.base)

        self.assert_issue_matches(issues, r"(?:task.*journal|journal.*task)")
        self.assert_issue_matches(issues, r"(?:component.*journal|journal.*component)")

    def test_accepted_decision_body_is_immutable_across_base_diff(self) -> None:
        """Accepted decision history cannot be rewritten in place."""
        decision = self._write(
            "docs/decisions/0001-auth-boundary.md",
            front_matter(
                doc_id="decision.0001.auth-boundary",
                doc_type="decision",
                title="Authentication boundary",
                status="accepted",
                parent_id="decisions.root",
            )
            + decision_body(
                "Authentication boundary", "Original accepted rationale."
            ),
        )
        issues, _ = docs_guard.generate_repository(self.repository, write=True)
        self.assertEqual([], issues)
        self._git("add", "-A")
        self._git("commit", "--quiet", "-m", "accepted decision")
        decision_base = self._git("rev-parse", "HEAD").stdout.strip()
        decision.write_text(
            decision.read_text().replace(
                "Original accepted rationale.", "Rewritten accepted rationale."
            ),
            encoding="utf-8",
        )

        issues, _ = docs_guard.audit_repository(self.repository, base=decision_base)

        self.assert_issue_matches(issues, r"(?:immutable|history.*rewrite|accepted.*chang)")

    def test_component_journal_history_is_append_only(self) -> None:
        """Existing component journal entries cannot be rewritten or removed."""
        journal = self.repository / "docs/journals/components/auth.md"
        journal.write_text(
            journal.read_text().replace(
                "Authentication component baseline recorded.",
                "Authentication history was silently replaced.",
            ),
            encoding="utf-8",
        )

        issues, _ = docs_guard.audit_repository(self.repository, base=self.base)

        self.assert_issue_matches(issues, r"(?:append.only|history.*rewrite|journal.*rewrit)")

    def test_deleted_tracked_source_is_reported_as_missing(self) -> None:
        """A stale catalog cannot keep a deleted tracked source looking present."""
        (self.repository / "src/auth.py").unlink()

        issues, _ = docs_guard.audit_repository(self.repository, base=self.base)
        text = self._issue_text(issues)

        self.assertIn("src/auth.py", text)
        self.assertRegex(text, r"(?:missing|deleted|matched no files|does not exist)")

    def test_renamed_tracked_source_reports_old_and_new_paths(self) -> None:
        """A stale catalog reports both halves of a tracked source rename."""
        self._git("mv", "src/auth.py", "src/authentication.py")

        issues, _ = docs_guard.audit_repository(self.repository, base=self.base)
        text = self._issue_text(issues)

        self.assertIn("src/auth.py", text)
        self.assertIn("src/authentication.py", text)

    def test_changed_excluded_file_uses_catalog_glob_key(self) -> None:
        """A justified exclusion remains excluded during change-aware auditing."""
        generated = self._write("src/generated/output.py", "VALUE = 1\n")
        self._write_catalog(
            [self.auth_component],
            exclude=[
                {
                    "glob": "src/generated/**",
                    "reason": "deterministically generated fixture output",
                }
            ],
        )
        self._git("add", "-A")
        self._git("commit", "--quiet", "-m", "exclude generated source")
        excluded_base = self._git("rev-parse", "HEAD").stdout.strip()
        generated.write_text("VALUE = 2\n", encoding="utf-8")

        issues, _ = docs_guard.audit_repository(self.repository, base=excluded_base)
        offending = [
            issue
            for issue in issues
            if issue.code == "changed_source_unowned"
            and "src/generated/output.py" in (issue.path or issue.message)
        ]

        self.assertEqual([], offending)

    def test_blanket_inventory_exclusion_is_rejected(self) -> None:
        """An exclusion cannot erase all reviewable source coverage."""
        self._write_catalog(
            [],
            include=["src/**"],
            exclude=[{"glob": "src/**", "reason": "claimed generated output"}],
            areas=[],
        )

        issues, _ = docs_guard.audit_repository(self.repository)

        self.assert_issue_matches(issues, r"(?:blanket|overbroad|broad).*exclu|exclu.*all")

    def test_source_symlink_outside_repository_is_rejected(self) -> None:
        """Catalog ownership cannot follow a source symlink outside the repository."""
        external = self.workspace / "external-source.py"
        external.write_text("EXTERNAL_SENTINEL = True\n", encoding="utf-8")
        source = self.repository / "src/auth.py"
        source.unlink()
        source.symlink_to(external)

        issues, _ = docs_guard.audit_repository(self.repository)

        self.assert_issue_matches(
            issues,
            r"src/auth\.py.*(?:symlink|outside|escape|traversal)|"
            r"(?:symlink|outside|escape|traversal).*src/auth\.py",
        )

    def test_generate_refuses_doc_symlink_and_preserves_external_bytes(self) -> None:
        """Generation never follows a documentation symlink outside the repository."""
        external = self.workspace / "external-document.md"
        external.write_text(
            front_matter(
                doc_id="development.external-sentinel",
                doc_type="development",
                title="External sentinel",
                parent_id=self._canonical_id("docs/development/README.md"),
            )
            + "# External sentinel\n\nEXTERNAL_BYTES_MUST_NOT_CHANGE\n\n"
            + "## Related documentation\n",
            encoding="utf-8",
        )
        before = external.read_bytes()
        link = self.repository / "docs/development/external.md"
        link.symlink_to(external)

        issues, _ = docs_guard.generate_repository(self.repository, write=True)

        self.assert_issue_matches(issues, r"(?:symlink|outside|escape|traversal)")
        self.assertEqual(before, external.read_bytes())

    def test_fenced_generated_markers_are_preserved_byte_for_byte(self) -> None:
        """Marker examples inside fenced code are authored content, not control data."""
        component = (
            self.repository
            / "docs/architecture/areas/frontend/components/auth.md"
        )
        fenced_example = (
            "```markdown\n"
            + docs_guard.MANAGED_LINKS_START
            + "\nFENCED_MARKER_SENTINEL\n"
            + docs_guard.MANAGED_LINKS_END
            + "\n```\n\n"
        )
        component.write_text(
            component.read_text().replace(
                "# Authentication\n\n", "# Authentication\n\n" + fenced_example, 1
            ),
            encoding="utf-8",
        )

        docs_guard.generate_repository(self.repository, write=True)
        rewritten = component.read_text(encoding="utf-8")

        self.assertIn(fenced_example, rewritten)

    def test_unmatched_generated_marker_refuses_write_and_preserves_bytes(self) -> None:
        """An unmatched managed marker is diagnosed without normalizing the file."""
        component = (
            self.repository
            / "docs/architecture/areas/frontend/components/auth.md"
        )
        component.write_text(
            component.read_text() + "\n" + docs_guard.MANAGED_LINKS_START + "\n",
            encoding="utf-8",
        )
        before = component.read_bytes()

        issues, _ = docs_guard.generate_repository(self.repository, write=True)

        self.assert_issue_matches(issues, r"(?:marker|managed.*block).*(?:unmatched|invalid)")
        self.assertEqual(before, component.read_bytes())

    def test_duplicate_generated_markers_refuse_write_and_preserve_bytes(self) -> None:
        """Duplicate managed blocks are diagnosed without deleting authored bytes."""
        component = (
            self.repository
            / "docs/architecture/areas/frontend/components/auth.md"
        )
        text = component.read_text(encoding="utf-8")
        start = text.index(docs_guard.MANAGED_LINKS_START)
        end = text.index(docs_guard.MANAGED_LINKS_END, start) + len(
            docs_guard.MANAGED_LINKS_END
        )
        component.write_text(text + "\n" + text[start:end] + "\n", encoding="utf-8")
        before = component.read_bytes()

        issues, _ = docs_guard.generate_repository(self.repository, write=True)

        self.assert_issue_matches(issues, r"(?:duplicate|multiple).*(?:marker|managed)")
        self.assertEqual(before, component.read_bytes())

    def test_migration_collision_leaves_entire_tree_unchanged(self) -> None:
        """Migration preflights every destination before making any filesystem change."""
        legacy = self.workspace / "migration-collision"
        source = legacy / "docs/superpowers/plans/example.md"
        destination = legacy / "docs/plans/example.md"
        source.parent.mkdir(parents=True)
        destination.parent.mkdir(parents=True)
        source.write_text("# Original legacy plan\n", encoding="utf-8")
        destination.write_text("# Existing canonical plan\n", encoding="utf-8")
        before = snapshot_tree(legacy)

        issues, _ = docs_guard.migrate_repository(legacy, apply=True)

        self.assert_issue_matches(issues, r"migration_destination_exists")
        self.assertEqual(before, snapshot_tree(legacy))

    def test_migration_preserves_unknown_legacy_front_matter(self) -> None:
        """Unrecognized factual metadata survives migration without silent deletion."""
        legacy = self.workspace / "metadata-migration"
        source = legacy / "docs/superpowers/plans/session.md"
        source.parent.mkdir(parents=True)
        source.write_text(
            "---\n"
            "owner: platform-team\n"
            "created: 2024-02-03\n"
            "custom_evidence: incident-417\n"
            "---\n"
            "# Session plan\n\nLEGACY_PLAN_BODY\n",
            encoding="utf-8",
        )

        issues, _ = docs_guard.migrate_repository(legacy, apply=True)
        destination = legacy / "docs/plans/session.md"
        migrated = destination.read_text(encoding="utf-8")

        self.assertEqual([], [issue for issue in issues if issue.severity == "error"])
        self.assertIn("owner: platform-team", migrated)
        self.assertIn("created: 2024-02-03", migrated)
        self.assertIn("custom_evidence: incident-417", migrated)
        self.assertIn("LEGACY_PLAN_BODY", migrated)

    def test_migration_preserves_legacy_system_map(self) -> None:
        """The established v1 system-map path becomes a redirect with preserved prose."""
        legacy = self.workspace / "system-map-migration"
        system_map = legacy / "docs/architecture/system-map.md"
        system_map.parent.mkdir(parents=True)
        system_map.write_text(
            "# Legacy system map\n\nSYSTEM_MAP_SENTINEL_7D9A\n",
            encoding="utf-8",
        )

        issues, _ = docs_guard.migrate_repository(legacy, apply=True)

        self.assertEqual([], [issue for issue in issues if issue.severity == "error"])
        self.assertIn("doc_type: redirect", system_map.read_text(encoding="utf-8"))
        preserved = [
            path
            for path in (legacy / "docs").rglob("*.md")
            if path != system_map
            and "SYSTEM_MAP_SENTINEL_7D9A" in path.read_text(encoding="utf-8")
        ]
        self.assertTrue(preserved, "Legacy system-map prose was not preserved canonically")

    def test_migration_recurses_nested_plans_and_specifications(self) -> None:
        """Nested legacy planning records migrate without being ignored or flattened away."""
        legacy = self.workspace / "nested-migration"
        plan = legacy / "docs/superpowers/plans/auth/session-plan.md"
        specification = legacy / "docs/superpowers/specs/auth/session-spec.md"
        plan.parent.mkdir(parents=True)
        specification.parent.mkdir(parents=True)
        plan.write_text("# Nested plan\n\nNESTED_PLAN_SENTINEL\n", encoding="utf-8")
        specification.write_text(
            "# Nested specification\n\nNESTED_SPEC_SENTINEL\n",
            encoding="utf-8",
        )

        issues, _ = docs_guard.migrate_repository(legacy, apply=True)

        self.assertEqual([], [issue for issue in issues if issue.severity == "error"])
        self.assertIn("doc_type: redirect", plan.read_text(encoding="utf-8"))
        self.assertIn("doc_type: redirect", specification.read_text(encoding="utf-8"))
        canonical_text = "\n".join(
            path.read_text(encoding="utf-8")
            for root in (legacy / "docs/plans", legacy / "docs/specifications")
            for path in root.rglob("*.md")
        )
        self.assertIn("NESTED_PLAN_SENTINEL", canonical_text)
        self.assertIn("NESTED_SPEC_SENTINEL", canonical_text)

    def test_bootstrap_tooling_collision_refuses_without_mutation(self) -> None:
        """Bootstrap never overwrites an unmanaged executable or partially installs."""
        repository = self.workspace / "bootstrap-tool-collision"
        wrapper = repository / "scripts/docs-guard"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text("#!/bin/sh\necho user-owned-wrapper\n", encoding="utf-8")
        wrapper.chmod(0o755)
        before = snapshot_tree(repository)

        issues, _ = docs_guard.bootstrap_repository(repository, apply=True)

        self.assert_issue_matches(issues, r"(?:collision|refus|unmanaged|overwrite)")
        self.assertEqual(before, snapshot_tree(repository))

    def test_bootstrap_refuses_alternate_lefthook_indentation_safely(self) -> None:
        """Unknown valid Lefthook layout causes an atomic refusal, not duplicate keys."""
        repository = self.workspace / "bootstrap-lefthook-layout"
        repository.mkdir()
        (repository / "lefthook.yml").write_text(
            "pre-push:\n"
            "    commands:\n"
            "        existing-check:\n"
            "            run: echo existing\n",
            encoding="utf-8",
        )
        before = snapshot_tree(repository)

        issues, _ = docs_guard.bootstrap_repository(repository, apply=True)

        self.assert_issue_matches(issues, r"(?:lefthook|yaml|indent).*(?:refus|unsafe|layout)")
        self.assertEqual(before, snapshot_tree(repository))

    def test_lefthook_merge_preserves_existing_pre_commit_without_duplicate_key(self) -> None:
        """A repository with only pre-commit receives one nested pre-push command."""
        existing = (
            "pre-commit:\n"
            "  commands:\n"
            "    existing-check:\n"
            "      run: python3 -m unittest\n"
        )

        merged = docs_guard._merge_lefthook(existing)

        self.assertEqual(1, merged.splitlines().count("pre-commit:"))
        self.assertEqual(1, merged.splitlines().count("pre-push:"))
        self.assertIn("existing-check", merged)
        self.assertIn("run: scripts/docs-guard .", merged)
        self.assertEqual(merged, docs_guard._merge_lefthook(merged))

    def test_canonical_ids_types_and_parents_match_v2_standard(self) -> None:
        """Canonical schema is verified against an independent normative fixture."""
        actual = {
            path: (doc_id, doc_type, parent_id)
            for path, doc_id, doc_type, parent_id, _ in docs_guard.CANONICAL_DOCUMENTS
        }

        self.assertEqual(EXPECTED_CANONICAL_RECORDS, actual)

    def test_orphan_component_page_and_journal_are_rejected(self) -> None:
        """Every component page and component journal must have a catalog record."""
        self._add_component_documents("rogue", include_source=False)

        issues, _ = docs_guard.audit_repository(self.repository)
        relevant = [
            issue
            for issue in issues
            if "architecture.component.rogue" in issue.message
            or issue.path
            == "docs/architecture/areas/frontend/components/rogue.md"
            or "journal.component.rogue" in issue.message
        ]

        self.assert_issue_matches(relevant, r"(?:catalog|unregistered|orphan)")

    def test_catalog_component_requires_component_journal(self) -> None:
        """A catalog component cannot exist without its append-only journal."""
        (self.repository / "docs/journals/components/auth.md").unlink()

        issues, _ = docs_guard.audit_repository(self.repository)

        self.assert_issue_matches(issues, r"component_journal_missing|component.*journal.*missing")

    def test_catalog_relationship_must_match_document_graph(self) -> None:
        """Authored catalog dependencies and document relations cannot diverge."""
        profile = self._add_component_documents("profile")
        self._write_catalog(
            [self.auth_component, profile],
            relationships=[{"from": "auth", "type": "depends-on", "to": "profile"}],
        )

        issues, _ = docs_guard.audit_repository(self.repository)

        self.assert_issue_matches(
            issues,
            r"(?:relationship|depends.on).*(?:graph|document|mirror|mismatch)",
        )

    def test_component_parent_must_match_catalog_area(self) -> None:
        """A component page parent must identify the same area as its catalog record."""
        component = (
            self.repository
            / "docs/architecture/areas/frontend/components/auth.md"
        )
        component.write_text(
            component.read_text().replace(
                "parent_id: architecture.area.frontend",
                "parent_id: architecture.root",
                1,
            ),
            encoding="utf-8",
        )

        issues, _ = docs_guard.audit_repository(self.repository)

        self.assert_issue_matches(
            issues,
            r"canonical_component_parent|"
            r"(?:component|catalog).*(?:parent|area).*(?:mismatch|wrong|differ)",
        )

    def test_redirect_cycle_is_rejected(self) -> None:
        """Redirect records must terminate at a canonical non-redirect document."""
        self._write(
            "docs/development/legacy-a.md",
            front_matter(
                doc_id="redirect.legacy.a",
                doc_type="redirect",
                title="Legacy A",
                parent_id="docs.root",
                redirect_to="redirect.legacy.b",
                relations=(("redirects-to", "redirect.legacy.b", None),),
            )
            + "# Legacy A\n\nRedirect A.\n\n## Related documentation\n",
        )
        self._write(
            "docs/development/legacy-b.md",
            front_matter(
                doc_id="redirect.legacy.b",
                doc_type="redirect",
                title="Legacy B",
                parent_id="docs.root",
                redirect_to="redirect.legacy.a",
                relations=(("redirects-to", "redirect.legacy.a", None),),
            )
            + "# Legacy B\n\nRedirect B.\n\n## Related documentation\n",
        )

        issues, _ = docs_guard.audit_repository(self.repository)

        self.assert_issue_matches(issues, r"redirect.*cycle|cycle.*redirect")

    def test_globs_are_segment_aware_and_match_dot_directories(self) -> None:
        """One star stays within a segment while double-star includes dot paths."""
        self.assertFalse(docs_guard._glob_matches("src/nested/a.py", "src/*.py"))
        self.assertTrue(
            docs_guard._glob_matches(".github/workflows/ci.yml", ".github/**")
        )
        self.assertTrue(
            docs_guard._glob_matches(".github/workflows/ci.yml", "./.github/**")
        )

    def test_globs_never_normalize_traversal_into_repository_paths(self) -> None:
        """Traversal-like inventory patterns cannot become valid in-repo matches."""
        self.assertFalse(docs_guard._glob_matches("src/a.py", "../../src/**"))
        self.assertFalse(docs_guard._glob_matches("src/a.py", "../src/**"))

    def test_shortcut_and_reference_links_are_both_extracted(self) -> None:
        """Shortcut, full, and collapsed reference links share validation coverage."""
        text = """[Shortcut]
[Full][target]
[Collapsed][]

[Shortcut]: docs/shortcut.md
[target]: docs/full.md
[Collapsed]: docs/collapsed.md
"""

        links = docs_guard.extract_markdown_links(text)
        actual = {(link.label, link.target, link.line) for link in links}

        self.assertEqual(
            {
                ("Shortcut", "docs/shortcut.md", 1),
                ("Full", "docs/full.md", 2),
                ("Collapsed", "docs/collapsed.md", 3),
            },
            actual,
        )

    def test_placeholder_prose_is_rejected_outside_component_pages(self) -> None:
        """No authored document type can satisfy the contract with placeholder prose."""
        self._write(
            "docs/operations/incomplete-runbook.md",
            front_matter(
                doc_id="operations.incomplete-runbook",
                doc_type="operations",
                title="Incomplete runbook",
                parent_id=self._canonical_id("docs/operations/README.md"),
            )
            + "# Incomplete runbook\n\nTBD\n\n## Related documentation\n",
        )

        issues, _ = docs_guard.audit_repository(self.repository)

        self.assert_issue_matches(issues, r"(?:placeholder|tbd)")

    def test_noncanonical_architecture_decision_path_is_rejected(self) -> None:
        """Architecture decisions live only in the canonical decisions directory."""
        self._write(
            "docs/architecture/decisions/rogue.md",
            front_matter(
                doc_id="decision.rogue-location",
                doc_type="decision",
                title="Rogue decision",
                status="accepted",
                parent_id="decisions.root",
            )
            + decision_body("Rogue decision", "Decision prose remains reviewable."),
        )

        issues, _ = docs_guard.audit_repository(self.repository)

        self.assert_issue_matches(issues, r"(?:decision.*path|noncanonical|wrong.*director)")


if __name__ == "__main__":
    unittest.main()
