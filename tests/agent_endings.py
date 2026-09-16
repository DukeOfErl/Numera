"""Every way a question can end, built once and shared by the tests that need all of them.

Two suites now assert a property across *all* endings rather than across the ones
somebody remembered: `test_agent.py` that each ends with a `QuestionEnded`, and
`test_question_and_answer_records.py` that each answer it emits is recorded. Those
enumerations must not drift apart -- a ninth ending added to one copy and not the
other would leave the second suite silently checking eight branches out of nine,
which is the shape of gap this project keeps finding.

Each entry is a zero-argument build returning `(agent, session_id)`. They are
builds rather than agents because several have to ask a question first to reach
the state they are named for, and one patches a module constant that outlives it.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.messages import AIMessage

from agent_doubles import costing, says, scripted, tool_call
from scinumbers_ask.agent import AskAgent
from scinumbers_ask.config import Config, usd


def ending_builds(repo, config, tmp_path, monkeypatch) -> tuple[Callable, ...]:
    """The nine builds, in the order `test_agent.py` has always run them.

    `at_conversation_bound` stays last: it patches `CONVERSATION_BOUND` through
    `monkeypatch`, and that patch outlives the closure.
    """
    from conftest import agent_with

    def normal():
        return agent_with(repo, config, tmp_path, scripted(says("an answer")), "n.sqlite"), "s"

    def blank():
        return agent_with(repo, config, tmp_path, scripted(AIMessage(content="")), "b.sqlite"), "s"

    def provider_dead():
        return agent_with(repo, config, tmp_path, scripted(says("x"), failures=99), "p.sqlite"), "s"

    def call_limit():
        model = scripted(tool_call("search_entries", property="Cell"))
        return agent_with(repo, config, tmp_path, model, "l.sqlite"), "s"

    def unconfigured():
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        return AskAgent(repo, config, str(tmp_path / "u.sqlite")), "s"

    def at_conversation_bound():
        # Must ask once first: with a fresh session the bound is not yet reached,
        # so lowering it alone produced an ordinary answer rather than a refusal.
        # Last in the list, because the patched bound outlives this closure.
        monkeypatch.setattr("scinumbers_ask.agent.CONVERSATION_BOUND", 1)
        agent = agent_with(repo, config, tmp_path, scripted(says("a"), says("b")), "c.sqlite")
        list(agent.ask("s", "a first question, which fills the conversation"))
        return agent, "s"

    def at_spend_ceiling():
        tight = Config(model=config.model, question_ceiling=usd("0.000120"), run_budget=usd("1.20"))
        model = scripted(costing(tool_call("search_entries", property="Cell"), 0.000_200))
        return AskAgent(repo, tight, str(tmp_path / "sc.sqlite"), model=model), "s"

    def at_run_budget():
        budgeted = Config(
            model=config.model, question_ceiling=usd("0.60"), run_budget=usd("0.000050")
        )
        model = scripted(costing(says("an answer"), 0.000_110))
        agent = AskAgent(repo, budgeted, str(tmp_path / "rb.sqlite"), model=model)
        list(agent.ask("s", "a first question, which exhausts the budget"))
        return agent, "s"

    def unpriceable():
        model = scripted(says("an answer"), reports_cost=False)
        return agent_with(repo, config, tmp_path, model, "up.sqlite"), "s"

    return (
        normal,
        blank,
        provider_dead,
        call_limit,
        unconfigured,
        at_spend_ceiling,
        at_run_budget,
        unpriceable,
        at_conversation_bound,
    )
