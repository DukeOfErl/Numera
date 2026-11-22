"""What the review page takes from the deployment: its database, and a person's rung.

The one module in the validator that reaches the ask app and Streamlit, so the tests here are the
only ones in the package that stub `st.connection`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from numera_ask.accounts import Account
from numera_ask.permissions import Role
from numera_validator import deployment
from numera_validator.records import ReviewerRole


class TestStoreEngine:
    """Where the page finds its database: `[connections.review]`, then a URL from the environment,
    and never the trail's `[connections.usage]` (ADR-2000)."""

    @staticmethod
    def sections(monkeypatch, **configured):
        """`st.connection` as the secrets would answer it: an engine for each named section, the
        not-found error Streamlit raises for any other."""
        from streamlit.errors import StreamlitSecretNotFoundError

        def connection(name, **kwargs):
            if name not in configured:
                raise StreamlitSecretNotFoundError(f"no [connections.{name}]")
            return SimpleNamespace(engine=configured[name])

        monkeypatch.setattr(deployment.st, "connection", connection)

    def test_a_plain_url_serves_a_machine_with_no_secrets(self, monkeypatch, tmp_path):
        self.sections(monkeypatch)
        monkeypatch.setenv(deployment.DB_URL_ENV, f"sqlite:///{tmp_path}/review.sqlite")

        engine = deployment.store_engine()

        assert engine is not None and engine.url.get_backend_name() == "sqlite"

    def test_the_trail_s_section_is_not_the_review_store(self, monkeypatch, tmp_path):
        """The case that failed: a developer's secrets name the trail, and the page opened it."""
        self.sections(monkeypatch, usage=object())
        monkeypatch.setenv(deployment.DB_URL_ENV, f"sqlite:///{tmp_path}/review.sqlite")

        engine = deployment.store_engine()

        assert engine is not None and engine.url.get_backend_name() == "sqlite"

    def test_the_review_section_wins_over_the_environment(self, monkeypatch, tmp_path):
        configured = object()
        self.sections(monkeypatch, review=configured, usage=object())
        monkeypatch.setenv(deployment.DB_URL_ENV, f"sqlite:///{tmp_path}/other.sqlite")

        assert deployment.store_engine() is configured

    def test_a_broken_review_section_is_raised_not_read_as_absent(self, monkeypatch, tmp_path):
        """Read as absence, a typo in the section would send the page to the environment's store."""

        def broken(name, **kwargs):
            raise ValueError("Can't load plugin: sqlalchemy.dialects:postgresql.pyscopg")

        monkeypatch.setattr(deployment.st, "connection", broken)
        monkeypatch.setenv(deployment.DB_URL_ENV, f"sqlite:///{tmp_path}/other.sqlite")

        with pytest.raises(ValueError, match="pyscopg"):
            deployment.store_engine()

    def test_neither_means_none(self, monkeypatch):
        self.sections(monkeypatch, usage=object())
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
