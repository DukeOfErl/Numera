"""`numera-monitor`: start the monitor page for one named branch (ADR-1950).

The command only replaces itself with Streamlit; the page reads the trail and
nothing else. The branch is the one thing it will not guess -- see `BRANCH_REQUIRED`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

APP = Path(__file__).with_name("app.py")
NO_SECRETS = Path(__file__).with_name("no-secrets.toml")

#: No default, for the reason `pending.NO_BRANCH` has none: the deployment's testers
#: are in one branch and a rehearsal's in another. Worded for a command that writes
#: nothing, so it does not talk about rows landing anywhere.
BRANCH_REQUIRED = (
    "no branch named. Which environment should be viewed? There is no default -- "
    "the deployment's testers are in one branch and a rehearsal's are in another, "
    "and a silent view of the wrong one is worse than no view. "
    "Add --branch alpha."
)


def streamlit_argv(branch: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP),
        # Loopback only: the page shows testers' email addresses and comments and has
        # no sign-in of its own, so reachability from another machine would be the
        # only thing standing between them and a stranger.
        "--server.address",
        "127.0.0.1",
        "--server.headless",
        "true",
        # No secrets file. Started from the repository root, Streamlit would load
        # `.streamlit/secrets.toml`, and the owner's database URL with it -- the one
        # credential this view is built never to hold (ADR-1960).
        "--secrets.files",
        str(NO_SECRETS),
        "--",
        "--branch",
        branch,
    ]


def main(argv: list[str] | None = None, *, exec_=os.execv) -> int:
    parser = argparse.ArgumentParser(prog="numera-monitor", description=__doc__)
    parser.add_argument(
        "--branch", help="REQUIRED, no default: the Neon branch the deployment writes to"
    )
    args = parser.parse_args(argv)

    if not args.branch or not args.branch.strip():
        print(BRANCH_REQUIRED, file=sys.stderr)
        return 2
    exec_(sys.executable, streamlit_argv(args.branch.strip()))
    return 0
