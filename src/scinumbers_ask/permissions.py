"""Who a reader is, and what a role is granted: the grant table, as data.

Three things live here and nothing else: the roles an enrolled account can hold,
the permissions a role can be granted, and `GRANTS`, the table that says which
role holds which. `authorization.py` reads the table; nothing else should.

**The table is default-deny.** A `(role, permission)` pair the table does not
grant is refused -- there is no "deny" entry to forget, because absence is the
refusal. Adding a permission therefore refuses it to every role until a row
grants it, which is the safe direction for the one guard here that a person can
be wrongly let through (ADR-0800).

**A permission exists only where some role is refused it.** That is the pruning
rule, and it is why the table is one column wide. Reading answers and giving
feedback are what enrolment grants: every role would hold both, so a `read` or
`feedback` row could be refused only to `None`, and refusing `None` is
enrolment's job, not this table's. A row nobody can be refused cannot be tested
against a real role, and a row that cannot be tested is a grant that drifts.
When a role that may read but not rate arrives, `feedback` becomes a permission
with a row to test -- not before.

**The three tester roles are identical here, and so are the two operator
roles.** Student, scientist and senior scientist differ in the weight their
judgements will later carry, which is a property of how the trail is read, not
of what the page allows. Dev and admin differ by label. Both are deliberate:
five rows that say two things is a table a reader can hold in their head.

**Nothing here reaches the agent.** `Identity` is a driver's value: the web
driver looks it up at sign-in and stamps it onto trail records at the sink. The
agent is never handed it, and `tests/test_driver_independence.py` asserts over
the source that `agent.py`, `trace.py` and `feedback.py` neither name it nor
import this module (`test_identity_never_enters_the_agent_the_trail_or_the_feedback`). If the
agent must one day know what is permitted, it is handed permissions, never the
role (ADR-0820).

No Streamlit here: this module is on the agent's side of the dependency line, so
that the refusal in `authorization.py` can be exercised by a test -- or a second
caller -- without a browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    """The one role every enrolled account holds. Stored as its value."""

    STUDENT = "student"
    SCIENTIST = "scientist"
    SENIOR_SCIENTIST = "senior scientist"
    DEV = "dev"
    ADMIN = "admin"


class Permission(StrEnum):
    """What a role can be granted. One member, for the reason the module docstring gives."""

    #: See this session's own trail records, as a sidebar section.
    DEV_PANEL = "dev panel"


@dataclass(frozen=True)
class Identity:
    """An enrolled account as the driver knows it: who, and as what.

    The credential is not here. It is the one per-person fact the agent needs,
    and it travels separately so that this value can be kept out of the agent
    entirely.
    """

    email: str
    role: Role


#: The grant table. Every `Role` has a row; a role's row is the set of
#: permissions it holds, and anything absent is refused. Kept exactly as the spec
#: `user-identity` states it, so the two can be compared by eye.
GRANTS: dict[Role, frozenset[Permission]] = {
    Role.STUDENT: frozenset(),
    Role.SCIENTIST: frozenset(),
    Role.SENIOR_SCIENTIST: frozenset(),
    Role.DEV: frozenset({Permission.DEV_PANEL}),
    Role.ADMIN: frozenset({Permission.DEV_PANEL}),
}
