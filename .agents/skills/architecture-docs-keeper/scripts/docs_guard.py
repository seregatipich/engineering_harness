#!/usr/bin/env python3
"""Build and validate deterministic architecture-documentation maps.

``docs_guard`` deliberately uses only the Python standard library so a copy can
be installed into any repository.  Version 2 separates three concerns:

* Markdown front matter is the stable document graph.  Every architecture page
  declares ``doc_id``, ``doc_type``, ``title``, ``status``, ``parent_id``, and
  ``relations``.  Relations are mappings with ``type``, ``target_id``, and an
  optional ``anchor``; parent, child, and backlink edges are derived rather
  than duplicated.
* ``docs/architecture/catalog.json`` is the reviewed source/component ownership
  catalog.  It defines inventory globs, justified exclusions, components, and
  typed component relationships.
* ``docs/catalog.json`` and the managed link block in each Markdown page are
  generated projections.  ``generate --check`` makes drift deterministic.

The validator proves structural consistency and complete ownership of the
configured inventory.  It cannot prove that prose accurately describes runtime
behavior; that remains a review responsibility and is never reported as an
automated guarantee.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import stat
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator, Sequence
from urllib.parse import unquote, urlsplit


ARCHITECTURE_DIR = Path("docs/architecture")
ARCHITECTURE_CATALOG = ARCHITECTURE_DIR / "catalog.json"
GENERATED_DOCS_CATALOG = Path("docs/catalog.json")
ROOT_DOC_ID = "docs.root"
SCHEMA_VERSION = 2

MANAGED_LINKS_START = "<!-- docs:links:start -->"
MANAGED_LINKS_END = "<!-- docs:links:end -->"
POLICY_START = "<!-- docs-guard:policy:start -->"
POLICY_END = "<!-- docs-guard:policy:end -->"
LEFTHOOK_START = "# docs-guard:pre-push:start"
LEFTHOOK_END = "# docs-guard:pre-push:end"

DOC_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
COMPONENT_ID_PATTERN = DOC_ID_PATTERN
PLACEHOLDER_PATTERN = re.compile(
    r"(?i)(?:\bTODO\b|\bTBD\b|\bFIXME\b|lorem\s+ipsum|"
    r"\[\s*(?:fill|insert|describe|replace)[^\]]*\]|<\s*(?:insert|describe)\b)"
)

RELATION_TYPES = frozenset(
    {
        "related",
        "depends-on",
        "implements",
        "specified-by",
        "planned-by",
        "decided-by",
        "changes",
        "documents",
        "supersedes",
        "redirects-to",
        "verified-by",
    }
)

DOC_TYPE_STATUSES: dict[str, frozenset[str]] = {
    "root": frozenset({"active"}),
    "architecture-root": frozenset({"active"}),
    "architecture-context": frozenset({"active"}),
    "architecture-container": frozenset({"active"}),
    "architecture-area": frozenset({"active"}),
    "architecture-flow": frozenset({"active"}),
    "architecture-concept": frozenset({"active"}),
    "architecture-deployment": frozenset({"active"}),
    "architecture-component": frozenset(
        {"active", "experimental", "deprecated", "removed"}
    ),
    "plan": frozenset(
        {"draft", "approved", "in-progress", "completed", "cancelled", "superseded"}
    ),
    "specification": frozenset({"draft", "approved", "superseded"}),
    "journal-root": frozenset({"active"}),
    "journal-task": frozenset({"active", "closed"}),
    "journal-component": frozenset({"active", "closed"}),
    "decision": frozenset(
        {"proposed", "accepted", "rejected", "deprecated", "superseded"}
    ),
    "operations": frozenset({"active"}),
    "development": frozenset({"active"}),
    "redirect": frozenset({"active"}),
}

REQUIRED_FRONT_MATTER_FIELDS = (
    "doc_id",
    "doc_type",
    "title",
    "status",
    "relations",
)
OPTIONAL_FRONT_MATTER_FIELDS = frozenset({"parent_id", "profile", "redirect_to"})

REQUIRED_SECTIONS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "architecture-context": (
        "Purpose", "External actors", "Trust boundaries", "System interactions",
        "Data ownership", "Failure boundaries", "Evidence", "Related documentation",
    ),
    "architecture-container": (
        "Runtime containers", "Responsibilities", "Communication", "Data stores",
        "Startup and shutdown", "Deployment mapping", "Failure and recovery",
        "Related documentation",
    ),
    "architecture-area": (
        "Responsibility", "Boundaries", "Entry points", "Components", "Dependencies",
        "Data and control flow", "Security and operations", "Related documentation",
    ),
    "architecture-component": (
        "Summary", "Responsibility", "Boundaries",
        "Entry points and public interfaces", "Dependencies", "Data and control flow",
        "State and side effects", "Failure modes and recovery",
        "Security and permissions", "Observability and operations", "Tests and evidence",
        "Change impact", "Profile requirements", "Related documentation",
    ),
    "architecture-flow": (
        "Trigger", "Participants", "Preconditions", "Sequence", "Data transformations",
        "Failure paths", "Security boundaries", "Verification", "Related documentation",
    ),
    "architecture-concept": (
        "Definition", "Invariants", "Ownership", "Lifecycle", "Implementations",
        "Misuse and failure", "Related documentation",
    ),
    "architecture-deployment": (
        "Environment", "Deployed containers", "Configuration and secrets",
        "Network and trust boundaries", "Data stores", "Rollout and rollback",
        "Health and observability", "Recovery", "Related documentation",
    ),
    "plan": (
        "Objective", "Scope", "Constraints", "Affected documents and components",
        "Work breakdown", "Verification", "Rollout and recovery", "Outcome",
        "Related documentation",
    ),
    "specification": (
        "Problem", "Requirements", "Non-requirements", "Design", "Interfaces and data",
        "Failure and security behavior", "Compatibility and migration",
        "Acceptance criteria", "Verification", "Related documentation",
    ),
    "journal-task": (
        "Context", "Timeline", "Verification evidence", "Outcome", "Related documentation",
    ),
    "journal-component": (
        "Component", "Timeline", "Current operational notes", "Related documentation",
    ),
    "decision": (
        "Context", "Decision drivers", "Considered options", "Decision", "Consequences",
        "Verification", "Amendments", "Related documentation",
    ),
    "operations": (
        "Procedure", "Prerequisites", "Safety boundaries", "Verification", "Rollback",
        "Escalation", "Related documentation",
    ),
    "development": (
        "Setup", "Workflows", "Commands", "Test strategy", "Constraints",
        "Troubleshooting", "Related documentation",
    ),
}

REQUIRED_ARCHITECTURE_ROOT_SECTIONS = (
    "Scope", "System summary", "Areas", "Runtime boundaries",
    "Cross-cutting concerns", "Coverage and exclusions", "Maintenance",
    "Related documentation",
)

# Backward-compatible public constant used by v1 callers and tests.
REQUIRED_COMPONENT_SECTIONS = REQUIRED_SECTIONS_BY_TYPE["architecture-component"]

CANONICAL_ARCHITECTURE_DIRECTORIES = (
    "system",
    "areas",
    "flows",
    "concepts",
)

PROFILE_KINDS: dict[str, frozenset[str]] = {
    "application-runtime": frozenset({"application", "process", "cli"}),
    "frontend-ui": frozenset({"page", "layout", "ui-component"}),
    "frontend-state": frozenset({"store", "hook", "api-client"}),
    "backend-api": frozenset({"route", "controller", "handler", "middleware", "policy"}),
    "domain-service": frozenset({"service", "domain-module"}),
    "worker-job": frozenset({"worker", "job", "consumer", "queue"}),
    "data-persistence": frozenset({"repository", "database", "schema", "migration"}),
    "integration-adapter": frozenset({"adapter", "external-client"}),
    "shared-library": frozenset({"library", "shared-schema"}),
    "infrastructure": frozenset(
        {"infrastructure", "deployment-config", "runtime-config"}
    ),
}

# Required structural records.  Leaf records (components, flows, plans, and so
# on) are discovered from their authored pages and catalogs.
CANONICAL_DOCUMENTS: tuple[tuple[str, str, str, str | None, str], ...] = (
    ("docs/README.md", "docs.root", "root", None, "Documentation"),
    ("docs/architecture/README.md", "architecture.root", "architecture-root", "docs.root", "Architecture"),
    ("docs/architecture/system/README.md", "architecture.system.index", "architecture-root", "architecture.root", "System"),
    ("docs/architecture/system/context.md", "architecture.context.system", "architecture-context", "architecture.system.index", "System context"),
    ("docs/architecture/system/containers.md", "architecture.container.runtime", "architecture-container", "architecture.system.index", "Runtime containers"),
    ("docs/architecture/system/deployments/README.md", "architecture.deployments.index", "architecture-root", "architecture.system.index", "Deployments"),
    ("docs/architecture/areas/README.md", "architecture.areas.index", "architecture-root", "architecture.root", "Architecture areas"),
    ("docs/architecture/flows/README.md", "architecture.flows.index", "architecture-root", "architecture.root", "Architecture flows"),
    ("docs/architecture/concepts/README.md", "architecture.concepts.index", "architecture-root", "architecture.root", "Architecture concepts"),
    ("docs/plans/README.md", "plans.root", "root", "docs.root", "Plans"),
    ("docs/specifications/README.md", "specifications.root", "root", "docs.root", "Specifications"),
    ("docs/journals/README.md", "journals.root", "journal-root", "docs.root", "Journals"),
    ("docs/journals/tasks/README.md", "journals.tasks.index", "journal-root", "journals.root", "Task journals"),
    ("docs/journals/components/README.md", "journals.components.index", "journal-root", "journals.root", "Component journals"),
    ("docs/decisions/README.md", "decisions.root", "root", "docs.root", "Decisions"),
    ("docs/operations/README.md", "operations.root", "root", "docs.root", "Operations"),
    ("docs/development/README.md", "development.root", "root", "docs.root", "Development"),
)


@dataclass(frozen=True)
class Issue:
    """A stable machine- and human-readable validation diagnostic."""

    code: str
    message: str
    path: str | None = None
    line: int | None = None
    severity: str = "error"

    def as_dict(self) -> dict[str, object]:
        """Return the deterministic JSON representation of this issue."""
        result: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }
        if self.path is not None:
            result["path"] = self.path
        if self.line is not None:
            result["line"] = self.line
        return result


@dataclass(frozen=True)
class Relation:
    """A typed edge declared by a document."""

    relation_type: str
    target_id: str
    anchor: str | None = None

    def as_dict(self) -> dict[str, str]:
        """Return the canonical mapping representation."""
        result = {"target_id": self.target_id, "type": self.relation_type}
        if self.anchor:
            result["anchor"] = self.anchor
        return result


@dataclass(frozen=True)
class DocumentMetadata:
    """Stable architecture document identity and graph metadata."""

    doc_id: str
    doc_type: str
    title: str
    status: str
    parent_id: str | None
    relations: tuple[Relation, ...]
    profile: str | None = None
    redirect_to: str | None = None


@dataclass
class Document:
    """A parsed architecture Markdown document."""

    path: Path
    relative_path: str
    text: str
    body: str
    body_start_line: int
    metadata: DocumentMetadata | None
    issues: list[Issue] = field(default_factory=list)


@dataclass(frozen=True)
class MarkdownLink:
    """A Markdown link discovered outside fenced code blocks."""

    target: str
    line: int
    label: str
    reference: bool = False


@dataclass(frozen=True)
class PlannedChange:
    """A deterministic bootstrap or migration action."""

    action: str
    path: str
    detail: str

    def render(self) -> str:
        """Render the action for CLI output."""
        return f"{self.action}: {self.path} ({self.detail})"


def _relative(path: Path, repository: Path) -> str:
    """Return a slash-normalized path relative to ``repository`` when possible."""
    try:
        return path.resolve().relative_to(repository.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _strip_quotes(value: str) -> str:
    """Remove one matching quote pair from a scalar."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_list_scalar(value: str) -> list[str] | None:
    """Parse a JSON-like one-line string list, returning ``None`` when not a list."""
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return None
    try:
        parsed = json.loads(value.replace("'", '"'))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        return None
    return list(parsed)


def parse_front_matter(path: Path, repository: Path) -> Document:
    """Parse the deliberately small, deterministic YAML front-matter subset.

    The supported format contains top-level scalar fields, a string list for
    canonical relation mappings with ``type``, ``target_id``,
    and optional ``anchor``.  Other nesting is rejected so typos do not silently
    change graph semantics.  No external YAML dependency is needed.
    """
    text = path.read_text(encoding="utf-8")
    relative_path = _relative(path, repository)
    lines = text.splitlines()
    issues: list[Issue] = []
    if not lines or lines[0].strip() != "---":
        issues.append(
            Issue(
                "frontmatter_missing",
                "architecture Markdown must begin with front matter",
                relative_path,
                1,
            )
        )
        return Document(path, relative_path, text, text, 1, None, issues)

    try:
        closing_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        issues.append(
            Issue(
                "frontmatter_unclosed",
                "front matter has no closing delimiter",
                relative_path,
                1,
            )
        )
        return Document(path, relative_path, text, text, 1, None, issues)

    values: dict[str, str | list[object]] = {}
    active_list: str | None = None
    active_relation: dict[str, str] | None = None
    for index, raw_line in enumerate(lines[1:closing_index], start=2):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw_line[:1].isspace() and not stripped.startswith("-"):
            if active_list == "relations" and active_relation is not None and ":" in stripped:
                relation_key, relation_value = stripped.split(":", 1)
                relation_key = relation_key.strip()
                relation_value = _strip_quotes(relation_value)
                if relation_key not in {"type", "target_id", "anchor"}:
                    issues.append(
                        Issue(
                            "relation_unknown_field",
                            f"unsupported relation field '{relation_key}'",
                            relative_path,
                            index,
                        )
                    )
                elif relation_key in active_relation:
                    issues.append(
                        Issue(
                            "relation_duplicate_field",
                            f"duplicate relation field '{relation_key}'",
                            relative_path,
                            index,
                        )
                    )
                else:
                    active_relation[relation_key] = relation_value
                continue
            issues.append(
                Issue(
                    "frontmatter_nested_value",
                    "only relation mappings may contain nested values",
                    relative_path,
                    index,
                )
            )
            continue
        if stripped.startswith("- "):
            if active_list != "relations":
                issues.append(
                    Issue(
                        "frontmatter_unexpected_list_item",
                        f"list item has no supported list field: {stripped}",
                        relative_path,
                        index,
                    )
                )
                continue
            assert isinstance(values[active_list], list)
            item = stripped[2:].strip()
            if not item:
                issues.append(
                    Issue(
                        "frontmatter_empty_list_item",
                        f"{active_list} contains an empty item",
                        relative_path,
                        index,
                    )
                )
            else:
                if ":" not in item:
                    issues.append(
                        Issue(
                            "relation_invalid_mapping",
                            "relations must use mappings with type and target_id",
                            relative_path,
                            index,
                        )
                    )
                    active_relation = None
                else:
                    relation_key, relation_value = item.split(":", 1)
                    relation_key = relation_key.strip()
                    relation_value = _strip_quotes(relation_value)
                    active_relation = {}
                    values[active_list].append(active_relation)
                    if relation_key not in {"type", "target_id", "anchor"}:
                        issues.append(
                            Issue(
                                "relation_unknown_field",
                                f"unsupported relation field '{relation_key}'",
                                relative_path,
                                index,
                            )
                        )
                    else:
                        active_relation[relation_key] = relation_value
            continue
        if ":" not in raw_line:
            issues.append(
                Issue(
                    "frontmatter_invalid_line",
                    f"invalid front-matter line: {stripped}",
                    relative_path,
                    index,
                )
            )
            active_list = None
            active_relation = None
            continue
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if key in values:
            issues.append(
                Issue(
                    "frontmatter_duplicate_field",
                    f"duplicate front-matter field '{key}'",
                    relative_path,
                    index,
                )
            )
            active_list = None
            active_relation = None
            continue
        allowed_fields = set(REQUIRED_FRONT_MATTER_FIELDS) | set(OPTIONAL_FRONT_MATTER_FIELDS)
        if key not in allowed_fields:
            issues.append(
                Issue(
                    "frontmatter_unknown_field",
                    f"unsupported front-matter field '{key}'",
                    relative_path,
                    index,
                )
            )
        if key == "relations":
            if not raw_value:
                values[key] = []
                active_list = key
                active_relation = None
            else:
                parsed_list = _parse_list_scalar(raw_value)
                if parsed_list is None or parsed_list:
                    issues.append(
                        Issue(
                            "frontmatter_invalid_list",
                            f"field '{key}' has an unsupported inline value",
                            relative_path,
                            index,
                        )
                    )
                    values[key] = []
                else:
                    values[key] = parsed_list
                active_list = None
                active_relation = None
        else:
            values[key] = _strip_quotes(raw_value)
            active_list = None
            active_relation = None

    for field_name in REQUIRED_FRONT_MATTER_FIELDS:
        if field_name not in values:
            issues.append(
                Issue(
                    "frontmatter_required_field",
                    f"missing required front-matter field '{field_name}'",
                    relative_path,
                    1,
                )
            )

    body = "\n".join(lines[closing_index + 1 :])
    if text.endswith("\n"):
        body += "\n"
    body_start_line = closing_index + 2
    if any(field_name not in values for field_name in REQUIRED_FRONT_MATTER_FIELDS):
        return Document(path, relative_path, text, body, body_start_line, None, issues)

    scalar_fields = ("doc_id", "doc_type", "title", "status")
    for field_name in scalar_fields:
        if not isinstance(values[field_name], str) or not str(values[field_name]).strip():
            issues.append(
                Issue(
                    "frontmatter_empty_field",
                    f"front-matter field '{field_name}' must not be empty",
                    relative_path,
                    1,
                )
            )

    doc_id = str(values["doc_id"]).strip()
    doc_type = str(values["doc_type"]).strip()
    title = str(values["title"]).strip()
    status = str(values["status"]).strip()
    raw_parent = str(values.get("parent_id", "")).strip()
    parent_id = None if raw_parent.lower() in {"", "null", "none", "~"} else raw_parent
    raw_relations = values["relations"] if isinstance(values["relations"], list) else []
    raw_profile = str(values.get("profile", "")).strip()
    profile = raw_profile or None
    raw_redirect_to = str(values.get("redirect_to", "")).strip()
    redirect_to = raw_redirect_to or None

    relations: list[Relation] = []
    seen_relations: set[tuple[str, str, str | None]] = set()
    for relation_value in raw_relations:
        if not isinstance(relation_value, dict):
            issues.append(
                Issue(
                    "relation_invalid_mapping",
                    "relation must be a mapping with type and target_id",
                    relative_path,
                    1,
                )
            )
            continue
        relation_fields = set(relation_value)
        if not {"type", "target_id"}.issubset(relation_fields):
            issues.append(
                Issue(
                    "relation_required_field",
                    "relation mapping requires type and target_id",
                    relative_path,
                    1,
                )
            )
            continue
        relation_type = str(relation_value["type"]).strip()
        target_id = str(relation_value["target_id"]).strip()
        anchor_value = relation_value.get("anchor")
        anchor = str(anchor_value).strip() if anchor_value is not None else None
        if anchor and (anchor != anchor.lower() or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", anchor)):
            issues.append(
                Issue(
                    "relation_anchor_invalid",
                    f"relation anchor must be a lowercase Markdown anchor: '{anchor}'",
                    relative_path,
                    1,
                )
            )
        if relation_type not in RELATION_TYPES:
            issues.append(
                Issue(
                    "relation_invalid_type",
                    f"unsupported relation type '{relation_type}'",
                    relative_path,
                    1,
                )
            )
        edge = (relation_type, target_id, anchor)
        if edge in seen_relations:
            issues.append(
                Issue(
                    "relation_duplicate",
                    f"duplicate relation '{relation_type}' to '{target_id}'",
                    relative_path,
                    1,
                )
            )
            continue
        seen_relations.add(edge)
        relations.append(Relation(relation_type, target_id, anchor))

    metadata = DocumentMetadata(
        doc_id=doc_id,
        doc_type=doc_type,
        title=title,
        status=status,
        parent_id=parent_id,
        relations=tuple(relations),
        profile=profile,
        redirect_to=redirect_to,
    )
    return Document(path, relative_path, text, body, body_start_line, metadata, issues)


def _visible_markdown_lines(text: str, start_line: int = 1) -> Iterator[tuple[int, str]]:
    """Yield Markdown lines outside backtick or tilde fenced code blocks."""
    fence_character: str | None = None
    fence_length = 0
    for line_number, line in enumerate(text.splitlines(), start=start_line):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            continue
        if fence_character is None:
            yield line_number, line


def _inline_destination(raw: str) -> str:
    """Extract an inline Markdown destination without its optional title."""
    raw = raw.strip()
    if raw.startswith("<"):
        closing = raw.find(">", 1)
        return raw[1:closing] if closing >= 0 else raw[1:]
    escaped = False
    depth = 0
    for index, character in enumerate(raw):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        elif character.isspace() and depth == 0:
            return raw[:index]
    return raw


def _inline_links_in_line(line: str, line_number: int) -> tuple[list[MarkdownLink], list[tuple[int, int]]]:
    """Parse inline Markdown links on one visible line using balanced delimiters."""
    links: list[MarkdownLink] = []
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(line):
        opening = line.find("[", index)
        if opening < 0:
            break
        if opening > 0 and line[opening - 1] in {"!", "\\"}:
            index = opening + 1
            continue
        label_end = line.find("]", opening + 1)
        if label_end < 0 or label_end + 1 >= len(line) or line[label_end + 1] != "(":
            index = opening + 1
            continue
        cursor = label_end + 2
        depth = 1
        escaped = False
        angle = False
        while cursor < len(line):
            character = line[cursor]
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == "<" and depth == 1:
                angle = True
            elif character == ">" and angle:
                angle = False
            elif not angle and character == "(":
                depth += 1
            elif not angle and character == ")":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        if depth != 0:
            index = label_end + 1
            continue
        target = _inline_destination(line[label_end + 2 : cursor])
        if target:
            links.append(MarkdownLink(target, line_number, line[opening + 1 : label_end]))
        spans.append((opening, cursor + 1))
        index = cursor + 1
    return links, spans


def extract_markdown_links(text: str, start_line: int = 1) -> tuple[MarkdownLink, ...]:
    """Return fence-aware Markdown, reference, autolink, and HTML links."""
    visible_lines = list(_visible_markdown_lines(text, start_line))
    definitions: dict[str, tuple[str, int]] = {}
    definition_lines: set[int] = set()
    definition_pattern = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)")
    for line_number, line in visible_lines:
        match = definition_pattern.match(line)
        if match:
            label = re.sub(r"\s+", " ", match.group(1).strip()).casefold()
            definitions[label] = (_inline_destination(match.group(2)), line_number)
            definition_lines.add(line_number)

    links: list[MarkdownLink] = []
    reference_pattern = re.compile(r"(?<!!)\[([^\]]+)\]\[([^\]]*)\]")
    shortcut_pattern = re.compile(r"(?<!!)\[([^\]]+)\](?![\[(])")
    html_target_pattern = re.compile(
        r"\b(?:href|src)\s*=\s*([\"'])(.*?)\1", re.IGNORECASE
    )
    autolink_pattern = re.compile(r"<([^<>\s]+)>")
    for line_number, line in visible_lines:
        if line_number in definition_lines:
            continue
        inline_links, inline_spans = _inline_links_in_line(line, line_number)
        links.extend(inline_links)
        occupied_spans = list(inline_spans)
        for match in reference_pattern.finditer(line):
            if any(start <= match.start() < end for start, end in inline_spans):
                continue
            occupied_spans.append(match.span())
            raw_label = match.group(2) or match.group(1)
            normalized_label = re.sub(r"\s+", " ", raw_label.strip()).casefold()
            definition = definitions.get(normalized_label)
            if definition is not None:
                links.append(
                    MarkdownLink(definition[0], line_number, match.group(1), reference=True)
                )
        for match in shortcut_pattern.finditer(line):
            if any(start <= match.start() < end for start, end in occupied_spans):
                continue
            normalized_label = re.sub(r"\s+", " ", match.group(1).strip()).casefold()
            definition = definitions.get(normalized_label)
            if definition is not None:
                links.append(
                    MarkdownLink(definition[0], line_number, match.group(1), reference=True)
                )
                occupied_spans.append(match.span())
        for match in html_target_pattern.finditer(line):
            links.append(MarkdownLink(match.group(2), line_number, "HTML link"))
        for match in autolink_pattern.finditer(line):
            target = match.group(1)
            if (
                "/" in target
                or target.startswith((".", "#"))
                or target.lower().endswith((".md", ".markdown"))
                or urlsplit(target).scheme
            ):
                links.append(MarkdownLink(target, line_number, target))
    return tuple(links)


def _slugify_heading(heading: str) -> str:
    """Return a GitHub-compatible-enough anchor for architecture link checks."""
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = re.sub(r"[*_~`]", "", heading).strip().lower()
    heading = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE)
    return re.sub(r"\s+", "-", heading)


def markdown_anchors(text: str) -> frozenset[str]:
    """Collect heading and explicit HTML anchors outside fenced code blocks."""
    anchors: set[str] = set()
    counts: defaultdict[str, int] = defaultdict(int)
    for _, line in _visible_markdown_lines(text):
        heading_match = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading_match:
            base = _slugify_heading(heading_match.group(1))
            if base:
                count = counts[base]
                anchors.add(base if count == 0 else f"{base}-{count}")
                counts[base] += 1
        for explicit in re.finditer(r"<a\s+(?:[^>]*?\s)?(?:id|name)=[\"']([^\"']+)[\"']", line, re.I):
            anchors.add(explicit.group(1))
    return frozenset(anchors)


def load_documents(repository: Path) -> tuple[list[Document], list[Issue]]:
    """Load all documentation Markdown without following or accepting symlinks."""
    repository = repository.resolve()
    docs_root = repository / "docs"
    if not docs_root.is_dir():
        return [], [
            Issue(
                "docs_missing",
                "docs does not exist",
                "docs",
            )
        ]
    documents: list[Document] = []
    loader_issues: list[Issue] = []
    for path in sorted(docs_root.rglob("*.md"), key=lambda item: item.as_posix()):
        relative_path = _relative(path, repository)
        if path.is_symlink():
            loader_issues.append(
                Issue(
                    "document_symlink",
                    "Markdown documents must be regular files, not symlinks",
                    relative_path,
                )
            )
            continue
        try:
            path.resolve().relative_to(repository)
            mode = path.lstat().st_mode
        except (FileNotFoundError, OSError, ValueError):
            loader_issues.append(
                Issue(
                    "document_outside_repository",
                    "Markdown document cannot be resolved safely inside the repository",
                    relative_path,
                )
            )
            continue
        if not stat.S_ISREG(mode):
            loader_issues.append(
                Issue(
                    "document_not_regular",
                    "Markdown documents must be regular files",
                    relative_path,
                )
            )
            continue
        documents.append(parse_front_matter(path, repository))
    issues = [issue for document in documents for issue in document.issues]
    return documents, [*loader_issues, *issues]


def validate_document_graph(
    documents: Sequence[Document],
) -> tuple[list[Issue], dict[str, Document], dict[str, str]]:
    """Validate identities, statuses, parent topology, and typed relations."""
    issues: list[Issue] = []
    by_id: dict[str, Document] = {}
    aliases: dict[str, str] = {}
    for document in documents:
        metadata = document.metadata
        if metadata is None:
            continue
        if not DOC_ID_PATTERN.fullmatch(metadata.doc_id):
            issues.append(
                Issue(
                    "doc_id_invalid",
                    f"invalid doc_id '{metadata.doc_id}'",
                    document.relative_path,
                )
            )
        existing = by_id.get(metadata.doc_id)
        if existing is not None:
            issues.append(
                Issue(
                    "doc_id_duplicate",
                    f"doc_id '{metadata.doc_id}' also belongs to {existing.relative_path}",
                    document.relative_path,
                )
            )
        else:
            by_id[metadata.doc_id] = document
        allowed_statuses = DOC_TYPE_STATUSES.get(metadata.doc_type)
        if allowed_statuses is None:
            issues.append(
                Issue(
                    "doc_type_invalid",
                    f"unsupported doc_type '{metadata.doc_type}'",
                    document.relative_path,
                )
            )
        elif metadata.status not in allowed_statuses:
            issues.append(
                Issue(
                    "doc_status_invalid",
                    f"status '{metadata.status}' is invalid for {metadata.doc_type}",
                    document.relative_path,
                )
            )
        if metadata.doc_type == "architecture-component":
            if metadata.profile not in PROFILE_KINDS:
                issues.append(
                    Issue(
                        "component_profile_invalid",
                        "architecture-component requires a supported profile",
                        document.relative_path,
                    )
                )
        elif metadata.profile is not None:
            issues.append(
                Issue(
                    "profile_wrong_type",
                    "profile is only valid on architecture-component",
                    document.relative_path,
                )
            )
        if metadata.doc_type == "redirect":
            redirect_relations = [
                relation
                for relation in metadata.relations
                if relation.relation_type == "redirects-to"
            ]
            if metadata.redirect_to is None:
                issues.append(
                    Issue(
                        "redirect_target_missing",
                        "redirect requires redirect_to",
                        document.relative_path,
                    )
                )
            if len(redirect_relations) != 1:
                issues.append(
                    Issue(
                        "redirect_relation_count",
                        "redirect requires exactly one redirects-to relation",
                        document.relative_path,
                    )
                )
            elif metadata.redirect_to != redirect_relations[0].target_id:
                issues.append(
                    Issue(
                        "redirect_target_mismatch",
                        "redirect_to must equal the redirects-to target_id",
                        document.relative_path,
                    )
                )
        elif metadata.redirect_to is not None:
            issues.append(
                Issue(
                    "redirect_target_wrong_type",
                    "redirect_to is only valid on redirect",
                    document.relative_path,
                )
            )

    redirect_targets = {
        doc_id: document.metadata.redirect_to
        for doc_id, document in by_id.items()
        if document.metadata is not None
        and document.metadata.doc_type == "redirect"
        and document.metadata.redirect_to is not None
    }
    for redirect_id, target_id in sorted(redirect_targets.items()):
        trail: list[str] = []
        current = redirect_id
        while current in redirect_targets:
            if current in trail:
                cycle = " -> ".join((*trail[trail.index(current) :], current))
                issues.append(
                    Issue(
                        "redirect_cycle",
                        f"redirect cycle detected: {cycle}",
                        by_id[redirect_id].relative_path,
                    )
                )
                break
            trail.append(current)
            next_target = redirect_targets[current]
            assert next_target is not None
            current = next_target
        else:
            if current not in by_id:
                issues.append(
                    Issue(
                        "redirect_target_orphan",
                        f"redirect target '{target_id}' does not resolve",
                        by_id[redirect_id].relative_path,
                    )
                )
            else:
                aliases[redirect_id] = current
                if len(trail) > 1:
                    issues.append(
                        Issue(
                            "redirect_target_redirect",
                            "redirects must point directly to a canonical non-redirect document",
                            by_id[redirect_id].relative_path,
                        )
                    )

    root = by_id.get(ROOT_DOC_ID)
    if root is None:
        issues.append(Issue("root_missing", f"required root doc_id '{ROOT_DOC_ID}' is missing"))
    elif root.metadata is not None:
        if root.metadata.parent_id is not None:
            issues.append(
                Issue("root_has_parent", "docs.root must not have a parent", root.relative_path)
            )
        if root.metadata.doc_type != "root":
            issues.append(
                Issue("root_wrong_type", "docs.root must use doc_type 'root'", root.relative_path)
            )

    children: defaultdict[str, list[str]] = defaultdict(list)
    for doc_id, document in by_id.items():
        metadata = document.metadata
        assert metadata is not None
        if doc_id != ROOT_DOC_ID and metadata.parent_id is None:
            issues.append(
                Issue("parent_missing", f"'{doc_id}' has no parent_id", document.relative_path)
            )
        if metadata.parent_id is not None:
            canonical_parent = aliases.get(metadata.parent_id, metadata.parent_id)
            if canonical_parent not in by_id:
                issues.append(
                    Issue(
                        "parent_orphan",
                        f"parent_id '{metadata.parent_id}' does not resolve",
                        document.relative_path,
                    )
                )
            else:
                children[canonical_parent].append(doc_id)
        for relation in metadata.relations:
            canonical_target = aliases.get(relation.target_id, relation.target_id)
            if relation.relation_type not in RELATION_TYPES:
                continue
            if canonical_target == doc_id:
                issues.append(
                    Issue(
                        "relation_self",
                        "self-relations are invalid",
                        document.relative_path,
                    )
                )
            if canonical_target not in by_id:
                issues.append(
                    Issue(
                        "relation_orphan",
                        f"relation target '{relation.target_id}' does not resolve",
                        document.relative_path,
                    )
                )
            elif relation.anchor and relation.anchor not in markdown_anchors(
                by_id[canonical_target].text
            ):
                issues.append(
                    Issue(
                        "relation_anchor_missing",
                        f"relation anchor '#{relation.anchor}' does not exist on '{canonical_target}'",
                        document.relative_path,
                    )
                )
            elif canonical_target in by_id and by_id[canonical_target].metadata is not None:
                target_type = by_id[canonical_target].metadata.doc_type
                required_target_types = {
                    "specified-by": {"specification"},
                    "planned-by": {"plan"},
                    "decided-by": {"decision"},
                    "verified-by": {"journal-task", "journal-component"},
                }.get(relation.relation_type)
                if required_target_types is not None and target_type not in required_target_types:
                    issues.append(
                        Issue(
                            "relation_target_type",
                            f"{relation.relation_type} cannot target doc_type '{target_type}'",
                            document.relative_path,
                        )
                    )
                if relation.relation_type == "supersedes" and target_type != metadata.doc_type:
                    issues.append(
                        Issue(
                            "supersedes_type_mismatch",
                            "supersedes normally requires matching document types",
                            document.relative_path,
                        )
                    )
            if relation.relation_type == "redirects-to" and metadata.doc_type != "redirect":
                issues.append(
                    Issue(
                        "redirect_relation_wrong_type",
                        "redirects-to is only valid on redirect documents",
                        document.relative_path,
                    )
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit_parent(doc_id: str, trail: tuple[str, ...]) -> None:
        if doc_id in visited:
            return
        if doc_id in visiting:
            cycle_start = trail.index(doc_id) if doc_id in trail else 0
            cycle = " -> ".join((*trail[cycle_start:], doc_id))
            issues.append(
                Issue(
                    "parent_cycle",
                    f"parent cycle detected: {cycle}",
                    by_id[doc_id].relative_path,
                )
            )
            return
        visiting.add(doc_id)
        document = by_id[doc_id]
        assert document.metadata is not None
        parent_id = document.metadata.parent_id
        canonical_parent = aliases.get(parent_id, parent_id) if parent_id else None
        if canonical_parent in by_id:
            visit_parent(canonical_parent, (*trail, doc_id))
        visiting.remove(doc_id)
        visited.add(doc_id)

    for doc_id in sorted(by_id):
        visit_parent(doc_id, ())

    if root is not None:
        reachable: set[str] = set()
        pending = [ROOT_DOC_ID]
        while pending:
            current = pending.pop()
            if current in reachable:
                continue
            reachable.add(current)
            pending.extend(children.get(current, ()))
        for doc_id in sorted(set(by_id) - reachable):
            issues.append(
                Issue(
                    "doc_unreachable",
                    f"'{doc_id}' is not reachable from docs.root",
                    by_id[doc_id].relative_path,
                )
            )
    return issues, by_id, aliases


def validate_canonical_structure(
    repository: Path,
    by_id: dict[str, Document],
) -> list[Issue]:
    """Validate required structural indexes and canonical authored paths."""
    issues: list[Issue] = []
    for relative_path, doc_id, doc_type, parent_id, _ in CANONICAL_DOCUMENTS:
        path = repository / relative_path
        if not path.is_file():
            issues.append(
                Issue(
                    "canonical_document_missing",
                    f"required structural document is missing: {relative_path}",
                    relative_path,
                )
            )
            continue
        document = by_id.get(doc_id)
        if document is None or document.path.resolve() != path.resolve():
            issues.append(
                Issue(
                    "canonical_doc_id_path",
                    f"{relative_path} must declare doc_id '{doc_id}'",
                    relative_path,
                )
            )
            continue
        assert document.metadata is not None
        if document.metadata.doc_type != doc_type:
            issues.append(
                Issue(
                    "canonical_doc_type",
                    f"{relative_path} must use doc_type '{doc_type}'",
                    relative_path,
                )
            )
        if document.metadata.parent_id != parent_id:
            issues.append(
                Issue(
                    "canonical_parent",
                    f"{relative_path} must use parent_id '{parent_id}'",
                    relative_path,
                )
            )

    for doc_id, document in by_id.items():
        metadata = document.metadata
        assert metadata is not None
        expected_path: str | None = None
        expected_parent: str | None = None
        identifier: str | None = None
        if metadata.doc_type == "architecture-area":
            prefix = "architecture.area."
            if doc_id.startswith(prefix):
                identifier = doc_id[len(prefix) :]
                expected_path = f"docs/architecture/areas/{identifier}/README.md"
                expected_parent = "architecture.areas.index"
        elif metadata.doc_type == "architecture-component":
            prefix = "architecture.component."
            if doc_id.startswith(prefix):
                identifier = doc_id[len(prefix) :]
                parent_prefix = "architecture.area."
                if metadata.parent_id and metadata.parent_id.startswith(parent_prefix):
                    area_id = metadata.parent_id[len(parent_prefix) :]
                    expected_path = (
                        f"docs/architecture/areas/{area_id}/components/{identifier}.md"
                    )
                else:
                    issues.append(
                        Issue(
                            "canonical_component_parent",
                            f"'{doc_id}' must have an architecture.area.<area-id> parent",
                            document.relative_path,
                        )
                    )
        elif metadata.doc_type == "journal-component":
            prefix = "journal.component."
            if doc_id.startswith(prefix):
                identifier = doc_id[len(prefix) :]
                expected_path = f"docs/journals/components/{identifier}.md"
                expected_parent = "journals.components.index"
        elif metadata.doc_type == "journal-task":
            prefix = "journal.task."
            if doc_id.startswith(prefix):
                identifier = doc_id[len(prefix) :]
                expected_path = f"docs/journals/tasks/{identifier}.md"
                expected_parent = "journals.tasks.index"
        elif metadata.doc_type == "decision":
            if not re.fullmatch(r"docs/decisions/[0-9]{4}-[a-z0-9.-]+\.md", document.relative_path):
                issues.append(
                    Issue(
                        "decision_path_noncanonical",
                        "decision document is outside the canonical docs/decisions/NNNN-<slug>.md path",
                        document.relative_path,
                    )
                )
            expected_parent = "decisions.root"
        elif metadata.doc_type in {"operations", "development"}:
            section = metadata.doc_type
            if not re.fullmatch(rf"docs/{section}/[a-z0-9.-]+\.md", document.relative_path):
                issues.append(
                    Issue(
                        "canonical_leaf_path",
                        f"{section} leaf is outside its canonical docs/{section} directory",
                        document.relative_path,
                    )
                )
            expected_parent = f"{section}.root"
        else:
            leaf_rules = {
                "architecture-flow": (
                    "architecture.flow.", "docs/architecture/flows/{id}.md", "architecture.flows.index"
                ),
                "architecture-concept": (
                    "architecture.concept.", "docs/architecture/concepts/{id}.md", "architecture.concepts.index"
                ),
                "architecture-deployment": (
                    "architecture.deployment.",
                    "docs/architecture/system/deployments/{id}.md",
                    "architecture.deployments.index",
                ),
                "plan": ("plan.", "docs/plans/{id}.md", "plans.root"),
                "specification": (
                    "specification.", "docs/specifications/{id}.md", "specifications.root"
                ),
            }
            rule = leaf_rules.get(metadata.doc_type)
            if rule is not None and doc_id.startswith(rule[0]):
                identifier = doc_id[len(rule[0]) :]
                expected_path = rule[1].format(id=identifier)
                expected_parent = rule[2]
        if metadata.doc_type in {
            "architecture-area", "architecture-component", "architecture-flow",
            "architecture-concept", "architecture-deployment", "plan", "specification",
            "journal-task", "journal-component",
        } and not identifier:
            issues.append(
                Issue(
                    "canonical_leaf_doc_id",
                    f"doc_id '{doc_id}' does not use the namespace required for {metadata.doc_type}",
                    document.relative_path,
                )
            )
        if expected_path is not None and document.relative_path != expected_path:
            issues.append(
                Issue(
                    "canonical_leaf_path",
                    f"'{doc_id}' must be stored at {expected_path}",
                    document.relative_path,
                )
            )
        if expected_parent is not None and metadata.parent_id != expected_parent:
            issues.append(
                Issue(
                    "canonical_leaf_parent",
                    f"'{doc_id}' must use parent_id '{expected_parent}'",
                    document.relative_path,
                )
            )
    return issues


def _path_has_exact_case(path: Path, repository: Path) -> bool:
    """Check every repository-relative path segment with exact casing."""
    try:
        relative_parts = path.resolve().relative_to(repository.resolve()).parts
    except ValueError:
        return False
    current = repository.resolve()
    for part in relative_parts:
        try:
            names = {child.name for child in current.iterdir()}
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            return False
        if part not in names:
            return False
        current /= part
    return True


def _case_insensitive_existing_path(path: Path, repository: Path) -> Path | None:
    """Resolve a differently-cased repository path for portable diagnostics."""
    try:
        relative_parts = path.relative_to(repository.resolve()).parts
    except ValueError:
        return None
    current = repository.resolve()
    for part in relative_parts:
        try:
            matches = [child for child in current.iterdir() if child.name.casefold() == part.casefold()]
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            return None
        if len(matches) != 1:
            return None
        current = matches[0]
    return current if current.exists() else None


def _resolve_internal_target(
    document: Document, target: str, repository: Path
) -> tuple[Path | None, str | None, str | None]:
    """Resolve a Markdown target to ``(path, anchor, error_code)``."""
    stripped = target.strip()
    parsed = urlsplit(stripped)
    if parsed.scheme or stripped.startswith("//"):
        return None, None, None
    decoded_path = unquote(parsed.path)
    anchor = unquote(parsed.fragment) or None
    if not decoded_path:
        return document.path.resolve(), anchor, None
    if decoded_path.startswith("/"):
        candidate = repository / decoded_path.lstrip("/")
    else:
        candidate = document.path.parent / decoded_path
    candidate = candidate.resolve()
    try:
        candidate.relative_to(repository.resolve())
    except ValueError:
        return candidate, anchor, "link_outside_repository"
    return candidate, anchor, None


def _managed_marker_analysis(
    text: str,
) -> tuple[tuple[int, int] | None, tuple[tuple[str, int], ...]]:
    """Return one safe visible marker range and structural marker failures."""
    markers = [
        (line_number, line.strip())
        for line_number, line in _visible_markdown_lines(text)
        if line.strip() in {MANAGED_LINKS_START, MANAGED_LINKS_END}
    ]
    failures: list[tuple[str, int]] = []
    active_start: int | None = None
    ranges: list[tuple[int, int]] = []
    for line_number, marker in markers:
        if marker == MANAGED_LINKS_START:
            if active_start is not None:
                failures.append(("managed_links_marker_nested", line_number))
            else:
                active_start = line_number
        elif active_start is None:
            failures.append(("managed_links_marker_unmatched", line_number))
        else:
            ranges.append((active_start, line_number))
            active_start = None
    if active_start is not None:
        failures.append(("managed_links_marker_unmatched", active_start))
    starts = sum(marker == MANAGED_LINKS_START for _, marker in markers)
    ends = sum(marker == MANAGED_LINKS_END for _, marker in markers)
    if starts > 1 or ends > 1:
        duplicate_line = markers[1][0] if len(markers) > 1 else 1
        failures.append(("managed_links_marker_duplicate", duplicate_line))
    if starts != 1 or ends != 1 or len(ranges) != 1:
        failures.append(("managed_links_marker_count", markers[0][0] if markers else 1))
    if failures:
        return None, tuple(dict.fromkeys(failures))
    return ranges[0], ()


def validate_managed_markers(
    documents: Sequence[Document], *, allow_missing: bool = False
) -> list[Issue]:
    """Reject malformed visible marker blocks without considering fenced examples."""
    issues: list[Issue] = []
    messages = {
        "managed_links_marker_nested": "generated link markers cannot be nested",
        "managed_links_marker_unmatched": "generated link marker is unmatched or out of order",
        "managed_links_marker_duplicate": "document contains duplicate generated link markers",
        "managed_links_marker_count": "document must contain exactly one ordered generated link block",
    }
    for document in documents:
        if allow_missing and not any(
            line.strip() in {MANAGED_LINKS_START, MANAGED_LINKS_END}
            for _, line in _visible_markdown_lines(document.text)
        ):
            continue
        _, failures = _managed_marker_analysis(document.text)
        for code, line in failures:
            issues.append(Issue(code, messages[code], document.relative_path, line))
    return issues


def validate_internal_links(
    repository: Path,
    documents: Sequence[Document],
    by_id: dict[str, Document],
    aliases: dict[str, str],
) -> list[Issue]:
    """Validate local link paths, exact case, anchors, and graph relations."""
    issues: list[Issue] = []
    by_path = {document.path.resolve(): document for document in documents}
    relation_pairs: set[tuple[str, str]] = set()
    structural_pairs: set[tuple[str, str]] = set()
    for document in documents:
        metadata = document.metadata
        if metadata is None:
            continue
        if metadata.parent_id:
            parent_id = aliases.get(metadata.parent_id, metadata.parent_id)
            structural_pairs.add((metadata.doc_id, parent_id))
            structural_pairs.add((parent_id, metadata.doc_id))
        for relation in metadata.relations:
            target_id = aliases.get(relation.target_id, relation.target_id)
            relation_pairs.add((metadata.doc_id, target_id))
            relation_pairs.add((target_id, metadata.doc_id))

    for document in documents:
        source_metadata = document.metadata
        managed_range, marker_failures = _managed_marker_analysis(document.text)
        messages = {
            "managed_links_marker_nested": "generated link markers cannot be nested",
            "managed_links_marker_unmatched": "generated link marker is unmatched or out of order",
            "managed_links_marker_duplicate": "document contains duplicate generated link markers",
            "managed_links_marker_count": "document must contain exactly one ordered generated link block",
        }
        for code, line in marker_failures:
            issues.append(Issue(code, messages[code], document.relative_path, line))
        for link in extract_markdown_links(document.text):
            resolved, anchor, resolve_error = _resolve_internal_target(document, link.target, repository)
            if resolved is None:
                continue
            if resolve_error is not None:
                issues.append(
                    Issue(
                        resolve_error,
                        f"link escapes repository: '{link.target}'",
                        document.relative_path,
                        link.line,
                    )
                )
                continue
            if not resolved.exists():
                case_variant = _case_insensitive_existing_path(resolved, repository)
                if case_variant is not None and case_variant.is_file():
                    issues.append(
                        Issue(
                            "link_path_case",
                            f"link target casing does not match filesystem: '{link.target}'",
                            document.relative_path,
                            link.line,
                        )
                    )
                    resolved = case_variant.resolve()
                else:
                    issues.append(
                        Issue(
                            "link_target_missing",
                            f"link target does not exist: '{link.target}'",
                            document.relative_path,
                            link.line,
                        )
                    )
                    continue
            if not resolved.is_file():
                issues.append(
                    Issue(
                        "link_target_missing",
                        f"link target does not exist: '{link.target}'",
                        document.relative_path,
                        link.line,
                    )
                )
                continue
            if not _path_has_exact_case(resolved, repository):
                issues.append(
                    Issue(
                        "link_path_case",
                        f"link target casing does not match filesystem: '{link.target}'",
                        document.relative_path,
                        link.line,
                    )
                )
            target_document = by_path.get(resolved)
            if anchor and resolved.suffix.lower() == ".md":
                target_text = (
                    target_document.text
                    if target_document is not None
                    else resolved.read_text(encoding="utf-8")
                )
                if anchor not in markdown_anchors(target_text):
                    issues.append(
                        Issue(
                            "link_anchor_missing",
                            f"anchor '#{anchor}' does not exist in '{link.target}'",
                            document.relative_path,
                            link.line,
                        )
                    )
            if (
                source_metadata is not None
                and target_document is not None
                and target_document.metadata is not None
                and source_metadata.doc_id != target_document.metadata.doc_id
            ):
                pair = (source_metadata.doc_id, target_document.metadata.doc_id)
                inside_managed_block = (
                    managed_range is not None
                    and managed_range[0] < link.line < managed_range[1]
                )
                if not inside_managed_block:
                    issues.append(
                        Issue(
                            "doc_link_outside_managed_block",
                            "cross-document links must be generated from graph metadata",
                            document.relative_path,
                            link.line,
                        )
                    )
                elif pair not in relation_pairs and pair not in structural_pairs:
                    issues.append(
                        Issue(
                            "link_relation_missing",
                            f"link to doc_id '{target_document.metadata.doc_id}' has no parent or declared relation",
                            document.relative_path,
                            link.line,
                        )
                    )
    return issues


def _without_managed_links(text: str) -> str:
    """Remove one valid visible generated block while preserving fenced examples."""
    marker_range, failures = _managed_marker_analysis(text)
    if marker_range is None or failures:
        return text.rstrip() + "\n"
    start_line, end_line = marker_range
    lines = text.splitlines()
    preserved = [*lines[: start_line - 1], *lines[end_line:]]
    return "\n".join(preserved).rstrip() + "\n"


def lint_component_sections(documents: Sequence[Document]) -> list[Issue]:
    """Reject missing, reordered, empty, or placeholder required authored sections."""
    issues: list[Issue] = []
    for document in documents:
        if document.metadata is None:
            continue
        metadata = document.metadata
        if metadata.doc_type == "architecture-root" and metadata.doc_id == "architecture.root":
            required_sections = REQUIRED_ARCHITECTURE_ROOT_SECTIONS
        else:
            required_sections = REQUIRED_SECTIONS_BY_TYPE.get(metadata.doc_type)
        if required_sections is None:
            continue
        diagnostic_prefix = (
            "component" if metadata.doc_type == "architecture-component" else "document"
        )
        visible = list(_visible_markdown_lines(document.text))
        headings: list[tuple[str, int, int]] = []
        for visible_index, (line_number, line) in enumerate(visible):
            match = re.match(r"^ {0,3}##\s+(.+?)\s*#*\s*$", line)
            if match:
                headings.append((match.group(1).strip(), visible_index, line_number))
        heading_lookup = {heading: (index, line) for heading, index, line in headings}
        if len(heading_lookup) != len(headings):
            issues.append(
                Issue(
                    f"{diagnostic_prefix}_heading_duplicate",
                    "document contains duplicate H2 headings",
                    document.relative_path,
                )
            )
        previous_index = -1
        for required_heading in required_sections:
            location = heading_lookup.get(required_heading)
            if location is None:
                issues.append(
                        Issue(
                        f"{diagnostic_prefix}_section_missing",
                        f"missing required section '## {required_heading}'",
                        document.relative_path,
                    )
                )
                continue
            heading_index, heading_line = location
            if heading_index < previous_index:
                issues.append(
                        Issue(
                        f"{diagnostic_prefix}_section_order",
                        f"section '## {required_heading}' is out of order",
                        document.relative_path,
                        heading_line,
                    )
                )
            previous_index = heading_index
            next_heading_index = len(visible)
            for _, candidate_index, _ in headings:
                if candidate_index > heading_index:
                    next_heading_index = candidate_index
                    break
            body_lines = [line for _, line in visible[heading_index + 1 : next_heading_index]]
            body = "\n".join(body_lines).strip()
            if not body:
                issues.append(
                        Issue(
                        f"{diagnostic_prefix}_section_empty",
                        f"section '## {required_heading}' is empty",
                        document.relative_path,
                        heading_line,
                    )
                )
            elif PLACEHOLDER_PATTERN.search(body):
                issues.append(
                        Issue(
                        f"{diagnostic_prefix}_section_placeholder",
                        f"section '## {required_heading}' contains placeholder text",
                        document.relative_path,
                        heading_line,
                    )
                )
            elif re.fullmatch(r"(?is)not applicable\s*[—:-]\s*.{0,9}", body):
                issues.append(
                        Issue(
                        f"{diagnostic_prefix}_section_unexplained_na",
                        f"section '## {required_heading}' needs a substantive N/A reason",
                        document.relative_path,
                        heading_line,
                    )
                )
        authored_text = _without_managed_links(document.text)
        if PLACEHOLDER_PATTERN.search(authored_text):
            issues.append(
                Issue(
                    f"{diagnostic_prefix}_placeholder",
                    "authored document contains placeholder prose",
                    document.relative_path,
                )
            )
    return issues


def _validate_repository_pattern(pattern: str) -> str | None:
    """Return why a repository glob is unsafe, or ``None`` when it is valid."""
    if not pattern or not pattern.strip():
        return "pattern is empty"
    if pattern != pattern.strip():
        return "pattern has surrounding whitespace"
    if "\\" in pattern:
        return "pattern must use POSIX separators"
    if pattern.startswith("/") or re.match(r"^[A-Za-z]:/", pattern):
        return "absolute patterns are forbidden"
    if "\0" in pattern:
        return "pattern contains a NUL byte"
    parts = pattern.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return "pattern contains an empty, current, or parent segment"
    if any(character in pattern for character in "?[]{}"):
        return "only literal characters, '*' and whole-segment '**' are supported"
    if any("**" in part and part != "**" for part in parts):
        return "'**' must occupy a complete path segment"
    return None


def _segment_matches(value: str, pattern: str) -> bool:
    """Match one path segment where ``*`` cannot cross a slash."""
    expression = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return re.fullmatch(expression, value) is not None


def _glob_matches(path: str, pattern: str) -> bool:
    """Match safe POSIX path globs with segment-aware ``*`` and ``**``."""
    if pattern.startswith("./") and not pattern.startswith("../"):
        pattern = pattern[2:]
    if _validate_repository_pattern(pattern) is not None:
        return False
    if "\\" in path or path.startswith("/"):
        return False
    path_parts = tuple(part for part in path.split("/") if part)
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
                path_index < len(path_parts) and matches(pattern_index, path_index + 1)
            )
        else:
            result = (
                path_index < len(path_parts)
                and _segment_matches(path_parts[path_index], pattern_parts[pattern_index])
                and matches(pattern_index + 1, path_index + 1)
            )
        memo[key] = result
        return result

    return matches(0, 0)


def _is_blanket_exclusion(pattern: str) -> bool:
    """Reject exclusions broad enough to hide a whole inventory family."""
    parts = pattern.split("/")
    literal_segments = [part for part in parts if "*" not in part]
    if not literal_segments:
        return True
    return len(literal_segments) == 1 and parts[-1] == "**"


def _repository_files(repository: Path) -> tuple[str, ...]:
    """Return existing, regular, in-root Git-visible files without symlinks."""
    repository = repository.resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        candidates = (
            path
            for path in repository.rglob("*")
            if ".git" not in path.relative_to(repository).parts
        )
    else:
        candidates = (
            repository / item.decode("utf-8", errors="surrogateescape")
            for item in result.stdout.split(b"\0")
            if item
        )
    visible: list[str] = []
    for path in candidates:
        try:
            relative = path.relative_to(repository).as_posix()
            mode = path.lstat().st_mode
            path.resolve().relative_to(repository)
        except (FileNotFoundError, OSError, ValueError):
            continue
        if stat.S_ISREG(mode) and not path.is_symlink():
            visible.append(relative)
    return tuple(sorted(set(visible)))


def _safe_repository_file(repository: Path, raw_path: str) -> tuple[Path | None, str | None]:
    """Resolve an exact repository-relative regular file without traversal or escape."""
    normalized = raw_path.replace("\\", "/")
    source_path = PurePosixPath(normalized)
    if source_path.is_absolute() or ".." in source_path.parts:
        return None, "source_path_traversal"
    unresolved = repository / Path(*source_path.parts)
    if unresolved.is_symlink():
        return unresolved, "source_path_symlink"
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(repository.resolve())
    except ValueError:
        return None, "source_path_traversal"
    if not candidate.exists():
        return candidate, "source_path_missing"
    try:
        mode = candidate.lstat().st_mode
    except OSError:
        return candidate, "source_path_missing"
    if not stat.S_ISREG(mode) or candidate.is_symlink():
        return candidate, "source_path_not_file"
    if not _path_has_exact_case(candidate, repository):
        return candidate, "source_path_case"
    return candidate, None


def _load_json_object(path: Path, repository: Path) -> tuple[dict[str, object] | None, list[Issue]]:
    """Read a JSON object and return actionable parse/type issues."""
    relative_path = _relative(path, repository)
    if not path.is_file():
        return None, [Issue("catalog_missing", f"required catalog is missing: {relative_path}", relative_path)]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        line = error.lineno if isinstance(error, json.JSONDecodeError) else None
        return None, [Issue("catalog_invalid_json", str(error), relative_path, line)]
    if not isinstance(payload, dict):
        return None, [Issue("catalog_not_object", "catalog root must be a JSON object", relative_path)]
    return payload, []


def validate_architecture_catalog(
    repository: Path,
    documents_by_id: dict[str, Document],
    aliases: dict[str, str],
) -> tuple[list[Issue], dict[str, object] | None, dict[str, str]]:
    """Validate architecture catalog schema, graph, and 100% configured inventory ownership.

    Inventory includes are globs over Git-visible files.  Exclusions are objects
    with ``glob`` and a non-empty ``reason``.  Component ``sources`` and ``tests``
    use repository-relative paths or narrow globs; every eligible source must have
    exactly one owner.
    """
    catalog_path = repository / ARCHITECTURE_CATALOG
    catalog, issues = _load_json_object(catalog_path, repository)
    if catalog is None:
        return issues, None, {}
    catalog_relative = ARCHITECTURE_CATALOG.as_posix()
    allowed_root_fields = {
        "schema_version",
        "inventory",
        "areas",
        "components",
        "relationships",
    }
    for unknown in sorted(set(catalog) - allowed_root_fields):
        issues.append(
            Issue(
                "catalog_unknown_field",
                f"unsupported catalog field '{unknown}'",
                catalog_relative,
            )
        )
    if catalog.get("schema_version") != SCHEMA_VERSION:
        issues.append(
            Issue(
                "catalog_schema_version",
                f"schema_version must be {SCHEMA_VERSION}",
                catalog_relative,
            )
        )

    inventory = catalog.get("inventory")
    include_patterns: list[str] = []
    exclusion_rules: list[tuple[str, str]] = []
    if not isinstance(inventory, dict) or set(inventory) != {"include", "exclude"}:
        issues.append(
            Issue(
                "inventory_invalid",
                "inventory must contain exactly include and exclude",
                catalog_relative,
            )
        )
    else:
        includes = inventory.get("include")
        if not isinstance(includes, list) or not all(
            isinstance(item, str) and item.strip() for item in includes
        ):
            issues.append(
                Issue(
                    "inventory_include_invalid",
                    "inventory.include must be a non-empty string list",
                    catalog_relative,
                )
            )
        else:
            include_patterns = []
            for index, pattern in enumerate(includes):
                assert isinstance(pattern, str)
                pattern_error = _validate_repository_pattern(pattern)
                if pattern_error is not None:
                    issues.append(
                        Issue(
                            "inventory_include_pattern",
                            f"inventory.include[{index}] is unsafe: {pattern_error}",
                            catalog_relative,
                        )
                    )
                else:
                    include_patterns.append(pattern)
            if not include_patterns:
                issues.append(
                    Issue(
                        "inventory_include_empty",
                        "inventory.include must select reviewed files",
                        catalog_relative,
                    )
                )
        excludes = inventory.get("exclude")
        if not isinstance(excludes, list):
            issues.append(
                Issue(
                    "inventory_exclude_invalid",
                    "inventory.exclude must be a list",
                    catalog_relative,
                )
            )
        else:
            for index, exclusion in enumerate(excludes):
                if not isinstance(exclusion, dict) or set(exclusion) != {"glob", "reason"}:
                    issues.append(
                        Issue(
                            "inventory_exclude_invalid",
                            f"inventory.exclude[{index}] must contain exactly glob/reason",
                            catalog_relative,
                        )
                    )
                    continue
                pattern = exclusion.get("glob")
                reason = exclusion.get("reason")
                if not isinstance(pattern, str) or not pattern.strip():
                    issues.append(
                        Issue(
                            "inventory_exclude_glob",
                            f"inventory.exclude[{index}] needs glob",
                            catalog_relative,
                        )
                    )
                    continue
                pattern_error = _validate_repository_pattern(pattern)
                if pattern_error is not None:
                    issues.append(
                        Issue(
                            "inventory_exclude_pattern",
                            f"inventory exclusion '{pattern}' is unsafe: {pattern_error}",
                            catalog_relative,
                        )
                    )
                    continue
                if _is_blanket_exclusion(pattern):
                    issues.append(
                        Issue(
                            "inventory_exclusion_blanket",
                            f"inventory exclusion '{pattern}' is too broad",
                            catalog_relative,
                        )
                    )
                    continue
                if not isinstance(reason, str) or not reason.strip():
                    issues.append(
                        Issue(
                            "inventory_exclude_reason",
                            f"inventory exclusion '{pattern}' needs a reason",
                            catalog_relative,
                        )
                    )
                    continue
                exclusion_rules.append((pattern, reason))

    repository_files = set(_repository_files(repository))
    eligible_files = {
        path
        for path in repository_files
        if any(_glob_matches(path, pattern) for pattern in include_patterns)
        and not any(_glob_matches(path, pattern) for pattern, _ in exclusion_rules)
    }

    areas = catalog.get("areas")
    if not isinstance(areas, list):
        issues.append(Issue("areas_invalid", "areas must be a list", catalog_relative))
        areas = []
    elif not areas:
        issues.append(Issue("areas_empty", "areas must contain reviewed architecture areas", catalog_relative))
    area_ids: set[str] = set()
    for index, area in enumerate(areas):
        if not isinstance(area, dict) or set(area) != {"id", "name", "doc_id"}:
            issues.append(
                Issue(
                    "area_invalid",
                    f"areas[{index}] must contain exactly id/name/doc_id",
                    catalog_relative,
                )
            )
            continue
        area_id = area.get("id")
        doc_id = area.get("doc_id")
        if not isinstance(area_id, str) or not DOC_ID_PATTERN.fullmatch(area_id):
            issues.append(Issue("area_id_invalid", f"areas[{index}] has invalid id", catalog_relative))
            continue
        if area_id in area_ids:
            issues.append(Issue("area_id_duplicate", f"duplicate area id '{area_id}'", catalog_relative))
        area_ids.add(area_id)
        target = documents_by_id.get(str(doc_id))
        if target is None:
            issues.append(Issue("area_doc_missing", f"area '{area_id}' doc_id '{doc_id}' does not resolve", catalog_relative))
        elif target.metadata is not None and target.metadata.doc_type != "architecture-area":
            issues.append(Issue("area_doc_wrong_type", f"area '{area_id}' does not point to architecture-area", catalog_relative))
        elif target.path.resolve() != (
            repository / ARCHITECTURE_DIR / "areas" / area_id / "README.md"
        ).resolve():
            issues.append(
                Issue(
                    "area_doc_wrong_path",
                    f"area '{area_id}' document is outside its canonical path",
                    catalog_relative,
                )
            )

    def expand_entries(
        entries: object,
        component_id: str,
        field_name: str,
    ) -> set[str]:
        expanded: set[str] = set()
        if not isinstance(entries, list) or not all(
            isinstance(item, str) and item.strip() for item in entries
        ):
            issues.append(
                Issue(
                    f"component_{field_name}_invalid",
                    f"component '{component_id}' {field_name} must be a string list",
                    catalog_relative,
                )
            )
            return expanded
        for entry in entries:
            assert isinstance(entry, str)
            pattern_error = _validate_repository_pattern(entry)
            if pattern_error is not None:
                issues.append(
                    Issue(
                        "source_path_traversal",
                        f"component '{component_id}' {field_name} entry is unsafe: '{entry}' ({pattern_error})",
                        catalog_relative,
                    )
                )
                continue
            if "*" not in entry:
                _, safe_error = _safe_repository_file(repository, entry)
                if safe_error in {"source_path_symlink", "source_path_traversal"}:
                    issues.append(
                        Issue(
                            safe_error,
                            f"component '{component_id}' {field_name} entry is unsafe: '{entry}'",
                            catalog_relative,
                        )
                    )
                    continue
            matches = {path for path in repository_files if _glob_matches(path, entry)}
            if not matches:
                issues.append(
                    Issue(
                        f"component_{field_name}_unmatched",
                        f"component '{component_id}' {field_name} entry matched no files: '{entry}'",
                        catalog_relative,
                    )
                )
            expanded.update(matches)
        return expanded

    components = catalog.get("components")
    if not isinstance(components, list):
        issues.append(Issue("components_invalid", "components must be a list", catalog_relative))
        components = []
    elif not components:
        issues.append(Issue("components_empty", "components must contain reviewed component ownership", catalog_relative))
    component_ids: dict[str, int] = {}
    component_doc_ids: dict[str, str] = {}
    source_owners: defaultdict[str, list[str]] = defaultdict(list)
    test_owners: defaultdict[str, list[str]] = defaultdict(list)
    allowed_component_fields = {
        "id",
        "name",
        "kind",
        "profile",
        "area",
        "doc_id",
        "status",
        "sources",
        "tests",
    }
    for index, raw_component in enumerate(components):
        if not isinstance(raw_component, dict):
            issues.append(Issue("component_invalid", f"components[{index}] must be an object", catalog_relative))
            continue
        if set(raw_component) != allowed_component_fields:
            missing = sorted(allowed_component_fields - set(raw_component))
            unknown = sorted(set(raw_component) - allowed_component_fields)
            issues.append(
                Issue(
                    "component_shape_invalid",
                    f"components[{index}] missing={missing} unknown={unknown}",
                    catalog_relative,
                )
            )
        component_id = raw_component.get("id")
        doc_id = raw_component.get("doc_id")
        if not isinstance(component_id, str) or not COMPONENT_ID_PATTERN.fullmatch(component_id):
            issues.append(Issue("component_id_invalid", f"components[{index}] has invalid id", catalog_relative))
            continue
        if component_id in component_ids:
            issues.append(Issue("component_id_duplicate", f"duplicate component id '{component_id}'", catalog_relative))
        component_ids[component_id] = index
        if not isinstance(doc_id, str) or not DOC_ID_PATTERN.fullmatch(doc_id):
            issues.append(Issue("component_doc_id_invalid", f"component '{component_id}' has invalid doc_id", catalog_relative))
            target_document = None
        else:
            if doc_id in component_doc_ids:
                issues.append(Issue("component_doc_id_duplicate", f"doc_id '{doc_id}' is assigned to multiple components", catalog_relative))
            component_doc_ids[doc_id] = component_id
            target_document = documents_by_id.get(aliases.get(doc_id, doc_id))
            if target_document is None:
                issues.append(Issue("component_doc_missing", f"component '{component_id}' doc_id '{doc_id}' does not resolve", catalog_relative))
            elif target_document.metadata is not None and target_document.metadata.doc_type != "architecture-component":
                issues.append(Issue("component_doc_wrong_type", f"component '{component_id}' points to non-component doc", catalog_relative))
        status = raw_component.get("status")
        profile = raw_component.get("profile")
        kind = raw_component.get("kind")
        area_id = raw_component.get("area")
        if status not in DOC_TYPE_STATUSES["architecture-component"]:
            issues.append(Issue("component_status_invalid", f"component '{component_id}' has invalid status '{status}'", catalog_relative))
        if profile not in PROFILE_KINDS:
            issues.append(Issue("component_profile_invalid", f"component '{component_id}' has invalid profile '{profile}'", catalog_relative))
        elif kind not in PROFILE_KINDS[str(profile)]:
            issues.append(Issue("component_kind_invalid", f"component '{component_id}' kind '{kind}' does not match profile '{profile}'", catalog_relative))
        if area_id not in area_ids:
            issues.append(Issue("component_area_missing", f"component '{component_id}' references unknown area '{area_id}'", catalog_relative))
        if target_document is not None and target_document.metadata is not None:
            expected_doc_id = f"architecture.component.{component_id}"
            if doc_id != expected_doc_id:
                issues.append(
                    Issue(
                        "component_doc_id_mismatch",
                        f"component '{component_id}' must use doc_id '{expected_doc_id}'",
                        catalog_relative,
                    )
                )
            expected_path = (
                repository
                / ARCHITECTURE_DIR
                / "areas"
                / str(area_id)
                / "components"
                / f"{component_id}.md"
            ).resolve()
            if target_document.path.resolve() != expected_path:
                issues.append(
                    Issue(
                        "component_doc_wrong_path",
                        f"component '{component_id}' page is outside its canonical path",
                        catalog_relative,
                    )
                )
            if target_document.metadata.profile != profile:
                issues.append(Issue("component_profile_mismatch", f"component '{component_id}' profile differs from page", catalog_relative))
            if target_document.metadata.status != status:
                issues.append(Issue("component_status_mismatch", f"component '{component_id}' status differs from page", catalog_relative))
            expected_parent_id = f"architecture.area.{area_id}"
            if target_document.metadata.parent_id != expected_parent_id:
                issues.append(
                    Issue(
                        "component_catalog_parent_area_mismatch",
                        f"component '{component_id}' parent and catalog area differ; expected '{expected_parent_id}'",
                        catalog_relative,
                    )
                )
        journal_id = f"journal.component.{component_id}"
        journal_document = documents_by_id.get(journal_id)
        expected_journal_path = (
            repository / "docs/journals/components" / f"{component_id}.md"
        ).resolve()
        if journal_document is None:
            issues.append(
                Issue(
                    "component_journal_missing",
                    f"component '{component_id}' has no component journal",
                    catalog_relative,
                )
            )
        elif (
            journal_document.metadata is None
            or journal_document.metadata.doc_type != "journal-component"
            or journal_document.path.resolve() != expected_journal_path
        ):
            issues.append(
                Issue(
                    "component_journal_invalid",
                    f"component '{component_id}' journal has wrong type or path",
                    catalog_relative,
                )
            )
        expanded_sources = expand_entries(raw_component.get("sources"), component_id, "sources")
        expanded_tests = expand_entries(raw_component.get("tests"), component_id, "tests")
        if status == "removed":
            if raw_component.get("sources") not in ([], None):
                issues.append(Issue("removed_component_sources", f"removed component '{component_id}' must have no current sources", catalog_relative))
        elif not expanded_sources:
            issues.append(Issue("component_sources_empty", f"component '{component_id}' has no existing source", catalog_relative))
        if status != "removed" and not expanded_tests:
            issues.append(Issue("component_tests_empty", f"component '{component_id}' has no existing test evidence", catalog_relative))
        for source in expanded_sources:
            source_owners[source].append(component_id)
        for test in expanded_tests:
            test_owners[test].append(component_id)

    relationships = catalog.get("relationships")
    if not isinstance(relationships, list):
        issues.append(Issue("relationships_invalid", "relationships must be a list", catalog_relative))
        relationships = []
    seen_relationships: set[tuple[str, str, str]] = set()
    for index, relationship in enumerate(relationships):
        if not isinstance(relationship, dict) or set(relationship) != {"from", "type", "to"}:
            issues.append(Issue("component_relationship_invalid", f"relationships[{index}] must contain exactly from/type/to", catalog_relative))
            continue
        source_id = relationship.get("from")
        target_id = relationship.get("to")
        relation_type = relationship.get("type")
        if relation_type not in {"related", "depends-on"}:
            issues.append(Issue("component_relationship_type", f"relationships[{index}] has unsupported type '{relation_type}'", catalog_relative))
        if source_id not in component_ids:
            issues.append(Issue("component_relationship_source", f"relationships[{index}] source '{source_id}' does not exist", catalog_relative))
        if target_id not in component_ids:
            issues.append(Issue("component_relationship_target", f"relationships[{index}] target '{target_id}' does not exist", catalog_relative))
        if source_id == target_id:
            issues.append(Issue("component_relationship_self", f"relationships[{index}] is a self-edge", catalog_relative))
        if isinstance(source_id, str) and isinstance(target_id, str) and isinstance(relation_type, str):
            edge = (source_id, relation_type, target_id)
            if edge in seen_relationships:
                issues.append(Issue("component_relationship_duplicate", f"duplicate component relationship {edge}", catalog_relative))
            seen_relationships.add(edge)
            if source_id in component_ids and target_id in component_ids:
                source_doc_id = f"architecture.component.{source_id}"
                target_doc_id = f"architecture.component.{target_id}"
                source_document = documents_by_id.get(source_doc_id)
                mirrored = (
                    source_document is not None
                    and source_document.metadata is not None
                    and any(
                        relation.relation_type == relation_type
                        and aliases.get(relation.target_id, relation.target_id) == target_doc_id
                        for relation in source_document.metadata.relations
                    )
                )
                if not mirrored:
                    issues.append(
                        Issue(
                            "component_relationship_not_documented",
                            f"catalog relationship {source_id} {relation_type} {target_id} is absent from source document relations",
                            catalog_relative,
                        )
                    )

    catalog_doc_ids = set(component_doc_ids)
    for document in documents_by_id.values():
        metadata = document.metadata
        if metadata is None or metadata.doc_type != "architecture-component":
            continue
        if metadata.doc_id not in catalog_doc_ids:
            issues.append(
                Issue(
                    "component_document_unlisted",
                    f"architecture component '{metadata.doc_id}' has no catalog component",
                    document.relative_path,
                )
            )

    catalog_component_ids = set(component_ids)
    for document in documents_by_id.values():
        metadata = document.metadata
        if metadata is None or metadata.doc_type != "journal-component":
            continue
        prefix = "journal.component."
        component_id = metadata.doc_id[len(prefix) :] if metadata.doc_id.startswith(prefix) else ""
        if component_id not in catalog_component_ids:
            issues.append(
                Issue(
                    "component_journal_unlisted",
                    f"component journal '{metadata.doc_id}' has no catalog component",
                    document.relative_path,
                )
            )

    known_tests = set(test_owners)

    def is_test_path(path: str) -> bool:
        name = PurePosixPath(path).name.lower()
        parts = {part.lower() for part in PurePosixPath(path).parts}
        return (
            path in known_tests
            or bool(parts & {"test", "tests", "__tests__", "spec", "specs"})
            or ".test." in name
            or ".spec." in name
            or name.startswith("test_")
            or re.search(r"_test\.[^.]+$", name) is not None
        )

    for source, owners in sorted(source_owners.items()):
        if source not in eligible_files:
            issues.append(Issue("source_not_in_inventory", f"owned source '{source}' is not selected by inventory", catalog_relative))
        if is_test_path(source):
            issues.append(Issue("test_listed_as_source", f"test file is listed as source: '{source}'", catalog_relative))
        if len(owners) > 1:
            issues.append(Issue("source_duplicate_owner", f"source '{source}' has multiple owners: {', '.join(sorted(owners))}", catalog_relative))
    for test in sorted(test_owners):
        if test not in eligible_files:
            issues.append(Issue("test_not_in_inventory", f"test evidence '{test}' is not selected by inventory", catalog_relative))
    for path in sorted(eligible_files):
        if is_test_path(path):
            if path not in test_owners:
                issues.append(Issue("test_uncovered", f"inventory test has no component evidence: '{path}'", catalog_relative))
        elif path not in source_owners:
            issues.append(Issue("source_uncovered", f"inventory source has no component owner: '{path}'", catalog_relative))

    unique_owners = {
        source: owners[0]
        for source, owners in source_owners.items()
        if len(owners) == 1
    }
    for test, owners in test_owners.items():
        if owners:
            unique_owners.setdefault(test, owners[0])
    return issues, catalog, unique_owners


def _relative_doc_link(source: Document, target: Document) -> str:
    """Return a portable relative link from one Markdown page to another."""
    return posixpath.relpath(target.relative_path, posixpath.dirname(source.relative_path))


def _managed_links_block(
    document: Document,
    by_id: dict[str, Document],
    aliases: dict[str, str],
) -> str:
    """Render deterministic parent, child, related, and backlink navigation."""
    assert document.metadata is not None
    metadata = document.metadata
    children = sorted(
        (
            candidate
            for candidate in by_id.values()
            if candidate.metadata is not None
            and aliases.get(candidate.metadata.parent_id, candidate.metadata.parent_id) == metadata.doc_id
        ),
        key=lambda item: item.metadata.doc_id if item.metadata else "",
    )
    related: list[tuple[Relation, Document]] = []
    for relation in metadata.relations:
        target_id = aliases.get(relation.target_id, relation.target_id)
        if target_id in by_id:
            related.append((relation, by_id[target_id]))
    related.sort(
        key=lambda item: (
            item[0].relation_type,
            item[1].metadata.doc_id if item[1].metadata else "",
            item[0].anchor or "",
        )
    )
    backlinks: list[tuple[str, Document]] = []
    for candidate in by_id.values():
        if candidate.metadata is None or candidate.metadata.doc_id == metadata.doc_id:
            continue
        for relation in candidate.metadata.relations:
            if aliases.get(relation.target_id, relation.target_id) == metadata.doc_id:
                backlinks.append((relation.relation_type, candidate))
    backlinks.sort(key=lambda item: (item[0], item[1].metadata.doc_id if item[1].metadata else ""))

    lines = [MANAGED_LINKS_START]
    if metadata.parent_id:
        parent_id = aliases.get(metadata.parent_id, metadata.parent_id)
        parent = by_id.get(parent_id)
        if parent is not None and parent.metadata is not None:
            lines.append(f"- Parent: [{parent.metadata.title}]({_relative_doc_link(document, parent)})")
    else:
        lines.append("- Parent: None (documentation root).")
    if children:
        lines.append("- Children:")
        for child in children:
            assert child.metadata is not None
            lines.append(f"  - [{child.metadata.title}]({_relative_doc_link(document, child)})")
    else:
        lines.append("- Children: None.")
    if related:
        lines.append("- Related:")
        for relation, target in related:
            assert target.metadata is not None
            anchor_suffix = f"#{relation.anchor}" if relation.anchor else ""
            lines.append(
                f"  - {relation.relation_type}: [{target.metadata.title}]({_relative_doc_link(document, target)}{anchor_suffix})"
            )
    else:
        lines.append("- Related: None.")
    if backlinks:
        lines.append("- Backlinks:")
        for relation_type, source in backlinks:
            assert source.metadata is not None
            lines.append(f"  - {relation_type}: [{source.metadata.title}]({_relative_doc_link(document, source)})")
    else:
        lines.append("- Backlinks: None.")
    lines.extend([MANAGED_LINKS_END, ""])
    return "\n".join(lines)


def _expected_document_text(document: Document, by_id: dict[str, Document], aliases: dict[str, str]) -> str:
    """Return document text with exactly one current managed link block."""
    clean_text = _without_managed_links(document.text).rstrip()
    visible_headings = [
        line_number
        for line_number, line in _visible_markdown_lines(clean_text)
        if re.match(r"^ {0,3}##\s+Related documentation\s*#*\s*$", line)
    ]
    if not visible_headings:
        clean_text += "\n\n## Related documentation"
        heading_line = len(clean_text.splitlines())
    else:
        heading_line = visible_headings[-1]
    lines = clean_text.splitlines()
    trailing_content = "\n".join(lines[heading_line:]).strip()
    if trailing_content:
        prefix = "\n".join(lines[: heading_line - 1]).rstrip()
        clean_text = (
            prefix
            + "\n\n"
            + trailing_content
            + "\n\n## Related documentation"
        )
        lines = clean_text.splitlines()
        heading_line = len(lines)
    insertion_index = heading_line
    block_lines = _managed_links_block(document, by_id, aliases).rstrip().splitlines()
    lines[insertion_index:insertion_index] = ["", *block_lines]
    return "\n".join(lines).rstrip() + "\n"


def _generated_catalog_text(documents: Sequence[Document]) -> str:
    """Render ``docs/catalog.json`` as a stable projection of Markdown metadata."""
    records: list[dict[str, object]] = []
    for document in sorted(documents, key=lambda item: item.metadata.doc_id if item.metadata else item.relative_path):
        metadata = document.metadata
        if metadata is None:
            continue
        records.append(
            {
                "doc_id": metadata.doc_id,
                "doc_type": metadata.doc_type,
                "parent_id": metadata.parent_id,
                "path": document.relative_path,
                "relations": [relation.as_dict() for relation in metadata.relations],
                "profile": metadata.profile,
                "redirect_to": metadata.redirect_to,
                "status": metadata.status,
                "title": metadata.title,
            }
        )
    redirect_aliases = [
        {
            "legacy_path": document.relative_path,
            "target_id": document.metadata.redirect_to,
        }
        for document in documents
        if document.metadata is not None
        and document.metadata.doc_type == "redirect"
        and document.metadata.redirect_to is not None
    ]
    payload = {
        "aliases": redirect_aliases,
        "documents": records,
        "root_doc_id": ROOT_DOC_ID,
        "schema_version": SCHEMA_VERSION,
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def generated_drift(
    repository: Path,
    documents: Sequence[Document],
    by_id: dict[str, Document],
    aliases: dict[str, str],
) -> list[Issue]:
    """Return all generated catalog and managed-link differences."""
    issues: list[Issue] = []
    generated_path = repository / GENERATED_DOCS_CATALOG
    expected_catalog = _generated_catalog_text(documents)
    if not generated_path.is_file() or generated_path.read_text(encoding="utf-8") != expected_catalog:
        issues.append(Issue("generated_catalog_drift", "docs/catalog.json is missing or stale", GENERATED_DOCS_CATALOG.as_posix()))
    for document in documents:
        if document.metadata is None:
            continue
        if document.text != _expected_document_text(document, by_id, aliases):
            issues.append(Issue("managed_links_drift", "managed architecture link block is missing or stale", document.relative_path))
    return issues


def generate_repository(repository: Path, write: bool) -> tuple[list[Issue], list[str]]:
    """Check or write generated catalog and managed Markdown link blocks."""
    documents, issues = load_documents(repository)
    graph_issues, by_id, aliases = validate_document_graph(documents)
    issues.extend(graph_issues)
    issues.extend(validate_canonical_structure(repository, by_id))
    issues.extend(validate_managed_markers(documents, allow_missing=True))
    if any(issue.severity == "error" for issue in issues):
        return issues, []
    drift = generated_drift(repository, documents, by_id, aliases)
    if not write:
        return drift, []
    changed: list[str] = []
    generated_path = repository / GENERATED_DOCS_CATALOG
    expected_catalog = _generated_catalog_text(documents)
    if not generated_path.is_file() or generated_path.read_text(encoding="utf-8") != expected_catalog:
        generated_path.parent.mkdir(parents=True, exist_ok=True)
        generated_path.write_text(expected_catalog, encoding="utf-8")
        changed.append(GENERATED_DOCS_CATALOG.as_posix())
    for document in documents:
        if document.metadata is None:
            continue
        expected_text = _expected_document_text(document, by_id, aliases)
        if document.text != expected_text:
            document.path.write_text(expected_text, encoding="utf-8")
            changed.append(document.relative_path)
    return [], changed


def _git_changed_entries(
    repository: Path, base: str
) -> tuple[dict[str, str], list[Issue]]:
    """Return current, deleted, renamed, and untracked paths changed from ``base``."""
    try:
        result = subprocess.run(
            [
                "git", "-C", str(repository), "diff", "--name-status", "-z",
                "--find-renames", base, "--",
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        untracked = subprocess.run(
            [
                "git", "-C", str(repository), "ls-files", "-z", "--others",
                "--exclude-standard",
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        return {}, [Issue("git_base_invalid", f"unable to diff base '{base}': {error}")]
    fields = [
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    ]
    changed: dict[str, str] = {}
    index = 0
    while index < len(fields):
        status_value = fields[index]
        index += 1
        status_code = status_value[:1]
        if status_code in {"R", "C"}:
            if index + 1 >= len(fields):
                return {}, [Issue("git_diff_invalid", "Git returned a truncated rename record")]
            old_path, new_path = fields[index], fields[index + 1]
            index += 2
            changed[old_path] = "D" if status_code == "R" else "C"
            changed[new_path] = "A"
        else:
            if index >= len(fields):
                return {}, [Issue("git_diff_invalid", "Git returned a truncated change record")]
            changed[fields[index]] = status_code
            index += 1
    for item in untracked.stdout.split(b"\0"):
        if item:
            changed[item.decode("utf-8", errors="surrogateescape")] = "A"
    return changed, []


def _git_changed_paths(repository: Path, base: str) -> tuple[set[str], list[Issue]]:
    """Backward-compatible changed-path view including both sides of renames."""
    entries, issues = _git_changed_entries(repository, base)
    return set(entries), issues


def _git_file_at_base(repository: Path, base: str, path: str) -> str | None:
    """Read one UTF-8 file from a Git revision, returning ``None`` when absent."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), "show", f"{base}:{path}"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return result.stdout.decode("utf-8")
    except (FileNotFoundError, UnicodeDecodeError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _git_docs_at_base(repository: Path, base: str) -> dict[str, str]:
    """Return every Markdown document at ``base`` keyed by repository path."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), "ls-tree", "-r", "--name-only", "-z", base, "--", "docs"],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return {}
    documents: dict[str, str] = {}
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        path = item.decode("utf-8", errors="surrogateescape")
        if not path.lower().endswith(".md"):
            continue
        text = _git_file_at_base(repository, base, path)
        if text is not None:
            documents[path] = text
    return documents


def _raw_frontmatter_scalar(text: str, key: str) -> str | None:
    """Extract a simple canonical front-matter scalar from repository history."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(rf"^{re.escape(key)}:\s*(.*?)\s*$", line)
        if match:
            return _strip_quotes(match.group(1))
    return None


def _authored_history_body(text: str) -> str:
    """Return authored body excluding front matter and the generated navigation tail."""
    clean = _without_managed_links(text)
    lines = clean.splitlines()
    if lines and lines[0].strip() == "---":
        try:
            end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
            lines = lines[end + 1 :]
        except StopIteration:
            pass
    related_indexes = [
        index
        for index, line in enumerate(lines)
        if re.match(r"^ {0,3}##\s+Related documentation\s*#*\s*$", line)
    ]
    if related_indexes:
        lines = lines[: related_indexes[-1]]
    return "\n".join(lines).rstrip()


def _split_authored_h2_sections(body: str) -> tuple[str, list[tuple[str, str]]]:
    """Split authored history into an immutable preamble and ordered H2 sections."""
    lines = body.splitlines()
    headings: list[tuple[int, str]] = []
    for line_number, line in _visible_markdown_lines(body):
        match = re.match(r"^ {0,3}##\s+(.+?)\s*#*\s*$", line)
        if match:
            headings.append((line_number - 1, match.group(1).strip()))
    if not headings:
        return body.rstrip(), []
    preamble = "\n".join(lines[: headings[0][0]]).rstrip()
    sections: list[tuple[str, str]] = []
    for heading_index, (line_index, heading) in enumerate(headings):
        next_index = (
            headings[heading_index + 1][0]
            if heading_index + 1 < len(headings)
            else len(lines)
        )
        sections.append(
            (heading, "\n".join(lines[line_index + 1 : next_index]).rstrip())
        )
    return preamble, sections


def _sectioned_history_is_append_only(old_body: str, new_body: str) -> bool:
    """Allow journal additions inside existing sections without permitting rewrites."""
    old_preamble, old_sections = _split_authored_h2_sections(old_body)
    new_preamble, new_sections = _split_authored_h2_sections(new_body)
    if old_preamble != new_preamble:
        return False
    if [heading for heading, _ in old_sections] != [
        heading for heading, _ in new_sections
    ]:
        return False
    return all(
        new_content == old_content or new_content.startswith(old_content + "\n")
        for (_, old_content), (_, new_content) in zip(old_sections, new_sections)
    )


def _decision_history_is_append_only(old_body: str, new_body: str) -> bool:
    """Permit accepted-decision additions only under the Amendments section."""
    old_preamble, old_sections = _split_authored_h2_sections(old_body)
    new_preamble, new_sections = _split_authored_h2_sections(new_body)
    if old_preamble != new_preamble:
        return False
    if [heading for heading, _ in old_sections] != [
        heading for heading, _ in new_sections
    ]:
        return False
    amendments_seen = False
    for (heading, old_content), (_, new_content) in zip(old_sections, new_sections):
        if heading == "Amendments":
            amendments_seen = True
            if not (
                new_content == old_content
                or new_content.startswith(old_content + "\n")
            ):
                return False
        elif new_content != old_content:
            return False
    return amendments_seen


def _catalog_selects_path(catalog: dict[str, object] | None, path: str) -> bool:
    """Return whether a catalog inventory includes and does not exclude ``path``."""
    if catalog is None:
        return False
    inventory = catalog.get("inventory")
    if not isinstance(inventory, dict):
        return False
    includes = inventory.get("include")
    excludes = inventory.get("exclude")
    included = isinstance(includes, list) and any(
        isinstance(pattern, str) and _glob_matches(path, pattern)
        for pattern in includes
    )
    excluded = isinstance(excludes, list) and any(
        isinstance(rule, dict)
        and isinstance(rule.get("glob"), str)
        and _glob_matches(path, str(rule["glob"]))
        for rule in excludes
    )
    return included and not excluded


def _catalog_component_owners(
    catalog: dict[str, object] | None, path: str
) -> set[str]:
    """Resolve catalog component IDs owning a current or historical changed path."""
    if catalog is None:
        return set()
    components = catalog.get("components")
    if not isinstance(components, list):
        return set()
    result: set[str] = set()
    for component in components:
        if not isinstance(component, dict) or not isinstance(component.get("id"), str):
            continue
        patterns = [
            entry
            for field_name in ("sources", "tests")
            for entry in (component.get(field_name) if isinstance(component.get(field_name), list) else [])
            if isinstance(entry, str)
        ]
        if any(_glob_matches(path, pattern) for pattern in patterns):
            result.add(str(component["id"]))
    return result


def validate_changes_against_base(
    repository: Path,
    base: str,
    documents: Sequence[Document],
    by_id: dict[str, Document],
    current_catalog: dict[str, object] | None,
) -> tuple[list[Issue], set[str]]:
    """Reconcile changed files, journals, and immutable history against ``base``."""
    changed, issues = _git_changed_entries(repository, base)
    if issues:
        return issues, set()
    base_catalog_text = _git_file_at_base(
        repository, base, ARCHITECTURE_CATALOG.as_posix()
    )
    base_catalog: dict[str, object] | None = None
    if base_catalog_text is not None:
        try:
            loaded = json.loads(base_catalog_text)
            if isinstance(loaded, dict):
                base_catalog = loaded
        except json.JSONDecodeError:
            pass

    relevant_paths: set[str] = set()
    affected_components: set[str] = set()
    for path in changed:
        owners = _catalog_component_owners(current_catalog, path) | _catalog_component_owners(base_catalog, path)
        affected_components.update(owners)
        if (
            owners
            or _catalog_selects_path(current_catalog, path)
            or _catalog_selects_path(base_catalog, path)
            or path.startswith("docs/")
        ):
            relevant_paths.add(path)

    live_changes = {path for path, status_value in changed.items() if status_value != "D"}
    task_journal_changes = {
        path
        for path in live_changes
        if re.fullmatch(r"docs/journals/tasks/[^/]+\.md", path)
        and path != "docs/journals/tasks/README.md"
    }
    if relevant_paths and not task_journal_changes:
        issues.append(
            Issue(
                "task_journal_change_missing",
                "every relevant editable change requires a changed task journal",
            )
        )
    for component_id in sorted(affected_components):
        journal_path = f"docs/journals/components/{component_id}.md"
        if journal_path not in live_changes:
            issues.append(
                Issue(
                    "component_journal_change_missing",
                    f"changed component '{component_id}' requires an appended component journal entry",
                    journal_path,
                )
            )

    current_by_id = {
        document.metadata.doc_id: document
        for document in documents
        if document.metadata is not None
    }
    for base_path, base_text in _git_docs_at_base(repository, base).items():
        doc_id = _raw_frontmatter_scalar(base_text, "doc_id")
        doc_type = _raw_frontmatter_scalar(base_text, "doc_type")
        status_value = _raw_frontmatter_scalar(base_text, "status")
        if not doc_id or not doc_type:
            continue
        current_document = current_by_id.get(doc_id)
        protected_kind: str | None = None
        exact = False
        if doc_type in {"journal-task", "journal-component"}:
            protected_kind = "append-only journal history"
        elif doc_type == "decision" and status_value in {
            "accepted", "rejected", "deprecated", "superseded"
        }:
            protected_kind = f"{status_value} decision history"
        elif doc_type == "specification" and status_value == "approved":
            protected_kind = "approved specification immutable body"
            exact = True
        if protected_kind is None:
            continue
        if current_document is None:
            issues.append(
                Issue(
                    "protected_document_deleted",
                    f"{protected_kind} cannot be deleted or lose its stable doc_id",
                    base_path,
                )
            )
            continue
        old_body = _authored_history_body(base_text)
        new_body = _authored_history_body(current_document.text)
        if exact:
            valid = new_body == old_body
        elif doc_type in {"journal-task", "journal-component"}:
            valid = _sectioned_history_is_append_only(old_body, new_body)
        elif doc_type == "decision":
            valid = _decision_history_is_append_only(old_body, new_body)
        else:
            valid = new_body == old_body or new_body.startswith(old_body + "\n")
        if not valid:
            issues.append(
                Issue(
                    "protected_history_rewrite",
                    f"{protected_kind} rewrite detected; preserve existing content and append evidence",
                    current_document.relative_path,
                )
            )
    return issues, set(changed)


def audit_repository(repository: Path, base: str | None = None) -> tuple[list[Issue], dict[str, object]]:
    """Run the complete v2 structural, graph, link, catalog, and drift audit."""
    documents, issues = load_documents(repository)
    graph_issues, by_id, aliases = validate_document_graph(documents)
    issues.extend(graph_issues)
    issues.extend(validate_canonical_structure(repository, by_id))
    issues.extend(validate_internal_links(repository, documents, by_id, aliases))
    issues.extend(lint_component_sections(documents))
    catalog_issues, catalog, owners = validate_architecture_catalog(repository, by_id, aliases)
    issues.extend(catalog_issues)
    issues.extend(generated_drift(repository, documents, by_id, aliases))
    changed_paths: set[str] = set()
    if base:
        change_issues, changed_paths = validate_changes_against_base(
            repository, base, documents, by_id, catalog
        )
        issues.extend(change_issues)
        for changed_path in sorted(changed_paths):
            if (
                _catalog_selects_path(catalog, changed_path)
                and not _catalog_component_owners(catalog, changed_path)
            ):
                issues.append(
                    Issue(
                        "changed_source_unowned",
                        f"changed inventory source has no owner: '{changed_path}'",
                        changed_path,
                    )
                )
    issues.sort(key=lambda item: (item.path or "", item.line or 0, item.code, item.message))
    errors = sum(issue.severity == "error" for issue in issues)
    warnings = sum(issue.severity == "warning" for issue in issues)
    summary: dict[str, object] = {
        "documents": len([document for document in documents if document.metadata is not None]),
        "errors": errors,
        "warnings": warnings,
        "owned_sources": len(
            [
                path
                for path in owners
                if not (
                    ".test." in PurePosixPath(path).name.lower()
                    or ".spec." in PurePosixPath(path).name.lower()
                    or PurePosixPath(path).name.lower().startswith("test_")
                    or re.search(r"_test\.[^.]+$", PurePosixPath(path).name.lower())
                    or bool(
                        {part.lower() for part in PurePosixPath(path).parts}
                        & {"test", "tests", "__tests__", "spec", "specs"}
                    )
                )
            ]
        ),
        "accounted_files": len(owners),
        "changed_paths": len(changed_paths),
        "semantic_accuracy": "not-machine-verifiable",
    }
    return issues, summary


def _render_front_matter(metadata: DocumentMetadata) -> str:
    """Render canonical v2 YAML front matter without a YAML dependency."""
    lines = [
        "---",
        f"doc_id: {metadata.doc_id}",
        f"doc_type: {metadata.doc_type}",
        f"title: {metadata.title}",
        f"status: {metadata.status}",
    ]
    if metadata.parent_id is not None:
        lines.append(f"parent_id: {metadata.parent_id}")
    if metadata.profile is not None:
        lines.append(f"profile: {metadata.profile}")
    if metadata.redirect_to is not None:
        lines.append(f"redirect_to: {metadata.redirect_to}")
    if metadata.relations:
        lines.append("relations:")
        for relation in metadata.relations:
            lines.extend(
                [
                    f"  - type: {relation.relation_type}",
                    f"    target_id: {relation.target_id}",
                ]
            )
            if relation.anchor:
                lines.append(f"    anchor: {relation.anchor}")
    else:
        lines.append("relations: []")
    return "\n".join((*lines, "---", ""))


def _bootstrap_document(
    doc_id: str,
    doc_type: str,
    parent_id: str | None,
    title: str,
    path: str,
) -> str:
    """Create a conservative structural page without inventing components."""
    metadata = DocumentMetadata(doc_id, doc_type, title, "active", parent_id, ())
    section_headings: dict[str, tuple[str, ...]] = {
        "docs/architecture/README.md": (
            "Scope",
            "System summary",
            "Areas",
            "Runtime boundaries",
            "Cross-cutting concerns",
            "Coverage and exclusions",
            "Maintenance",
        ),
        "docs/architecture/system/context.md": (
            "Purpose",
            "External actors",
            "Trust boundaries",
            "System interactions",
            "Data ownership",
            "Failure boundaries",
            "Evidence",
        ),
        "docs/architecture/system/containers.md": (
            "Runtime containers",
            "Responsibilities",
            "Communication",
            "Data stores",
            "Startup and shutdown",
            "Deployment mapping",
            "Failure and recovery",
        ),
    }
    lines = [_render_front_matter(metadata), f"# {title}", ""]
    headings = section_headings.get(path, ())
    for heading in headings:
        lines.extend(
            [
                f"## {heading}",
                "",
                "No repository-specific records have been authored for this section.",
                "",
            ]
        )
    if not headings:
        lines.extend(
            [
                "This structural index is populated from document graph metadata.",
                "",
            ]
        )
    lines.extend(["## Related documentation", ""])
    return "\n".join(lines).rstrip() + "\n"


def _replace_managed_text_block(
    existing: str,
    start_marker: str,
    end_marker: str,
    block: str,
) -> str:
    """Replace or append one marker-delimited text block idempotently."""
    pattern = re.compile(
        rf"\n?{re.escape(start_marker)}.*?{re.escape(end_marker)}\n?",
        re.DOTALL,
    )
    if pattern.search(existing):
        return pattern.sub("\n" + block.rstrip() + "\n", existing).lstrip("\n")
    return existing.rstrip() + ("\n\n" if existing.strip() else "") + block.rstrip() + "\n"


def _bootstrap_payloads() -> dict[str, str]:
    """Return deterministic repo-local policy, wrappers, and CI integration."""
    policy_block = "\n".join(
        [
            POLICY_START,
            "## Documentation guard",
            "",
            "For every editable task, maintain the v2 document graph and architecture ownership catalog.",
            "Use `$architecture-docs-keeper` for the documentation workflow.",
            "Run `scripts/docs-guard .` before completion.",
            POLICY_END,
        ]
    )
    lefthook = "\n".join(
        [
            LEFTHOOK_START,
            "pre-commit:",
            "  commands:",
            "    docs-guard:",
            "      run: python3 .codex/scripts/docs_guard.py links . --internal && python3 .codex/scripts/docs_guard.py generate --check .",
            "pre-push:",
            "  commands:",
            "    docs-guard:",
            "      run: scripts/docs-guard .",
            LEFTHOOK_END,
            "",
        ]
    )
    wrapper = """#!/bin/sh
set -eu
repository=${1:-.}
shift || true
root=$(git -C "$repository" rev-parse --show-toplevel)
guard="$root/.codex/scripts/docs_guard.py"
base=${DOCS_GUARD_BASE:-}

if [ -z "$base" ]; then
  upstream=$(git -C "$root" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)
  if [ -n "$upstream" ]; then
    base=$(git -C "$root" merge-base HEAD "$upstream" 2>/dev/null || true)
  fi
fi

if [ -z "$base" ]; then
  for candidate in origin/dev origin/main origin/master dev main master; do
    if git -C "$root" rev-parse --verify "$candidate^{commit}" >/dev/null 2>&1; then
      base=$(git -C "$root" merge-base HEAD "$candidate" 2>/dev/null || true)
      [ -n "$base" ] && break
    fi
  done
fi

if [ -z "$base" ]; then
  base=$(git -C "$root" hash-object -t tree /dev/null)
fi

python3 "$guard" generate "$root" --check
exec python3 "$guard" audit "$root" --base "$base" --format human "$@"
"""
    workflow = """name: docs-guard

on:
  pull_request:
  push:

jobs:
  docs-guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - name: Run available documentation contract tests
        run: |
          if [ -d .agents/skills/architecture-docs-keeper/tests ]; then
            PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .agents/skills/architecture-docs-keeper/tests -v
          fi
          if [ -f tests/test_repository_contract.py ]; then
            PYTHONDONTWRITEBYTECODE=1 python3 tests/test_repository_contract.py -v
          fi
      - name: Check internal documentation links
        run: python3 .codex/scripts/docs_guard.py links . --internal
      - name: Check generated documentation
        run: python3 .codex/scripts/docs_guard.py generate --check .
      - name: Audit complete documentation
        run: python3 .codex/scripts/docs_guard.py audit . --format human
      - name: Audit documentation change
        env:
          PR_BASE: ${{ github.event.pull_request.base.sha }}
          PUSH_BASE: ${{ github.event.before }}
          DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}
        run: |
          base="${PR_BASE:-$PUSH_BASE}"
          if [ -z "$base" ] || printf '%s' "$base" | grep -Eq '^0+$' || ! git cat-file -e "$base^{commit}" 2>/dev/null; then
            base=""
            if [ -n "$DEFAULT_BRANCH" ] && git rev-parse --verify "origin/$DEFAULT_BRANCH^{commit}" >/dev/null 2>&1; then
              base=$(git merge-base HEAD "origin/$DEFAULT_BRANCH" 2>/dev/null || true)
            fi
          fi
          if [ -z "$base" ]; then
            base=$(git hash-object -t tree /dev/null)
          fi
          python3 .codex/scripts/docs_guard.py audit . --base "$base" --format human
"""
    project_hooks = """{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \\"$(git rev-parse --show-toplevel)/.agents/skills/architecture-docs-keeper/scripts/docs_hook.py\\"",
            "commandWindows": "for /f \\"delims=\\" %i in ('git rev-parse --show-toplevel') do py -3 \\"%i\\\\.agents\\\\skills\\\\architecture-docs-keeper\\\\scripts\\\\docs_hook.py\\"",
            "timeout": 30,
            "statusMessage": "Loading project documentation policy"
          }
        ]
      }
    ],
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \\"$(git rev-parse --show-toplevel)/.agents/skills/architecture-docs-keeper/scripts/docs_hook.py\\"",
            "commandWindows": "for /f \\"delims=\\" %i in ('git rev-parse --show-toplevel') do py -3 \\"%i\\\\.agents\\\\skills\\\\architecture-docs-keeper\\\\scripts\\\\docs_hook.py\\"",
            "timeout": 30,
            "statusMessage": "Loading project documentation policy"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \\"$(git rev-parse --show-toplevel)/.agents/skills/architecture-docs-keeper/scripts/docs_hook.py\\"",
            "commandWindows": "for /f \\"delims=\\" %i in ('git rev-parse --show-toplevel') do py -3 \\"%i\\\\.agents\\\\skills\\\\architecture-docs-keeper\\\\scripts\\\\docs_hook.py\\"",
            "timeout": 60,
            "statusMessage": "Recording the documentation baseline"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \\"$(git rev-parse --show-toplevel)/.agents/skills/architecture-docs-keeper/scripts/docs_hook.py\\"",
            "commandWindows": "for /f \\"delims=\\" %i in ('git rev-parse --show-toplevel') do py -3 \\"%i\\\\.agents\\\\skills\\\\architecture-docs-keeper\\\\scripts\\\\docs_hook.py\\"",
            "timeout": 300,
            "statusMessage": "Verifying project documentation"
          }
        ]
      }
    ]
  }
}
"""
    return {
        "AGENTS.md": policy_block,
        "lefthook.yml": lefthook,
        "scripts/docs-guard": wrapper,
        ".github/workflows/docs-guard.yml": workflow,
        ".codex/hooks.json": project_hooks,
    }


def _merge_lefthook(existing: str) -> str:
    """Add one command to the small Lefthook layouts that can be merged safely."""
    lines = existing.splitlines()
    if any("\t" in line for line in lines):
        raise ValueError("lefthook YAML tab indentation is unsafe; refusing layout")
    if any(
        re.match(r"^\s*docs-guard:\s*$", line)
        for line in lines
    ) and not any(line.strip() == LEFTHOOK_START for line in lines):
        raise ValueError("unmanaged lefthook docs-guard command collision; refusing overwrite")
    command_body = [
        LEFTHOOK_START,
        "docs-guard:",
        "  run: scripts/docs-guard .",
        LEFTHOOK_END,
    ]
    start_indexes = [
        index for index, line in enumerate(lines) if line.strip() == LEFTHOOK_START
    ]
    end_indexes = [
        index for index, line in enumerate(lines) if line.strip() == LEFTHOOK_END
    ]
    if bool(start_indexes) != bool(end_indexes) or len(start_indexes) > 1 or len(end_indexes) > 1:
        raise ValueError("lefthook managed markers are unsafe; refusing layout")
    if len(start_indexes) == 1 and len(end_indexes) == 1 and start_indexes[0] < end_indexes[0]:
        start, end = start_indexes[0], end_indexes[0]
        indentation = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
        contains_pre_push = any(
            line.strip() == "pre-push:" for line in lines[start + 1 : end]
        )
        if contains_pre_push:
            replacement = [
                indentation + line
                for line in _bootstrap_payloads()["lefthook.yml"].splitlines()
            ]
        else:
            replacement = [indentation + line for line in command_body]
        return "\n".join((*lines[:start], *replacement, *lines[end + 1 :])).rstrip() + "\n"

    pre_push_candidates = [
        index for index, line in enumerate(lines) if re.match(r"^pre-push:\s*$", line)
    ]
    if len(pre_push_candidates) > 1 or any(
        re.match(r"^\s*pre-push\s*:", line) and not re.match(r"^pre-push:\s*$", line)
        for line in lines
    ):
        raise ValueError("lefthook pre-push indentation/layout is unsafe; refusing merge")
    pre_push = pre_push_candidates[0] if pre_push_candidates else None
    if pre_push is None:
        has_pre_commit = any(
            re.match(r"^pre-commit:\s*$", line) for line in lines
        )
        if has_pre_commit:
            block = "\n".join(
                [
                    "pre-push:",
                    "  commands:",
                    *["    " + line for line in command_body],
                ]
            )
        else:
            block = _bootstrap_payloads()["lefthook.yml"]
        return (
            existing.rstrip()
            + ("\n\n" if existing.strip() else "")
            + block.rstrip()
            + "\n"
        )
    section_end = len(lines)
    for index in range(pre_push + 1, len(lines)):
        if lines[index].strip() and not lines[index].startswith((" ", "\t", "#")):
            section_end = index
            break
    commands = next(
        (
            index
            for index in range(pre_push + 1, section_end)
            if re.match(r"^  commands:\s*$", lines[index])
        ),
        None,
    )
    if commands is None:
        non_comment_content = [
            line for line in lines[pre_push + 1 : section_end]
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if non_comment_content:
            raise ValueError("lefthook pre-push layout is unsupported; refusing unsafe merge")
        insertion = ["  commands:", *["    " + line for line in command_body]]
        lines[pre_push + 1 : pre_push + 1] = insertion
    else:
        command_end = section_end
        for index in range(commands + 1, section_end):
            if lines[index].strip() and len(lines[index]) - len(lines[index].lstrip()) <= 2:
                command_end = index
                break
        lines[command_end:command_end] = ["    " + line for line in command_body]
    return "\n".join(lines).rstrip() + "\n"


def bootstrap_repository(
    repository: Path,
    apply: bool,
    *,
    generate: bool = True,
    allow_existing_docs: bool = False,
) -> tuple[list[Issue], list[PlannedChange]]:
    """Plan or install the deterministic repo-local documentation harness.

    Bootstrap creates structural indexes and an empty authored catalog, but no
    component record or component prose.  The empty inventory intentionally does
    not pass a completion audit until an agent derives it from repository evidence.
    """
    issues: list[Issue] = []
    actions: list[PlannedChange] = []
    if not repository.is_dir():
        return [Issue("repository_missing", f"repository does not exist: {repository}")], []

    desired_files: dict[str, str] = {}
    for path, doc_id, doc_type, parent_id, title in CANONICAL_DOCUMENTS:
        desired_files[path] = _bootstrap_document(
            doc_id, doc_type, parent_id, title, path
        )
    desired_files[ARCHITECTURE_CATALOG.as_posix()] = json.dumps(
        {
            "areas": [],
            "components": [],
            "inventory": {"exclude": [], "include": []},
            "relationships": [],
            "schema_version": SCHEMA_VERSION,
        },
        indent=2,
        sort_keys=True,
    ) + "\n"
    desired_files[".codex/scripts/docs_guard.py"] = Path(__file__).read_text(
        encoding="utf-8"
    )

    payloads = _bootstrap_payloads()
    agents_path = repository / "AGENTS.md"
    if agents_path.is_symlink():
        issues.append(Issue("bootstrap_collision", "refusing to overwrite symlinked AGENTS.md", "AGENTS.md"))
        existing_agents = ""
    else:
        existing_agents = agents_path.read_text(encoding="utf-8") if agents_path.is_file() else ""
    desired_files["AGENTS.md"] = _replace_managed_text_block(
        existing_agents,
        POLICY_START,
        POLICY_END,
        payloads.pop("AGENTS.md"),
    )
    lefthook_path = repository / "lefthook.yml"
    lefthook_payload = payloads.pop("lefthook.yml")
    if lefthook_path.is_symlink():
        issues.append(Issue("bootstrap_lefthook_layout", "lefthook symlink is unsafe; refusing layout", "lefthook.yml"))
    elif lefthook_path.is_file():
        existing_lefthook = lefthook_path.read_text(encoding="utf-8")
        try:
            desired_files["lefthook.yml"] = _merge_lefthook(existing_lefthook)
        except ValueError as error:
            issues.append(Issue("bootstrap_lefthook_layout", str(error), "lefthook.yml"))
    else:
        desired_files["lefthook.yml"] = lefthook_payload
    desired_files.update(payloads)

    required_directories = {
        "docs/architecture/system/deployments",
        "docs/architecture/areas",
        "docs/architecture/flows",
        "docs/architecture/concepts",
        "docs/plans",
        "docs/specifications",
        "docs/journals/tasks",
        "docs/journals/components",
        "docs/decisions",
        "docs/operations",
        "docs/development",
    }
    docs_root = repository / "docs"
    if docs_root.is_symlink():
        issues.append(
            Issue(
                "bootstrap_collision",
                "refusing symlinked docs root",
                "docs",
            )
        )
        existing_docs = True
    else:
        existing_docs = docs_root.is_dir() and any(docs_root.rglob("*"))
    canonical_root = repository / "docs/README.md"
    v2_docs = (
        canonical_root.is_file()
        and not canonical_root.is_symlink()
        and re.search(r"(?m)^doc_id:\s*docs\.root\s*$", canonical_root.read_text(encoding="utf-8"))
        is not None
    )
    if existing_docs and not allow_existing_docs and not v2_docs:
        issues.append(
            Issue(
                "bootstrap_docs_collision",
                "existing documentation is unmanaged; refusing bootstrap and requiring migration",
                "docs",
            )
        )

    for directory in sorted(required_directories):
        path = repository / directory
        if path.exists() and (path.is_symlink() or not path.is_dir()):
            issues.append(
                Issue(
                    "bootstrap_collision",
                    f"refusing canonical directory collision at {directory}",
                    directory,
                )
            )

    protected_tooling = {
        ".codex/hooks.json",
        ".codex/scripts/docs_guard.py",
        "scripts/docs-guard",
        ".github/workflows/docs-guard.yml",
    }
    for relative_path, desired_text in sorted(desired_files.items()):
        path = repository / relative_path
        current_parent = path.parent
        while current_parent != repository:
            if current_parent.exists() and (
                current_parent.is_symlink() or not current_parent.is_dir()
            ):
                issues.append(
                    Issue(
                        "bootstrap_collision",
                        f"refusing unsafe parent collision for {relative_path}",
                        _relative(current_parent, repository),
                    )
                )
                break
            current_parent = current_parent.parent
        if path.is_symlink():
            issues.append(
                Issue(
                    "bootstrap_collision",
                    f"refusing to overwrite symlink at {relative_path}",
                    relative_path,
                )
            )
            continue
        if path.exists() and not path.is_file():
            issues.append(
                Issue(
                    "bootstrap_collision",
                    f"refusing non-file collision at {relative_path}",
                    relative_path,
                )
            )
            continue
        if path.is_file() and relative_path in protected_tooling:
            existing_text = path.read_text(encoding="utf-8")
            if existing_text != desired_text:
                issues.append(
                    Issue(
                        "bootstrap_tooling_collision",
                        f"unmanaged tooling collision; refusing to overwrite {relative_path}",
                        relative_path,
                    )
                )

    if any(issue.severity == "error" for issue in issues):
        return issues, []

    for directory in sorted(required_directories):
        if not (repository / directory).is_dir():
            actions.append(PlannedChange("create-directory", directory, "canonical v2 tree"))

    for relative_path, desired_text in sorted(desired_files.items()):
        path = repository / relative_path
        existing_text = path.read_text(encoding="utf-8") if path.is_file() else None
        if existing_text is not None and relative_path.startswith("docs/"):
            continue
        if existing_text == desired_text:
            continue
        action = "create" if existing_text is None else "update"
        actions.append(PlannedChange(action, relative_path, "docs-guard bootstrap"))
    if apply:
        for directory in sorted(required_directories):
            (repository / directory).mkdir(parents=True, exist_ok=True)
        for relative_path, desired_text in sorted(desired_files.items()):
            path = repository / relative_path
            existing_text = path.read_text(encoding="utf-8") if path.is_file() else None
            if existing_text is not None and relative_path.startswith("docs/"):
                continue
            if existing_text == desired_text:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(desired_text, encoding="utf-8")
            if relative_path in {"scripts/docs-guard", ".codex/scripts/docs_guard.py"}:
                path.chmod(path.stat().st_mode | 0o111)

    if apply and generate:
        generation_issues, generated = generate_repository(repository, write=True)
        issues.extend(generation_issues)
        actions.extend(
            PlannedChange("generate", path, "document graph projection")
            for path in generated
        )
    return issues, actions


def _legacy_front_matter(text: str) -> tuple[dict[str, object], str]:
    """Parse schema-v1 scalar fields and ``sources`` while preserving its body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return {}, text
    values: dict[str, object] = {}
    sources: list[str] = []
    active_sources = False
    for line in lines[1:end]:
        stripped = line.strip()
        if stripped.startswith("- ") and active_sources:
            sources.append(_strip_quotes(stripped[2:]))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = _strip_quotes(value)
        active_sources = key == "sources" and not value
        if value:
            values[key] = value
    if sources:
        values["sources"] = sources
    body = "\n".join(lines[end + 1 :])
    if text.endswith("\n"):
        body += "\n"
    return values, body


def _legacy_front_matter_archive(text: str) -> str:
    """Preserve the complete legacy metadata block as authored migration evidence."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return ""
    metadata = "\n".join(lines[1:end]).rstrip()
    if not metadata:
        return ""
    return (
        "\n\n## Migrated legacy front matter\n\n"
        "```yaml\n"
        + metadata
        + "\n```\n"
    )


def _migration_profile(area: str) -> tuple[str, str]:
    """Return a conservative profile/kind for well-known legacy area names."""
    normalized = area.casefold()
    if normalized == "frontend":
        return "frontend-ui", "ui-component"
    if normalized in {"backend", "api"}:
        return "backend-api", "handler"
    if normalized in {"worker", "workers", "jobs"}:
        return "worker-job", "worker"
    if normalized in {"database", "data", "persistence"}:
        return "data-persistence", "repository"
    if normalized in {"integrations", "integration"}:
        return "integration-adapter", "adapter"
    if normalized in {"infrastructure", "infra"}:
        return "infrastructure", "infrastructure"
    return "shared-library", "library"


def _legacy_component_id(value: str, filename: str) -> str:
    """Preserve a valid legacy component identity, falling back to its filename."""
    candidate = value.strip()
    if candidate.startswith("architecture.component."):
        candidate = candidate.removeprefix("architecture.component.")
    if COMPONENT_ID_PATTERN.fullmatch(candidate):
        return candidate
    fallback = re.sub(r"[^a-z0-9.-]+", "-", Path(filename).stem.lower()).strip(".-")
    return fallback or hashlib.sha256(filename.encode()).hexdigest()[:12]


def _redirect_text(
    redirect_id: str,
    title: str,
    target_id: str,
    parent_id: str,
) -> str:
    """Render a canonical redirect stub whose navigation is generated."""
    metadata = DocumentMetadata(
        redirect_id,
        "redirect",
        title,
        "active",
        parent_id,
        (Relation("redirects-to", target_id),),
        redirect_to=target_id,
    )
    return (
        _render_front_matter(metadata)
        + f"# {title}\n\n"
        + "This established legacy path redirects through document graph metadata.\n\n"
        + "## Related documentation\n"
    )


def _is_v2_document(path: Path, repository: Path) -> bool:
    """Return whether a Markdown page has successfully parsed v2 metadata."""
    return path.is_file() and parse_front_matter(path, repository).metadata is not None


def _rewrite_links_for_moves(
    text: str,
    original_document: Path,
    destination_document: Path,
    moves: dict[Path, Path],
    repository: Path,
) -> str:
    """Rebase visible Markdown links and retarget known migration moves."""
    rewritten = text
    for link in extract_markdown_links(text):
        parsed = urlsplit(link.target)
        if parsed.scheme or not parsed.path:
            continue
        decoded_path = unquote(parsed.path)
        if decoded_path.startswith("/"):
            old_target = (repository / decoded_path.lstrip("/")).resolve()
        else:
            old_target = (original_document.parent / decoded_path).resolve()
        new_target = moves.get(old_target, old_target)
        if original_document == destination_document and new_target == old_target:
            continue
        try:
            new_target.relative_to(repository.resolve())
        except ValueError:
            continue
        new_path = posixpath.relpath(
            new_target.as_posix(), destination_document.parent.resolve().as_posix()
        )
        suffix = ""
        if parsed.query:
            suffix += f"?{parsed.query}"
        if parsed.fragment:
            suffix += f"#{parsed.fragment}"
        replacement = new_path + suffix
        rewritten = rewritten.replace(f"({link.target})", f"({replacement})")
        rewritten = re.sub(
            rf"(?m)(^ {{0,3}}\[[^\]]+\]:\s*)<?{re.escape(link.target)}>?(?=\s|$)",
            lambda match: match.group(1) + replacement,
            rewritten,
        )
    return rewritten


def migrate_repository(
    repository: Path,
    apply: bool,
) -> tuple[list[Issue], list[PlannedChange]]:
    """Plan or migrate the schema-v1 area/component layout without data loss.

    The migrator handles the documentation system's v1 tree
    ``docs/architecture/<area>/components/*.md``.  It preserves body text,
    converts source ownership, leaves redirect stubs at established paths, and
    refuses to overwrite a conflicting canonical destination.
    """
    issues: list[Issue] = []
    actions: list[PlannedChange] = []
    moves: dict[Path, Path] = {}
    if not repository.is_dir():
        return [Issue("repository_missing", f"repository does not exist: {repository}")], []
    repository = repository.resolve()

    if apply:
        preflight_issues, preflight_actions = migrate_repository(repository, apply=False)
        if any(issue.severity == "error" for issue in preflight_issues):
            return preflight_issues, preflight_actions

    bootstrap_issues, bootstrap_actions = bootstrap_repository(
        repository, apply=apply, generate=False, allow_existing_docs=True
    )
    issues.extend(bootstrap_issues)
    actions.extend(bootstrap_actions)

    architecture_root = repository / ARCHITECTURE_DIR
    legacy_root = architecture_root / "README.md"
    if legacy_root.is_file() and not _is_v2_document(legacy_root, repository):
        legacy_text = legacy_root.read_text(encoding="utf-8")
        _, body = _legacy_front_matter(legacy_text)
        metadata = DocumentMetadata(
            "architecture.root",
            "architecture-root",
            "Architecture",
            "active",
            "docs.root",
            (),
        )
        converted = _render_front_matter(metadata) + body.lstrip() + _legacy_front_matter_archive(legacy_text)
        if "## Related documentation" not in converted:
            converted = converted.rstrip() + "\n\n## Related documentation\n"
        actions.append(
            PlannedChange("convert", ARCHITECTURE_DIR.joinpath("README.md").as_posix(), "schema-v1 architecture root")
        )
        if apply:
            legacy_root.write_text(converted, encoding="utf-8")

    canonical_names = {"system", "areas", "flows", "concepts"}
    legacy_areas = [
        path
        for path in sorted(architecture_root.iterdir(), key=lambda item: item.name)
        if path.is_dir() and path.name not in canonical_names and not path.name.startswith(".")
    ] if architecture_root.is_dir() else []

    catalog_path = repository / ARCHITECTURE_CATALOG
    catalog_payload, catalog_issues = _load_json_object(catalog_path, repository)
    if catalog_payload is None:
        catalog_payload = {
            "schema_version": SCHEMA_VERSION,
            "inventory": {"include": [], "exclude": []},
            "areas": [],
            "components": [],
            "relationships": [],
        }
    areas = catalog_payload.setdefault("areas", [])
    components = catalog_payload.setdefault("components", [])
    inventory = catalog_payload.setdefault("inventory", {"include": [], "exclude": []})
    assert isinstance(areas, list)
    assert isinstance(components, list)
    assert isinstance(inventory, dict)
    includes = inventory.setdefault("include", [])
    assert isinstance(includes, list)
    existing_area_ids = {
        area.get("id") for area in areas if isinstance(area, dict) and isinstance(area.get("id"), str)
    }
    existing_component_ids = {
        component.get("id")
        for component in components
        if isinstance(component, dict) and isinstance(component.get("id"), str)
    }

    for legacy_area in legacy_areas:
        area_id = re.sub(r"[^a-z0-9.-]+", "-", legacy_area.name.lower()).strip(".-")
        if not area_id:
            issues.append(Issue("migration_area_ambiguous", f"cannot derive area ID from {legacy_area.name}"))
            continue
        area_doc_id = f"architecture.area.{area_id}"
        destination_area = architecture_root / "areas" / area_id
        legacy_index = legacy_area / "README.md"
        destination_index = destination_area / "README.md"
        if legacy_index.is_file() and not _is_v2_document(legacy_index, repository):
            legacy_text = legacy_index.read_text(encoding="utf-8")
            _, body = _legacy_front_matter(legacy_text)
            area_metadata = DocumentMetadata(
                area_doc_id,
                "architecture-area",
                legacy_area.name.replace("-", " ").title(),
                "active",
                "architecture.areas.index",
                (),
            )
            converted = _render_front_matter(area_metadata) + body.lstrip() + _legacy_front_matter_archive(legacy_text)
            if "## Related documentation" not in converted:
                converted = converted.rstrip() + "\n\n## Related documentation\n"
            if destination_index.exists() and destination_index.read_text(encoding="utf-8") != converted:
                issues.append(
                    Issue(
                        "migration_destination_exists",
                        f"refusing to overwrite {destination_index.relative_to(repository).as_posix()}",
                    )
                )
            else:
                moves[legacy_index.resolve()] = destination_index.resolve()
                actions.extend(
                    [
                        PlannedChange("move", destination_index.relative_to(repository).as_posix(), f"preserve {legacy_index.relative_to(repository).as_posix()} content"),
                        PlannedChange("redirect", legacy_index.relative_to(repository).as_posix(), area_doc_id),
                    ]
                )
                if apply:
                    destination_index.parent.mkdir(parents=True, exist_ok=True)
                    destination_index.write_text(converted, encoding="utf-8")
                    legacy_index.write_text(
                        _redirect_text(
                            f"redirect.architecture.area.{area_id}",
                            f"{area_metadata.title} documentation moved",
                            area_doc_id,
                            "architecture.root",
                        ),
                        encoding="utf-8",
                    )
        if area_id not in existing_area_ids:
            areas.append({"id": area_id, "name": legacy_area.name.replace("-", " ").title(), "doc_id": area_doc_id})
            existing_area_ids.add(area_id)

        components_dir = legacy_area / "components"
        if not components_dir.is_dir():
            continue
        for legacy_component in sorted(components_dir.rglob("*.md"), key=lambda item: item.as_posix()):
            if _is_v2_document(legacy_component, repository):
                continue
            legacy_text = legacy_component.read_text(encoding="utf-8")
            legacy_values, body = _legacy_front_matter(legacy_text)
            component_id = _legacy_component_id(str(legacy_values.get("component_id", "")), legacy_component.name)
            doc_id = f"architecture.component.{component_id}"
            profile, kind = _migration_profile(area_id)
            status = str(legacy_values.get("status", "active"))
            if status not in DOC_TYPE_STATUSES["architecture-component"]:
                status = "active"
            sources = [
                str(source)
                for source in legacy_values.get("sources", [])
                if isinstance(source, str)
            ] if isinstance(legacy_values.get("sources", []), list) else []
            tests = [source for source in sources if re.search(r"(?:^|/)(?:tests?|__tests__)(?:/|$)|(?:\.test\.|\.spec\.|_test\.)", source, re.I)]
            sources = [source for source in sources if source not in tests]
            destination = destination_area / "components" / f"{component_id}.md"
            metadata = DocumentMetadata(
                doc_id,
                "architecture-component",
                component_id.replace(".", " ").replace("-", " ").title(),
                status,
                area_doc_id,
                (),
                profile=profile,
            )
            converted = _render_front_matter(metadata) + body.lstrip() + _legacy_front_matter_archive(legacy_text)
            if "## Related documentation" not in converted:
                converted = converted.rstrip() + "\n\n## Related documentation\n"
            if destination.exists() and destination.read_text(encoding="utf-8") != converted:
                issues.append(Issue("migration_destination_exists", f"refusing to overwrite {destination.relative_to(repository).as_posix()}"))
                continue
            actions.extend(
                [
                    PlannedChange("move", destination.relative_to(repository).as_posix(), f"preserve {legacy_component.relative_to(repository).as_posix()} content"),
                    PlannedChange("redirect", legacy_component.relative_to(repository).as_posix(), doc_id),
                ]
            )
            moves[legacy_component.resolve()] = destination.resolve()
            if apply:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(converted, encoding="utf-8")
                redirect_hash = hashlib.sha256(
                    legacy_component.relative_to(repository).as_posix().encode()
                ).hexdigest()[:12]
                legacy_component.write_text(
                    _redirect_text(
                        f"redirect.architecture.component.{redirect_hash}",
                        f"{metadata.title} documentation moved",
                        doc_id,
                        "architecture.root",
                    ),
                    encoding="utf-8",
                )
            if component_id not in existing_component_ids:
                components.append(
                    {
                        "id": component_id,
                        "name": metadata.title,
                        "kind": kind,
                        "profile": profile,
                        "area": area_id,
                        "doc_id": doc_id,
                        "status": status,
                        "sources": sources,
                        "tests": tests,
                    }
                )
                existing_component_ids.add(component_id)
                for owned_path in (*sources, *tests):
                    if owned_path not in includes:
                        includes.append(owned_path)

    def migrate_legacy_leaf(
        source: Path,
        destination: Path,
        metadata: DocumentMetadata,
        *,
        replace_bootstrap_placeholder: bool = False,
    ) -> None:
        """Preserve one legacy document and leave a graph-backed redirect."""
        if not source.is_file() or _is_v2_document(source, repository):
            return
        legacy_text = source.read_text(encoding="utf-8")
        _, body = _legacy_front_matter(legacy_text)
        converted = _render_front_matter(metadata) + body.lstrip() + _legacy_front_matter_archive(legacy_text)
        if "## Related documentation" not in converted:
            converted = converted.rstrip() + "\n\n## Related documentation\n"
        destination_is_bootstrap_placeholder = False
        if destination.exists() and replace_bootstrap_placeholder:
            destination_relative = destination.relative_to(repository).as_posix()
            canonical_record = next(
                (record for record in CANONICAL_DOCUMENTS if record[0] == destination_relative),
                None,
            )
            if canonical_record is not None:
                destination_is_bootstrap_placeholder = destination.read_text(encoding="utf-8") == _bootstrap_document(
                    canonical_record[1], canonical_record[2], canonical_record[3],
                    canonical_record[4], canonical_record[0]
                )
        if (
            destination.exists()
            and destination.read_text(encoding="utf-8") != converted
            and not destination_is_bootstrap_placeholder
        ):
            issues.append(
                Issue(
                    "migration_destination_exists",
                    f"refusing to overwrite {destination.relative_to(repository).as_posix()}",
                )
            )
            return
        moves[source.resolve()] = destination.resolve()
        actions.extend(
            [
                PlannedChange(
                    "move",
                    destination.relative_to(repository).as_posix(),
                    f"preserve {source.relative_to(repository).as_posix()} content",
                ),
                PlannedChange(
                    "redirect",
                    source.relative_to(repository).as_posix(),
                    metadata.doc_id,
                ),
            ]
        )
        if apply:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(converted, encoding="utf-8")
            redirect_hash = hashlib.sha256(
                source.relative_to(repository).as_posix().encode()
            ).hexdigest()[:12]
            source.write_text(
                _redirect_text(
                    f"redirect.legacy.{redirect_hash}",
                    f"{metadata.title} documentation moved",
                    metadata.doc_id,
                    "docs.root",
                ),
                encoding="utf-8",
            )

    legacy_plan_root = repository / "docs/superpowers/plans"
    if legacy_plan_root.is_dir():
        for source in sorted(legacy_plan_root.rglob("*.md"), key=lambda item: item.as_posix()):
            relative_stem = source.relative_to(legacy_plan_root).with_suffix("").as_posix()
            slug = re.sub(r"[^a-z0-9.-]+", "-", relative_stem.lower()).strip(".-")
            migrate_legacy_leaf(
                source,
                repository / "docs/plans" / f"{slug}.md",
                DocumentMetadata(
                    f"plan.{slug}",
                    "plan",
                    source.stem.replace("-", " ").title(),
                    "draft",
                    "plans.root",
                    (),
                ),
            )

    legacy_spec_root = repository / "docs/superpowers/specs"
    if legacy_spec_root.is_dir():
        for source in sorted(legacy_spec_root.rglob("*.md"), key=lambda item: item.as_posix()):
            relative_stem = source.relative_to(legacy_spec_root).with_suffix("").as_posix()
            slug = re.sub(r"[^a-z0-9.-]+", "-", relative_stem.lower()).strip(".-")
            migrate_legacy_leaf(
                source,
                repository / "docs/specifications" / f"{slug}.md",
                DocumentMetadata(
                    f"specification.{slug}",
                    "specification",
                    source.stem.replace("-", " ").title(),
                    "draft",
                    "specifications.root",
                    (),
                ),
            )

    legacy_components_root = repository / "docs/components"
    if legacy_components_root.is_dir():
        for source in sorted(
            legacy_components_root.glob("*/changelog.md"), key=lambda item: item.as_posix()
        ):
            component_id = _legacy_component_id(source.parent.name, source.parent.name)
            migrate_legacy_leaf(
                source,
                repository / "docs/journals/components" / f"{component_id}.md",
                DocumentMetadata(
                    f"journal.component.{component_id}",
                    "journal-component",
                    f"{component_id.replace('.', ' ').replace('-', ' ').title()} journal",
                    "active",
                    "journals.components.index",
                    (),
                ),
            )

    legacy_decisions = architecture_root / "decisions.md"
    migrate_legacy_leaf(
        legacy_decisions,
        repository / "docs/decisions/0001-legacy-decisions.md",
        DocumentMetadata(
            "decision.0001.legacy-decisions",
            "decision",
            "Legacy architecture decisions",
            "accepted",
            "decisions.root",
            (),
        ),
    )

    legacy_system_map = architecture_root / "system-map.md"
    migrate_legacy_leaf(
        legacy_system_map,
        architecture_root / "system/context.md",
        DocumentMetadata(
            "architecture.context.system",
            "architecture-context",
            "System context",
            "active",
            "architecture.system.index",
            (),
        ),
        replace_bootstrap_placeholder=True,
    )

    expected_catalog = json.dumps(catalog_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    current_catalog = catalog_path.read_text(encoding="utf-8") if catalog_path.is_file() else None
    if current_catalog != expected_catalog:
        actions.append(PlannedChange("update", ARCHITECTURE_CATALOG.as_posix(), "migrated ownership catalog"))
        if apply:
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text(expected_catalog, encoding="utf-8")

    if not apply and moves:
        for source, destination in sorted(
            moves.items(), key=lambda item: item[0].as_posix()
        ):
            if not source.is_file():
                continue
            original_text = source.read_text(encoding="utf-8")
            _, body = _legacy_front_matter(original_text)
            if _rewrite_links_for_moves(
                body,
                source,
                destination,
                moves,
                repository,
            ) != body:
                actions.append(
                    PlannedChange(
                        "rewrite-links",
                        destination.relative_to(repository).as_posix(),
                        "retarget migrated documents",
                    )
                )

    if apply and moves:
        original_by_destination = {destination: source for source, destination in moves.items()}
        for markdown_path in sorted((repository / "docs").rglob("*.md"), key=lambda item: item.as_posix()):
            original_path = original_by_destination.get(markdown_path.resolve(), markdown_path.resolve())
            current_text = markdown_path.read_text(encoding="utf-8")
            rewritten = _rewrite_links_for_moves(
                current_text,
                original_path,
                markdown_path.resolve(),
                moves,
                repository,
            )
            if rewritten != current_text:
                markdown_path.write_text(rewritten, encoding="utf-8")
                actions.append(
                    PlannedChange(
                        "rewrite-links",
                        markdown_path.relative_to(repository).as_posix(),
                        "retarget migrated documents",
                    )
                )

    if apply and not any(issue.severity == "error" for issue in issues):
        generation_issues, generated = generate_repository(repository, write=True)
        issues.extend(generation_issues)
        actions.extend(
            PlannedChange("generate", path, "document graph projection")
            for path in generated
        )
    return issues, actions


def _print_issues(issues: Sequence[Issue]) -> None:
    """Print stable human-readable diagnostics to stderr."""
    for issue in issues:
        location = issue.path or "docs-guard"
        if issue.line is not None:
            location += f":{issue.line}"
        print(
            f"{issue.severity}: {location}: [{issue.code}] {issue.message}",
            file=sys.stderr,
        )


def _build_parser() -> argparse.ArgumentParser:
    """Create the public CLI parser."""
    parser = argparse.ArgumentParser(
        description="Bootstrap, migrate, generate, and audit v2 repository documentation."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap", help="install a repo-local v2 harness")
    bootstrap_mode = bootstrap.add_mutually_exclusive_group(required=True)
    bootstrap_mode.add_argument("--dry-run", action="store_true")
    bootstrap_mode.add_argument("--apply", action="store_true")
    bootstrap.add_argument("repository", nargs="?", default=".")

    migrate = subparsers.add_parser("migrate", help="migrate schema-v1 architecture maps")
    migrate_mode = migrate.add_mutually_exclusive_group(required=True)
    migrate_mode.add_argument("--plan", action="store_true")
    migrate_mode.add_argument("--apply", action="store_true")
    migrate.add_argument("repository", nargs="?", default=".")

    generate = subparsers.add_parser("generate", help="manage generated graph projections")
    generate_mode = generate.add_mutually_exclusive_group(required=True)
    generate_mode.add_argument("--check", action="store_true")
    generate_mode.add_argument("--write", action="store_true")
    generate.add_argument("repository", nargs="?", default=".")

    audit = subparsers.add_parser("audit", help="run the complete documentation audit")
    audit.add_argument("repository", nargs="?", default=".")
    audit.add_argument("--base")
    audit.add_argument("--format", choices=("human", "json"), default="human")

    links = subparsers.add_parser("links", help="validate internal Markdown links")
    links.add_argument("repository", nargs="?", default=".")
    links.add_argument("--internal", action="store_true", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the docs-guard CLI and return a conventional process status."""
    args = _build_parser().parse_args(argv)
    repository = Path(args.repository).expanduser().resolve()
    if not repository.is_dir():
        _print_issues(
            [Issue("repository_missing", f"repository does not exist: {repository}")]
        )
        return 2

    if args.command == "bootstrap":
        issues, actions = bootstrap_repository(repository, apply=args.apply)
        if args.apply and not any(issue.severity == "error" for issue in issues):
            post_issues, _ = audit_repository(repository)
            issues.extend(post_issues)
        for action in actions:
            print(action.render())
        _print_issues(issues)
        return 1 if any(issue.severity == "error" for issue in issues) else 0

    if args.command == "migrate":
        issues, actions = migrate_repository(repository, apply=args.apply)
        if args.apply and not any(issue.severity == "error" for issue in issues):
            post_issues, _ = audit_repository(repository)
            issues.extend(post_issues)
        for action in actions:
            print(action.render())
        _print_issues(issues)
        return 1 if any(issue.severity == "error" for issue in issues) else 0

    if args.command == "generate":
        issues, changed = generate_repository(repository, write=args.write)
        if args.write and not any(issue.severity == "error" for issue in issues):
            post_issues, _ = audit_repository(repository)
            issues.extend(post_issues)
        if args.write:
            for path in changed:
                print(f"generated: {path}")
        elif not issues:
            print("Generated documentation is current.")
        _print_issues(issues)
        return 1 if issues else 0

    if args.command == "links":
        documents, issues = load_documents(repository)
        graph_issues, by_id, aliases = validate_document_graph(documents)
        issues.extend(graph_issues)
        issues.extend(validate_internal_links(repository, documents, by_id, aliases))
        issues.sort(key=lambda item: (item.path or "", item.line or 0, item.code))
        if not issues:
            print(f"Internal documentation links passed for {len(documents)} document(s).")
        _print_issues(issues)
        return 1 if any(issue.severity == "error" for issue in issues) else 0

    issues, summary = audit_repository(repository, base=args.base)
    payload = {
        "issues": [issue.as_dict() for issue in issues],
        "ok": not any(issue.severity == "error" for issue in issues),
        "summary": summary,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        if payload["ok"]:
            print(
                "Documentation audit passed: "
                f"{summary['documents']} document(s), "
                f"{summary['owned_sources']} owned source(s)."
            )
        _print_issues(issues)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
