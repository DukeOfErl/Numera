# ADR-0800: Permissions are default-deny, and a permission exists only where some role is refused it

- **Status:** accepted
- **Date:** 2026-09-16
- **Pull request:** _pending — `feat/user-identity`_

## Context

Five roles — student, scientist, senior scientist, dev, admin — and the question
of what each may do. Eight permissions were discussed for the first grant table
(roadmap §WP3, 2026-09-16, revised the same day): read, feedback, rate an entry,
suggest a problem, suggest an edit, edit with provenance, ask for calculations,
query aggregated results, manage accounts, dev panel.

Two things were wrong with a table that wide. Most of its columns gated features
the application does not have, so their rows were promises rather than
permissions. And its two live columns — read and feedback — were granted to every
role, so their deny direction could be tested only against nobody: a test that
refuses `None` has not exercised the table.

Two further choices sat under the table: whether an absent entry means refused
or allowed, and where the refusal is enforced.

## Decision

**Default-deny.** `GRANTS: dict[Role, frozenset[Permission]]` in `permissions.py`
lists what each role holds; anything absent is refused. There is no "deny"
entry to forget. A wrong deny announces itself — somebody clicks and is refused —
while a wrong grant is silent and looks like ordinary use, so the cheap direction
absorbs the uncertainty.

**The pruning rule: a permission exists only where some role is refused it.**
That removed every column but one:

- *suggest an edit, edit with provenance, ask for calculations* — no code path
  exists to refuse.
- *rate an entry, suggest a problem* — the same widget as rating the prose today;
  no place to refuse one without the other.
- *query aggregated results* — meant a question spanning more than one organism
  or property, which the agent cannot yet classify.
- *manage accounts* — done outside the application; nothing to refuse.
- *read, feedback* — every role would hold both. Being enrolled *is* reading and
  rating: an account that is signed in but not enrolled is refused before the
  table is consulted, and the table decides only what an enrolled role may do
  beyond that. `feedback` returns as a permission the day a role that may read
  but not rate exists.

What remains is `dev panel`: dev and admin granted, the three tester roles
refused. It exists so that enforcement has a deny direction a test can drive
with a *real role*, and because operators will want the surface anyway.

**The refusal belongs to the operation.** `authorization.require` is called
inside `web.dev_panel_rows`, the accessor that produces what the permission
guards — not on the page that offers the section. Whatever asks for the rows
meets the same refusal: the sidebar, a test, a later page. A page that hides a
control has enforced nothing. `Refused` names the permission and nothing about
the account, because the message is shown.

**The table is asserted against the enums, not counted.** A test holds
`set(GRANTS) == set(Role)` and that every permission is refused to at least one
role, so a new role with no row, or a permission that quietly became universal,
fails by construction rather than passing a count somebody updated.

## Trade-off accepted

**A one-column table looks like ceremony.** Five roles that say two things could
have been a boolean. Kept as a table because the roles are also the weights
ratings will later carry and the gate on human review of the generated
database, and both of those need the roles to exist as data now — and because a
table with a rule for growing is easier to grow correctly than a boolean is to
replace.

**The three tester roles are identical, and so are dev and admin.** A reader who
expects a senior scientist to be able to do more than a student will find
nothing here that says so. Deliberate: a row nobody can test is a grant that
drifts, and the difference between those roles is in how their judgements are
read, not in what the page allows.

**Reading and rating cannot be withdrawn from an enrolled account except by
disabling it.** That is the cost of not having a `read` row. It is the right
cost today — there is no role that should read and not rate — and the rule says
when it stops being right.
