#!/usr/bin/env python3
"""Enforce project architecture documentation at Codex lifecycle boundaries.

The hook records a per-turn Git working-tree baseline during
``UserPromptSubmit``. At ``Stop`` it attributes only net changes made after that
baseline, then runs the project skill's deterministic documentation guard. Lifecycle
context events remind both the primary agent and subagents to use the bundled
documentation workflow.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

STATE_SCHEMA_VERSION = 1
STATE_DIRECTORY_NAME = "architecture-docs-keeper"
GUARD_TIMEOUT_SECONDS = 120
MAX_ERROR_OUTPUT_CHARS = 4_000
MAX_CHANGED_PATHS_IN_MESSAGE = 30
ARCHITECTURE_CATALOG_PATH = Path("docs/architecture/catalog.json")
TASK_JOURNAL_DIRECTORY = PurePosixPath("docs/journals/tasks")
COMPONENT_JOURNAL_DIRECTORY = PurePosixPath("docs/journals/components")
COMPONENT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")

CONTEXT_MESSAGE = (
    "For writable repository work, invoke $architecture-docs-keeper and keep "
    "the complete documentation system synchronized: architecture maps, the "
    "internal link graph, plans and specifications, task and component journals, "
    "and decisions. Run every guard command reported by the lifecycle gate. Do "
    "not modify repository files for read-only tasks; the gate checks only net "
    "changes made during this turn."
)

DOCUMENTATION_SUFFIXES = {".adoc", ".md", ".mdx", ".rst"}
IGNORED_DIRECTORY_NAMES = {
    ".cache",
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".turbo",
    "__pycache__",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
IGNORED_FILE_NAMES = {".DS_Store", "Thumbs.db"}
IGNORED_SUFFIXES = {".log", ".pyc", ".swp", ".tmp"}


class GitSnapshotError(RuntimeError):
    """Raised when a reliable Git working-tree snapshot cannot be captured."""


def _run_git(repo_or_cwd: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    """Run Git without a shell and return its byte-oriented result."""

    try:
        return subprocess.run(
            ["git", "-C", str(repo_or_cwd), *arguments],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GitSnapshotError(f"unable to run git: {error}") from error


def _decode_git_path(raw_path: bytes) -> str:
    """Decode a NUL-delimited Git path without losing unusual byte values."""

    return raw_path.decode("utf-8", errors="surrogateescape")


def _repo_root(cwd: Path) -> Path | None:
    """Return the canonical Git root for ``cwd``, or ``None`` outside a repo."""

    result = _run_git(cwd, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return None

    raw_root = result.stdout.rstrip(b"\r\n")
    if not raw_root:
        return None
    return Path(_decode_git_path(raw_root)).resolve()


def _head_revision(repo_root: Path) -> str | None:
    """Return the current HEAD object ID, including ``None`` for unborn repos."""

    result = _run_git(repo_root, "rev-parse", "--verify", "HEAD")
    if result.returncode != 0:
        return None
    return result.stdout.decode("ascii", errors="replace").strip() or None


def _safe_repo_path(repo_root: Path, git_path: str) -> Path:
    """Resolve a Git path while rejecting paths that escape the repository."""

    relative_path = PurePosixPath(git_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise GitSnapshotError(f"unsafe path reported by git: {git_path!r}")
    return repo_root.joinpath(*relative_path.parts)


def _hash_path(repo_root: Path, git_path: str) -> tuple[str | None, str]:
    """Return a stable content hash and kind for a changed working-tree path."""

    path = _safe_repo_path(repo_root, git_path)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None, "missing"
    except OSError as error:
        return f"error:{type(error).__name__}", "unreadable"

    digest = hashlib.sha256()
    if stat.S_ISLNK(metadata.st_mode):
        digest.update(b"symlink\0")
        try:
            target = os.readlink(path)
        except OSError as error:
            return f"error:{type(error).__name__}", "unreadable-symlink"
        digest.update(os.fsencode(target))
        return digest.hexdigest(), "symlink"

    if stat.S_ISREG(metadata.st_mode):
        digest.update(b"file\0")
        digest.update(f"mode:{stat.S_IMODE(metadata.st_mode)}\0".encode("ascii"))
        try:
            with path.open("rb") as file_handle:
                for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            return f"error:{type(error).__name__}", "unreadable-file"
        return digest.hexdigest(), "file"

    digest.update(f"mode:{metadata.st_mode}".encode("ascii"))
    return digest.hexdigest(), "other"


def _status_paths(repo_root: Path) -> dict[str, dict[str, str | None]]:
    """Capture status and hashes for every modified, staged, or untracked path."""

    result = _run_git(
        repo_root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise GitSnapshotError(detail or "git status failed")

    records = result.stdout.split(b"\0")
    paths_with_status: dict[str, str] = {}
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            raise GitSnapshotError("git status returned an unexpected record")

        status_code = record[:2].decode("ascii", errors="replace")
        git_path = _decode_git_path(record[3:])
        paths_with_status[git_path] = status_code

        if "R" in status_code or "C" in status_code:
            if index >= len(records) or not records[index]:
                raise GitSnapshotError("git status omitted a rename source path")
            related_path = _decode_git_path(records[index])
            index += 1
            paths_with_status[related_path] = f"{status_code}:related"

    snapshot: dict[str, dict[str, str | None]] = {}
    for git_path in sorted(paths_with_status):
        content_hash, path_kind = _hash_path(repo_root, git_path)
        snapshot[git_path] = {
            "status": paths_with_status[git_path],
            "sha256": content_hash,
            "kind": path_kind,
        }
    return snapshot


def capture_git_snapshot(cwd: Path) -> dict[str, Any] | None:
    """Capture a reliable Git baseline for a repository working tree."""

    repo_root = _repo_root(cwd)
    if repo_root is None:
        return None
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "repo_root": str(repo_root),
        "head": _head_revision(repo_root),
        "files": _status_paths(repo_root),
    }


def _state_file(payload: Mapping[str, Any], environment: Mapping[str, str]) -> Path | None:
    """Return a traversal-safe state path derived from opaque lifecycle IDs."""

    state_root_value = environment.get("ARCHITECTURE_DOCS_KEEPER_STATE_DIR")
    session_id = payload.get("session_id")
    turn_id = payload.get("turn_id")
    cwd_value = payload.get("cwd")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(turn_id, str) or not turn_id:
        return None
    if not isinstance(cwd_value, str) or not cwd_value:
        return None

    if state_root_value:
        state_root = Path(state_root_value)
    else:
        try:
            git_directory_result = _run_git(
                Path(cwd_value), "rev-parse", "--absolute-git-dir"
            )
        except GitSnapshotError:
            return None
        if git_directory_result.returncode != 0:
            return None
        raw_git_directory = git_directory_result.stdout.rstrip(b"\r\n")
        if not raw_git_directory:
            return None
        state_root = (
            Path(_decode_git_path(raw_git_directory)).resolve()
            / "codex-project-hook-state"
        )

    opaque_key = hashlib.sha256(
        session_id.encode("utf-8", errors="surrogatepass")
        + b"\0"
        + turn_id.encode("utf-8", errors="surrogatepass")
        + b"\0"
        + os.path.realpath(cwd_value).encode("utf-8", errors="surrogatepass")
    ).hexdigest()
    return (
        state_root
        / STATE_DIRECTORY_NAME
        / "turn-baselines"
        / f"{opaque_key}.json"
    )


def _write_snapshot(path: Path, snapshot: Mapping[str, Any]) -> None:
    """Atomically persist a baseline in the project hook's state directory."""

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(snapshot, temporary_file, ensure_ascii=True, sort_keys=True)
            temporary_file.write("\n")
        try:
            temporary_path.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def _load_snapshot(path: Path) -> dict[str, Any] | None:
    """Load a valid baseline, treating corrupt or incompatible state as absent."""

    try:
        raw_snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw_snapshot, dict):
        return None
    if raw_snapshot.get("schema_version") != STATE_SCHEMA_VERSION:
        return None
    if not isinstance(raw_snapshot.get("repo_root"), str):
        return None
    if not isinstance(raw_snapshot.get("files"), dict):
        return None
    return raw_snapshot


def _remove_snapshot(path: Path) -> None:
    """Remove completed turn state without making hook completion fail."""

    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _committed_paths(repo_root: Path, previous_head: str, current_head: str) -> set[str]:
    """Return paths committed between two revisions, or no paths on ambiguity."""

    result = _run_git(
        repo_root,
        "diff",
        "--name-only",
        "-z",
        previous_head,
        current_head,
        "--",
    )
    if result.returncode != 0:
        return set()
    return {
        _decode_git_path(raw_path)
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    }


def changed_paths_since(
    baseline: Mapping[str, Any], current: Mapping[str, Any]
) -> set[str]:
    """Return net paths changed after ``baseline``, including committed files."""

    baseline_files = baseline.get("files")
    current_files = current.get("files")
    if not isinstance(baseline_files, dict) or not isinstance(current_files, dict):
        return set()

    changed_paths = {
        path
        for path in baseline_files.keys() | current_files.keys()
        if baseline_files.get(path) != current_files.get(path)
    }

    previous_head = baseline.get("head")
    current_head = current.get("head")
    repo_root = current.get("repo_root")
    if (
        isinstance(previous_head, str)
        and isinstance(current_head, str)
        and previous_head != current_head
        and isinstance(repo_root, str)
    ):
        changed_paths.update(
            _committed_paths(Path(repo_root), previous_head, current_head)
        )
    return changed_paths


def _is_ignored_path(git_path: str) -> bool:
    """Return whether a changed path is non-architectural generated noise."""

    path = PurePosixPath(git_path)
    return (
        path.name in IGNORED_FILE_NAMES
        or path.suffix.lower() in IGNORED_SUFFIXES
        or any(part in IGNORED_DIRECTORY_NAMES for part in path.parts)
    )


def _is_documentation_path(git_path: str) -> bool:
    """Return whether a changed path belongs to documentation only."""

    path = PurePosixPath(git_path)
    return (
        bool(path.parts and path.parts[0] == "docs")
        or path.suffix.lower() in DOCUMENTATION_SUFFIXES
    )


def classify_changes(changed_paths: set[str]) -> tuple[str | None, list[str]]:
    """Classify net relevant changes as docs-only, full, or absent."""

    relevant_paths = sorted(
        path for path in changed_paths if not _is_ignored_path(path)
    )
    if not relevant_paths:
        return None, []
    if all(_is_documentation_path(path) for path in relevant_paths):
        return "docs", relevant_paths
    return "full", relevant_paths


def _is_changed_task_journal(git_path: str) -> bool:
    """Return whether a net-changed path is a concrete task journal page."""

    path = PurePosixPath(git_path)
    return (
        path.parent == TASK_JOURNAL_DIRECTORY
        and path.suffix == ".md"
        and path.name != "README.md"
    )


def _safe_catalog_glob(raw_pattern: object) -> str | None:
    """Return a safe repository-relative catalog glob without normalizing it."""

    if not isinstance(raw_pattern, str) or not raw_pattern or not raw_pattern.strip():
        return None
    if raw_pattern != raw_pattern.strip() or "\\" in raw_pattern:
        return None
    if raw_pattern.startswith("/") or re.match(r"^[A-Za-z]:/", raw_pattern):
        return None
    if "\0" in raw_pattern:
        return None
    parts = raw_pattern.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    if any(character in raw_pattern for character in "?[]{}"):
        return None
    if any("**" in part and part != "**" for part in parts):
        return None
    return raw_pattern


def _catalog_segment_matches(value: str, pattern: str) -> bool:
    """Match one catalog path segment where ``*`` cannot cross a slash."""

    expression = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return re.fullmatch(expression, value) is not None


def _catalog_glob_matches(git_path: str, pattern: str) -> bool:
    """Match safe POSIX catalog globs with segment-aware ``*`` and ``**``."""

    if _safe_catalog_glob(pattern) is None:
        return False
    if "\\" in git_path or git_path.startswith("/"):
        return False
    path_parts = tuple(part for part in git_path.split("/") if part)
    pattern_parts = tuple(pattern.split("/"))
    memo: dict[tuple[int, int], bool] = {}

    def matches(pattern_index: int, path_index: int) -> bool:
        key = (pattern_index, path_index)
        if key in memo:
            return memo[key]
        if pattern_index == len(pattern_parts):
            result = path_index == len(path_parts)
        elif pattern_parts[pattern_index] == "**":
            result = matches(pattern_index + 1, path_index) or (
                path_index < len(path_parts)
                and matches(pattern_index, path_index + 1)
            )
        else:
            result = (
                path_index < len(path_parts)
                and _catalog_segment_matches(
                    path_parts[path_index], pattern_parts[pattern_index]
                )
                and matches(pattern_index + 1, path_index + 1)
            )
        memo[key] = result
        return result

    return matches(0, 0)


def _catalog_component_patterns(
    repo_root: Path,
) -> tuple[tuple[str, tuple[str, ...]], ...] | None:
    """Load safe source/test ownership patterns from a valid v2 catalog.

    ``None`` deliberately delegates missing or malformed catalog diagnostics to
    the normal full guard instead of inventing component ownership.
    """

    catalog_path = repo_root / ARCHITECTURE_CATALOG_PATH
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(catalog, dict) or catalog.get("schema_version") != 2:
        return None
    components = catalog.get("components")
    if not isinstance(components, list):
        return None

    seen_component_ids: set[str] = set()
    ownership: list[tuple[str, tuple[str, ...]]] = []
    for component in components:
        if not isinstance(component, dict):
            return None
        component_id = component.get("id")
        if (
            not isinstance(component_id, str)
            or not COMPONENT_ID_PATTERN.fullmatch(component_id)
            or component_id in seen_component_ids
        ):
            return None
        seen_component_ids.add(component_id)

        patterns: list[str] = []
        for field_name in ("sources", "tests"):
            raw_patterns = component.get(field_name)
            if not isinstance(raw_patterns, list):
                return None
            for raw_pattern in raw_patterns:
                safe_pattern = _safe_catalog_glob(raw_pattern)
                if safe_pattern is None:
                    return None
                patterns.append(safe_pattern)
        ownership.append((component_id, tuple(patterns)))
    return tuple(ownership)


def required_journal_failures(
    mode: str,
    relevant_paths: Sequence[str],
    repo_root: Path,
) -> list[str]:
    """Return missing task and affected-component journal diagnostics."""

    failures: list[str] = []
    changed_path_set = set(relevant_paths)
    if not any(_is_changed_task_journal(path) for path in changed_path_set):
        failures.append(
            "Missing required task journal update: add or append at least one "
            "docs/journals/tasks/*.md file changed in this turn; README.md does "
            "not count."
        )

    if mode != "full":
        return failures
    ownership = _catalog_component_patterns(repo_root)
    if ownership is None:
        return failures

    affected_component_ids = {
        component_id
        for component_id, patterns in ownership
        if any(
            _catalog_glob_matches(changed_path, pattern)
            for changed_path in changed_path_set
            for pattern in patterns
        )
    }
    for component_id in sorted(affected_component_ids):
        journal_path = (
            COMPONENT_JOURNAL_DIRECTORY / f"{component_id}.md"
        ).as_posix()
        if journal_path not in changed_path_set:
            failures.append(
                "Missing required component journal update: "
                f"{journal_path} (affected component: {component_id})."
            )
    return failures


def _guard_specs(mode: str, repo_root: Path) -> tuple[tuple[str, ...], ...]:
    """Return the locked docs-guard subcommands for a change class."""

    repository = str(repo_root)
    return (
        ("audit", repository),
        ("generate", repository, "--check"),
    )


def _format_command(command: Sequence[str]) -> str:
    """Format a command safely for a human-facing diagnostic."""

    if os.name == "nt":
        return subprocess.list2cmdline(list(command))
    return shlex.join(command)


def run_guard_commands(
    mode: str,
    repo_root: Path,
    environment: Mapping[str, str],
) -> list[str]:
    """Run deterministic documentation checks and return actionable failures."""

    configured_guard = environment.get("ARCHITECTURE_DOCS_KEEPER_GUARD")
    guard_script = (
        Path(configured_guard)
        if configured_guard
        else Path(__file__).resolve().with_name("docs_guard.py")
    )
    if not guard_script.is_file():
        return [
            f"Documentation guard is missing at {guard_script}. Restore the "
            "project-local architecture-docs-keeper skill."
        ]

    python_command = ("py", "-3") if os.name == "nt" else ("python3",)
    failures: list[str] = []
    for arguments in _guard_specs(mode, repo_root):
        command = (*python_command, str(guard_script), *arguments)
        try:
            result = subprocess.run(
                command,
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=GUARD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            failures.append(
                f"`{_format_command(command)}` timed out after "
                f"{GUARD_TIMEOUT_SECONDS} seconds."
            )
            continue
        except OSError as error:
            failures.append(f"`{_format_command(command)}` could not run: {error}")
            continue

        if result.returncode == 0:
            continue
        detail = (result.stderr or result.stdout).strip()
        if len(detail) > MAX_ERROR_OUTPUT_CHARS:
            detail = f"{detail[:MAX_ERROR_OUTPUT_CHARS]}\n… output truncated"
        if not detail:
            detail = "no diagnostic output"
        failures.append(
            f"`{_format_command(command)}` exited {result.returncode}: {detail}"
        )
    return failures


def _emit_json(payload: Mapping[str, Any]) -> None:
    """Write one compact JSON hook response to stdout."""

    json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")


def _emit_context(event_name: str) -> None:
    """Add the architecture workflow as developer context for an agent."""

    _emit_json(
        {
            "hookSpecificOutput": {
                "hookEventName": event_name,
                "additionalContext": CONTEXT_MESSAGE,
            }
        }
    )


def _emit_guard_failure(changed_paths: Sequence[str], failures: Sequence[str]) -> None:
    """Stop completion with current hook fields and actionable diagnostics."""

    displayed_paths = list(changed_paths[:MAX_CHANGED_PATHS_IN_MESSAGE])
    path_lines = "\n".join(f"- {path}" for path in displayed_paths)
    if len(changed_paths) > len(displayed_paths):
        path_lines += f"\n- … and {len(changed_paths) - len(displayed_paths)} more"
    failure_lines = "\n".join(f"- {failure}" for failure in failures)
    system_message = (
        "Documentation system checks failed for files changed during this "
        f"turn:\n{path_lines}\n\nFailures:\n{failure_lines}\n\n"
        "Invoke $architecture-docs-keeper; reconcile the architecture maps, "
        "internal link graph, plans and specifications, task and component "
        "journals, and decisions; then run every reported docs_guard.py command "
        "before completion."
    )
    _emit_json(
        {
            "continue": False,
            "stopReason": "Documentation system checks failed.",
            "systemMessage": system_message,
        }
    )


def _record_turn_baseline(
    payload: Mapping[str, Any], environment: Mapping[str, str]
) -> None:
    """Persist the current Git state for a safely identified Codex turn."""

    state_file = _state_file(payload, environment)
    cwd_value = payload.get("cwd")
    if state_file is None or not isinstance(cwd_value, str) or not cwd_value:
        return
    try:
        state_file.unlink(missing_ok=True)
    except OSError:
        return
    try:
        snapshot = capture_git_snapshot(Path(cwd_value))
        if snapshot is not None:
            _write_snapshot(state_file, snapshot)
    except (GitSnapshotError, OSError):
        # An absent baseline is intentionally non-blocking: without it, a later
        # Stop event cannot distinguish this turn from pre-existing user work.
        return


def _verify_turn(
    payload: Mapping[str, Any], environment: Mapping[str, str]
) -> None:
    """Check only changes attributable to the current turn before completion."""

    state_file = _state_file(payload, environment)
    cwd_value = payload.get("cwd")
    if state_file is None or not isinstance(cwd_value, str) or not cwd_value:
        return
    baseline = _load_snapshot(state_file)
    if baseline is None:
        _remove_snapshot(state_file)
        return

    try:
        current = capture_git_snapshot(Path(cwd_value))
    except (GitSnapshotError, OSError):
        return
    if current is None:
        return

    baseline_root = os.path.normcase(str(Path(baseline["repo_root"]).resolve()))
    current_root = os.path.normcase(str(Path(current["repo_root"]).resolve()))
    if baseline_root != current_root:
        _remove_snapshot(state_file)
        return

    mode, relevant_paths = classify_changes(changed_paths_since(baseline, current))
    if mode is None:
        _remove_snapshot(state_file)
        return
    repo_root = Path(current["repo_root"])
    failures = required_journal_failures(mode, relevant_paths, repo_root)
    failures.extend(run_guard_commands(mode, repo_root, environment))
    if failures:
        _emit_guard_failure(relevant_paths, failures)
        return
    _remove_snapshot(state_file)


def main() -> int:
    """Dispatch one Codex lifecycle event supplied as JSON on stdin."""

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        print(f"architecture docs hook received invalid JSON: {error}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("architecture docs hook expected a JSON object", file=sys.stderr)
        return 1

    event_name = payload.get("hook_event_name")
    if isinstance(event_name, str) and event_name in {
        "SessionStart",
        "SubagentStart",
    }:
        _emit_context(event_name)
    elif event_name == "UserPromptSubmit":
        _record_turn_baseline(payload, os.environ)
    elif event_name == "Stop":
        _verify_turn(payload, os.environ)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
