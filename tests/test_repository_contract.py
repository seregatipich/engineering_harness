"""Repository contracts for the project-local documentation skill."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPOSITORY_ROOT / ".agents/skills/architecture-docs-keeper"


EXPECTED_OWNERSHIP = {
    "documentation.guard": {
        "sources": [
            ".agents/skills/architecture-docs-keeper/scripts/docs_guard.py",
            ".codex/scripts/docs_guard.py",
            "scripts/docs-guard",
        ],
        "tests": [
            ".agents/skills/architecture-docs-keeper/tests/test_docs_guard.py",
            ".agents/skills/architecture-docs-keeper/tests/test_docs_guard_adversarial.py",
        ],
    },
    "documentation.lifecycle-hooks": {
        "sources": [
            ".agents/skills/architecture-docs-keeper/scripts/docs_hook.py",
            ".codex/hooks.json",
        ],
        "tests": [
            ".agents/skills/architecture-docs-keeper/tests/test_docs_hook.py"
        ],
    },
    "documentation.workflow-skill": {
        "sources": [
            ".agents/skills/architecture-docs-keeper/SKILL.md",
            ".agents/skills/architecture-docs-keeper/agents/openai.yaml",
            ".agents/skills/architecture-docs-keeper/references/architecture-standard.md",
        ],
        "tests": [
            ".agents/skills/architecture-docs-keeper/tests/test_skill_contract.py"
        ],
    },
    "documentation.project-integration": {
        "sources": [
            ".github/workflows/docs-guard.yml",
            ".gitignore",
            "AGENTS.md",
            "LICENSE",
            "README.md",
            "lefthook.yml",
        ],
        "tests": ["tests/test_repository_contract.py"],
    },
}


class RepositoryContractTestCase(unittest.TestCase):
    """Verify project scope, exact ownership, wrapper behavior, and CI wiring."""

    def test_skill_is_repository_scoped_without_marketplace_installation(self) -> None:
        """Discovery uses .agents/skills and requires no user or plugin install."""
        self.assertTrue((SKILL_ROOT / "SKILL.md").is_file())
        self.assertFalse((REPOSITORY_ROOT / ".agents/plugins/marketplace.json").exists())
        self.assertFalse((REPOSITORY_ROOT / "plugins").exists())
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("project scope", readme)
        self.assertIn("No user-level", readme)
        self.assertNotIn("codex plugin add", readme)

    def test_repo_local_guard_is_byte_identical_to_skill_guard(self) -> None:
        """Repository gates invoke the same validator implementation the skill ships."""
        skill_guard = SKILL_ROOT / "scripts/docs_guard.py"
        local_guard = REPOSITORY_ROOT / ".codex/scripts/docs_guard.py"

        self.assertEqual(skill_guard.read_bytes(), local_guard.read_bytes())

    def test_shell_wrapper_executes_generate_then_change_aware_audit(self) -> None:
        """The executable wrapper forwards repository, base, and trailing arguments."""
        wrapper = REPOSITORY_ROOT / "scripts/docs-guard"
        self.assertTrue(wrapper.stat().st_mode & stat.S_IXUSR)

        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            subprocess.run(
                ["git", "-C", str(repository), "init", "--quiet"],
                check=True,
                capture_output=True,
            )
            guard = repository / ".codex/scripts/docs_guard.py"
            guard.parent.mkdir(parents=True)
            guard.write_text(
                """import os
import sys
with open(os.environ["DOCS_GUARD_TEST_LOG"], "a", encoding="utf-8") as log:
    log.write("|".join(sys.argv[1:]) + "\\n")
""",
                encoding="utf-8",
            )
            call_log = repository / "calls.log"
            environment = os.environ.copy()
            environment.update(
                {
                    "DOCS_GUARD_BASE": "base-object",
                    "DOCS_GUARD_TEST_LOG": str(call_log),
                }
            )

            subprocess.run(
                [str(wrapper), str(repository), "--json-summary"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                env=environment,
            )

            self.assertEqual(
                [
                    f"generate|{repository.resolve()}|--check",
                    f"audit|{repository.resolve()}|--base|base-object|--format|human|--json-summary",
                ],
                call_log.read_text(encoding="utf-8").splitlines(),
            )

    def test_architecture_catalog_owns_every_non_documentation_file(self) -> None:
        """Four component records account for the complete selected project surface."""
        catalog = json.loads(
            (REPOSITORY_ROOT / "docs/architecture/catalog.json").read_text(
                encoding="utf-8"
            )
        )
        components = {component["id"]: component for component in catalog["components"]}

        self.assertEqual(set(EXPECTED_OWNERSHIP), set(components))
        for component_id, expected in EXPECTED_OWNERSHIP.items():
            self.assertEqual(expected["sources"], components[component_id]["sources"])
            self.assertEqual(expected["tests"], components[component_id]["tests"])
        selected = sorted(
            path
            for ownership in EXPECTED_OWNERSHIP.values()
            for field_name in ("sources", "tests")
            for path in ownership[field_name]
        )
        self.assertEqual(selected, sorted(catalog["inventory"]["include"]))
        self.assertEqual([], catalog["inventory"]["exclude"])
        self.assertTrue(all((REPOSITORY_ROOT / path).is_file() for path in selected))

    def test_workflow_runs_tests_and_change_aware_documentation_gate(self) -> None:
        """CI tests every layer and audits against an event-derived base object."""
        workflow = (REPOSITORY_ROOT / ".github/workflows/docs-guard.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn(
            "python3 -m unittest discover -s .agents/skills/architecture-docs-keeper/tests -v",
            workflow,
        )
        self.assertIn("python3 tests/test_repository_contract.py -v", workflow)
        self.assertIn("github.event.pull_request.base.sha", workflow)
        self.assertIn("github.event.before", workflow)
        self.assertIn("github.event.repository.default_branch", workflow)
        self.assertIn('git merge-base HEAD "origin/$DEFAULT_BRANCH"', workflow)
        self.assertIn("git hash-object -t tree /dev/null", workflow)
        self.assertIn('audit . --base "$base" --format human', workflow)
        self.assertIn("links . --internal", workflow)
        self.assertIn("generate --check .", workflow)
        self.assertIn("audit . --format human", workflow)


if __name__ == "__main__":
    unittest.main()
