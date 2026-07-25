# Research contract — what a research subagent must return

Paste this file's full content into every research prompt. It is written to be read by the researcher.

Research is the cheap place to buy detail. Mapping a five-layer feature costs a fraction of implementing it,
and the researcher already has the file open at the moment the fact matters. Every fact it declines to
transcribe gets rediscovered later by an executor that is slower, has less context, and may be a weaker
model. Description is not the deliverable — **transcription** is.

Research runs in two passes, because the partition needs only the map and the mechanics can't be written
until the merge order is known.

* **Pass 1 — map.** Problem restatement, root cause, and the *exhaustive* set of files the issue will
  create or modify with one line each. That's all the conflict/dependency map needs. Keep it tight.
* **Pass 2 — mechanics.** Dispatched after the partition, with pass 1's file list inlined. This is where
  the fields below get filled, and it is what the Brief is built from.

## Two rules that gate everything else

**Evidence rule.** Every citation is `path:Lstart-Lend` *plus the quoted lines*. Get them by reading the
file at a known offset — never through a pipe that truncates, and never from a search-result snippet.
**A file you did not open may not be named as a precedent.** In the run this contract comes from, one
research agent spent sixty-three turns without opening a single file and named a handler it had never read;
the executor paid for that at turn two hundred.

**Mirror rule.** "Model it on X" is not compliant. A mirror is a path *and* up to 40 quoted lines, inline.
The quoting is the deliverable: it converts an executor's invention into transcription, and it is the single
highest-leverage thing you can hand one.

If you cannot satisfy a field, write `UNRESOLVED: <what you could not establish and the command that would
settle it>`. An honest gap is cheap — the orchestrator resolves it in the Master Plan. A confident guess is
the most expensive thing in this system, because nothing downstream will doubt it.

## Required fields (pass 2)

**1. Registration & guard sweep.** Pick the closest existing sibling capability, take one literal symbol
from it, and run `scripts/sibling_sweep.sh <literal>`. Paste both lists. Central registries and allowlists
are invisible from both visible ends of a feature, and they are usually guarded by tests that enumerate
their members exactly — a guard a weak model "fixes" by weakening the assertion. Report each site as
`path:line` with the array or list literal quoted, so the Brief can carry the exact line to imitate.

**2. Test harness per tier.** For every test tier the issue touches, name **one** exemplar — the most
recently added test file in that tier — open it, and report: (a) its full path and line range, (b) how the
subject under test is constructed, quoted, (c) the fixture or fake it uses, (d) any header pragma, import or
environment variable the file gates on, (e) the exact command that runs *that one file*, and (f) its
prerequisites — a built artifact, a live database, a seeded fixture. Listing the test directory is not
compliance; the file must be opened.

Field (f) is what stops an executor mistaking an unbuilt working tree for a regression it caused and
reverting good work.

**3. Change mechanics, per generated or derived artifact.** For anything the issue touches that is
generated — migrations, codegen output, lockfiles, API clients, snapshots — establish the procedure by
inspecting the last two real examples: `git log -2 -- <artifact-dir>` and read the newest artifact.
**Report what the last two commits actually did, not what the config names.** A repo whose config declares a
generator may have stopped using it years ago; prescribing the generator then corrupts the tree. Give either
the exact command or the hand-authoring procedure, and say which of the two the repo actually does.

**4. Contracts, as literal code.** Every identifier that will appear in more than one file: types, function
signatures, enum members, event names, response shapes, audit action strings, test ids. Write them as code,
not prose. Prose contracts get invented independently at each call site and then disagree.

**5. Docs to update.** Which documentation files this change contradicts, with the exact heading and row
format — and, for each, whether that list is **exhaustive or partial**, with the evidence for your answer
(e.g. "documents 25 of 27 methods, so partial — add nothing"). Docs that contradict the implementation are a
defect under this repo's rules, and an exhaustive table that silently goes stale is the common way it happens.

**6. Repo conventions digest.** Read the repo's own agent-instruction file first — `AGENTS.md`,
`CLAUDE.md`, `CONTRIBUTING.md`, `.cursorrules` — and quote, verbatim, the parts that bind: migration style,
docs policy, commit format, definition of done, review requirements. Quote rather than paraphrase; the
orchestrator has to reconcile these with the skill's own contract and cannot do that from a summary.

**7. Third-party behaviour.** For any external API or SDK the issue touches: the version actually installed,
the official documentation URL for *that* version, and the quoted behaviour. Never from memory. If you
cannot reach the docs, write `UNVERIFIED` — do not paraphrase a recollection.

**8. Design forks — closed, or explicitly open.** Any place the issue admits more than one implementation:
state the chosen option, the rejected ones with a one-line reason each, and the *concrete values* the
decision depends on (a config constant with its `path:line`, a deployment boundary, a process the code runs
in). A design that crosses a process, container or privilege boundary must name the mechanism that bridges
it — or be marked `UNRESOLVED`. Deciding it at implementation time costs an order of magnitude more, because
by then the surrounding code has been written against the wrong assumption.

## Budgets

Keep pass 1 under a page per issue. In pass 2, cap each quoted mirror at 40 lines and each field at what a
reader needs to act — the Brief has to stay readable as a GitHub comment. When a field would run long,
prefer more `path:line` anchors and fewer quoted lines: the anchor is what the executor needs, the quote is
only there for the shapes it cannot infer.

## Return shape

Return data, not an essay. Head each field with its number and title from this file so the orchestrator can
assemble the Brief mechanically. Where a field does not apply to this issue, say `N/A: <why>` rather than
omitting it — a missing heading is indistinguishable from a forgotten one.
