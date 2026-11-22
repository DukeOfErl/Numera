# ADR-1900: The project is named Numera; the validator follows, the ingester does not

- **Status:** accepted
- **Date:** 2026-11-19
- **Pull request:** _pending — refactor/rename-to-numera_

## Context

The project is going public as a portfolio piece under the name **Numera**. It currently answers to
three names: SciNumbers on the page and in the README, `scinumbers_ask` and `SCINUMBERS_*` in the
ask package, and `bionumbers` for the distribution and for the grounding validator.

ADR-0400 renamed the ask package from `bionumbers_ask` and set the rule this change follows: a
package is named for what it does, and the one package that *is* bound to BioNumbers,
`bionumbers_ingest`, keeps that name because it is the BioNumbers adapter. ADR-0400 left the
validator's `bionumbers` alone only because it lived on an unmerged branch. It has been on `dev`
since 2026-10-17, and nothing in it is BioNumbers-specific: it checks numbers harvested from papers.

Two questions were on the table. **One namespace (`numera.ask`, `numera.validator`) or top-level
packages?** And **what does an old environment name do?**

## Decision

The distribution becomes `numera`. Two packages are renamed at the top level: `numera_ask` and
`numera_validator`. Every console script and environment variable takes the `numera` prefix.
`bionumbers_ingest` and `bionumbers-ingest` keep their names, for ADR-0400's reason.

Top-level packages rather than a namespace: the rename stays mechanical, and
`test_driver_independence.py`, which enforces the dependency direction over the source, keeps
reading the layout it was written for.

**An old environment name is refused by name, never read as a fallback.** This extends the map
ADR-0400 introduced. A fallback would be a second code path to remove later, and while it existed a
stale secret would keep working silently, which is the failure the refusal exists to prevent. A
name retired twice (`BIONUMBERS_ASK_CORPUS`) names its current replacement (`NUMERA_CORPUS`), not
the intermediate name, which is itself retired: being told to set a variable that is then refused
is a loop.

The validator refuses its own two retired names where it reads them, not through the ask package's
map: its core may not import the ask package, and a refusal placed in a caller protects only that
caller (ADR-0250).

## Trade-off accepted

**Every external setting must be renamed in one moment.** Streamlit Cloud secrets, the Actions
secret `SCINUMBERS_TRAIL_READ_URL` and a local `enrol.env` all stop working the instant the deployed
branch moves to this code. Refusal makes that loud rather than silent, but it is still an outage if
the secrets are not renamed alongside. The CHANGELOG lists them, and the deploy switch is a step of
its own.

**In-flight sessions and old checkpoints are dropped.** Session-state keys and the module paths
LangGraph records change. Accepted, as it was in ADR-0400: nothing durable lives in either.

**Two names remain for one project.** A reader sees `numera_*` packages beside `bionumbers_ingest`.
That is the point rather than an oversight, and the README says why.
