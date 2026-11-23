# ADR-2000: The review store has its own secrets section

- **Status:** accepted
- **Date:** 2026-11-22
- **Pull request:** _pending — feat/review-store-section_

## Context

`deployment.store_engine` took the review page's database from the trail's `[connections.usage]`,
and from `NUMERA_REVIEW_DB_URL` only where no such section existed. The reasoning, in its
docstring, was that the review tables are three more tables in the trail's database, and that a
second secrets section is a second thing to get wrong on a deployment.

No review page has been deployed. Every developer's `.streamlit/secrets.toml`, though, names the
trail, because the ask app writes to it. So the page, started from the main checkout, opened the
Neon trail database, found no `review_paper` table and failed; the only way to review a local
store was to hide the secrets file (`--secrets.files` pointed at an empty one), or to run from a
worktree that had none. The rule protected a deployment that does not exist, at the cost of the
one use that does.

Two other options were on the table. **Let the environment variable win over the secrets**: one
line, but a deployed page could then be redirected by a variable, which is what the old rule was
written to prevent. **A launch command that starts the page with no secrets file** (as
`numera-monitor` does): local review without sign-in, deployment untouched; chosen against
because Yoav wants the page to keep its sign-in locally.

## Decision

The review store has its own section, `[connections.review]`, read with `st.connection` so its
engine is cached across sessions. Where the section is absent, `NUMERA_REVIEW_DB_URL` names the
store. The trail's `[connections.usage]` is never read for it. A configured section still wins
over the environment, and a section that is present but unusable is raised, not read as absence.

## Trade-off accepted

**A deployed review page needs a second section,** holding the same URL as the trail's if the
review tables live in the same database. That is the second thing to get wrong the old rule
avoided; it is paid only on the day a review page is deployed, and the page fails loudly rather
than reading the wrong store.

**Locally, the page signs readers in where the secrets have `[auth]`,** so it runs on the port
`redirect_uri` names, and the door writes its sign-in events to the trail as the ask app's does.
