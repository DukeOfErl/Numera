# ADR-1280: Reader addresses appear in an issue comment, so the repository must stay private

- **Status:** accepted
- **Date:** 2026-10-02
- **Pull request:** none yet (`feat/first-use-notice`)

## Context

The first-use notice names each new reader by the address they signed in with — the
operator needs to know who arrived — and delivers it as a comment on a GitHub issue
(ADR-1270). An issue comment is visible to everyone who can see the repository.

The repository is currently **private** (`gh repo view`: `PRIVATE`, 2026-10-02). The
trail holds the addresses; the operator already holds them as enrolled accounts, so
this adds a place they are stored, not a new disclosure to the operator.

## Decision

Addresses go into the issue comment and **nowhere else**. The command writes its
report to a file and never to standard output in the workflow, so the Actions log
does not carry them. **One exception, stated rather than hidden:** the operator's exclusion
list (`FIRST_USE_EXCLUDE`, their own and test addresses, a plain variable) is printed by
GitHub as a step `env` value, because only secrets are masked; it names no reader.
`tests/test_scheduled_workflows.py` fails if a step prints the
report file without redirecting it, and if an address is written into the workflow
itself (the operator's exclusions come from a repository variable).

The workflow file carries a comment saying so beside the step that posts it.
**Making the repository public publishes every address the notice has ever posted**,
and deleting the comments does not recall copies that were indexed or cached. Before
that, remove the workflow, delete the `first use` issue and its history, and treat the
addresses as disclosed.

## Trade-off accepted

A convenience (mail through GitHub, no mail account) is bought with a standing
constraint on the repository's visibility that nothing in GitHub enforces. The test
suite guards the workflow's own text, not the repository's setting.

**What was not checked:** that GitHub's issue notification mail carries the comment
body — and so the address — rather than a link, which changes who else could see it
in transit; and the retention of an issue's edit history after a comment is deleted.
