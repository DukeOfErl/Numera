"""`scinumbers-monitor`: no branch, no view; with one, a page bound to this machine.

The exec is stubbed, so nothing starts. "Another machine cannot connect" is asserted
here as the address handed to Streamlit, not by a connection attempt -- recorded as
such in `test_spec_conformance.py`.
"""

from __future__ import annotations

import pytest

from scinumbers_monitor import cli


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
    assert cli.APP.parent.name == "scinumbers_monitor"
