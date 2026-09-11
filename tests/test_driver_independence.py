"""The agent is one body of code, and neither driver is privileged in it.

Task 8.5 asks for verification that the agent is unchanged from the version the
terminal driver ran. Reading the diff would answer it once, today; these assert
the property that made it true, so it stays answered.

The property has a direction: adapters may depend on the agent, and the agent may
not depend on an adapter. Nothing enforces that in Python -- an `import streamlit`
in the tool layer would work perfectly and quietly weld the agent to one
interface -- so it is checked here, over the source rather than over behaviour,
because the point is what the code is allowed to reach.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "scinumbers_ask"

# The two interactive adapters. `messages` and `entries_table` are shared *by* them
# -- wording and a table both drivers present -- and belong on the presentation side
# of the line even though neither draws anything itself.
DRIVERS = {"cli", "web"}
# The evaluation harness is the third adapter, and it is on this side for the same
# reason the other two are: it drives the agent through the port and the agent must
# not be able to reach it. Listed apart from `DRIVERS` so a failure can say which
# kind of adapter was reached, and so the harness can be held to the extra rule
# below -- it may not reach for an interactive driver either. Names are added here
# as each module lands, and `test_every_named_adapter_exists` refuses a name with no
# file: a guard listing a module that was renamed protects nothing, and nothing else
# would say so.
HARNESS = {"question_set", "evaluation", "scoring", "report", "answer_sheet", "eval_cli"}
ADAPTERS = DRIVERS | HARNESS
# `autobuild` joins them: it decides whether to build a corpus, which is a driver's
# policy and not the agent's, and it is the one module allowed to import the
# ingester. Putting it on this side is what keeps that dependency out of the core.
PRESENTATION = ADAPTERS | {"messages", "entries_table", "autobuild"}

AGENT_CORE = sorted(
    path.stem
    for path in PACKAGE.glob("*.py")
    if path.stem not in PRESENTATION and not path.stem.startswith("__")
)


def imports_of(module: str) -> set[str]:
    """Every module name reached by an import in this module, however written."""
    tree = ast.parse((PACKAGE / f"{module}.py").read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # `from . import x, y` names the modules in the aliases; `from .x import y`
            # names it in the module. Both reach a sibling, so both count.
            if node.module:
                names.add(node.module.lstrip(".").split(".")[0])
            if node.level and not node.module:
                names.update(alias.name for alias in node.names)
    return names


def test_the_agent_core_is_not_empty():
    """A path typo would otherwise make every test below pass over nothing."""
    assert "agent" in AGENT_CORE and "tools" in AGENT_CORE and len(AGENT_CORE) > 5


def test_every_named_adapter_exists():
    """A name in these sets with no file behind it is a guard over nothing.

    `PRESENTATION` also decides `AGENT_CORE` by subtraction, so a stale name is
    silent in both directions: it asserts nothing itself, and it would exclude the
    module from the core the day someone created a file by that name.
    """
    missing = {name for name in PRESENTATION if not (PACKAGE / f"{name}.py").exists()}
    assert not missing, f"named as presentation but no such module: {sorted(missing)}"


@pytest.mark.parametrize("module", AGENT_CORE)
def test_no_agent_module_reaches_for_a_driver(module):
    reached = imports_of(module) & ADAPTERS
    kind = "the evaluation harness" if reached <= HARNESS else "a driver"
    assert not reached, (
        f"{module} imports {sorted(reached)} -- {kind}. The agent would no longer "
        f"be replaceable under one driver"
    )


@pytest.mark.parametrize("module", sorted(HARNESS))
def test_no_harness_module_reaches_for_an_interactive_driver(module):
    """The harness is an adapter, not a caller of the other adapters.

    Nothing above says this: the core is checked against every adapter, and the
    adapters are checked against `streamlit` only. So `question_set` could import
    `cli`, or the evaluation command could import `web`, and no test would fail --
    while the harness is the side about to grow four more modules.
    """
    reached = imports_of(module) & DRIVERS
    assert not reached, (
        f"{module} imports {sorted(reached)}; the harness would then need a "
        f"terminal or a web framework to run unattended"
    )


@pytest.mark.parametrize("module", AGENT_CORE)
def test_no_agent_module_reaches_for_the_web_framework(module):
    """`streamlit` in the agent is the whole failure in one line: it would run,
    and the terminal driver would be running a different agent from that moment."""
    assert "streamlit" not in imports_of(module)


def test_only_the_web_driver_knows_the_web_framework():
    users = {
        module.stem for module in PACKAGE.glob("*.py") if "streamlit" in imports_of(module.stem)
    }
    assert users == {"web"}


def test_both_drivers_put_questions_to_the_same_agent():
    """Same class, same method -- not two paths that happen to agree today."""
    from scinumbers_ask import cli, web
    from scinumbers_ask.agent import AskAgent

    assert cli.AskAgent is AskAgent
    assert web.AskAgent is AskAgent


def test_the_agent_takes_no_parameter_naming_its_caller():
    """It cannot behave one way for a person and another for the evaluation harness."""
    import inspect

    from scinumbers_ask.agent import AskAgent

    taken = set(inspect.signature(AskAgent.ask).parameters) | set(
        inspect.signature(AskAgent.__init__).parameters
    )
    assert not (taken & {"driver", "mode", "caller", "interactive", "web", "terminal"})
