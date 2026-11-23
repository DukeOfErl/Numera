# ADR-2050: The first-use alert runs in a private repository

- **Status:** accepted
- **Date:** 2026-11-23
- **Pull request:** _pending — chore/first-use-alerts-to-numera-ops_
- **Supersedes:** ADR-1280; amends ADR-1270 (where the job and its issue live)

## Context

The hourly first-use alert (ADR-1250, ADR-1270) reports each new reader by the address they signed
in with, as a comment on a standing GitHub issue, which mails the operator. ADR-1280 accepted that
on one condition, in its title: the repository stays private. The repository is now going public as
a portfolio piece. A public repository's issues are public, and so are its Actions logs, which also
printed the exclusion list (the operator's own addresses) on every run.

Three ways out were weighed with Yoav on 2026-11-23. **Keep the job here and post counts only**
("two new readers signed in"): no address leaves the database, but tester activity becomes public on
the issue, and the operator loses the name the alert exists to give. **Retire the alert**: the
command stays, the operator runs it by hand, and a first reader goes unnoticed until someone looks.
**Move the job to a private repository**: chosen.

## Decision

The job, its standing issue and a digest of its own live in the private `DukeOfErl/numera-ops`.
It checks this repository's code out and runs `numera_ask.first_use` unchanged; it holds the
read-only trail URL and, now as a secret so Actions masks it, the exclusion list. It holds **no
credential to this repository**: the checkout needs none once this repository is public, which is
why the switch-over happens at the moment of going public, with the alert disabled here from
2026-11-23 until then.

This repository keeps the command (`numera-first-use`) and its tests; the workflow, and the tests
that execute its steps, moved with it (`tests/test_workflows.py` in `numera-ops`). The requirement
they prove ("A new reader's arrival reaches the operator…", `user-identity`) is recorded in
`tests/test_spec_conformance.py` as tested there. `tests/test_scheduled_workflows.py` fails if any
workflow here reads the trail or names `first-use` again.

## Trade-off accepted

**Numera's suite no longer tests the delivery.** A change to the command that breaks the job is
caught only when `numera-ops` runs, and that suite runs only on a push there. The job runs this
repository's code from `dev`, so a breaking change reaches it on the next tick.

**Two repositories to keep in step.** The workflow's pinned dependencies (`sqlalchemy`, `psycopg`)
must move with `uv.lock` here, as they did when the job lived beside it, and the operator now
watches two digests.
