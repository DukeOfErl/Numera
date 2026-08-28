# ADR-0030: OpenSpec specs are the behavioral record, replacing docs/REQUIREMENTS.md

- **Status:** accepted
- **Date:** 2026-08-08
- **Pull request:** _(not yet opened — branch `chore/drop-requirements-doc`)_

## Context

`CLAUDE.md`'s documentation-upkeep section listed four documents to keep current, one of which was
`docs/REQUIREMENTS.md`, described as "the behavioral spec (what the app must do, kept
implementation-agnostic)".

Adopting OpenSpec ([ADR-0010](0010-adopt-openspec-for-spec-driven-development.md)) introduced a
second home for exactly that content. Under the `spec-driven` schema, each change carries delta
specs written as requirements with concrete scenarios, and archiving promotes them into
`openspec/specs/`. That directory is, by construction, the implementation-agnostic statement of what
the system must do.

Keeping both would mean maintaining two hand-synchronised copies of the same content, with nothing
comparing them. The drift would be silent, and a stale requirements document is worse than none —
readers cannot tell which copy is current.

`docs/REQUIREMENTS.md` had not yet been created, so no content is being discarded.

## Decision

Remove `docs/REQUIREMENTS.md` from the documentation-upkeep list and point readers at
`openspec/specs/` instead. Behavioral requirements are written as spec deltas on a change and
promoted into `openspec/specs/` at archive time; they are not restated in a separate document.

`README.md`, `docs/diagrams/`, and this file's Architecture section remain as they were — none of
them duplicates the behavioral spec.

## Trade-off accepted

Behavioral requirements are now less browsable: reading the full spec means looking at
`openspec/specs/` rather than opening a single file, and until a change is archived its requirements
live under `openspec/changes/<name>/specs/` instead. There is also now a workflow dependency for
what was previously a plain Markdown file anyone could edit.

In exchange there is exactly one source of truth, `openspec validate` checks its structure, and
requirements arrive tied to the change that introduced them rather than being retrofitted into a
document afterwards.
