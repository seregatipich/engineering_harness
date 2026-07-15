"""Packaging contracts for the project-local architecture documentation skill."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SKILL_ROOT.parents[2]


class SkillContractTestCase(unittest.TestCase):
    """Verify project discovery, resources, hooks, and the public workflow."""

    def test_skill_front_matter_is_project_discoverable(self) -> None:
        """The checked-in skill has only the required discovery fields."""
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---\n", skill, re.DOTALL)

        self.assertIsNotNone(match)
        assert match is not None
        keys = [
            line.split(":", 1)[0]
            for line in match.group(1).splitlines()
            if line.strip()
        ]
        self.assertEqual(["name", "description"], keys)
        self.assertIn("name: architecture-docs-keeper", match.group(1))
        self.assertIn("every editable repository task", match.group(1))

    def test_skill_contains_every_runtime_resource(self) -> None:
        """Every file required by discovery and execution exists in the skill."""
        required = {
            "SKILL.md",
            "agents/openai.yaml",
            "references/architecture-standard.md",
            "scripts/docs_guard.py",
            "scripts/docs_hook.py",
        }

        missing = sorted(path for path in required if not (SKILL_ROOT / path).is_file())

        self.assertEqual([], missing)

    def test_project_hook_descriptor_wires_all_lifecycle_boundaries(self) -> None:
        """Project hooks resolve the checked-in skill from the Git root."""
        descriptor = json.loads(
            (REPOSITORY_ROOT / ".codex/hooks.json").read_text(encoding="utf-8")
        )
        hooks = descriptor["hooks"]

        self.assertEqual(
            {"SessionStart", "SubagentStart", "UserPromptSubmit", "Stop"},
            set(hooks),
        )
        for event_name, event_entries in hooks.items():
            self.assertEqual(1, len(event_entries), event_name)
            commands = event_entries[0]["hooks"]
            self.assertEqual(1, len(commands), event_name)
            command = commands[0]
            self.assertEqual("command", command["type"])
            self.assertIn("git rev-parse --show-toplevel", command["command"])
            self.assertIn(
                ".agents/skills/architecture-docs-keeper/scripts/docs_hook.py",
                command["command"],
            )
            self.assertIn(
                "\\.agents\\skills\\architecture-docs-keeper\\scripts\\docs_hook.py",
                command["commandWindows"],
            )
            self.assertNotIn("PLUGIN_ROOT", command["command"])
            self.assertGreater(command["timeout"], 0)

    def test_skill_metadata_and_standard_define_the_v2_workflow(self) -> None:
        """Agent metadata and normative guidance expose the complete workflow."""
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        agent_metadata = (SKILL_ROOT / "agents/openai.yaml").read_text(
            encoding="utf-8"
        )
        standard = (SKILL_ROOT / "references/architecture-standard.md").read_text(
            encoding="utf-8"
        )

        for command in (
            "bootstrap --dry-run",
            "migrate --plan",
            'links "$REPOSITORY_ROOT" --internal',
            "generate --check",
            'audit "$REPOSITORY_ROOT" --base "$BASE_SHA"',
        ):
            self.assertIn(command, skill)
        self.assertIn("allow_implicit_invocation: true", agent_metadata)
        self.assertIn("$architecture-docs-keeper", agent_metadata)
        for heading in (
            "## Exact tree",
            "## Relation graph",
            "## Exhaustive coverage",
            "## Change reconciliation",
            "## Completion gate",
        ):
            self.assertIn(heading, standard)
        for forbidden in ("plugins/cache", "~/.agents/skills", "~/.codex/skills"):
            self.assertNotIn(forbidden, skill)

    def test_guard_cli_is_runnable_from_the_skill(self) -> None:
        """The canonical project-local guard exposes every public subcommand."""
        result = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts/docs_guard.py"), "--help"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        for command in ("bootstrap", "migrate", "generate", "links", "audit"):
            self.assertIn(command, result.stdout)

    def test_runtime_python_uses_only_the_standard_library(self) -> None:
        """Guard and hook have no third-party runtime import."""
        sources = (
            SKILL_ROOT / "scripts/docs_guard.py",
            SKILL_ROOT / "scripts/docs_hook.py",
        )
        third_party: dict[str, list[str]] = {}
        for source in sources:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".", 1)[0])
            external = sorted(
                name
                for name in imported
                if name != "__future__" and name not in sys.stdlib_module_names
            )
            if external:
                third_party[source.relative_to(SKILL_ROOT).as_posix()] = external

        self.assertEqual({}, third_party)


if __name__ == "__main__":
    unittest.main()
