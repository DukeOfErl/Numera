"""The validator's dependency direction, asserted over the source (design D9).

Core modules of `bionumbers` import no Streamlit and nothing from `scinumbers_ask`; only
`deployment.py` (the page's database and a person's rung) and the root `review_app.py` (the
driver) may. `review.py` is core: the simulated review builds its screens from it. Nothing in Python
enforces this -- `import streamlit` inside `store.py` would run perfectly -- so it is read from the
AST, the way `test_driver_independence.py` reads the ask package's.

The core is *every file in the package minus `deployment`*, computed rather than listed, so a module
added tomorrow is under the rule before anyone remembers to name it. Imports are read wherever
they sit: at top level, inside a function, relative or absolute -- the absolute intra-package form
is the one a sibling test found its predecessor blind to.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "bionumbers"
REVIEW_APP = ROOT / "review_app.py"

#: The one module in the package allowed to reach a driver framework or the ask package.
PRESENTATION = {"deployment"}

#: What no core module may reach: the web framework, and the ask package under any of its names.
FORBIDDEN = {"streamlit", "scinumbers_ask"}

#: The two packages whose `from pkg import name` form names a submodule, expanded by `imports_in`.
PACKAGES = {"bionumbers", "scinumbers_ask"}

CORE = sorted(
    path.stem
    for path in PACKAGE.glob("*.py")
    if path.stem not in PRESENTATION and not path.stem.startswith("__")
)

#: The driver's allowance, by top-level distribution: what the page draws with, the package it
#: presents, and the ask app's door. Nothing else that is not the standard library.
REVIEW_APP_ALLOWED = {"streamlit", "bionumbers", "scinumbers_ask"}
#: Within those, the exact modules the page is allowed to touch. `scinumbers_ask` narrows to the
#: door: the page has no business with the ask app's agent, corpus or spend.
REVIEW_APP_ALLOWED_MODULES = {
    "bionumbers.deployment",
    "bionumbers.review",
    "bionumbers.store",
    "bionumbers.records",
    "scinumbers_ask.web",
}


def top_level(dotted: str) -> str:
    """The distribution an import reaches: `streamlit.testing.v1` is `streamlit`."""
    return dotted.split(".")[0]


def imports_in(source: str) -> set[str]:
    """Every dotted module path an import in this source reaches, however written.

    Top level or inside a function or class, `import x.y` or `from x.y import z`. A relative
    import is resolved against `bionumbers` -- the only package this file reads with relative
    imports -- so `from . import store` and `from .store import x` both read `bionumbers.store`.
    `from bionumbers import review` names a submodule in the alias rather than in the module, and
    is read as `bionumbers.review` so the page's allowance can be checked module by module;
    that expansion is done only for the two packages this file knows, since for anything else
    the alias is as likely a name as a module.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                module = "bionumbers" + (f".{node.module}" if node.module else "")
            else:
                module = node.module or ""
            if module in PACKAGES:
                names.update(f"{module}.{alias.name}" for alias in node.names)
            elif module:
                names.add(module)
    return names


def forbidden_in(source: str) -> set[str]:
    """The forbidden distributions this source reaches, empty when it is clean."""
    return {top_level(name) for name in imports_in(source)} & FORBIDDEN


# --- the helper can fail ---------------------------------------------------------------------


def test_the_helper_sees_an_import_hidden_inside_a_function():
    source = "def draw():\n    import streamlit as st\n    return st\n"
    assert forbidden_in(source) == {"streamlit"}


def test_the_helper_sees_the_ask_package_under_its_from_form():
    source = "def door():\n    from scinumbers_ask import web\n    return web\n"
    assert forbidden_in(source) == {"scinumbers_ask"}


def test_the_helper_sees_the_absolute_dotted_form_and_the_submodule_form():
    assert forbidden_in("import scinumbers_ask.web as w\n") == {"scinumbers_ask"}
    assert forbidden_in("from streamlit.testing.v1 import AppTest\n") == {"streamlit"}


def test_the_helper_passes_a_clean_module():
    source = "import re\nfrom sqlalchemy import Engine\nfrom bionumbers.records import Claim\n"
    assert forbidden_in(source) == set()


def test_the_helper_resolves_relative_imports_to_this_package():
    assert imports_in("from . import store\n") == {"bionumbers.store"}
    assert imports_in("from .records import Claim\n") == {"bionumbers.records"}


# --- the core -----------------------------------------------------------------------------


def test_the_core_is_not_empty_and_deployment_is_not_in_it():
    assert len(CORE) >= 5, CORE
    assert "deployment" not in CORE
    assert "review" in CORE, "the screens are core: the simulated review needs no ask extra"
    assert (PACKAGE / "deployment.py").exists(), "the exemption names a module that is not there"


@pytest.mark.parametrize("module", CORE)
def test_no_core_module_reaches_for_streamlit_or_the_ask_package(module):
    source = (PACKAGE / f"{module}.py").read_text()
    assert forbidden_in(source) == set(), (
        f"bionumbers.{module} reaches {sorted(forbidden_in(source))}; only deployment may (D9)"
    )


def test_deployment_is_the_one_module_that_reaches_the_ask_package():
    """The exemption is used, not just granted: if `deployment` stopped needing the ask package
    the allowance above would be dead and should go."""
    source = (PACKAGE / "deployment.py").read_text()
    assert "scinumbers_ask" in forbidden_in(source)


# --- the page -----------------------------------------------------------------------------


def test_the_review_page_imports_only_what_a_driver_needs():
    """Streamlit, the package it presents, the ask app's door, and the standard library."""
    reached = imports_in(REVIEW_APP.read_text())
    third_party = {name for name in reached if not _is_standard_library(top_level(name))}
    assert {top_level(name) for name in third_party} <= REVIEW_APP_ALLOWED, sorted(third_party)
    assert third_party <= REVIEW_APP_ALLOWED_MODULES | {"streamlit"}, sorted(third_party)


def test_the_review_page_reaches_the_door_and_the_review_module():
    """The positive half: the page really does go through the seams the design names."""
    reached = imports_in(REVIEW_APP.read_text())
    assert {"scinumbers_ask.web", "bionumbers.review", "bionumbers.deployment"} <= reached


def test_the_helper_expands_a_package_s_from_form_to_its_submodules():
    assert imports_in("from bionumbers import review, store\n") == {
        "bionumbers.review",
        "bionumbers.store",
    }
    assert imports_in("from scinumbers_ask import web\n") == {"scinumbers_ask.web"}
    # Anything else keeps the module and drops the names: `Claim` is not a module.
    assert imports_in("from bionumbers.records import Claim\n") == {"bionumbers.records"}


def _is_standard_library(name: str) -> bool:
    return name in sys.stdlib_module_names
