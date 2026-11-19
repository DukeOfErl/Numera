"""The web driver: the session identifier it keeps, and the state it does not.

Streamlit re-runs the whole script on every interaction, so a driver built on it
starts from nothing each time. Everything the conversation needs comes back from
the checkpoint, reached through one identifier held in session state -- which is
the same property the terminal driver's `run()` demonstrates by being callable
twice, tested here against the framework that actually re-runs.

`AppTest` runs the real entry script in-process. It sees only the last value
written to any one screen location, which is why what the page draws is decided
in `web.items_for` and asserted there rather than read back off the page.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import FIXTURE, agent_with, ask_question
from streamlit.testing.v1 import AppTest

from agent_doubles import batched_tool_calls, costing, says, scripted, tool_call
from numera_ask import entries_table, messages, web
from numera_ask.agent import AskAgent
from numera_ask.cli import render
from numera_ask.corpus import load
from numera_ask.events import (
    Answer,
    AnswerEntries,
    CitationWarning,
    ConversationWarning,
    CostProjection,
    EndReason,
    QuestionEnded,
    QuestionStarted,
    Retrieval,
    SpendWarning,
)
from numera_ask.repository import CorpusRepository

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")

# Generous, and deliberately so: the default is three seconds, the first run in a
# process pays for component discovery, and a timeout here is indistinguishable
# from a hang in the agent.
TIMEOUT = 30

# The session-state keys feedback is allowed to keep, named exactly rather than
# matched by a wildcard: a rule that permitted anything under a namespace would
# permit the copies of the conversation and the spend it exists to forbid.
FEEDBACK_PREFIXES = (
    "numera_ask.feedback",
    "numera_ask.verdict.",
    "numera_ask.comment.",
)


def app(monkeypatch, repo, agent) -> AppTest:
    """The real script, with the corpus and agent a test chose.

    `resources` is replaced rather than driven through the environment because it
    is cached for the life of the process: a second test would be served the
    first one's agent.
    """
    monkeypatch.setattr(web, "resources", lambda corpus=None, store=None: repo)
    monkeypatch.setattr(web, "agent_for", lambda state, repo, admission: agent)
    return AppTest.from_file(APP, default_timeout=TIMEOUT)


ask = ask_question


# -- events become items --------------------------------------------------


def test_an_answer_becomes_an_answer_item():
    item = web.item_for(Answer(question_id="q", text="about 1 micrometre (BNID 100002)"))
    assert item.kind is web.Kind.ANSWER
    assert item.text == "about 1 micrometre (BNID 100002)"


def test_the_ending_reports_why_it_ended_what_it_cost_and_which_model():
    item = web.item_for(
        QuestionEnded(
            question_id="q",
            reason=EndReason.ANSWERED,
            spend=110,
            run_spend=220,
            model="fake/model",
            tool_calls=3,
        )
    )
    assert item.kind is web.Kind.ENDING
    assert "answered" in item.text
    assert "$0.000110" in item.text and "run $0.000220" in item.text
    assert "fake/model" in item.text and "3 tool calls" in item.text


def test_an_unfinished_question_says_so_rather_than_reading_as_an_answer():
    item = web.item_for(
        QuestionEnded(
            question_id="q",
            reason=EndReason.SPEND_CEILING,
            spend=110,
            run_spend=220,
            model="fake/model",
            tool_calls=3,
            incomplete=True,
        )
    )
    assert "incomplete" in item.text


def test_an_event_the_page_does_not_draw_yields_no_item():
    """The start of a question is the driver's cue, not something to say."""
    started = QuestionStarted(question_id="q", session_id="s", question="how wide?")
    assert web.item_for(started) is None


def test_the_stream_is_drained_in_order_and_only_once(repo, config, tmp_path):
    model = scripted(tool_call("search_entries", property="Cell"), says("an answer"))
    agent = agent_with(repo, config, tmp_path, model)

    items = web.items_for(agent.ask("s", "how wide?"))

    assert [item.kind for item in items] == [web.Kind.PROGRESS, web.Kind.ANSWER, web.Kind.ENDING]


# -- the session identifier ------------------------------------------------


def test_a_first_run_creates_a_session_identifier(monkeypatch, repo, config, tmp_path):
    at = app(monkeypatch, repo, agent_with(repo, config, tmp_path, scripted(says("a")))).run()
    assert at.session_state[web.SESSION_KEY]


def test_the_identifier_survives_a_re_run(monkeypatch, repo, config, tmp_path):
    """A re-run is what every interaction causes, so this is the whole claim."""
    at = app(monkeypatch, repo, agent_with(repo, config, tmp_path, scripted(says("a")))).run()
    first = at.session_state[web.SESSION_KEY]

    at.run()

    assert at.session_state[web.SESSION_KEY] == first


def test_two_browser_sessions_do_not_share_an_identifier(monkeypatch, repo, config, tmp_path):
    """Otherwise one visitor's conversation would continue in another's tab."""
    model = scripted(says("a"))
    one = app(monkeypatch, repo, agent_with(repo, config, tmp_path, model, "1.sqlite")).run()
    two = app(monkeypatch, repo, agent_with(repo, config, tmp_path, model, "2.sqlite")).run()

    assert one.session_state[web.SESSION_KEY] != two.session_state[web.SESSION_KEY]


def test_the_identifier_is_generated_rather_than_read_from_an_empty_state():
    state: dict = {}
    first = web.session_id(state, {})
    assert web.session_id(state, {}) == first
    assert web.session_id({}, {}) != first


# -- a question, and the one after it --------------------------------------


def test_a_question_is_put_to_the_agent_and_its_answer_drawn(monkeypatch, repo, config, tmp_path):
    model = scripted(
        tool_call("search_entries", property="Cell"), says("about 1 micrometre (BNID 100002)")
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    assert "about 1 micrometre (BNID 100002)" in [m.value for m in at.markdown]
    assert any("answered" in c.value for c in at.caption)


def test_a_follow_up_continues_the_conversation_rather_than_starting_one(
    monkeypatch, repo, config, tmp_path
):
    """The identifier is only worth keeping if it reaches the same conversation."""
    model = scripted(says("first answer"), says("second answer"))
    agent = agent_with(repo, config, tmp_path, model)
    at = app(monkeypatch, repo, agent).run()

    ask(at, "how wide is an E. coli cell?")
    session = at.session_state[web.SESSION_KEY]
    assert agent.conversation_length(session) == 2

    ask(at, "and yeast?")
    assert agent.conversation_length(session) == 4, "the follow-up began a fresh conversation"


def test_both_questions_and_answers_stay_on_screen_across_the_re_run(
    monkeypatch, repo, config, tmp_path
):
    model = scripted(says("first answer"), says("second answer"))
    at = app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run()

    ask(at, "how wide is an E. coli cell?")
    at = ask(at, "and yeast?")

    drawn = [m.value for m in at.markdown]
    assert drawn.index("how wide is an E. coli cell?") < drawn.index("first answer")
    assert drawn.index("first answer") < drawn.index("and yeast?") < drawn.index("second answer")


# -- the driver holds no agent state ---------------------------------------


def test_spend_is_the_ledger_s_rather_than_something_the_page_added_up(
    monkeypatch, repo, config, tmp_path
):
    """Two re-runs, and the run total still comes from the checkpoint."""
    model = scripted(costing(says("first"), 0.000_110), costing(says("second"), 0.000_110))
    agent = agent_with(repo, config, tmp_path, model)
    at = app(monkeypatch, repo, agent).run()

    ask(at, "first")
    at = ask(at, "second")

    assert agent.run_spend() == 220
    assert any(r"run \$0.000220" in c.value for c in at.caption)


def test_session_state_holds_the_identifier_and_what_was_drawn_and_nothing_else(
    monkeypatch, repo, config, tmp_path
):
    """A copy of the conversation, the spend or the ceiling here would be a
    second source of truth for something the checkpoint already owns.

    Feedback is the one exception, and it is allowed by name rather than by
    loosening the rule. What a reader has rated *in this session* is not
    something the checkpoint owns: the durable record is a row in the trail, and
    this is only what stops a redraw recording the same judgement twice. It
    disappears with the session, and losing it costs at most one duplicate.

    The question box's key is the second exception, and a different kind. It is
    not state this driver keeps at all -- it is a Streamlit widget's own value,
    which lands in session state because the widget was given a key. It is given
    one so the page can read, before it draws anything, whether a question is
    about to run: every control already on screen is live while that run works,
    and a click on one abandons the agent's generator mid-tool-call.

    The tab's own identifier is the third, and it is here for the reason the
    session identifier is: it is an identity this driver mints and must keep,
    because the session cap counts browser sessions and a browser session is
    exactly what this dictionary outlives nothing of. It cannot come from the
    URL -- that is the conversation's token, which anyone holding the link can
    supply (ADR-0830).

    The rule keeps its teeth: anything else namespaced here still fails, and the
    allowance is a prefix rather than a wildcard, so `numera_ask.spend` or a
    second copy of the conversation would still be caught.
    """
    model = scripted(says("an answer"))
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    kept = {k for k in at.session_state.filtered_state if k.startswith("numera_ask.")}
    feedback_keys = {k for k in kept if k.startswith(FEEDBACK_PREFIXES)}
    assert kept - feedback_keys == {
        web.SESSION_KEY,
        web.TAB_KEY,
        web.TRANSCRIPT_KEY,
        web.ASK_KEY,
    }


def test_a_missing_corpus_is_explained_rather_than_raised(monkeypatch):
    from numera_ask.corpus import CorpusUnavailable

    def unavailable(corpus=None, store=None):
        raise CorpusUnavailable("no corpus was supplied")

    monkeypatch.setattr(web, "resources", unavailable)
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    assert not at.exception
    assert "no corpus was supplied" in [e.value for e in at.error]


# -- what the markdown renderer would misread ------------------------------


def test_a_cost_keeps_its_currency_sign_rather_than_opening_an_equation():
    """Two dollar signs in one line made Streamlit typeset the cost between them.

    The ending carries a per-question figure and a run figure, so the pair is on
    every line the page draws: "$0.008181 (run $0.008181)" rendered as mathematics
    with both signs eaten, leaving a bare number with no currency on it.
    """
    assert web.as_text("$0.008181 (run $0.008181)") == r"\$0.008181 (run \$0.008181)"


def test_the_ending_the_page_draws_is_escaped(monkeypatch, repo, config, tmp_path):
    model = scripted(costing(says("an answer"), 0.000_110))
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    ending = next(c.value for c in at.caption if "answered" in c.value)
    assert r"\$0.000110" in ending
    assert "$0.000110" not in ending.replace(r"\$", "")


def test_an_answer_is_escaped_too_since_a_model_may_write_a_dollar_sign(
    monkeypatch, repo, config, tmp_path
):
    model = scripted(says("about $5 of glucose"))
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "cost?")

    assert r"about \$5 of glucose" in [m.value for m in at.markdown]


# -- the indexes are built once, not per interaction -----------------------


@pytest.fixture
def counted(monkeypatch, tmp_path):
    """The real cached `resources()`, with the file read and the index build counted.

    The other tests here replace `resources` wholesale, which bypasses the cache
    entirely -- so the caching is exactly the thing they cannot see. This drives
    the real one and counts what happens inside it.

    `st.cache_resource` holds its entry in the function for the life of the
    process, not in the per-run storage the harness replaces, so it has to be
    cleared on both sides or one test is served another's corpus.
    """
    web.resources.clear()
    counts = {"read": 0, "indexed": 0}
    rows = load(FIXTURE)

    def counting_load(path, store=None):
        counts["read"] += 1
        return rows

    def counting_repository(entries):
        counts["indexed"] += 1
        return CorpusRepository(entries)

    monkeypatch.setattr(web, "load_configured", counting_load)
    monkeypatch.setattr(web, "CorpusRepository", counting_repository)
    monkeypatch.setattr(web.trace, "to_file", lambda spec: None)
    monkeypatch.setenv("NUMERA_CHECKPOINTS", str(tmp_path / "c.sqlite"))
    yield counts
    web.resources.clear()


def test_the_corpus_is_read_and_indexed_once_however_often_the_script_re_runs(counted):
    """Every interaction re-runs the whole script; the index must not follow it."""
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    at.run()
    at.run()

    assert counted == {"read": 1, "indexed": 1}


def test_a_second_browser_session_is_served_the_same_index(counted):
    """The point of a resource cache rather than session state: one index, not one each."""
    AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    assert counted == {"read": 1, "indexed": 1}


def test_the_page_is_served_the_index_that_was_built(counted):
    """Cached and correct are separate claims; a cache returning nothing passes the first."""
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    assert any("6 entries" in c.value for c in at.caption)


# -- progress, drawn while the question is still running -------------------


def test_a_retrieval_becomes_a_progress_item_naming_the_tool_and_its_argument():
    item = web.item_for(
        Retrieval(
            question_id="q",
            tool="search_entries",
            detail={"property": "Cell volume", "matched": 12},
        )
    )
    assert item.kind is web.Kind.PROGRESS
    assert "search_entries" in item.text
    assert "'Cell volume'" in item.text and "matched=12" in item.text


def test_the_identifiers_a_search_returned_stay_off_the_progress_line():
    """Fifty identifiers would bury what the search was actually for."""
    item = web.item_for(
        Retrieval(
            question_id="q",
            tool="search_entries",
            detail={"property": "Cell", "entry_ids": [100001, 100002]},
        )
    )
    assert "entry_ids" not in item.text and "100001" not in item.text


def test_progress_reaches_the_page_in_order_before_the_answer(monkeypatch, repo, config, tmp_path):
    """The point of the whole exercise: the page is not blank while work happens."""
    model = scripted(
        batched_tool_calls(
            ("search_entries", {"property": "Cell"}),
            ("list_values", {"field": "organism", "term": "coli"}),
        ),
        says("about 1 micrometre (BNID 100002)"),
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    progress = [c.value for c in at.caption if c.value.startswith("·")]
    assert len(progress) == 2, progress
    assert any("search_entries" in line for line in progress)


def test_each_retrieval_is_its_own_element_rather_than_one_line_rewritten(
    monkeypatch, repo, config, tmp_path
):
    """A rewritten line composes into its last value and the sequence is lost."""
    model = scripted(
        tool_call("search_entries", property="Cell"),
        tool_call("get_entry", entry_id=100002),
        says("an answer"),
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    progress = [c.value for c in at.caption if c.value.startswith("·")]
    assert len(progress) == 2, "one retrieval overwrote the other"
    assert "search_entries" in progress[0] and "get_entry" in progress[1]


def test_a_question_that_retrieved_nothing_draws_no_retrieval_box(
    monkeypatch, repo, config, tmp_path
):
    """An empty box claims a search that never happened.

    Driven through `AppTest` rather than over items, because the defect is not in
    what the items say -- there are no progress items at all -- but in an element
    the driver creates on its own. Nothing below the script can see it.
    """
    model = scripted(says("I could not answer this."))
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    assert [box.label for box in at.status] == []


def test_a_question_that_retrieved_something_still_draws_the_box(
    monkeypatch, repo, config, tmp_path
):
    """The other direction: the fix must not be "never draw it".

    The two differ only in whether a retrieval happened, which is the one thing the
    rule reads.
    """
    model = scripted(
        tool_call("search_entries", property="Cell"),
        says("about 1 micrometre (BNID 100002)"),
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    assert len(at.status) == 1 and at.status[0].label.startswith("Searched “Cell”")


# -- warnings are said, not swallowed --------------------------------------


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (SpendWarning(question_id="q", spent=600, threshold=500), "past the"),
        (CostProjection(question_id="q", projected=900, threshold=500), "could cost up to"),
        (
            ConversationWarning(question_id="q", tokens=90_000, bound=120_000),
            "90,000 of 120,000 tokens",
        ),
        (CitationWarning(question_id="q", unknown=(999999,)), "not in the corpus"),
        (CitationWarning(question_id="q", unretrieved=(100002,)), "cited without being retrieved"),
    ],
)
def test_every_warning_becomes_an_item(event, expected):
    item = web.item_for(event)
    assert item is not None, "a warning the page would never show"
    assert item.kind is web.Kind.WARNING
    assert expected in item.text


def test_the_two_drivers_word_a_warning_identically():
    """Same fact, same sentence. The terminal adds a marker and nothing else."""
    event = SpendWarning(question_id="q", spent=600, threshold=500)
    assert render(event).strip(" !") == web.item_for(event).text


def test_a_citation_warning_reaches_the_page(monkeypatch, repo, config, tmp_path):
    """It was silently dropped before: an answer citing what it never retrieved looked clean."""
    model = scripted(says("about 1 micrometre (BNID 100002)"))
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    assert any("cited without being retrieved" in w.value for w in at.warning)


# -- 8.4: the session survives the server ----------------------------------


def test_the_identifier_is_published_to_the_url(monkeypatch, repo, config, tmp_path):
    at = app(monkeypatch, repo, agent_with(repo, config, tmp_path, scripted(says("a")))).run()
    assert at.query_params[web.QUERY_KEY] == [at.session_state[web.SESSION_KEY]]


def test_a_url_identifier_is_adopted_rather_than_replaced():
    state: dict = {}
    assert web.session_id(state, {web.QUERY_KEY: "abc12345"}) == "abc12345"


def test_session_state_wins_over_a_url_edited_mid_session():
    """Otherwise pasting a link into the address bar would silently switch sessions."""
    state = {web.SESSION_KEY: "original"}
    assert web.session_id(state, {web.QUERY_KEY: "someone-elses"}) == "original"


def test_a_follow_up_continues_the_conversation_after_a_restart(
    monkeypatch, repo, config, tmp_path
):
    """8.4. A restart loses session state; the checkpoint and the URL survive it.

    The second AppTest is a new server process as far as the driver can tell:
    nothing carries over but the checkpoint file on disk and the identifier in
    the link the browser reloads.
    """
    store = str(tmp_path / "restart.sqlite")
    first = agent_with(repo, config, tmp_path, scripted(says("first answer")), "restart.sqlite")
    at = app(monkeypatch, repo, first).run()
    ask(at, "how wide is an E. coli cell?")
    session = at.session_state[web.SESSION_KEY]
    assert first.conversation_length(session) == 2

    # The server restarts: a new agent over the same store, and a page that knows
    # only what the URL carried.
    restarted = AskAgent(repo, config, store, model=scripted(says("second answer")))
    monkeypatch.setattr(web, "agent_for", lambda state, repo, admission: restarted)
    after = AppTest.from_file(APP, default_timeout=TIMEOUT)
    after.query_params = {web.QUERY_KEY: session}
    after.run()

    assert after.session_state[web.SESSION_KEY] == session, "the restart orphaned the session"
    ask(after, "and yeast?")
    assert restarted.conversation_length(session) == 4, "the follow-up began a fresh conversation"


def test_without_the_url_a_restart_starts_a_new_session(monkeypatch, repo, config, tmp_path):
    """The negative half: what the URL is actually carrying."""
    at = app(monkeypatch, repo, agent_with(repo, config, tmp_path, scripted(says("a")))).run()
    session = at.session_state[web.SESSION_KEY]

    fresh = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    assert fresh.session_state[web.SESSION_KEY] != session


# -- 8.6: the entries table ------------------------------------------------


def entries(cited=(100002,), retrieved=(100002, 100001), **kwargs):
    return AnswerEntries(question_id="q", cited=cited, retrieved=retrieved, **kwargs)


def test_the_table_needs_the_corpus_since_the_event_carries_only_identifiers(repo):
    assert web.item_for(entries()) is None
    assert web.item_for(entries(), repo).kind is web.Kind.ENTRIES


def test_a_question_that_retrieved_nothing_draws_no_table(repo):
    assert web.item_for(entries(cited=(), retrieved=()), repo) is None


def test_the_cited_entries_come_first(repo):
    table = web.item_for(entries(cited=(100002,), retrieved=(100001, 100002)), repo).table
    assert [row.entry_id for row in table.rows][0] == 100002
    assert [row.cited for row in table.rows] == [True, False]


def test_an_opened_entry_names_itself_and_its_identifier(monkeypatch, repo, config, tmp_path):
    model = scripted(
        tool_call("get_entry", entry_id=100002), says("about 1 micrometre (BNID 100002)")
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")
    at.main.get("button_group")[0].set_value(1).run()
    drawn = [m.value for m in at.main.markdown]
    assert "**Entry 1** · `BNID 100002`" in drawn
    assert "**Cell diameter**" in drawn


def test_a_row_without_a_recorded_method_is_marked(repo):
    """The corpus records no method for 100002, and a marked row says so, after its value."""
    table = web.item_for(entries(), repo).table
    row = next(r for r in table.rows if r.entry_id == 100002)
    assert not row.method_recorded
    value = re.search(r'<td class="sn-v">(.*?)</td>', web.evidence_html((row,), {})).group(1)
    assert entries_table.NO_METHOD in value


def test_every_retrieved_entry_is_reachable(monkeypatch, repo, config, tmp_path):
    """Every row is carried: with no side panel, the evidence list is where each one is reached."""
    every = tuple(entry.entry_id for entry in load(FIXTURE))
    table = web.item_for(entries(cited=(), retrieved=every), repo).table
    assert len(table.rows) == len(every) > 2, "rows were dropped rather than carried"


def test_the_table_reaches_the_main_column_as_a_table(monkeypatch, repo, config, tmp_path):
    model = scripted(
        tool_call("get_entry", entry_id=100002), says("about 1 micrometre (BNID 100002)")
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    tables = [h.proto.body for h in at.main.get("html") if 'class="sn-ev"' in h.proto.body]
    assert tables, "no evidence list was drawn"
    assert any("Evidence for this answer" in m.value for m in at.markdown)


def test_an_entry_opens_beside_the_answer_not_in_the_side_panel(
    monkeypatch, repo, config, tmp_path
):
    """ADR-1850: chosen by number under the list, opened in the evidence column."""
    model = scripted(
        tool_call("get_entry", entry_id=100002), says("about 1 micrometre (BNID 100002)")
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    assert at.main.get("button_group"), "no way to open an entry"
    assert not any(m.value.startswith("**Entry") for m in at.main.markdown), "open by default"
    at.main.get("button_group")[0].set_value(1).run()
    assert any(m.value.startswith("**Entry 1** · `BNID 100002`") for m in at.main.markdown)
    assert not [e for e in at.sidebar.expander if e.label != messages.PRIVACY_HEADING]
    assert not at.sidebar.tabs, "one sidebar view needs no tab strip"


def test_an_opened_row_shows_the_entry_the_model_never_saw(monkeypatch, repo, config, tmp_path):
    """The reference is looked up for display and never travels through the agent."""
    model = scripted(
        tool_call("get_entry", entry_id=100002), says("about 1 micrometre (BNID 100002)")
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    at.main.get("button_group")[0].set_value(1).run()
    drawn = " ".join(c.value for c in at.caption) + " ".join(m.value for m in at.markdown)
    assert "Nelson DE. J Bacteriol. 2000 p.1719" in drawn


def test_the_cited_and_uncited_entries_are_separated(repo):
    """The requirement is the separation, not the terminal's dashed banner."""
    table = web.item_for(entries(cited=(100002,), retrieved=(100001, 100002)), repo).table
    assert [row.cited for row in table.rows] == [True, False], "not ordered for a break"


def test_the_panel_carries_every_entry_however_the_table_is_capped(repo):
    every = tuple(entry.entry_id for entry in load(FIXTURE))
    table = web.item_for(entries(cited=(), retrieved=every), repo).table
    assert len(table.rows) == len(every), "the panel would be missing entries"


def test_an_entry_with_no_scalar_is_marked_and_its_value_left_blank():
    """Repeating "(no scalar value)" in every such row crowds out the values that are there.

    Built here rather than read from the fixture, which holds no such entry: a
    test that reaches for one and silently skips when it is absent is a test that
    passes without running.
    """
    row = entries_table.Row(
        entry_id=106614,
        property="Length, diameter, volume",
        organism="Bacteria Escherichia coli",
        value="(no scalar value)",
        units="N/A",
        reference="Prats R. J Bacteriol. 1989",
        cited=False,
        has_scalar=False,
    )
    markup = web.evidence_html((row,), {"106614": 1})
    value = re.search(r'<td class="sn-v">(.*?)</td>', markup).group(1)
    assert "(no scalar value)" not in value, "the placeholder was repeated in the value column"
    # After the value, which is what a mark qualifies (ADR-1850), and not on the property.
    assert entries_table.NO_SCALAR in value
    assert "<td>Length, diameter, volume<" in markup
    assert entries_table.NO_SCALAR_LEGEND in web._legend((row,))


def test_the_legend_comes_before_the_table_and_only_for_marks_in_use(repo):
    table = web.item_for(entries(), repo).table
    legend = web._legend(table.rows)
    assert entries_table.NO_METHOD_LEGEND in legend
    assert entries_table.NOT_RETRIEVED_LEGEND not in legend, "explained a mark nothing carries"


def test_injected_markup_is_stripped_from_keywords_for_display(repo):
    """10,206 of the corpus's 14,294 entries carry `<IMG SRC=...>` in `keywords`."""
    rows = entries_table.rows_for(repo, (), (100001,), "")
    assert rows[0].keywords
    assert not any("<" in keyword for keyword in rows[0].keywords)


def test_the_first_view_says_what_the_page_is_for(monkeypatch, repo, config, tmp_path):
    """ADR-1850: a heading, a paragraph, questions to start from; the evidence column waiting."""
    at = app(monkeypatch, repo, agent_with(repo, config, tmp_path, scripted(says("a")))).run()

    assert "Ask about a scientific quantity" in [h.value for h in at.subheader]
    labels = [b.label for b in at.button]
    assert all(question in labels for question in web.EXAMPLES)
    assert any("entries behind each answer appear here" in c.value for c in at.caption)
    entries = [e for e in at.sidebar.expander if e.label != messages.PRIVACY_HEADING]
    assert not entries, "entries before anything was retrieved"


def test_an_example_question_asks_itself(monkeypatch, repo, config, tmp_path):
    model = scripted(says("about 1 micrometre"))
    at = app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run()
    next(b for b in at.button if b.label == web.EXAMPLES[0]).click().run()
    assert not at.exception
    assert any(web.EXAMPLES[0] in m.value for m in at.markdown), "the question was not asked"
    assert any("about 1 micrometre" in m.value for m in at.markdown)
    assert "Ask about a scientific quantity" not in [h.value for h in at.subheader]


def test_the_legend_sits_under_the_cited_list(monkeypatch, repo, config, tmp_path):
    """Under the list it explains, for the marks shown (ADR-1850)."""
    model = scripted(
        tool_call("search_entries", property="Cell"), says("about 1 micrometre (BNID 100002)")
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    assert any("Evidence for this answer" in m.value for m in at.markdown)
    assert any(entries_table.NO_METHOD_LEGEND in c.value for c in at.caption)


def test_an_identifier_is_shown_as_the_prose_cites_it(repo):
    """As a number it picked up a thousands separator and stopped reading as a BNID."""
    markup = web.evidence_html(web.item_for(entries(), repo).table.rows, {})
    assert '<span class="sn-id">BNID 100002</span>' in markup


def many(cited_count: int, uncited_count: int) -> tuple[entries_table.Row, ...]:
    """Rows enough to show that nothing is capped, cited first as `rows_for` orders them."""

    def row(i: int, cited: bool) -> entries_table.Row:
        return entries_table.Row(
            entry_id=100000 + i,
            property=f"Property {i}",
            organism="Bacteria Escherichia coli",
            value="1.0",
            units="um",
            reference="A reference",
            cited=cited,
        )

    return tuple(row(i, True) for i in range(cited_count)) + tuple(
        row(100 + i, False) for i in range(uncited_count)
    )


def test_every_entry_is_in_the_list_with_no_cap(repo):
    """With no side panel, a cap would hide an entry the answer rests on (ADR-1850)."""
    rows = many(cited_count=15, uncited_count=9)
    numbers = web.entry_numbers([[web.Item(web.Kind.ENTRIES, table=web.Table(rows))]])
    cited = web.evidence_html([r for r in rows if r.cited], numbers)
    rest = web.evidence_html([r for r in rows if not r.cited], numbers)
    assert cited.count("<tr>") == 15 + 1 and rest.count("<tr>") == 9 + 1


def test_nothing_is_announced_when_every_cited_entry_is_shown(monkeypatch, repo, config, tmp_path):
    model = scripted(tool_call("get_entry", entry_id=100002), says("about 1 um (BNID 100002)"))
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    assert not any("more cited" in w.value for w in at.warning)


def test_an_answer_that_cited_nothing_says_so_where_the_cited_table_would_be(
    monkeypatch, repo, config, tmp_path
):
    """A table that simply began with uncited rows read as though it had cited them."""
    model = scripted(tool_call("search_entries", property="Cell"), says("I could not find it."))
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    headings = [m.value for m in at.markdown]
    assert any(entries_table.NOTHING_CITED in h for h in headings), headings
    # The uncited rows are folded away, under a label that says what they are.
    assert any("retrieved but not cited" in e.label for e in at.expander)


def test_the_uncited_rows_are_folded_away_and_the_cited_ones_are_not(
    monkeypatch, repo, config, tmp_path
):
    """The asymmetry is the point, not the folding.

    The cited rows are what the prose stands on: a reader checking an answer
    against its evidence must not have to open anything to see them. The uncited
    rows are what it did *not* stand on -- context, and length in front of that
    reader.
    """
    model = scripted(
        tool_call("search_entries", property="Cell"), says("about 1 micrometre (BNID 100002)")
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    folded = at.main.expander
    assert len(folded) == 1, [e.label for e in folded]
    assert "retrieved but not cited" in folded[0].label
    assert not folded[0].proto.expanded, "the uncited rows were not folded away"
    assert any('class="sn-ev"' in h.proto.body for h in folded[0].get("html")), "the fold is empty"
    lists = [h for h in at.main.get("html") if 'class="sn-ev"' in h.proto.body]
    assert len(lists) == 2, "the cited list is behind the fold too, or missing"


def test_the_uncited_heading_says_what_the_rows_are_not_only_what_they_are_not():
    """They are ranked by closeness to the question, so "possibly relevant" is a fact."""
    assert "possibly relevant" in entries_table.UNCITED_BANNER
    assert "not cited" in entries_table.UNCITED_BANNER


def test_how_much_went_unlooked_at_is_body_text_not_a_footnote(monkeypatch, repo, config, tmp_path):
    """It is one of the few things a reader can judge an answer's worth by."""
    model = scripted(
        tool_call("search_entries", property="Cell", limit=1),
        says("about 1 micrometre (BNID 100002)"),
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    body = [m.value for m in at.markdown]
    assert any("entries retrieved" in line for line in body), body
    assert not any("entries retrieved" in c.value for c in at.caption), "still a caption"


# -- what the review found -------------------------------------------------


def test_a_citation_with_nothing_retrieved_still_draws_its_row(repo):
    """The fabricated-citation case, and the one where the table matters most.

    The page warns that an entry was cited without being retrieved; the rows are
    the evidence a reader would check that against. Guarding on `event.retrieved`
    dropped the whole table exactly there, so the warning arrived with nothing
    behind it -- while the terminal drew the row marked as not retrieved.
    """
    item = web.item_for(entries(cited=(100001,), retrieved=()), repo)
    assert item is not None and item.kind is web.Kind.ENTRIES
    assert [row.entry_id for row in item.table.rows] == [100001]
    assert not item.table.rows[0].retrieved
    # The same fact reaches the terminal, and has all along.
    assert entries_table.NOT_RETRIEVED in render(entries(cited=(100001,), retrieved=()), repo)


def test_the_summary_is_not_drawn_when_it_would_undercount_what_is_shown(repo):
    """`rows` counts cited entries too, `retrieved` does not, so a table showing
    three cited rows against one retrieved read 'showing 4 of 1 entries retrieved'.
    The terminal guards this; the web called it unconditionally."""
    item = web.item_for(
        entries(cited=(100001, 100002, 100003), retrieved=(100010,), matched=1), repo
    )
    shown = len(item.table.rows)
    assert shown > item.table.retrieved, "the case that produced the nonsense"
    assert "of 1 entries" in entries_table.summarise(
        shown, item.table.retrieved, item.table.matched, item.table.searches
    ), "ungated, this is the sentence"
    assert web.summary_for(item.table, shown) == "", "and the page must not draw it"
    # Still drawn where it says something true.
    assert web.summary_for(web.Table(item.table.rows, retrieved=99, matched=99), shown)


def _answer(text, *known):
    return web.Item(web.Kind.ANSWER, text, known=tuple(str(k) for k in known))


def test_entries_are_numbered_in_the_order_the_session_meets_them(repo):
    """ADR-1850: the answer's citations first, as they appear, then the turn's other rows."""
    first = [
        _answer("[[100003]] then [[100002]]", 100003, 100002),
        web.item_for(entries(cited=(100002, 100003), retrieved=(100002, 100003, 100001)), repo),
    ]
    numbers = web.entry_numbers([first])
    assert numbers == {"100003": 1, "100002": 2, "100001": 3}


def test_a_later_answer_keeps_an_entry_s_number(repo):
    first = [_answer("[[100002]]", 100002)]
    second = [_answer("[[100001]] and [[100002]]", 100001, 100002)]
    numbers = web.entry_numbers([first, second])
    assert numbers["100002"] == 1 and numbers["100001"] == 2
    # Drawn again from the same transcript -- a rerun -- nothing moves.
    assert web.entry_numbers([first, second]) == numbers


def test_an_identifier_the_corpus_does_not_hold_is_not_numbered(repo):
    """The item knows only what the corpus holds; the rest stays as written in the prose."""
    item = web.item_for(Answer(question_id="q", text="[[100002]] [[999999]]"), repo)
    assert item.known == ("100002",)
    assert web.entry_numbers([[item]]) == {"100002": 1}


def ending(reason, **kwargs):
    return QuestionEnded(
        question_id="q",
        reason=reason,
        spend=10,
        run_spend=10,
        model="m",
        tool_calls=0,
        **kwargs,
    )


@pytest.mark.parametrize("reason", sorted(messages.STOP_THE_RUN, key=lambda r: r.value))
def test_an_ending_that_stops_the_terminal_stops_the_page(reason):
    """Same agent, same events, same answer to 'may I ask another?'. The page used
    to keep the input live and replay an identical refusal for ever, which reads as
    a broken app rather than a limit reached."""
    item = web.item_for(ending(reason))
    assert item.ends_the_run
    assert web.run_is_over([("q", [item])])


def test_the_run_closing_is_said_on_the_run_that_closes_it(monkeypatch, repo):
    """Not one interaction later, which is what the page used to do.

    The banner is decided before the chat input, so on the run where the question is
    asked `run_is_over` is read *before* the ending exists. Streamlit reruns on the
    next interaction and not when a script finishes, so the reader was left with a
    live input on a closed run and no line saying why -- and only a reload revealed
    it. Seen on the deployed app's first question: a spent key, and nothing on the
    page to say so.

    Asserted through the real script, because the fault was in the ordering of one
    run and no test of `run_is_over` or `ends_the_run` can see that: both were right
    the whole time.
    """

    class SpentKey:
        def ask(self, session_id, question):
            yield Answer(question_id="q", text="I could not answer this.")
            yield ending(EndReason.PROVIDER_LIMIT, incomplete=True)

        def run_spend(self) -> int:
            return 0

        run_budget = 1_200_000

    at = ask(app(monkeypatch, repo, SpentKey()).run(), "hi")

    assert any("usage limit" in error.value for error in at.error), (
        "the reader has to be told on the run that closed, not after a reload"
    )
    assert not at.chat_input, "and not left an input that cannot produce a new answer"


def test_a_question_stopped_on_its_own_ceiling_does_not_stop_the_run():
    """The per-question ceiling refreshes; the run budget does not."""
    item = web.item_for(ending(EndReason.SPEND_CEILING))
    assert not item.ends_the_run
    assert not web.run_is_over([("q", [item])])


@pytest.mark.parametrize("reason", [EndReason.PROVIDER_LIMIT, EndReason.NOT_CONFIGURED])
def test_an_ending_a_new_session_cannot_fix_replaces_that_advice(reason):
    """The banner is the last thing on screen, so wrong advice there outranks the
    answer above it -- and for both of these the next session's first question meets
    the identical refusal."""
    advice = web.run_over_advice([("q", [web.item_for(ending(reason))])])
    assert "new session will not help" in advice


def test_the_advice_names_the_remedy_without_addressing_anyone():
    """One wording for two readers: someone on a hosted instance, and the developer
    running the same code on their own key. "Ask whoever deployed the app" told the
    second reader to contact themselves."""
    advice = web.run_over_advice([("q", [web.item_for(ending(EndReason.PROVIDER_LIMIT))])])
    assert "whoever funds it" in advice
    assert "ask" not in advice.lower(), "no second person: the local reader is the funder"


def test_an_ending_a_new_session_does_fix_leaves_the_page_its_own_line():
    """A fresh session really does refresh a spent budget and a full conversation, so
    the page's own wording is right and nothing should replace it."""
    assert web.run_over_advice([("q", [web.item_for(ending(EndReason.RUN_BUDGET))])]) == ""
    assert web.run_over_advice([("q", [web.item_for(ending(EndReason.CONVERSATION_BOUND))])]) == ""
    assert web.run_over_advice([("q", [web.item_for(ending(EndReason.ANSWERED))])]) == ""


def test_the_run_budget_shown_is_the_one_the_run_was_measured_against():
    """Read off the ending rather than out of configuration, so a session resumed
    in a differently-configured process reports the cap it is actually subject to."""
    item = web.item_for(ending(EndReason.ANSWERED, run_budget=1_200_000))
    assert web.run_status([("q", [item])]) == (10, 1_200_000)
    assert web.run_status([("q", [web.Item(web.Kind.ANSWER, "x")])]) is None


def test_keywords_that_are_all_stripped_markup_draw_no_keyword_line(repo):
    """`_without_markup` empties them, and testing the stored tuple rather than the
    stripped one rendered a bare 'Keywords: '. Most of the corpus is affected."""

    def row(keywords):
        return entries_table.Row(
            entry_id=1,
            property="p",
            organism="o",
            value="1",
            units="μm",
            reference="r",
            cited=True,
            keywords=keywords,
        )

    assert row(("",)).keywords, "truthy as stored, which is what the old guard read"
    assert web.shown_keywords(row(("",))) == [], "and empty once drawn"
    assert web.shown_keywords(row(("cell", ""))) == ["cell"]


def test_the_prototype_caveat_is_on_the_page(monkeypatch, repo, config, tmp_path):
    """Not decoration. The page shows entries, identifiers and dimension checks --
    every signal a reader uses to decide a number is solid -- so the one thing it
    must also say is that this has not been evaluated. In the header, in amber, on
    every view of the page (ADR-1850; it was pinned to the viewport before).
    """
    at = app(monkeypatch, repo, agent_with(repo, config, tmp_path, scripted(says("a")))).run()
    banner = [h.proto.body for h in at.get("html") if 'class="sn-proto"' in h.proto.body]
    assert banner, "the prototype line was not drawn"
    # `**` inside raw HTML renders as two asterisks, so the emphasis has to be translated.
    assert "not yet scientifically trustworthy" in banner[0]
    assert "original source" in banner[0]
    assert "**" not in banner[0], "markdown emphasis left unrendered inside raw HTML"
    assert not any(web.PROTOTYPE_SHORT in c.value for c in at.sidebar.caption), (
        "a second copy in the panel is the repetition a reader learns to skip"
    )


def test_the_page_and_the_readme_both_say_it_is_not_trustworthy_yet():
    """Two statements of one fact drift, and the README is what a reviewer reads
    first. Checks the claim survives in both, not that the wording matches."""
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    assert "prototype, not an instrument" in readme.lower()
    assert "not yet scientifically trustworthy" in readme
    assert "not yet scientifically trustworthy" in web.PROTOTYPE_NOTE
    # Both point past this project's own copy. "Check the cited entry" would read as
    # this page's rendering of it, which is the one thing checking cannot verify.
    assert "original source" in readme and "original source" in web.PROTOTYPE_NOTE


def test_a_failure_while_drawing_does_not_lose_the_question(repo, config, tmp_path):
    """The agent persists each turn as it goes. If drawing raises and the page has
    not recorded the question, the model remembers a turn the screen never shows,
    and the next answer rests on context a reader cannot see.

    Injected at the drawing seam, because nothing else can produce it: the agent
    raises no exception here and the suite stays green whether or not the question
    survives.
    """
    agent = agent_with(repo, config, tmp_path, scripted(says("an answer")))
    transcript: list[tuple[str, list[web.Item]]] = []
    items: list[web.Item] = []
    transcript.append(("a question", items))

    def exploding(item):
        raise RuntimeError("a rendering fault")

    with pytest.raises(RuntimeError, match="a rendering fault"):
        for item in web.items_for(agent.ask("s", "a question"), repo):
            items.append(item)
            exploding(item)

    assert agent.conversation_length("s") == 2, "the agent kept the turn"
    assert transcript[0][0] == "a question", "and so did the page"
    assert items, "with whatever had been drawn before the fault"


def test_the_page_refuses_a_retired_variable_before_it_looks_for_a_corpus(monkeypatch):
    """The web path has the same ordering hazard as the terminal one.

    The page resolves the corpus itself, before the cached `resources` runs, so a
    refusal living only in `resources` would arrive after the corpus lookup had
    already failed -- and the reader would be told a corpus is missing when what is
    wrong is the name of the variable holding its path.
    """
    monkeypatch.delenv("NUMERA_CORPUS", raising=False)
    monkeypatch.setenv("BIONUMBERS_ASK_CORPUS", "/somewhere/corpus.jsonl")

    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    errors = [e.value for e in at.error]
    assert any("NUMERA_CORPUS" in text for text in errors), errors
    assert not any("No corpus path supplied" in text for text in errors), errors
    assert not at.exception, "the page raised instead of explaining"


def test_a_finished_search_is_not_labelled_as_still_running(monkeypatch, repo, config, tmp_path):
    """Both paths name the finished box the same thing: what was searched, and what came of it.

    The live path opens the box on the first retrieval and relabels it when the
    answer is done; the replay path draws it already finished. They had two
    literals and had drifted, so every redrawn turn claimed to still be searching.
    """
    model = scripted(
        tool_call("search_entries", property="Cell"), says("about 1 micrometre (BNID 100002)")
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")
    (label,) = [box.label for box in at.status]
    assert label.startswith("Searched “Cell” · ") and label.endswith("cited")

    # And still so after another turn puts it through the replay path a second time.
    at = ask(at, "and in yeast?")
    assert web.RETRIEVAL_RUNNING not in [box.label for box in at.status]
    assert at.status[0].label == label


def test_the_evidence_list_has_no_fixed_widths_to_overflow(repo):
    """The width-budget test this replaces guarded a dataframe's fixed pixel columns against a
    horizontal scrollbar that hid the ID. The list is HTML and wraps (ADR-1850): no column width
    is fixed, so there is nothing to sum against the evidence column."""
    markup = web.evidence_html(web.item_for(entries(), repo).table.rows, {})
    assert "width:" not in markup and "style=" not in markup
    assert not hasattr(web, "COLUMN_WIDTHS")


# --- citations in a drawn answer (ADR-1240) --------------------------------------


def test_a_run_of_citations_is_drawn_as_pills():
    drawn = web.answer_markdown("42 μm³ [[100427]] [[100430]], and 1.1 μm³ [[100004]].")
    assert re.sub(r"<[^>]+>", "", drawn) == "42 μm³ 1 2, and 1.1 μm³ 3."
    assert drawn.count('class="sn-pill"') == 3
    assert "[[" not in drawn


def test_an_answer_drawn_with_html_allowed_is_escaped_first():
    """HTML is turned on for the superscripts alone. The answer is model output, so
    it is escaped before any tag of ours goes in -- and in this one function, so no
    caller can turn HTML on for an answer that was not."""
    drawn = web.answer_markdown('<img src=x onerror="alert(1)"> **bold** [[100001]] costs $5')
    assert "<img" not in drawn and "&lt;img" in drawn
    assert "**bold**" in drawn, "markdown is left for Streamlit to draw"
    assert r"\$5" in drawn, "and `$` is still kept out of mathematics"


def test_the_page_draws_an_answer_s_citations_as_pills(monkeypatch, repo, config, tmp_path):
    model = scripted(says("about 1 micrometre [[100002]] [[100003]] <b>x</b>"))
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")
    (drawn,) = [m for m in at.markdown if "micrometre" in m.value]
    assert 'title="BNID 100002"><b>1</b></span>' in drawn.value
    assert 'title="BNID 100003"><b>2</b></span>' in drawn.value
    assert "&lt;b&gt;x&lt;/b&gt;" in drawn.value
    assert drawn.proto.allow_html


def _draw_turn(count, answering):
    """One finished turn with `count` cited entries, redrawn as the replay path draws it."""
    from numera_ask import entries_table, web

    rows = tuple(
        entries_table.Row(
            entry_id=100000 + i,
            property=f"Property {i}",
            organism="Bacteria Escherichia coli",
            value="1.0",
            units="um",
            reference="A reference",
            cited=True,
        )
        for i in range(count)
    )
    web.show(
        [web.Item(web.Kind.ENTRIES, table=web.Table(rows), question_id="q1")], answering=answering
    )


def test_twelve_entries_are_buttons_and_thirteen_a_list():
    """Above twelve the buttons become a wall of numbers (the user's call, 2026-10-17)."""
    at = AppTest.from_function(_draw_turn, args=(12, False), default_timeout=TIMEOUT).run()
    assert at.get("button_group") and not at.selectbox
    at = AppTest.from_function(_draw_turn, args=(13, False), default_timeout=TIMEOUT).run()
    assert at.selectbox and not at.get("button_group")
    # Nothing opened until chosen, and a way back to nothing (the user's call, 2026-10-17).
    assert at.selectbox[0].options[0] == web.SHOW_NO_ENTRY and at.selectbox[0].value is None
    assert at.selectbox[0].options[7] == "7 · Property 6"


def test_no_entry_can_be_chosen_while_a_question_is_answering():
    """A click re-runs the page and would cut the answer off mid-tool-call."""
    at = AppTest.from_function(_draw_turn, args=(3, True), default_timeout=TIMEOUT).run()
    assert at.get("button_group")[0].proto.disabled
    at = AppTest.from_function(_draw_turn, args=(3, False), default_timeout=TIMEOUT).run()
    assert not at.get("button_group")[0].proto.disabled


def test_an_entry_is_closed_until_chosen_and_closed_again_by_its_number():
    """The user's call (2026-10-17): open by default, a record per turn filled the page."""
    at = AppTest.from_function(_draw_turn, args=(3, False), default_timeout=TIMEOUT).run()
    assert not any(m.value.startswith("**Entry") for m in at.markdown)
    at.get("button_group")[0].set_value(2).run()
    assert "**Entry 2** · `BNID 100001`" in [m.value for m in at.markdown]
    # A second click on the open number deselects it in the browser because the pills are not
    # `required` (st.pills, 1.61.1). AppTest cannot press a selected pill again -- its
    # `set_value(None)` keeps the last value -- so what is asserted is the setting that does it.
    assert not at.get("button_group")[0].proto.required


def test_a_new_question_closes_every_opened_entry(monkeypatch, repo, config, tmp_path):
    model = scripted(
        tool_call("get_entry", entry_id=100002),
        says("about 1 micrometre [[100002]]"),
        tool_call("get_entry", entry_id=100003),
        says("and [[100003]]"),
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")
    at.main.get("button_group")[0].set_value(1).run()
    assert any(m.value.startswith("**Entry 1**") for m in at.main.markdown)
    at = ask(at, "and the other?")
    assert not at.exception
    assert not any(m.value.startswith("**Entry") for m in at.main.markdown), "left open"
