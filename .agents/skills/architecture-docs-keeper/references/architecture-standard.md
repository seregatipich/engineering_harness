# Repository documentation system standard

This document defines schema version 2. It is normative for every repository managed by the skill.

## Index

- [Scope](#scope)
- [Exact tree](#exact-tree)
- [Identifiers and paths](#identifiers-and-paths)
- [Markdown front matter](#markdown-front-matter)
- [Document types and statuses](#document-types-and-statuses)
- [Relation graph](#relation-graph)
- [Generated links and backlinks](#generated-links-and-backlinks)
- [Architecture catalog](#architecture-catalog)
- [Exhaustive coverage](#exhaustive-coverage)
- [Architecture document requirements](#architecture-document-requirements)
- [Plans](#plans)
- [Specifications](#specifications)
- [Journals](#journals)
- [Decisions](#decisions)
- [Operations and development](#operations-and-development)
- [Bootstrap and migration](#bootstrap-and-migration)
- [Change reconciliation](#change-reconciliation)
- [Content integrity](#content-integrity)
- [Completion gate](#completion-gate)

## Scope

The documentation system records:

- the complete architecture and ownership of relevant source, test, configuration, schema, deployment, and infrastructure files;
- implementation plans and their outcomes;
- approved and draft behavioral specifications;
- append-only task and component history;
- durable engineering decisions;
- operational and development guidance;
- a machine-readable graph of every Markdown document, including generated links and backlinks.

Repository-specific rules may add requirements. They must not weaken this standard.

## Exact tree

Use this tree. Omit only operations or development leaf documents when the repository has no corresponding material. Keep every index and catalog shown.

~~~text
docs/
├── README.md
├── catalog.json
├── architecture/
│   ├── README.md
│   ├── catalog.json
│   ├── system/
│   │   ├── README.md
│   │   ├── context.md
│   │   ├── containers.md
│   │   └── deployments/
│   │       ├── README.md
│   │       └── <deployment-id>.md
│   ├── areas/
│   │   ├── README.md
│   │   └── <area-id>/
│   │       ├── README.md
│   │       └── components/
│   │           └── <stable-component-id>.md
│   ├── flows/
│   │   ├── README.md
│   │   └── <flow-id>.md
│   └── concepts/
│       ├── README.md
│       └── <concept-id>.md
├── plans/
│   ├── README.md
│   └── <plan-id>.md
├── specifications/
│   ├── README.md
│   └── <specification-id>.md
├── journals/
│   ├── README.md
│   ├── tasks/
│   │   ├── README.md
│   │   └── <task-id>.md
│   └── components/
│       ├── README.md
│       └── <stable-component-id>.md
├── decisions/
│   ├── README.md
│   └── NNNN-<slug>.md
├── operations/
│   ├── README.md
│   └── <document-id>.md
└── development/
    ├── README.md
    └── <document-id>.md
~~~

docs/catalog.json is generated from Markdown front matter. docs/architecture/catalog.json is the authored architecture inventory and ownership catalog. Do not hand-edit docs/catalog.json or content inside generated blocks.

Architecture decisions live only in docs/decisions. Architecture documents point to them with decided-by relations. Do not create docs/architecture/decisions.

Use these records for section indexes:

| Path | doc_id | doc_type | parent_id |
| --- | --- | --- | --- |
| docs/README.md | docs.root | root | absent |
| docs/architecture/README.md | architecture.root | architecture-root | docs.root |
| docs/architecture/system/README.md | architecture.system.index | architecture-root | architecture.root |
| docs/architecture/system/deployments/README.md | architecture.deployments.index | architecture-root | architecture.system.index |
| docs/architecture/areas/README.md | architecture.areas.index | architecture-root | architecture.root |
| docs/architecture/flows/README.md | architecture.flows.index | architecture-root | architecture.root |
| docs/architecture/concepts/README.md | architecture.concepts.index | architecture-root | architecture.root |
| docs/plans/README.md | plans.root | root | docs.root |
| docs/specifications/README.md | specifications.root | root | docs.root |
| docs/journals/README.md | journals.root | journal-root | docs.root |
| docs/journals/tasks/README.md | journals.tasks.index | journal-root | journals.root |
| docs/journals/components/README.md | journals.components.index | journal-root | journals.root |
| docs/decisions/README.md | decisions.root | root | docs.root |
| docs/operations/README.md | operations.root | root | docs.root |
| docs/development/README.md | development.root | root | docs.root |

Only migration-created redirect documents may remain at an established legacy Markdown path outside the canonical leaf patterns. Each such file must satisfy the redirect schema and point into the canonical tree.

The parent graph and generator own the index content inside every README generated-link block. Do not maintain child lists or backlinks by hand.

## Identifiers and paths

Use lowercase identifiers containing letters, digits, dots, and hyphens. Do not encode a mutable filesystem path or area in a stable component ID.

Use these namespaces:

| Record | ID form | Example |
| --- | --- | --- |
| Documentation root | docs.root | docs.root |
| Section root | <section>.root | plans.root |
| Architecture context | architecture.context.<id> | architecture.context.system |
| Architecture container | architecture.container.<id> | architecture.container.runtime |
| Architecture area | architecture.area.<area-id> | architecture.area.frontend |
| Component | <domain>.<component> | authentication.login-form |
| Component document | architecture.component.<component-id> | architecture.component.authentication.login-form |
| Flow | architecture.flow.<flow-id> | architecture.flow.user-login |
| Concept | architecture.concept.<concept-id> | architecture.concept.authorization |
| Deployment | architecture.deployment.<deployment-id> | architecture.deployment.production |
| Plan | plan.<plan-id> | plan.20260715-session-hardening |
| Specification | specification.<specification-id> | specification.session-cookie |
| Task journal | journal.task.<task-id> | journal.task.20260715-session-hardening |
| Component journal | journal.component.<component-id> | journal.component.authentication.login-form |
| Decision | decision.NNNN.<slug> | decision.0007.session-storage |
| Redirect | redirect.<unique-id> | redirect.architecture.old-login-form |

The component ID, component document ID, and component journal ID remain stable when the component changes area. Move the component page to the new area directory, update catalog area and parent_id, and generate a redirect at an established old document path when compatibility requires it.

Use repository-relative paths and POSIX separators in catalogs and documentation. Do not store absolute paths, parent traversal, file URLs, or user-level cache paths.

## Markdown front matter

Every Markdown file under docs starts with YAML front matter. JSON catalogs are the only exceptions.

Allowed scalar fields:

- doc_id
- doc_type
- title
- status
- parent_id
- profile
- redirect_to

relations is the only allowed structured field. It is a list of objects containing type, target_id, and optional anchor.

Example architecture component:

~~~yaml
---
doc_id: architecture.component.authentication.login-form
doc_type: architecture-component
title: Login form
status: active
parent_id: architecture.area.frontend
profile: frontend-ui
relations:
  - type: depends-on
    target_id: architecture.component.authentication.session-client
    anchor: entry-points-and-public-interfaces
  - type: specified-by
    target_id: specification.session-cookie
  - type: decided-by
    target_id: decision.0007.session-storage
---
~~~

Rules:

1. doc_id is globally unique and stable.
2. doc_type, title, status, and relations are required.
3. parent_id is required except on docs.root.
4. profile is required on architecture-component and absent on other types.
5. redirect_to is required only on redirect and absent on other types.
6. relations may be empty but must be present as an empty list.
7. Unknown front-matter fields are invalid.
8. Duplicate relation tuples are invalid.
9. A relation target and optional anchor must resolve.
10. Front matter is the source of truth for the documentation graph. Markdown paths are derived.

Redirect example:

~~~yaml
---
doc_id: redirect.architecture.old-login-form
doc_type: redirect
title: Login form documentation moved
status: active
parent_id: architecture.root
redirect_to: architecture.component.authentication.login-form
relations:
  - type: redirects-to
    target_id: architecture.component.authentication.login-form
---
~~~

## Document types and statuses

Use only these document types:

- root
- architecture-root
- architecture-context
- architecture-container
- architecture-area
- architecture-component
- architecture-flow
- architecture-concept
- architecture-deployment
- plan
- specification
- journal-root
- journal-task
- journal-component
- decision
- operations
- development
- redirect

Allowed status values are type-specific:

| Document type | Allowed statuses |
| --- | --- |
| root | active |
| architecture-root | active |
| architecture-context | active |
| architecture-container | active |
| architecture-area | active |
| architecture-component | active, experimental, deprecated, removed |
| architecture-flow | active |
| architecture-concept | active |
| architecture-deployment | active |
| plan | draft, approved, in-progress, completed, cancelled, superseded |
| specification | draft, approved, superseded |
| journal-root | active |
| journal-task | active, closed |
| journal-component | active, closed |
| decision | proposed, accepted, rejected, deprecated, superseded |
| operations | active |
| development | active |
| redirect | active |

A terminal record remains in the graph. Do not delete completed, cancelled, rejected, deprecated, superseded, removed, or closed records merely to make indexes shorter.

## Relation graph

Use only these relation types:

| Type | Meaning |
| --- | --- |
| related | The documents have a material association that no narrower type represents. |
| depends-on | The source requires the target to function or remain valid. |
| implements | The source implements the target contract or decision. |
| specified-by | The source behavior is governed by the target specification. |
| planned-by | Work affecting the source is tracked by the target plan. |
| decided-by | The source design is governed by the target decision. |
| changes | The source plan, journal, or decision changes the target. |
| documents | The source describes the target. |
| supersedes | The source replaces the target record. |
| redirects-to | A redirect points to its canonical target. |
| verified-by | The source claim or outcome is evidenced by the target record. |

Relation rules:

1. target_id always contains a document ID, never a path or component ID.
2. related is declared once. The generated backlink makes it navigable from both documents.
3. supersedes points from the replacement to the older record and normally targets the same doc_type.
4. redirects-to is valid only on redirect and must equal redirect_to.
5. specified-by targets specification.
6. planned-by targets plan.
7. decided-by targets decision.
8. verified-by targets a document containing reviewable verification evidence, normally journal-task.
9. parent and child edges are derived from parent_id. Do not encode them as relations.
10. Backlinks are derived from incoming relations. Do not duplicate a reverse edge solely to create navigation.
11. Self-relations and parent cycles are invalid.
12. An anchor is a lowercase Markdown anchor that must exist in the target document.

## Generated links and backlinks

Every Markdown document contains exactly one generated block under its final Related documentation heading. A component-page block has this form:

~~~markdown
## Related documentation

<!-- docs:links:start -->
- Parent: [Frontend](../README.md)
<!-- docs:links:end -->
~~~

The generator replaces the complete marker-delimited body. Do not edit, reorder, or partially preserve generated content.

All cross-document navigation is graph-backed:

- declare the relationship in front matter;
- run links with --internal;
- run generate with --write;
- use the generated relative Markdown link;
- keep source-code, test, and external links outside the generated block when they are evidence rather than document-graph edges.

A hand-written link to another document outside the generated block is invalid. Add a relation instead. A generated link must remain inside docs, use a relative path, resolve to the target doc_id, and include a valid anchor when one is declared.

docs/catalog.json contains the generated doc_id-to-path registry. It must agree with every Markdown front matter record and contain no orphan path, duplicate ID, missing parent, missing relation target, or cycle.

## Architecture catalog

docs/architecture/catalog.json has this exact top-level shape:

~~~json
{
  "schema_version": 2,
  "inventory": {
    "include": [
      "apps/**/*",
      "packages/**/*",
      "infrastructure/**/*"
    ],
    "exclude": [
      {
        "glob": "**/node_modules/**",
        "reason": "Vendored dependencies are not repository-owned components."
      },
      {
        "glob": "**/dist/**",
        "reason": "Generated build output is represented by its source component."
      }
    ]
  },
  "areas": [
    {
      "id": "frontend",
      "name": "Frontend",
      "doc_id": "architecture.area.frontend"
    }
  ],
  "components": [
    {
      "id": "authentication.login-form",
      "name": "Login form",
      "kind": "ui-component",
      "profile": "frontend-ui",
      "area": "frontend",
      "doc_id": "architecture.component.authentication.login-form",
      "status": "active",
      "sources": [
        "apps/web/src/features/auth/LoginForm.tsx",
        "apps/web/src/features/auth/login-form.css"
      ],
      "tests": [
        "apps/web/src/features/auth/LoginForm.test.tsx"
      ]
    },
    {
      "id": "authentication.session-client",
      "name": "Session client",
      "kind": "api-client",
      "profile": "frontend-state",
      "area": "frontend",
      "doc_id": "architecture.component.authentication.session-client",
      "status": "active",
      "sources": [
        "apps/web/src/features/auth/session-client.ts"
      ],
      "tests": [
        "apps/web/src/features/auth/session-client.test.ts"
      ]
    }
  ],
  "relationships": [
    {
      "type": "depends-on",
      "from": "authentication.login-form",
      "to": "authentication.session-client"
    }
  ]
}
~~~

Catalog rules:

1. schema_version is the integer 2.
2. inventory.include contains repository-relative glob patterns defining the auditable inventory.
3. Every exclusion has a narrow glob and a factual, non-empty reason.
4. areas IDs are unique and resolve to architecture-area documents.
5. component IDs are unique, stable, and independent of area.
6. component doc_id resolves to exactly one architecture-component document.
7. component profile equals the page front-matter profile.
8. component status equals the page front-matter status.
9. sources contains repository-relative files or narrow globs owned by the component.
10. tests contains repository-relative test files proving the component.
11. relationship from and to contain component IDs. Catalog component relationships use related or depends-on.
12. Every active, experimental, or deprecated component has at least one existing source.
13. A removed component has no current sources and keeps its historical page and graph edges.

## Exhaustive coverage

Expand inventory.include, subtract inventory.exclude, and compare the result with all expanded component sources and tests.

- Every relevant source, test, runtime configuration, schema, migration, deployment, and infrastructure file is accounted for.
- Every included non-test file has exactly one owning component.
- Every included test file appears in at least one component tests list.
- If a registration, schema, or adapter is shared, model it as its own component and relate consumers to it. Do not use unexplained duplicate source ownership.
- Exclude generated output, vendored dependencies, caches, lockfiles, binary assets, and snapshots only when they contain no independent architecture.
- Do not exclude an entire application, package, language, configuration family, or test tree to make the audit pass.
- Source descriptions, tests, relationships, and runtime claims must agree with current code and wiring.
- An architecture audit that validates only documented files is insufficient. Unowned inventory entries are errors.

## Architecture document requirements

### Root

docs/architecture/README.md uses doc_type architecture-root and contains these H2 headings:

1. Scope
2. System summary
3. Areas
4. Runtime boundaries
5. Cross-cutting concerns
6. Coverage and exclusions
7. Maintenance
8. Related documentation

### System context

docs/architecture/system/context.md uses doc_type architecture-context with parent_id architecture.system.index and contains:

1. Purpose
2. External actors
3. Trust boundaries
4. System interactions
5. Data ownership
6. Failure boundaries
7. Evidence
8. Related documentation

### Containers

docs/architecture/system/containers.md uses doc_type architecture-container with parent_id architecture.system.index and contains:

1. Runtime containers
2. Responsibilities
3. Communication
4. Data stores
5. Startup and shutdown
6. Deployment mapping
7. Failure and recovery
8. Related documentation

### Area

Each docs/architecture/areas/<area-id>/README.md uses doc_type architecture-area with parent_id architecture.areas.index and contains:

1. Responsibility
2. Boundaries
3. Entry points
4. Components
5. Dependencies
6. Data and control flow
7. Security and operations
8. Related documentation

### Component

Every component page uses parent_id equal to its architecture-area doc_id and has these H2 headings in this order:

1. Summary
2. Responsibility
3. Boundaries
4. Entry points and public interfaces
5. Dependencies
6. Data and control flow
7. State and side effects
8. Failure modes and recovery
9. Security and permissions
10. Observability and operations
11. Tests and evidence
12. Change impact
13. Profile requirements
14. Related documentation

The page states verified facts for every catalog source and test. Use Not applicable followed by a concrete reason only when a required concern cannot apply to that component.

Create a separate component when a unit has at least one independent architectural boundary: a public cross-component contract, runtime lifecycle, persistent state, trust boundary, deployment unit, external integration, or independently owned change impact. Assign private helpers and feature-local presentation leaves to their owning component while listing every file in catalog sources. Give a shared presentation component its own page when multiple features consume its public API.

### Component profiles

Use one profile:

| Profile | Typical kinds | Required content under Profile requirements |
| --- | --- | --- |
| application-runtime | application, process, cli | Startup, shutdown, configuration, concurrency, deployment. |
| frontend-ui | page, layout, ui-component | Rendering, interaction, accessibility, responsive behavior, user-visible failure. |
| frontend-state | store, hook, api-client | State ownership, synchronization, caching, invalidation, race behavior. |
| backend-api | route, controller, handler, middleware, policy | Contract, validation, authentication, authorization, error mapping, compatibility. |
| domain-service | service, domain-module | Invariants, orchestration, transaction boundaries, idempotency. |
| worker-job | worker, job, consumer, queue | Triggering, delivery semantics, retries, idempotency, ordering, dead-letter recovery. |
| data-persistence | repository, database, schema, migration | Ownership, consistency, transactions, migration, retention, rollback. |
| integration-adapter | adapter, external-client | External contract, authentication, timeouts, rate limits, degradation, reconciliation. |
| shared-library | library, shared-schema | Public API, compatibility, consumers, versioning, failure propagation. |
| infrastructure | infrastructure, deployment-config, runtime-config | Provisioning, secrets, rollout, health, scaling, rollback, disaster recovery. |

kind uses one of the typical values in this table. Add a new kind or profile only by updating this standard, the guard schema, and all affected catalog validation in the same change.

### Flows, concepts, and deployments

Architecture-flow documents use parent_id architecture.flows.index and contain:

1. Trigger
2. Participants
3. Preconditions
4. Sequence
5. Data transformations
6. Failure paths
7. Security boundaries
8. Verification
9. Related documentation

Architecture-concept documents use parent_id architecture.concepts.index and contain:

1. Definition
2. Invariants
3. Ownership
4. Lifecycle
5. Implementations
6. Misuse and failure
7. Related documentation

Architecture-deployment documents use parent_id architecture.deployments.index and contain:

1. Environment
2. Deployed containers
3. Configuration and secrets
4. Network and trust boundaries
5. Data stores
6. Rollout and rollback
7. Health and observability
8. Recovery
9. Related documentation

## Plans

Create a plan for multi-step work, cross-component changes, migrations, rollout or recovery work, or work whose completion must be coordinated.

Plan documents use parent_id plans.root.

A plan contains:

1. Objective
2. Scope
3. Constraints
4. Affected documents and components
5. Work breakdown
6. Verification
7. Rollout and recovery
8. Outcome
9. Related documentation

Use changes relations from the plan to affected documents, or planned-by relations from affected documents to the plan. A completed, cancelled, or superseded plan retains its final outcome and evidence.

## Specifications

Create or update a specification for user-visible behavior, public or internal interfaces, data schemas, permissions, compatibility contracts, and acceptance criteria.

Specification documents use parent_id specifications.root.

A specification contains:

1. Problem
2. Requirements
3. Non-requirements
4. Design
5. Interfaces and data
6. Failure and security behavior
7. Compatibility and migration
8. Acceptance criteria
9. Verification
10. Related documentation

An approved specification is immutable. Replace a changed contract with a new specification that supersedes the old record. Do not silently rewrite the approved contract.

## Journals

Create one journal-task document for every editable task. Create one journal-component document for every catalog component and append an entry whenever the component changes.

Task journals use parent_id journals.tasks.index. Component journals use parent_id journals.components.index.

Task journals contain:

1. Context
2. Timeline
3. Verification evidence
4. Outcome
5. Related documentation

Component journals contain:

1. Component
2. Timeline
3. Current operational notes
4. Related documentation

Journal rules:

1. Timeline entries use an ISO 8601 UTC timestamp heading and record change, evidence, and result.
2. Append entries in chronological order.
3. Never delete, reorder, or rewrite an existing entry.
4. Correct an error by appending a correction that identifies the original timestamp.
5. Do not insert reconstructed history without evidence. Mark imported history with its source revision.
6. Close a task journal only after its verification and outcome are recorded.
7. A component journal remains active until the component is removed; then append the removal evidence and close it.

## Decisions

Use sequential four-digit filenames such as 0007-session-storage.md. Never reuse a number.

Decision documents use parent_id decisions.root.

A decision contains:

1. Context
2. Decision drivers
3. Considered options
4. Decision
5. Consequences
6. Verification
7. Amendments
8. Related documentation

Decision rules:

1. A proposed decision may be edited.
2. After accepted or rejected, existing body content is immutable.
3. Append later clarification under Amendments with an ISO 8601 UTC timestamp. Do not rewrite the original rationale.
4. Replace a material decision with a new decision containing supersedes. Change the old status to superseded and preserve its body.
5. Deprecation changes only status and appends the reason under Amendments.
6. Generated backlinks are not body mutations.

## Operations and development

Operations leaf documents use doc_type operations with parent_id operations.root. They describe executable procedures, prerequisites, safety boundaries, verification, rollback, escalation, and related documentation.

Development leaf documents use doc_type development with parent_id development.root. They describe setup, workflows, commands, test strategy, constraints, troubleshooting, and related documentation.

Commands and examples must match the repository revision. Remove obsolete instructions in the same change that invalidates them.

## Bootstrap and migration

Use the checked-in project skill and repository root:

~~~bash
REPOSITORY_ROOT="$(git rev-parse --show-toplevel)"
SKILL_ROOT="$REPOSITORY_ROOT/.agents/skills/architecture-docs-keeper"
python3 "$SKILL_ROOT/scripts/docs_guard.py" bootstrap --dry-run "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" bootstrap --apply "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" migrate --plan "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" migrate --apply "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" links "$REPOSITORY_ROOT" --internal
python3 "$SKILL_ROOT/scripts/docs_guard.py" generate --write "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" generate --check "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" audit "$REPOSITORY_ROOT" --format human
python3 "$SKILL_ROOT/scripts/docs_guard.py" audit "$REPOSITORY_ROOT" --base "$BASE_SHA" --format json
~~~

The final repository positional is optional and defaults to the current directory.

Bootstrap rules:

1. Use bootstrap only when no repository documentation system exists.
2. Inspect --dry-run output before --apply.
3. Derive inventory, areas, components, and document content from repository evidence.
4. Do not emit TODO, TBD, empty required sections, generic filler, or speculative descriptions.
5. Run links, generate --write, generate --check, and audit before beginning unrelated implementation.

Migration rules:

1. Use migrate whenever legacy, partial, or schema-v1 documentation exists.
2. Inspect --plan before --apply.
3. Preserve existing factual content and append-only records.
4. Prefer moves that retain file history.
5. Allocate stable doc IDs and component IDs before moving files.
6. Never overwrite a destination or discard unmatched content.
7. Create redirect documents for established old paths or IDs with inbound consumers.
8. Convert legacy source ownership into architecture/catalog.json and prove exhaustive inventory coverage.
9. Generate links and catalogs only after authored records and relations are valid.
10. Review the complete documentation diff and audit before deleting superseded duplicate files.

If a safe mapping is ambiguous, stop migration and resolve it from source evidence. Do not guess.

## Change reconciliation

| Change | Required documentation action |
| --- | --- |
| New source or configuration file | Assign one component owner, update component page and journal, update related flows/specifications when behavior changes. |
| Modified component | Update affected factual sections and append task and component journal evidence. |
| Component move | Preserve component and doc IDs, update area and parent, move page, add redirect when required. |
| Component removal | Mark removed, clear current sources after deletion, preserve history, update consumers and flows, close component journal. |
| Interface or schema change | Update or supersede specification, update all consumers and compatibility guidance. |
| Permission or trust-boundary change | Update component, flow, specification, decision when material, and verification evidence. |
| Dependency change | Update catalog relationship and affected component documents. Backlinks are generated. |
| Migration or rollout | Maintain a plan, deployment documentation, recovery procedure, and task journal evidence. |
| Material design choice | Add a decision and decided-by relations. |
| Documentation-only change | Update front matter when graph semantics change, then regenerate links and catalogs. |
| No documentation effect | Append task evidence explaining the verified no-effect result; do not create meaningless architecture churn. |

## Content integrity

- Use repository facts, exact source paths, exact test paths, and observed runtime behavior.
- Do not use TODO, TBD, TBA, FIXME, coming soon, lorem ipsum, placeholder headings, empty sections, or unverifiable claims.
- Do not copy template instructions into repository documents.
- A factual non-applicability statement includes the concrete reason.
- Preserve the repository documentation language; use English when no convention exists.
- Keep prose concise and indexed. Text remains authoritative when a diagram is also present.
- Mermaid diagrams contain only relationships verified by text, catalogs, and source wiring.
- Do not rewrite accurate documentation solely to produce a diff.

## Completion gate

An editable task is complete only when all applicable conditions hold:

1. The exact v2 tree and both catalogs exist.
2. Every Markdown document has valid front matter, a unique doc_id, a valid parent, and exactly one generated link block.
3. All relations, anchors, parents, children, redirects, and backlinks resolve.
4. docs/catalog.json matches the current Markdown graph.
5. docs/architecture/catalog.json is schema version 2 and every included repository file is accounted for.
6. Every active component has a valid page, profile, source ownership, test evidence, and component journal.
7. A task journal records the task, evidence, and outcome.
8. Required plans, specifications, decisions, flows, deployments, operations, and development documents are current.
9. Append-only journal and decision history is intact.
10. Generated content is current:

~~~bash
python3 "$SKILL_ROOT/scripts/docs_guard.py" links "$REPOSITORY_ROOT" --internal
python3 "$SKILL_ROOT/scripts/docs_guard.py" generate --write "$REPOSITORY_ROOT"
python3 "$SKILL_ROOT/scripts/docs_guard.py" generate --check "$REPOSITORY_ROOT"
~~~

11. The change-aware audit passes:

~~~bash
python3 "$SKILL_ROOT/scripts/docs_guard.py" audit "$REPOSITORY_ROOT" --base "$BASE_SHA" --format human
~~~

12. The documentation diff contains no placeholder, stale path, unexplained exclusion, orphan record, hand-edited generated block, or unrelated churn.

Do not claim completion when a required check is unavailable, inconclusive, skipped, or failing.
