"""The deployment branch installs what the app actually imports.

**Deployment branch only**, and it exists because the two lists it compares are a
copy of one another kept in step by hand. Streamlit Community Cloud picks
`uv.lock` and runs `uv sync`, which does not install extras, so `[project]
dependencies` has to carry the `ask` stack that every other branch declares as an
extra. The copy drifted: `ask` gained SQLAlchemy, psycopg and Authlib over two
changes and `dependencies` gained none of them, so the deployed app would have
started, served a page, and then failed to record anything or sign anyone in --
at runtime, in front of a tester, rather than at install where a missing package
belongs.

Comparing the lists is the cheapest thing that turns the next such merge into a
red test here instead.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text())["project"]


def test_the_deployment_declares_everything_the_ask_extra_does():
    project = _project()
    declared = set(project["dependencies"])
    missing = set(project["optional-dependencies"]["ask"]) - declared
    assert not missing, (
        f"the deployment would install without {sorted(missing)}. Community Cloud "
        f"runs `uv sync`, which does not install extras, so anything the `ask` "
        f"extra declares has to be repeated in [project] dependencies -- otherwise "
        f"it is absent on the deployed app and nowhere else."
    )


def test_the_two_lists_are_not_empty():
    """A parse that returned nothing would make the comparison above pass over it."""
    project = _project()
    assert len(project["dependencies"]) >= 5
    assert len(project["optional-dependencies"]["ask"]) >= 5
