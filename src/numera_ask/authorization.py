"""The refusal, in one function, belonging to the operation and not to the page.

`allowed` answers the question; `require` raises when the answer is no. The
operation that a permission guards calls `require` itself -- the dev panel's
accessor, today -- so that whatever asks for the thing meets the same refusal:
the page, a test, a second driver. A page that hides a control has not enforced
anything, and a guard placed in the caller protects exactly one caller.

`None` is refused. It is what a visitor who has not signed in, or an account
that is not enrolled, holds -- and "where there is no identity, nothing is
granted" is the spec's sentence, not a convenience.

`Refused` carries the permission's name and nothing about the account. The
message is going to be shown, and the account whose request was refused is not
something to print back at whoever is looking.
"""

from __future__ import annotations

from .permissions import GRANTS, Identity, Permission


class Refused(PermissionError):
    """The identity does not hold the permission. Names the permission only."""

    def __init__(self, permission: Permission) -> None:
        self.permission = permission
        super().__init__(f"not permitted: {permission.value}")


def allowed(identity: Identity | None, permission: Permission) -> bool:
    """Whether the identity's role is granted the permission. No identity, no grant."""
    if identity is None:
        return False
    return permission in GRANTS.get(identity.role, frozenset())


def require(identity: Identity | None, permission: Permission) -> None:
    """Raise `Refused` unless `allowed`. Called by the operation, never by the page."""
    if not allowed(identity, permission):
        raise Refused(permission)
