"""The grant table, both directions, and the refusal that reads it.

Auth is the one place this project does not skip the negative case: a wrongly
denied permission produces a complaint in minutes, a wrongly granted one
produces nothing at all. So every test here that grants also refuses, and the
refusal varies the dimension the rule reads -- the *role* -- not merely the
outcome. A test that refused only `None` would pass with a table that granted
everything to everyone.

**Mutation testing cannot reach this module, so seeding stands in for it.**
A run of `mutmut` 3.8 over `scinumbers_ask.permissions*` (2026-09-17) reported
*"Filtered for specific mutants, but nothing matches"*: mutmut rewrites function
bodies, and everything here is an enum body, a `@dataclass` body or a
module-level dict. `GRANTS` -- the thing most worth mutating in the package --
produces no mutants at all, and a run that reported "0 survivors" for this
module would be a false all-clear rather than a result. The same holds for
`accounts.Account.identity`, whose `@dataclass` body mutmut also left alone.

So the table was checked by hand-seeded defects into a copy instead, against
these two files and `test_web_driver_dev_panel.py`, from a green baseline of 31:

- `Role.STUDENT` granted `DEV_PANEL` -- the expensive direction, a tester
  silently let in -- caught by 5, among them
  `test_each_tester_role_is_refused_the_dev_panel[student]`,
  `test_the_two_populations_partition_the_roles` and, through the page,
  `test_web_driver_dev_panel.py::test_a_tester_s_page_has_no_such_section[student]`.
- `Role.DEV` stripped of `DEV_PANEL` -- caught by 10.
- `SENIOR_SCIENTIST`'s stored value misspelt -- caught by
  `test_the_role_values_are_the_words_the_spec_and_the_table_use` alone, which is
  why that test is here: a renamed value enrols nobody and stamps a different
  word, and nothing else in the suite would say so.
- `DEV_PANEL`'s stored value changed -- caught by 3.

Re-seed these when the table grows a row; the mutation run will not do it for you.
"""

from __future__ import annotations

import pytest

from scinumbers_ask.authorization import Refused, allowed, require
from scinumbers_ask.permissions import GRANTS, Identity, Permission, Role

TESTERS = (Role.STUDENT, Role.SCIENTIST, Role.SENIOR_SCIENTIST)
OPERATORS = (Role.DEV, Role.ADMIN)


def _as(role: Role) -> Identity:
    return Identity(email="someone@example.org", role=role)


# --- the table, as the spec states it ---------------------------------------


@pytest.mark.parametrize("role", OPERATORS)
def test_dev_and_admin_are_granted_the_dev_panel(role):
    assert allowed(_as(role), Permission.DEV_PANEL)
    require(_as(role), Permission.DEV_PANEL)  # does not raise


@pytest.mark.parametrize("role", TESTERS)
def test_each_tester_role_is_refused_the_dev_panel(role):
    """The refused *roles* are the test. These are enrolled accounts with a real
    role, so a table that granted the panel to every role fails here and not only
    on `None`."""
    assert not allowed(_as(role), Permission.DEV_PANEL)
    with pytest.raises(Refused):
        require(_as(role), Permission.DEV_PANEL)


def test_no_identity_is_refused():
    assert not allowed(None, Permission.DEV_PANEL)
    with pytest.raises(Refused):
        require(None, Permission.DEV_PANEL)


def test_a_role_the_table_does_not_know_is_refused():
    """`GRANTS.get(role, frozenset())`: the default is the deny direction, and a
    mutant that made it `frozenset(Permission)` survived until this test. The
    annotation says `Role`; nothing at runtime enforces it, and `accounts.lookup`
    reads role text off a database row."""
    stranger = Identity(email="someone@example.org", role="curator")  # type: ignore[arg-type]
    assert not allowed(stranger, Permission.DEV_PANEL)
    with pytest.raises(Refused):
        require(stranger, Permission.DEV_PANEL)


def test_the_role_values_are_the_words_the_spec_and_the_table_use():
    """These strings are what `sql/accounts.sql` documents, what `accounts.lookup`
    parses off the row, and what `user_role` is written as. A renamed member
    value would enrol nobody and stamp a different word; pinned here so that a
    change to one is a change to all four on purpose."""
    assert {r.value for r in Role} == {"student", "scientist", "senior scientist", "dev", "admin"}
    assert Permission.DEV_PANEL.value == "dev panel"


def test_the_two_populations_partition_the_roles():
    """Both directions, measured over the whole table rather than sampled.

    The grant table is a classification rule: a change to it moves roles in both
    directions and the author looks at one. This asserts the granted set and the
    refused set by identity, so that adding a role, or moving one, has to be
    reflected here on purpose.
    """
    granted = {role for role in Role if allowed(_as(role), Permission.DEV_PANEL)}
    refused = {role for role in Role if not allowed(_as(role), Permission.DEV_PANEL)}
    assert granted == set(OPERATORS)
    assert refused == set(TESTERS)


# --- the table's shape ---------------------------------------------------------


def test_the_table_has_a_row_for_every_role_and_names_only_known_permissions():
    """Asserted against the enums, not counted, for the reason `agent_endings.py`
    gives: a count cannot say which member is missing, and a new `Role` with no
    row would pass `len(GRANTS) == 5` the moment somebody updated the 5."""
    assert set(GRANTS) == set(Role)
    assert set().union(*GRANTS.values()) <= set(Permission)


def test_every_permission_is_refused_to_some_role():
    """The pruning rule, enforced: a permission nobody can be refused is a row
    that cannot be tested against a real role, and the module docstring says it
    must not exist."""
    for permission in Permission:
        refusing = [role for role in Role if permission not in GRANTS[role]]
        assert refusing, f"{permission.value} is granted to every role"


# --- the refusal -----------------------------------------------------------------


def test_the_refusal_names_the_permission_and_nothing_about_the_account():
    """The message will be shown; the email of the person refused must not be in it."""
    identity = Identity(email="refused.person@example.org", role=Role.STUDENT)
    with pytest.raises(Refused) as caught:
        require(identity, Permission.DEV_PANEL)
    assert caught.value.permission is Permission.DEV_PANEL
    assert "dev panel" in str(caught.value)
    assert "refused.person" not in str(caught.value)
    assert "student" not in str(caught.value)


def test_refused_is_a_permission_error():
    """So a caller that does not know this module can still catch the right thing."""
    assert issubclass(Refused, PermissionError)
