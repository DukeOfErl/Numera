"""`numera-monitor`: no branch, no view; with one, a page bound to this machine.

The exec is stubbed, so nothing starts. "Another machine cannot connect" is asserted
here as the address handed to Streamlit, not by a connection attempt -- recorded as
such in `test_spec_conformance.py`.
"""

from __future__ import annotations

import pytest

from numera_monitor import cli


class Exec:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def __call__(self, file: str, argv: list[str]) -> None:
        self.calls.append((file, argv))


@pytest.mark.parametrize("argv", [[], ["--branch", ""], ["--branch", "   "]])
def test_no_branch_starts_nothing_and_says_one_must_be_named(argv, capsys):
    run = Exec()
    status = cli.main(argv, exec_=run)
    assert status != 0
    assert run.calls == []
    assert cli.BRANCH_REQUIRED in capsys.readouterr().err


def test_a_branch_starts_streamlit_on_the_app_bound_to_localhost():
    run = Exec()
    cli.main(["--branch", "alpha"], exec_=run)
    [(_, argv)] = run.calls
    assert str(cli.APP) in argv
    assert argv[argv.index("--server.address") + 1] == "127.0.0.1"
    assert argv[argv.index("--server.headless") + 1] == "true"
    script_args = argv[argv.index("--") + 1 :]
    assert script_args == ["--branch", "alpha"]


def test_the_app_it_starts_exists():
    assert cli.APP.name == "app.py"
    assert cli.APP.parent.name == "numera_monitor"


def test_the_page_is_told_to_load_no_secrets_file(tmp_path, monkeypatch):
    """Started from the repository root, Streamlit would load
    `.streamlit/secrets.toml`, which holds the owner's database URL. Measured with
    Streamlit's own loader: a secrets file in the working directory is read without
    the flag and ignored with it."""
    from streamlit import config
    from streamlit.runtime.secrets import Secrets

    run = Exec()
    cli.main(["--branch", "alpha"], exec_=run)
    [(_, argv)] = run.calls
    files = argv[argv.index("--secrets.files") + 1]
    assert argv.index("--secrets.files") < argv.index("--")

    (tmp_path / ".streamlit").mkdir()
    (tmp_path / ".streamlit" / "secrets.toml").write_text('owner = "postgresql://owner:pw@h/db"\n')
    monkeypatch.chdir(tmp_path)

    original = config.get_option("secrets.files")
    try:
        # The suite points Streamlit's default locations at an empty file (conftest,
        # `_streamlit_reads_no_secrets_file_on_this_machine`), so the canary names the
        # working directory's file itself: the one a run from the repository root reads.
        config.set_option("secrets.files", [str(tmp_path / ".streamlit" / "secrets.toml")])
        default = Secrets()
        default.load_if_toml_exists()
        assert "owner" in default, "the canary: without the flag the file is read"

        config.set_option("secrets.files", [files])
        told = Secrets()
        told.load_if_toml_exists()
        assert dict(told) == {}
    finally:
        config.set_option("secrets.files", original)
