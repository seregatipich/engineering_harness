---
name: architecture-blueprint-generator
description: Analyze a codebase and generate a comprehensive architecture blueprint document that captures its technology stack, architectural patterns, component boundaries, cross-cutting concerns, and extension points. Use when the user asks to document the architecture, produce an architecture overview or blueprint, map the system design, or onboard onto an unfamiliar codebase. Triggers include "generate an architecture blueprint", "document the architecture", "map the system design", "how is this codebase structured".
argument-hint: "[path-or-focus] (optional; defaults to whole repo, auto-detect stack)"
---

# Architecture Blueprint Generator

Produce a single `Project_Architecture_Blueprint.md` that documents the architecture **as it is actually implemented**, so it can serve as the reference for maintaining consistency and guiding new work.

`$ARGUMENTS` optionally narrows scope (a subdirectory or package to analyze) or names a focus (e.g. `data layer`, `auth`). With no arguments, analyze the whole repository. If the user names an output path, write there instead of the default.

## Ground rule

Document only what the code shows. Cite real files, paths, and symbols. When a section's evidence is absent (no tests, no deployment config, etc.), say so explicitly — never fill gaps with generic patterns the codebase does not use. Diagrams must reflect actual dependencies, not textbook versions of a pattern.

## 1. Detect stack and architecture

Infer, don't assume:

- **Stack**: read manifests and configs (`package.json`, `pyproject.toml`, `go.mod`, `*.csproj`, `pom.xml`, `Cargo.toml`, lockfiles, Dockerfiles, CI configs), then confirm against actual imports and framework usage.
- **Architecture pattern(s)**: infer from folder organization, dependency direction, module boundaries, and how components communicate (e.g. layered, hexagonal, MVC/MVVM, microservices, event-driven, monolith). Note hybrids and deviations from the canonical form.

For anything beyond a handful of files, dispatch **Explore subagents** to read in isolated context and return only findings — one per subsystem where useful. Run independent explorations in parallel.

## 2. Analyze these dimensions

Cover each that applies; skip and note the ones the codebase doesn't have:

- **Overview** — guiding principles, boundaries and how they're enforced, any hybrid adaptations.
- **Components** — for each major component: responsibility, internal structure and key abstractions, how it communicates (interfaces, DI, events), and how it's extended.
- **Layers and dependencies** — layer map, dependency rules, abstraction seams, and any circular deps or layer violations.
- **Data architecture** — domain model, entity relationships, data-access patterns (repositories, mappers), mapping/transformation, caching, and validation.
- **Cross-cutting concerns** — auth/authz, error handling and resilience, logging/observability, configuration and secrets, feature flags.
- **Service communication** — protocols and formats, sync vs async, API versioning, service discovery, resilience patterns.
- **Stack-specific patterns** — the idioms of the detected framework(s) (e.g. middleware pipeline, DI container setup, state management, ORM usage, async model).
- **Testing** — test levels present, test-double/mocking approach, fixtures/data strategy, tooling.
- **Deployment** — topology from config, environment differences, containerization/orchestration, cloud integrations.
- **Extension and evolution** — where and how to add features safely, integration/adapter seams, deprecation and migration patterns.

## 3. Write the blueprint

Create `Project_Architecture_Blueprint.md` (or the user's path) with this outline, keeping each section grounded in Step 2's findings:

1. **Overview** — approach, principles, boundaries.
2. **Architecture diagrams** — Mermaid diagrams at multiple levels: a high-level subsystem view, a component/dependency view, and a key data-flow or request sequence. Keep them faithful to the code.
3. **Components** — one subsection each, per Step 2.
4. **Layers and dependencies**.
5. **Data architecture**.
6. **Cross-cutting concerns**.
7. **Service communication** (omit if not applicable).
8. **Stack-specific patterns**.
9. **Testing architecture**.
10. **Deployment architecture**.
11. **Extension guide** — starting points by feature type, component-creation sequence, and common pitfalls / violations to avoid.
12. **Decision records** — notable architectural decisions evident in the code: context, forces, and consequences. Infer only what the code and its history support.

Illustrate patterns with short, real code excerpts pulled from the repo (interface/impl separation, a representative service or handler, an extension point). Keep excerpts focused on the architectural point.

End the document with the date it was generated and a one-line note to regenerate it when the architecture changes.

## Guardrails

- Never invent components, layers, or patterns the codebase doesn't contain.
- Prefer excerpts and file references over prose descriptions of code.
- If scope is large, state which parts you analyzed deeply versus sampled.
