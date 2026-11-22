"""Every way a question can end, built once and shared by the tests that need all of them.

Two suites assert a property across *all* endings rather than across the ones
somebody remembered: `test_agent.py` that each ends with a `QuestionEnded`, and
`test_question_and_answer_records.py` that each answer it emits is recorded. Those
enumerations must not drift apart -- one ending added to one copy and not the
other leaves the second suite silently checking ten branches out of eleven, which
is the shape of gap this project keeps finding.

**Both callers assert the set against `EndReason` itself, not a count.** The
count was the original form and it hid a real gap: nine builds reached eight
endings, the test asserted `== 8`, and `PROVIDER_LIMIT` -- the partial answer kept
when a key runs out of credit, which is the ending most likely to be rated down --
was reached by nothing. A number cannot tell you which member is missing, and
adding a tenth `EndReason` would not have failed anything. `COVERED` below is that
set, and `EndReason` gaining a member breaks it by construction.

Each entry is a zero-argument build returning `(agent, session_id)`. They are
builds rather than agents because several have to ask a question first to reach
the state they are named for, and one patches a module constant that outlives it.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.messages import AIMessage

from agent_doubles import OutOfCreditModel, costing, says, scripted, tool_call
from numera_ask.agent import AskAgent
from numera_ask.config import Config, usd
from numera_ask.events import EndReason

#: Every ending these builds reach. Asserted as a set so a new `EndReason` with no
#: build behind it fails loudly rather than passing a count nobody recomputed.
COVERED = frozenset(EndReason)


def ending_builds(repo, config, tmp_path, monkeypatch) -> tuple[Callable, ...]:
    """The eleven builds, in the order `test_agent.py` has always run them.

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
        monkeypatch.setattr("numera_ask.agent.CONVERSATION_BOUND", 1)
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

    def at_provider_limit():
        """A 402 part-way through, which is where a balance actually runs out.

        `refuse_after=1` rather than 0 deliberately: the first call establishes
        text and a retrieval, so this reaches the branch that keeps a partial
        answer. Refusing immediately reaches the same ending by a path that
        yields the canned notice instead, and the partial is the case worth
        driving -- it is the `Answer` a reader is shown and rates.
        """
        model = OutOfCreditModel(
            responses=[
                AIMessage(
                    content="Cell diameter is about 1.0-1.1 um [[100002]].",
                    tool_calls=[
                        {"name": "search_entries", "args": {"property": "Cell"}, "id": "c1"}
                    ],
                )
            ],
            refuse_after=1,
        )
        return agent_with(repo, config, tmp_path, model, "pl.sqlite"), "s"

    def internal_error():
        """Our own defect, not the provider's. Yields no `Answer` at all.

        Included even so: a caller enumerating endings wants every ending, and
        "this one emits no answer" is a fact worth having asserted rather than
        assumed.
        """
        model = scripted(tool_call("search_entries", property="x"), says("unreachable"))
        return (
            AskAgent(
                _FailingRepo(AttributeError("corpus schema changed")),
                config,
                str(tmp_path / "ie.sqlite"),
                model=model,
            ),
            "s",
        )

    return (
        normal,
        blank,
        provider_dead,
        call_limit,
        unconfigured,
        at_spend_ceiling,
        at_run_budget,
        unpriceable,
        at_provider_limit,
        internal_error,
        at_conversation_bound,
    )


class _FailingRepo:
    """A repository whose search always raises.

    Fault injection at a seam we control: a defect of ours reaching the tool
    layer is the only way to `EndReason.INTERNAL_ERROR`, and it must not be
    dressed up as the provider's fault or as "the corpus has nothing on this".
    """

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.attempts = 0

    def search(self, **kwargs):
        self.attempts += 1
        raise self.exc

    def get(self, *a, **k):
        return None

    def vocabulary(self, *a, **k):
        return ()
