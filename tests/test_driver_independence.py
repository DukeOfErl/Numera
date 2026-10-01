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
HARNESS = {
    "question_set",
    "evaluation",
    "scoring",
    "report",
    "answer_sheet",
    "eval_cli",
    # The enrolment command. Here for the same reason as the rest: an operator
    # runs it from a terminal against a deployment they are not looking at, so a
    # module that reached for `web` would need a browser to enrol anybody.
    # `neon` is deliberately *not* here -- it imports nothing but the standard
    # library, and leaving it in the core is the stricter of the two placements.
    "enrol",
    # The daily check. Runs from cron with nobody watching, so it may not reach
    # for a terminal or a browser either.
    "pending",
}
ADAPTERS = DRIVERS | HARNESS
# `autobuild` joins them: it decides whether to build a corpus, which is a driver's
# policy and not the agent's, and it is the one module allowed to import the
# ingester. Putting it on this side is what keeps that dependency out of the core.
PRESENTATION = ADAPTERS | {
    "messages",
    "entries_table",
    "autobuild",
    "feedback",
    "allowance",
    # The door's recorded examples: text and markup a visitor sees, never read by
    # the agent. Presentation by what it is, and placed here so it is not
    # counted as core by subtraction.
    "door_demo",
}

AGENT_CORE = sorted(
    path.stem
    for path in PACKAGE.glob("*.py")
    if path.stem not in PRESENTATION and not path.stem.startswith("__")
)


def _reached(dotted: str) -> str:
    """The module a dotted import path reaches, with this package's own prefix
    stripped -- so `scinumbers_ask.web` counts as `web`, not as `scinumbers_ask`.

    This was the blind spot a verifier found: `import scinumbers_ask.web as _w`
    inside `agent.py` passed every dependency-direction test here, because the
    first segment was the package and never a sibling's name. The relative form
    was caught; the absolute form of the same import was not. An absolute
    intra-package import is legal Python and a one-line edit, which is exactly
    the kind of thing this file exists to refuse.
    """
    parts = dotted.lstrip(".").split(".")
    if parts and parts[0] == PACKAGE.name and len(parts) > 1:
        return parts[1]
    return parts[0]


def imports_of(module: str) -> set[str]:
    """Every module name reached by an import in this module, however written --
    at top level or inside a function, relative or absolute."""
    tree = ast.parse((PACKAGE / f"{module}.py").read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(_reached(alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # `from . import x, y` names the modules in the aliases; `from .x import y`
            # names it in the module. Both reach a sibling, so both count.
            if node.module:
                names.add(_reached(node.module))
            if node.level and not node.module:
                names.update(alias.name for alias in node.names)
    return names


def test_the_import_rule_sees_the_absolute_form_too():
    """`import scinumbers_ask.web` and `from .web import x` reach the same module
    and must be read the same way; only one of them was."""
    assert _reached("scinumbers_ask.web") == "web"
    assert _reached(".web") == "web"
    assert _reached("scinumbers_ask") == "scinumbers_ask"
    assert _reached("streamlit.testing.v1") == "streamlit"


def test_the_agent_core_is_not_empty():
    """A path typo would otherwise make every test below pass over nothing."""
    assert "agent" in AGENT_CORE and "tools" in AGENT_CORE and len(AGENT_CORE) > 5


def test_the_agent_cannot_reach_a_reader_s_feedback():
    """`answer-feedback` requires that the model is never shown a rating or a
    comment. This is where that requirement has teeth.

    `feedback` sits in `PRESENTATION`, which is the opposite call from
    `trail_store` and for a principled reason: the core legitimately records its
    own trail, but feedback is a stranger's judgement *of* the core, and a
    comment is the only input in this system authored by someone outside it. An
    `import feedback` in `agent.py` or `tools.py` -- the plausible future edit
    being "improve the agent by feeding ratings back" -- fails
    `test_no_agent_module_reaches_for_a_driver` rather than passing silently.

    The enforcement is `test_no_agent_module_reaches_for_presentation`, not the
    parametrized test above it: that one checks `ADAPTERS`, which is the drivers
    and the harness, and `feedback` is in `PRESENTATION` — a superset. An earlier
    version of this module's docstring named the wrong test and so described a
    guarantee that did not exist.

    What is left here is the membership itself, which no other test states and
    which a later edit could quietly drop — and `PRESENTATION` shapes
    `AGENT_CORE` by subtraction, so dropping it would silently move `feedback`
    into the core rather than fail anything.
    """
    assert "feedback" in PRESENTATION
    assert "feedback" not in ADAPTERS, (
        "`feedback` is neither a driver nor a harness; if it is added to either, "
        "`test_no_harness_module_reaches_for_an_interactive_driver` starts asserting "
        "something untrue of it"
    )
    assert "feedback" not in AGENT_CORE


def test_the_durable_trail_sink_is_core_and_that_is_deliberate():
    """`trail_store` is on the agent's side of the line, chosen rather than fallen into.

    It arrives there by subtraction -- it is not in `PRESENTATION` -- and
    subtraction is silent, so a reader cannot tell a decision from an oversight.
    This test is where the decision is written down.

    The argument for the other side is real: recording to an external database
    looks like a driver's policy, which is why `autobuild` sits in `PRESENTATION`.
    What settles it is what the dependency rule protects against -- the agent
    becoming unrunnable without an interface. `trail_store` is a `logging.Handler`
    over an engine it is handed; it imports no framework and needs no terminal, so
    the core recording its own trail costs the core nothing. The driver supplies
    the engine and decides nothing else.

    `trace` is already core for exactly this reason, and a sink for the trail
    living on the far side of the line from the trail itself would be the odder
    arrangement.
    """
    assert "trail_store" in AGENT_CORE
    assert "streamlit" not in imports_of("trail_store")
    assert not imports_of("trail_store") & ADAPTERS


# The identity modules. Core by decision, like `trail_store`, and for a sharper
# reason: the refusal in `authorization` has to be reachable by a test or a second
# caller with no browser, and the grant table in `permissions` is the data that
# refusal reads. `accounts` reads enrolment off a row and imports no framework
# either; the driver hands it the engine. `test_every_named_core_module_exists`
# refuses a name here with no file behind it.
IDENTITY_CORE = {"permissions", "authorization", "accounts"}


def test_the_identity_modules_are_core_and_that_is_deliberate():
    """Where a refusal lives decides who can be refused.

    Put `authorization` on the presentation side and the only thing that can
    call it is a page -- so the page's hiding of a control becomes the guard,
    which is exactly the arrangement the spec forbids ("the refusal belongs to
    the action, not to the page that offers it"). On the core side, the panel's
    accessor calls `require` itself and every caller meets the same refusal.

    Being core costs the core nothing: neither module imports a framework. The
    parametrized tests below hold them to that, but only because they are in
    `AGENT_CORE` by subtraction -- and subtraction is silent, so this is where
    the decision is written down.
    """
    assert IDENTITY_CORE <= set(AGENT_CORE), sorted(IDENTITY_CORE - set(AGENT_CORE))
    for module in IDENTITY_CORE:
        assert "streamlit" not in imports_of(module)
        assert not imports_of(module) & PRESENTATION


def test_every_named_core_module_exists():
    """The mirror of `test_every_named_adapter_exists`, for the same reason."""
    missing = {name for name in IDENTITY_CORE if not (PACKAGE / f"{name}.py").exists()}
    assert not missing, f"named as core but no such module: {sorted(missing)}"


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


@pytest.mark.parametrize("module", AGENT_CORE)
def test_no_agent_module_reaches_for_presentation(module):
    """The rest of the presentation side, which the test above does not cover.

    `ADAPTERS` is the drivers plus the harness. `PRESENTATION` is those *plus*
    `messages`, `entries_table`, `autobuild` and `feedback` — and until this
    test existed, nothing checked the core against that difference. Membership of
    `PRESENTATION` shaped `AGENT_CORE` by subtraction and enforced nothing
    directly, so a core module importing `messages` for a bit of wording, or
    `agent.py` importing `feedback`, passed the suite.

    `feedback` is why this was noticed. `answer-feedback` requires that the model
    is never shown a rating or a comment, and the plausible regression is someone
    improving the agent by feeding ratings back. That has to fail here, not be
    described as failing somewhere it would not.

    Verified to add no failures when written: no core module imports any of the
    four today. It codifies a rule CLAUDE.md already states rather than inventing
    one.
    """
    reached = imports_of(module) & (PRESENTATION - ADAPTERS)
    assert not reached, (
        f"{module} imports {sorted(reached)}, which is presentation. The agent "
        f"would depend on what an interface shows, or on what a reader said about it"
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
    # Nor one naming the person. `add-user-identity` hands the agent a credential
    # and nothing else about who holds it; the role and the account are stamped
    # onto the trail at the sink, where this class cannot see them (ADR-0820).
    assert not (taken & IDENTITY_TOKENS), sorted(taken & IDENTITY_TOKENS)


# Identifiers that would mean identity had reached the code that decides an
# answer, records the trail, or records a reader's judgement. Checked as
# *identifiers* -- names, parameters, attributes, keywords, imports -- and not as
# text, because `agent.py` legitimately writes `{"role": "user"}` as a string and
# mentions an account in prose. A string is not a way for the role to arrive.
IDENTITY_TOKENS = {
    "Identity",
    "identity",
    "Role",
    "role",
    "email",
    "account",
    "user_role",
    "user_email",
}
# The three modules identity must never enter. `agent.py` decides the answer;
# `trace.py` builds the records; `feedback.py` records what a stranger said. All
# three get stamped by the web driver's filter without knowing, which is the
# design's whole point -- a parameter, a field or an import here would mean the
# side door had been opened.
#
# `hosted_trace.py` joins them: it is what sends a question to a third party, so
# identity reaching it would reach the tracer. Who asked arrives there only as an
# opaque digest the web driver passes to `attributed()` (ADR-1020).
IDENTITY_FREE = ("agent", "trace", "feedback", "hosted_trace")


def identifiers_of(module: str) -> set[str]:
    """Every identifier the module's source binds, reads, passes or imports."""
    tree = ast.parse((PACKAGE / f"{module}.py").read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[-1])
    return names


@pytest.mark.parametrize("module", IDENTITY_FREE)
def test_identity_never_enters_the_agent_the_trail_or_the_feedback(module):
    """The spec: "the role SHALL NOT reach the agent, and neither SHALL the
    account" -- made structural, so that it is a property of the source and not
    of the discipline of whoever edits it next.

    A seeded `role` parameter on `AskAgent.__init__` fails this; so does
    `from .permissions import Identity` in `trace.py`, or `feedback._record`
    taking an `email`. Group 7 of `add-user-identity` seeds the first of those in
    a copy and names this test as the one that must fail.
    """
    reached = identifiers_of(module) & IDENTITY_TOKENS
    assert not reached, f"{module}.py names {sorted(reached)}; identity has a way in"
    # And the modules themselves, whatever they are imported as. `permissions`
    # and `authorization` are core, so the core-to-core rules above allow the
    # import; this is the one place that forbids it for these three. A verifier
    # seeded `from .permissions import Identity, Role` into all three and the
    # suite stayed green until this line existed.
    imported = imports_of(module) & IDENTITY_CORE
    assert not imported, f"{module}.py imports {sorted(imported)}; identity has a way in"
    # What is still invisible here, measured rather than guessed: `getattr(self,
    # "role")`, `kwargs["role"]`, `globals()[...]` -- string keys. Each of them
    # needs the value to have arrived first, by a parameter, a field or an
    # import, and those three routes are what the two assertions above close.
    # The registry itself lives in `web`, so reading it needs an import of `web`,
    # which the dependency rule refuses in both spellings.


def test_the_identity_free_modules_exist_and_are_core():
    """A renamed module would make the test above pass over nothing."""
    for module in IDENTITY_FREE:
        assert (PACKAGE / f"{module}.py").exists(), module
    assert {"agent", "trace", "hosted_trace"} <= set(AGENT_CORE)
    assert "feedback" in PRESENTATION  # stamped from outside like the other two
