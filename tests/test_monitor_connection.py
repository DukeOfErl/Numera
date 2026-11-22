"""How the view reaches the database, and the role it reaches it as.

Offline: Neon's API is the `_Opener` double from `test_enrol` (which refuses a
request without a credential), and the grant's statements are recorded rather than
run. What only a real database can say -- that the grants refuse what they should --
is `test_monitor_role_live.py`.
"""

from __future__ import annotations

import pytest
from test_enrol import _Opener

from numera_ask import neon
from numera_monitor import connection, grant

ENV = {
    "NEON_API_KEY": "napi",
    "NEON_PROJECT_ID": "proj",
    connection.PASSWORD_ENV: "pw",
}


def _endpoints(*specs):
    return {"endpoints": [{"type": t, "host": h} for t, h in specs]}


def _neon(endpoints):
    return _Opener(
        {
            "/branches?": {"branches": [{"id": "br-alpha", "name": "alpha"}]},
            "/branches/br-alpha/endpoints": endpoints,
        }
    )


# --- neon.endpoint_host ---------------------------------------------------------


def test_the_pooled_host_is_the_endpoint_id_with_pooler_appended():
    opener = _neon(_endpoints(("read_write", "ep-cool-1.eu-central-1.aws.neon.tech")))
    host = neon.endpoint_host("napi", "proj", "br-alpha", opener=opener)
    assert host == "ep-cool-1-pooler.eu-central-1.aws.neon.tech"


def test_the_direct_host_is_unchanged():
    opener = _neon(_endpoints(("read_write", "ep-cool-1.eu-central-1.aws.neon.tech")))
    host = neon.endpoint_host("napi", "proj", "br-alpha", pooled=False, opener=opener)
    assert host == "ep-cool-1.eu-central-1.aws.neon.tech"


def test_read_only_replicas_are_not_the_endpoint():
    opener = _neon(
        _endpoints(("read_only", "ep-replica.x.neon.tech"), ("read_write", "ep-main.x.neon.tech"))
    )
    assert neon.endpoint_host("napi", "proj", "br-alpha", opener=opener).startswith("ep-main-")


@pytest.mark.parametrize(
    "endpoints",
    [
        _endpoints(),
        _endpoints(("read_only", "ep-r.x.neon.tech")),
        _endpoints(("read_write", "ep-a.x.neon.tech"), ("read_write", "ep-b.x.neon.tech")),
    ],
)
def test_anything_but_one_read_write_endpoint_is_refused(endpoints):
    with pytest.raises(neon.NoEndpoint):
        neon.endpoint_host("napi", "proj", "br-alpha", opener=_neon(endpoints))


# --- connection -----------------------------------------------------------------


def test_the_view_connects_as_its_own_role_to_the_branch_s_pooled_host():
    opener = _neon(_endpoints(("read_write", "ep-cool-1.eu.aws.neon.tech")))
    url = connection.resolve("alpha", ENV, opener=opener)
    assert url == (
        "postgresql+psycopg://numera_monitor:pw@ep-cool-1-pooler.eu.aws.neon.tech"
        "/neondb?sslmode=require"
    )


def test_the_owner_s_url_is_never_asked_for():
    """`connection_uri` returns a URL with the owner's password in it. The view
    must not hold that, even in memory."""
    opener = _neon(_endpoints(("read_write", "ep-cool-1.eu.aws.neon.tech")))
    connection.resolve("alpha", ENV, opener=opener)
    assert not any("connection_uri" in url for _, url in opener.calls)


def test_a_password_with_url_characters_cannot_move_the_host():
    url = connection.monitor_url("ep-1-pooler.x.neon.tech", "a@b/c:d")
    assert "@ep-1-pooler.x.neon.tech/" in url
    assert url.count("@") == 1


def test_every_missing_setting_is_named_at_once():
    with pytest.raises(connection.Missing) as missing:
        connection.resolve("alpha", {"NEON_PROJECT_ID": "proj"}, opener=_neon({}))
    text = str(missing.value)
    assert "NEON_API_KEY" in text and connection.PASSWORD_ENV in text
    assert "NEON_PROJECT_ID" not in text


# --- grant ----------------------------------------------------------------------


class _Recording:
    """An engine that records statements. `format(...)` answers like Postgres would."""

    def __init__(self):
        self.statements: list[tuple[str, object]] = []

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def exec_driver_sql(self, sql, params=None):
        self.statements.append((sql, params))

        class _Result:
            def scalar_one(self):
                role, password = params
                return f"alter role {role} password '{password}'"

        return _Result()


def _granted(password="pw"):
    engine = _Recording()
    grant.grant(engine, password)
    return [sql for sql, _ in engine.statements]


def test_the_role_reads_the_trail_and_two_columns_of_accounts():
    sql = "\n".join(_granted()).lower()
    assert "grant select on trail to numera_monitor" in sql
    assert "grant select (email, disabled) on accounts to numera_monitor" in sql


def test_nothing_is_granted_wholesale():
    """Neon's own recipe grants every table and every future one, which would hand
    over each tester's OpenRouter key."""
    sql = "\n".join(_granted()).lower()
    assert "all tables" not in sql
    assert "default privileges" not in sql
    assert "openrouter" not in sql
    assert "insert" not in sql and "update" not in sql and "delete" not in sql


def test_the_role_defaults_to_read_only_transactions():
    assert any("default_transaction_read_only = on" in s for s in _granted())


def test_the_password_is_quoted_by_the_server_never_spliced_into_sql():
    """The only statement carrying the password is the one Postgres's `format(%L)`
    produced; on this side it travels as a bound parameter."""
    engine = _Recording()
    grant.grant(engine, "it's")
    assert (grant.ROLE, "it's") in [p for _, p in engine.statements]
    carrying = [sql for sql, _ in engine.statements if "it's" in sql]
    assert carrying == ["alter role numera_monitor password 'it's'"]


def test_a_new_password_has_the_entropy_neon_requires():
    a, b = grant.new_password(), grant.new_password()
    assert a != b
    assert len(a) == grant.PASSWORD_LENGTH >= 12


@pytest.mark.parametrize("argv", [[], ["--branch", " "]])
def test_grant_refuses_without_a_branch(argv, capsys):
    assert grant.main(argv) == 2
    assert "no branch named" in capsys.readouterr().err


def test_grant_refuses_without_neon_credentials(monkeypatch, capsys):
    monkeypatch.delenv("NEON_API_KEY", raising=False)
    monkeypatch.delenv("NEON_PROJECT_ID", raising=False)
    assert grant.main(["--branch", "dev"]) == 2
    assert "nothing was changed" in capsys.readouterr().err
