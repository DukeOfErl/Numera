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
    """Where the page finds its database: `[connections.review]`, then `NUMERA_REVIEW_DB_URL`, and
    never the trail's `[connections.usage]` (ADR-2000). Through Streamlit's own secrets loader and
    `st.connection`, over real files: a fake that raises an invented error is how a broken section
    once passed as "raised" while Streamlit's real error was read as absence."""

    @pytest.fixture
    def secrets(self, tmp_path, monkeypatch):
        """Point Streamlit's loader at one file (or none), with nothing cached from another test."""
        import streamlit as st
        from streamlit import config
        from streamlit.runtime.secrets import secrets_singleton

        path = tmp_path / "secrets.toml"
        original = config.get_option("secrets.files")

        def use(text: str | None) -> None:
            if text is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(text)
            config.set_option("secrets.files", [str(path)])
            secrets_singleton._reset()
            st.cache_resource.clear()

        yield use
        config.set_option("secrets.files", original)
        secrets_singleton._reset()
        st.cache_resource.clear()

    @staticmethod
    def sqlite(tmp_path, name: str) -> str:
        return f"sqlite:///{tmp_path}/{name}.sqlite"

    def test_with_no_secrets_file_the_environment_names_the_store(
        self, secrets, monkeypatch, tmp_path
    ):
        secrets(None)
        monkeypatch.setenv(deployment.DB_URL_ENV, self.sqlite(tmp_path, "env"))

        assert deployment.store_engine().url.database.endswith("env.sqlite")

    def test_the_trail_s_section_is_not_the_review_store(self, secrets, monkeypatch, tmp_path):
        """The case that failed: a developer's secrets name the trail, and the page opened it."""
        secrets(f'[connections.usage]\nurl = "{self.sqlite(tmp_path, "trail")}"\n')
        monkeypatch.setenv(deployment.DB_URL_ENV, self.sqlite(tmp_path, "env"))

        assert deployment.store_engine().url.database.endswith("env.sqlite")

    def test_the_review_section_wins_over_the_environment(self, secrets, monkeypatch, tmp_path):
        secrets(
            f'[connections.usage]\nurl = "{self.sqlite(tmp_path, "trail")}"\n'
            f'[connections.review]\nurl = "{self.sqlite(tmp_path, "review")}"\n'
        )
        monkeypatch.setenv(deployment.DB_URL_ENV, self.sqlite(tmp_path, "env"))

        assert deployment.store_engine().url.database.endswith("review.sqlite")

    def test_a_misspelled_review_section_is_raised_not_read_as_absent(
        self, secrets, monkeypatch, tmp_path
    ):
        """`URL` for `url`: a store the operator configured and the page cannot open."""
        secrets(f'[connections.review]\nURL = "{self.sqlite(tmp_path, "review")}"\n')
        monkeypatch.setenv(deployment.DB_URL_ENV, self.sqlite(tmp_path, "env"))

        from streamlit.errors import StreamlitAPIException

        # By type: which missing parameter Streamlit names varies from run to run.
        with pytest.raises(StreamlitAPIException):
            deployment.store_engine()

    def test_a_secrets_file_that_does_not_parse_is_raised_not_read_as_absent(
        self, secrets, monkeypatch, tmp_path
    ):
        from streamlit.errors import StreamlitSecretNotFoundError

        secrets('[connections.review\nurl = "postgresql+psycopg://u:p@h/db"\n')
        monkeypatch.setenv(deployment.DB_URL_ENV, self.sqlite(tmp_path, "env"))

        with pytest.raises(StreamlitSecretNotFoundError):
            deployment.store_engine()

    def test_neither_means_none(self, secrets, monkeypatch, tmp_path):
        secrets(f'[connections.usage]\nurl = "{self.sqlite(tmp_path, "trail")}"\n')
        monkeypatch.delenv(deployment.DB_URL_ENV, raising=False)

        assert deployment.store_engine() is None

    @pytest.mark.parametrize(
        ("url", "has_connect_timeout"),
        [("postgresql+psycopg://u:p@ep-x.neon.tech/db", True), ("sqlite:///x.sqlite", False)],
    )
    def test_the_engine_carries_the_trail_s_timeouts(
        self, secrets, monkeypatch, url, has_connect_timeout
    ):
        """A suspended database fails a rerun after `CONNECT_TIMEOUT_S` instead of hanging it;
        SQLite takes no `connect_timeout` and would refuse one."""
        from numera_ask import trail_store

        secrets(f'[connections.review]\nurl = "{url}"\n')
        seen = {}

        def connection(name, **options):
            seen.update(name=name, **options)
            return SimpleNamespace(engine=object())

        monkeypatch.setattr(deployment.st, "connection", connection)
        deployment.store_engine()

        assert seen["name"] == "review"
        assert seen["pool_recycle"] == trail_store.POOL_RECYCLE_S
        assert ("connect_args" in seen) is has_connect_timeout
        if has_connect_timeout:
            assert seen["connect_args"] == {"connect_timeout": trail_store.CONNECT_TIMEOUT_S}


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
