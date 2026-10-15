"""What the review page takes from the deployment: its database, and a person's rung.

The one module in the validator that reaches the ask app, so the tests here are the only ones in
the package that stub `scinumbers_ask.web`.
"""

from __future__ import annotations

import pytest

from bionumbers import deployment
from bionumbers.records import ReviewerRole
from scinumbers_ask.accounts import Account
from scinumbers_ask.permissions import Role


class TestStoreEngine:
    """Where the page finds its database: secrets first, a plain URL from the environment second."""

    def test_a_plain_url_serves_a_machine_with_no_secrets(self, monkeypatch, tmp_path):
        monkeypatch.setattr(deployment.web, "trail_destination", lambda: None)
        monkeypatch.setenv(deployment.DB_URL_ENV, f"sqlite:///{tmp_path}/review.sqlite")

        engine = deployment.store_engine()

        assert engine is not None and engine.url.get_backend_name() == "sqlite"

    def test_secrets_win_over_the_environment(self, monkeypatch, tmp_path):
        configured = object()
        monkeypatch.setattr(deployment.web, "trail_destination", lambda: configured)
        monkeypatch.setenv(deployment.DB_URL_ENV, f"sqlite:///{tmp_path}/other.sqlite")

        assert deployment.store_engine() is configured

    def test_neither_means_none(self, monkeypatch):
        monkeypatch.setattr(deployment.web, "trail_destination", lambda: None)
        monkeypatch.delenv(deployment.DB_URL_ENV, raising=False)

        assert deployment.store_engine() is None


@pytest.mark.parametrize(
    ("role", "rung"),
    [
        (Role.STUDENT, ReviewerRole.STUDENT),
        (Role.SCIENTIST, ReviewerRole.SCIENTIST),
        (Role.SENIOR_SCIENTIST, ReviewerRole.SENIOR_SCIENTIST),
        (Role.DEV, None),
        (Role.ADMIN, None),
    ],
)
def test_the_account_s_role_is_the_rung_a_person_s_decisions_count_on(role, rung):
    account = Account(email="r@example.org", role=role, openrouter_key=None)
    assert deployment.reviewer_role_of(account) is rung


def test_no_account_is_no_rung():
    assert deployment.reviewer_role_of(None) is None
