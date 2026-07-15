"""Regression tests for the architecture documentation lifecycle hook."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SKILL_ROOT.parents[2]
HOOK_PATH = SKILL_ROOT / "scripts" / "docs_hook.py"
MODULE_SPEC = importlib.util.spec_from_file_location("architecture_docs_hook", HOOK_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load lifecycle hook from {HOOK_PATH}")
docs_hook = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = docs_hook
MODULE_SPEC.loader.exec_module(docs_hook)


class DocsHookTestCase(unittest.TestCase):
    """Exercise hook events against isolated real Git working trees."""

    def setUp(self) -> None:
        """Create one clean repository and isolated project-hook state per test."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temporary_root = Path(self.temporary_directory.name)
        self.repository = self.temporary_root / "repository"
        self.repository.mkdir()
        self.state_root = self.temporary_root / "hook-state"
        self.environment = {
            "ARCHITECTURE_DOCS_KEEPER_STATE_DIR": str(self.state_root),
            "ARCHITECTURE_DOCS_KEEPER_GUARD": "",
        }
        self._git("init", "--quiet")
        self._git("config", "user.email", "docs-hook@example.invalid")
        self._git("config", "user.name", "Docs Hook Test")
        self._write("src/app.py", "print('baseline')\n")
        self._git("add", "src/app.py")
        self._git("commit", "--quiet", "-m", "baseline")

    def _git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        """Run a successful Git command in the isolated repository."""

        return subprocess.run(
            ["git", "-C", str(self.repository), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    def _write(self, relative_path: str, content: str) -> Path:
        """Write a UTF-8 fixture inside the isolated repository."""

        path = self.repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _write_catalog(self, components: list[dict[str, object]]) -> Path:
        """Write the ownership subset of a schema-v2 architecture catalog."""

        return self._write(
            "docs/architecture/catalog.json",
            json.dumps(
                {
                    "schema_version": 2,
                    "inventory": {"include": ["src/**/*"], "exclude": []},
                    "areas": [],
                    "components": components,
                    "relationships": [],
                }
            )
            + "\n",
        )

    def _payload(self, event_name: str, **overrides: object) -> dict[str, object]:
        """Create a lifecycle payload with stable session and turn IDs."""

        payload: dict[str, object] = {
            "hook_event_name": event_name,
            "session_id": "session-1",
            "turn_id": "turn-1",
            "cwd": str(self.repository),
        }
        payload.update(overrides)
        return payload

    def _invoke(
        self,
        payload: dict[str, object],
        *,
        environment: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """Invoke ``main`` with captured stdio and an isolated environment."""

        standard_output = io.StringIO()
        standard_error = io.StringIO()
        hook_environment = environment or self.environment
        with (
            mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))),
            mock.patch.dict(os.environ, hook_environment, clear=False),
            redirect_stdout(standard_output),
            redirect_stderr(standard_error),
        ):
            exit_code = docs_hook.main()
        return exit_code, standard_output.getvalue(), standard_error.getvalue()

    def _snapshot(self, **overrides: object) -> None:
        """Record a successful baseline for the current test turn."""

        exit_code, standard_output, standard_error = self._invoke(
            self._payload("UserPromptSubmit", **overrides)
        )
        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_output)
        self.assertEqual("", standard_error)

    def test_session_start_outputs_concise_required_context(self) -> None:
        """Session start injects the explicit architecture workflow."""

        exit_code, standard_output, standard_error = self._invoke(
            self._payload("SessionStart", source="startup")
        )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_error)
        response = json.loads(standard_output)
        hook_output = response["hookSpecificOutput"]
        self.assertEqual("SessionStart", hook_output["hookEventName"])
        context = hook_output["additionalContext"]
        self.assertIn("$architecture-docs-keeper", context)
        self.assertIn("architecture maps", context)
        self.assertIn("internal link graph", context)
        self.assertIn("plans and specifications", context)
        self.assertIn("task and component journals", context)
        self.assertIn("decisions", context)
        self.assertIn("guard command", context)
        self.assertIn("read-only", context)

    def test_subagent_start_receives_the_same_documentation_invariant(self) -> None:
        """Subagents receive explicit workflow context without transcript access."""

        exit_code, standard_output, standard_error = self._invoke(
            self._payload(
                "SubagentStart",
                agent_id="agent-1",
                agent_type="worker",
                transcript_path="/must/not/be/read",
            )
        )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_error)
        response = json.loads(standard_output)
        hook_output = response["hookSpecificOutput"]
        self.assertEqual("SubagentStart", hook_output["hookEventName"])
        self.assertIn("architecture maps", hook_output["additionalContext"])
        self.assertIn("task and component journals", hook_output["additionalContext"])

    def test_preexisting_dirty_files_are_not_attributed_to_the_turn(self) -> None:
        """Unchanged dirty tracked and untracked files do not trigger the gate."""

        self._write("src/app.py", "print('preexisting user edit')\n")
        self._write("src/untracked.py", "PREEXISTING = True\n")
        self._snapshot()

        with mock.patch.object(docs_hook, "run_guard_commands") as guard:
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_output)
        self.assertEqual("", standard_error)
        guard.assert_not_called()
        self.assertEqual([], list(self.state_root.rglob("*.json")))

    def test_read_only_turn_does_not_run_documentation_checks(self) -> None:
        """A clean read-only turn exits without touching or auditing the repo."""

        self._snapshot()

        with mock.patch.object(docs_hook, "run_guard_commands") as guard:
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_output)
        self.assertEqual("", standard_error)
        guard.assert_not_called()
        self.assertEqual([], list(self.state_root.rglob("*.json")))

    def test_code_change_blocks_with_actionable_full_audit_failure(self) -> None:
        """A source change emits current Stop failure fields when audit fails."""

        self._snapshot()
        self._write("src/app.py", "print('changed by agent')\n")
        failure = "`docs_guard.py audit` exited 1: component page is missing"

        with mock.patch.object(
            docs_hook, "run_guard_commands", return_value=[failure]
        ) as guard:
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_error)
        response = json.loads(standard_output)
        self.assertIs(False, response["continue"])
        self.assertEqual(
            "Documentation system checks failed.", response["stopReason"]
        )
        self.assertIn("src/app.py", response["systemMessage"])
        self.assertIn("component page is missing", response["systemMessage"])
        self.assertIn("$architecture-docs-keeper", response["systemMessage"])
        self.assertIn("internal link graph", response["systemMessage"])
        self.assertIn("plans and specifications", response["systemMessage"])
        self.assertIn("task and component journals", response["systemMessage"])
        self.assertIn("decisions", response["systemMessage"])
        self.assertIn("reported docs_guard.py command", response["systemMessage"])
        self.assertEqual("full", guard.call_args.args[0])
        self.assertEqual(1, len(list(self.state_root.rglob("*.json"))))

    def test_broken_docs_change_runs_docs_only_checks_and_blocks(self) -> None:
        """A documentation-only edit reports full audit or generated-file drift."""

        self._snapshot()
        self._write(
            "docs/architecture/README.md",
            "[Missing component](components/missing.md)\n",
        )
        failure = "links exited 1: broken internal link components/missing.md"

        with mock.patch.object(
            docs_hook, "run_guard_commands", return_value=[failure]
        ) as guard:
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_error)
        response = json.loads(standard_output)
        self.assertIs(False, response["continue"])
        self.assertIn("broken internal link", response["systemMessage"])
        self.assertEqual("docs", guard.call_args.args[0])

    def test_docs_only_mode_runs_full_audit_and_generated_check(self) -> None:
        """Documentation edits cannot bypass content, catalog, or section validation."""
        self.assertEqual(
            (
                ("audit", str(self.repository)),
                ("generate", str(self.repository), "--check"),
            ),
            docs_hook._guard_specs("docs", self.repository),
        )

    def test_docs_only_change_without_task_journal_blocks(self) -> None:
        """Even documentation-only work requires a concrete task journal."""

        self._snapshot()
        self._write("docs/architecture/README.md", "# Architecture\n")
        self._write("docs/journals/tasks/README.md", "# Task journals\n")

        with mock.patch.object(
            docs_hook, "run_guard_commands", return_value=[]
        ) as guard:
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_error)
        response = json.loads(standard_output)
        self.assertIs(False, response["continue"])
        self.assertIn("docs/journals/tasks/*.md", response["systemMessage"])
        self.assertIn("README.md does not count", response["systemMessage"])
        self.assertEqual("docs", guard.call_args.args[0])

    def test_source_change_without_required_journals_lists_both(self) -> None:
        """Owned source work requires task and affected-component journals."""

        self._write_catalog(
            [
                {
                    "id": "api.server",
                    "sources": ["src/app.py"],
                    "tests": ["tests/test_app.py"],
                }
            ]
        )
        self._snapshot()
        self._write("src/app.py", "print('owned source change')\n")

        with mock.patch.object(
            docs_hook, "run_guard_commands", return_value=[]
        ) as guard:
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_error)
        response = json.loads(standard_output)
        self.assertIn("docs/journals/tasks/*.md", response["systemMessage"])
        self.assertIn(
            "docs/journals/components/api.server.md", response["systemMessage"]
        )
        self.assertEqual("full", guard.call_args.args[0])

    def test_source_change_with_correct_journals_passes(self) -> None:
        """Task and owner journal updates satisfy the lifecycle policy."""

        self._write_catalog(
            [
                {
                    "id": "api.server",
                    "sources": ["src/**/*.py"],
                    "tests": ["tests/test_*.py"],
                }
            ]
        )
        self._snapshot()
        self._write("src/app.py", "print('documented source change')\n")
        self._write("docs/journals/tasks/tk-104.md", "Source change evidence.\n")
        self._write(
            "docs/journals/components/api.server.md",
            "Component change evidence.\n",
        )

        with mock.patch.object(
            docs_hook, "run_guard_commands", return_value=[]
        ) as guard:
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_output)
        self.assertEqual("", standard_error)
        self.assertEqual("full", guard.call_args.args[0])

    def test_changed_test_glob_requires_its_component_journal(self) -> None:
        """Catalog test ownership is enforced exactly like source ownership."""

        self._write_catalog(
            [
                {
                    "id": "api.server",
                    "sources": ["src/**/*.py"],
                    "tests": ["tests/test_*.py"],
                }
            ]
        )
        self._snapshot()
        self._write("tests/test_app.py", "def test_app():\n    assert True\n")
        self._write("docs/journals/tasks/test-change.md", "Test evidence.\n")

        with mock.patch.object(
            docs_hook, "run_guard_commands", return_value=[]
        ):
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_error)
        response = json.loads(standard_output)
        self.assertIn(
            "docs/journals/components/api.server.md", response["systemMessage"]
        )

    def test_catalog_globs_are_segment_aware_and_include_dot_directories(self) -> None:
        """Single stars stay in one segment while double stars cross segments."""

        self.assertTrue(docs_hook._catalog_glob_matches("src/app.py", "src/*.py"))
        self.assertFalse(
            docs_hook._catalog_glob_matches("src/nested/app.py", "src/*.py")
        )
        self.assertTrue(
            docs_hook._catalog_glob_matches("src/nested/app.py", "src/**/*.py")
        )
        self.assertTrue(
            docs_hook._catalog_glob_matches(
                ".github/workflows/ci.yml", ".github/**"
            )
        )

    def test_catalog_glob_safety_rejects_escape_and_ambiguous_patterns(self) -> None:
        """Traversal, absolute paths, and unsupported glob syntax are invalid."""

        for unsafe_pattern in (
            "../src/**",
            "src/../secret.py",
            "/absolute/**",
            "C:/absolute/**",
            "./src/**",
            "src//*.py",
            "src/**nested/*.py",
            "src/[ab].py",
            "src\\*.py",
        ):
            with self.subTest(pattern=unsafe_pattern):
                self.assertIsNone(docs_hook._safe_catalog_glob(unsafe_pattern))
                self.assertFalse(
                    docs_hook._catalog_glob_matches("src/app.py", unsafe_pattern)
                )

    def test_multiple_component_owners_each_require_a_changed_journal(self) -> None:
        """One shared path can require journals for every catalog owner."""

        self._write_catalog(
            [
                {
                    "id": "shared.alpha",
                    "sources": ["src/app.py"],
                    "tests": [],
                },
                {
                    "id": "shared.beta",
                    "sources": ["src/**/*.py"],
                    "tests": [],
                },
            ]
        )
        self._snapshot()
        self._write("src/app.py", "print('shared owner change')\n")
        self._write("docs/journals/tasks/shared-change.md", "Task evidence.\n")
        self._write(
            "docs/journals/components/shared.alpha.md",
            "Alpha evidence.\n",
        )

        with mock.patch.object(
            docs_hook, "run_guard_commands", return_value=[]
        ):
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_error)
        response = json.loads(standard_output)
        self.assertIn(
            "docs/journals/components/shared.beta.md", response["systemMessage"]
        )
        self.assertNotIn(
            "Missing required component journal update: "
            "docs/journals/components/shared.alpha.md",
            response["systemMessage"],
        )

    def test_dependency_text_file_is_a_full_configuration_change(self) -> None:
        """A requirements file is configuration, not docs-only text."""

        self._snapshot()
        self._write("requirements.txt", "example==1.0\n")
        self._write("docs/journals/tasks/dependency-change.md", "Task evidence.\n")

        with mock.patch.object(
            docs_hook, "run_guard_commands", return_value=[]
        ) as guard:
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_output)
        self.assertEqual("", standard_error)
        self.assertEqual("full", guard.call_args.args[0])

    def test_valid_full_audit_and_generate_check_allow_completion(self) -> None:
        """Successful real guard subprocesses produce no blocking response."""

        fake_skill_root = self.temporary_root / "fake-skill"
        guard_script = fake_skill_root / "scripts" / "docs_guard.py"
        guard_script.parent.mkdir(parents=True)
        guard_script.write_text(
            """import os
import sys

with open(os.environ["GUARD_CALL_LOG"], "a", encoding="utf-8") as log:
    log.write("|".join(sys.argv[1:]) + "\\n")
""",
            encoding="utf-8",
        )
        guard_call_log = self.temporary_root / "guard-calls.log"
        environment = {
            "ARCHITECTURE_DOCS_KEEPER_STATE_DIR": str(self.state_root),
            "ARCHITECTURE_DOCS_KEEPER_GUARD": str(guard_script),
            "GUARD_CALL_LOG": str(guard_call_log),
        }
        self._snapshot()
        self._write("src/app.py", "print('valid documented change')\n")
        self._write("docs/journals/tasks/valid-change.md", "Task evidence.\n")

        exit_code, standard_output, standard_error = self._invoke(
            self._payload("Stop"), environment=environment
        )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_output)
        self.assertEqual("", standard_error)
        self.assertEqual(
            [
                f"audit|{self.repository.resolve()}",
                f"generate|{self.repository.resolve()}|--check",
            ],
            guard_call_log.read_text(encoding="utf-8").splitlines(),
        )
        self.assertEqual([], list(self.state_root.rglob("*.json")))

    def test_guard_defaults_to_the_project_skill_sibling(self) -> None:
        """Project hooks require no plugin root or user-level installation."""
        completed = subprocess.CompletedProcess([], 0, "", "")

        with mock.patch.object(
            docs_hook.subprocess, "run", return_value=completed
        ) as run:
            failures = docs_hook.run_guard_commands(
                "docs", self.repository, environment={}
            )

        self.assertEqual([], failures)
        expected_guard = str(SKILL_ROOT / "scripts/docs_guard.py")
        self.assertEqual(2, run.call_count)
        for call in run.call_args_list:
            self.assertEqual(expected_guard, call.args[0][1])

    def test_new_catalog_and_journals_bootstrap_an_owned_source_change(self) -> None:
        """A bootstrap turn can establish ownership and both journals at once."""

        self._snapshot()
        self._write("src/app.py", "print('bootstrap source change')\n")
        self._write_catalog(
            [
                {
                    "id": "bootstrap.component",
                    "sources": ["src/app.py"],
                    "tests": [],
                }
            ]
        )
        self._write("docs/journals/tasks/bootstrap.md", "Bootstrap evidence.\n")
        self._write(
            "docs/journals/components/bootstrap.component.md",
            "Component bootstrap evidence.\n",
        )

        with mock.patch.object(
            docs_hook, "run_guard_commands", return_value=[]
        ) as guard:
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_output)
        self.assertEqual("", standard_error)
        self.assertEqual("full", guard.call_args.args[0])

    def test_missing_catalog_is_left_to_the_normal_full_guard(self) -> None:
        """Missing ownership data adds no guessed component-journal failure."""

        self._snapshot()
        self._write("src/app.py", "print('missing catalog')\n")
        self._write("docs/journals/tasks/missing-catalog.md", "Task evidence.\n")
        guard_failure = "audit exited 1: architecture catalog is missing"

        with mock.patch.object(
            docs_hook, "run_guard_commands", return_value=[guard_failure]
        ) as guard:
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_error)
        response = json.loads(standard_output)
        self.assertIn(guard_failure, response["systemMessage"])
        self.assertNotIn(
            "Missing required component journal update:", response["systemMessage"]
        )
        self.assertEqual("full", guard.call_args.args[0])

    def test_malformed_catalog_is_left_to_the_normal_full_guard(self) -> None:
        """Malformed ownership data is diagnosed by audit without speculation."""

        self._write("docs/architecture/catalog.json", "{not-json\n")
        self._snapshot()
        self._write("src/app.py", "print('malformed catalog')\n")
        self._write("docs/journals/tasks/malformed-catalog.md", "Task evidence.\n")
        guard_failure = "audit exited 1: architecture catalog JSON is malformed"

        with mock.patch.object(
            docs_hook, "run_guard_commands", return_value=[guard_failure]
        ):
            exit_code, standard_output, standard_error = self._invoke(
                self._payload("Stop")
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_error)
        response = json.loads(standard_output)
        self.assertIn(guard_failure, response["systemMessage"])
        self.assertNotIn(
            "Missing required component journal update:", response["systemMessage"]
        )

    def test_missing_baseline_or_repository_never_blames_existing_files(self) -> None:
        """Absent attribution evidence is non-blocking by design."""

        outside_repository = self.temporary_root / "not-a-repository"
        outside_repository.mkdir()
        payload = self._payload("Stop", cwd=str(outside_repository), turn_id="unknown")

        with mock.patch.object(docs_hook, "run_guard_commands") as guard:
            exit_code, standard_output, standard_error = self._invoke(payload)

        self.assertEqual(0, exit_code)
        self.assertEqual("", standard_output)
        self.assertEqual("", standard_error)
        guard.assert_not_called()

    def test_opaque_lifecycle_ids_cannot_escape_project_state(self) -> None:
        """Raw session and turn IDs never become filesystem path components."""

        self._snapshot(session_id="../../outside", turn_id="..\\..\\turn")

        baseline_files = list(self.state_root.rglob("*.json"))
        self.assertEqual(1, len(baseline_files))
        baseline_path = baseline_files[0].resolve()
        self.assertTrue(baseline_path.is_relative_to(self.state_root.resolve()))
        self.assertNotIn("outside", baseline_path.name)

    def test_default_state_path_stays_inside_git_metadata(self) -> None:
        """Project hooks persist no baseline in user or tracked project paths."""
        state_file = docs_hook._state_file(self._payload("UserPromptSubmit"), {})
        git_directory = Path(
            self._git("rev-parse", "--absolute-git-dir").stdout.strip()
        ).resolve()

        self.assertIsNotNone(state_file)
        assert state_file is not None
        self.assertTrue(state_file.resolve().is_relative_to(git_directory))
        self.assertIn("codex-project-hook-state", state_file.parts)

    def test_default_hook_file_wires_all_required_lifecycle_events(self) -> None:
        """Project hook discovery covers every lifecycle event used here."""

        hook_config = json.loads(
            (REPOSITORY_ROOT / ".codex/hooks.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            {"SessionStart", "SubagentStart", "UserPromptSubmit", "Stop"},
            set(hook_config["hooks"]),
        )
        for event_configuration in hook_config["hooks"].values():
            command_hook = event_configuration[0]["hooks"][0]
            self.assertIn("git rev-parse --show-toplevel", command_hook["command"])
            self.assertIn(
                ".agents/skills/architecture-docs-keeper/scripts/docs_hook.py",
                command_hook["command"],
            )
            self.assertNotIn("PLUGIN_ROOT", command_hook["command"])


if __name__ == "__main__":
    unittest.main()
