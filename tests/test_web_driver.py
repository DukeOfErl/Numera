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

from pathlib import Path

import pytest
from conftest import FIXTURE, agent_with
from streamlit.testing.v1 import AppTest

from agent_doubles import batched_tool_calls, costing, says, scripted, tool_call
from scinumbers_ask import entries_table, messages, web
from scinumbers_ask.agent import AskAgent
from scinumbers_ask.cli import render
from scinumbers_ask.corpus import load
from scinumbers_ask.events import (
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
from scinumbers_ask.repository import CorpusRepository

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")

# Generous, and deliberately so: the default is three seconds, the first run in a
# process pays for component discovery, and a timeout here is indistinguishable
# from a hang in the agent.
TIMEOUT = 30

# The session-state keys feedback is allowed to keep, named exactly rather than
# matched by a wildcard: a rule that permitted anything under a namespace would
# permit the copies of the conversation and the spend it exists to forbid.
FEEDBACK_PREFIXES = (
    "scinumbers_ask.feedback",
    "scinumbers_ask.verdict.",
    "scinumbers_ask.comment.",
)


def app(monkeypatch, repo, agent) -> AppTest:
    """The real script, with the corpus and agent a test chose.

    `resources` is replaced rather than driven through the environment because it
    is cached for the life of the process: a second test would be served the
    first one's agent.
    """
    monkeypatch.setattr(web, "resources", lambda corpus=None: (repo, agent))
    return AppTest.from_file(APP, default_timeout=TIMEOUT)


def ask(at: AppTest, question: str) -> AppTest:
    return at.chat_input[0].set_value(question).run()


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

    The rule keeps its teeth: anything else namespaced here still fails, and the
    allowance is a prefix rather than a wildcard, so `scinumbers_ask.spend` or a
    second copy of the conversation would still be caught.
    """
    model = scripted(says("an answer"))
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    kept = {k for k in at.session_state.filtered_state if k.startswith("scinumbers_ask.")}
    feedback_keys = {k for k in kept if k.startswith(FEEDBACK_PREFIXES)}
    assert kept - feedback_keys == {web.SESSION_KEY, web.TRANSCRIPT_KEY}


def test_a_missing_corpus_is_explained_rather_than_raised(monkeypatch):
    from scinumbers_ask.corpus import CorpusUnavailable

    def unavailable(corpus=None):
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

    def counting_load(path):
        counts["read"] += 1
        return rows

    def counting_repository(entries):
        counts["indexed"] += 1
        return CorpusRepository(entries)

    monkeypatch.setattr(web, "load", counting_load)
    monkeypatch.setattr(web, "CorpusRepository", counting_repository)
    monkeypatch.setattr(web.trace, "to_file", lambda spec: None)
    monkeypatch.setenv("SCINUMBERS_CHECKPOINTS", str(tmp_path / "c.sqlite"))
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

    assert [box.label for box in at.status] == ["Retrieval"]


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
    monkeypatch.setattr(web, "resources", lambda corpus=None: (repo, restarted))
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


def test_a_row_names_the_entry_and_its_identifier(repo):
    table = web.item_for(entries(), repo).table
    label = web._row_label(table.rows[0])
    assert "Cell diameter" in label and "Escherichia coli" in label
    assert "BNID 100002" in label


def test_a_row_without_a_recorded_method_is_marked(repo):
    """The corpus records no method for 100002, and a marked row says so."""
    table = web.item_for(entries(), repo).table
    row = next(r for r in table.rows if r.entry_id == 100002)
    assert not row.method_recorded
    assert web._row_label(row).startswith(entries_table.NO_METHOD)


def test_every_retrieved_entry_is_reachable_even_past_the_cap(monkeypatch, repo, config, tmp_path):
    """Beyond the cap they are listed rather than dropped: nothing retrieved is hidden."""
    monkeypatch.setattr(web, "CITED_ROWS", 2)
    monkeypatch.setattr(web, "UNCITED_ROWS", 1)
    every = tuple(entry.entry_id for entry in load(FIXTURE))
    table = web.item_for(entries(cited=(), retrieved=every), repo).table
    assert len(table.rows) == len(every) > 2, "rows were dropped rather than carried"


def test_the_table_reaches_the_main_column_as_a_table(monkeypatch, repo, config, tmp_path):
    model = scripted(
        tool_call("get_entry", entry_id=100002), says("about 1 micrometre (BNID 100002)")
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    assert at.dataframe, "no table was drawn"
    assert any("Cited in the answer" in m.value for m in at.markdown)


def test_the_openable_entries_are_in_the_side_panel_not_the_main_column(
    monkeypatch, repo, config, tmp_path
):
    """The main column is for reading the answer against; the panel is for digging."""
    model = scripted(
        tool_call("get_entry", entry_id=100002), says("about 1 micrometre (BNID 100002)")
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    labels = [e.label for e in at.sidebar.expander]
    assert any("BNID 100002" in label for label in labels), labels
    assert any("Full entries" in h.value for h in at.sidebar.header)


def test_an_opened_row_shows_the_entry_the_model_never_saw(monkeypatch, repo, config, tmp_path):
    """The reference is looked up for display and never travels through the agent."""
    model = scripted(
        tool_call("get_entry", entry_id=100002), says("about 1 micrometre (BNID 100002)")
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

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
    cell = web._frame((row,))[0]

    assert cell["Value"] == "", "the placeholder was repeated in the value column"
    assert cell["Property"].startswith(entries_table.NO_SCALAR)
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


def test_the_side_panel_is_there_before_any_question(monkeypatch, repo, config, tmp_path):
    """A panel that materialises after the first answer reads as a glitch."""
    at = app(monkeypatch, repo, agent_with(repo, config, tmp_path, scripted(says("a")))).run()

    assert any("Full entries" in h.value for h in at.sidebar.header)
    assert not at.sidebar.expander, "entries before anything was retrieved"


def test_the_legend_sits_between_the_two_tables(monkeypatch, repo, config, tmp_path):
    """Before both it explains marks nobody has met; after both it is too late."""
    model = scripted(
        tool_call("search_entries", property="Cell"), says("about 1 micrometre (BNID 100002)")
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "how wide?")

    headings = [m.value for m in at.markdown]
    captions = [c.value for c in at.caption]
    assert any("Cited in the answer" in h for h in headings)
    assert any(entries_table.NO_METHOD_LEGEND in c for c in captions)


def test_every_column_is_given_a_width_so_the_table_does_not_scroll_sideways(repo):
    """A table scrolled sideways hides the identifier, the one cell being checked."""
    table = web.item_for(entries(), repo).table
    assert set(web._frame(table.rows)[0]) == set(web.COLUMN_WIDTHS)
    assert sum(web.COLUMN_WIDTHS.values()) <= 700


def test_an_identifier_is_a_string_so_it_keeps_matching_the_prose(repo):
    """As a number it picks up a thousands separator and stops reading as a BNID."""
    table = web.item_for(entries(), repo).table
    assert web._frame(table.rows)[0]["ID"] == "100002"


# -- the two caps ----------------------------------------------------------


def many(cited_count: int, uncited_count: int) -> tuple[entries_table.Row, ...]:
    """Rows enough to exercise both caps, cited first as `rows_for` orders them."""

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


def test_every_cited_entry_is_shown_when_they_fit(repo):
    """Nine cited entries against a single eight-row cap dropped one of them."""
    rows = many(cited_count=9, uncited_count=5)
    cited = tuple(r for r in rows if r.cited)[: web.CITED_ROWS]
    assert len(cited) == 9, "a cited entry the answer rests on was left out of the table"


def test_the_uncited_section_survives_an_answer_that_cited_many(repo):
    """The single cap spent all its rows on cited entries and the section vanished."""
    rows = many(cited_count=9, uncited_count=5)
    rest = tuple(r for r in rows if not r.cited)[: web.UNCITED_ROWS]
    assert len(rest) == web.UNCITED_ROWS == 4


def test_fewer_uncited_entries_than_the_cap_shows_what_there_is(repo):
    rows = many(cited_count=1, uncited_count=2)
    assert len(tuple(r for r in rows if not r.cited)[: web.UNCITED_ROWS]) == 2


def test_cited_entries_beyond_the_cap_are_announced_not_dropped_silently(
    monkeypatch, repo, config, tmp_path
):
    """The one omission a reader cannot detect by looking at the table."""
    monkeypatch.setattr(web, "CITED_ROWS", 2)
    cited = (100001, 100002, 100003)
    model = scripted(
        batched_tool_calls(*[("get_entry", {"entry_id": b}) for b in cited]),
        says("BNIDs 100001, 100002 and 100003"),
    )
    at = ask(app(monkeypatch, repo, agent_with(repo, config, tmp_path, model)).run(), "sizes?")

    warnings = [w.value for w in at.warning]
    assert any("more cited" in w and "side panel" in w for w in warnings), warnings


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
    assert any(entries_table.UNCITED_BANNER.capitalize() in h for h in headings)


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


def test_the_side_panel_holds_the_newest_question_or_nothing(repo):
    """Not the newest question that had entries. Falling back leaves an earlier
    question's entries under 'Full entries' with nothing saying they are stale --
    and the main column's 'every one is in the side panel' then points at a panel
    that no longer holds them."""
    with_entries = [web.item_for(entries(), repo)]
    without = [web.Item(web.Kind.ANSWER, "no entries this time")]
    assert web.latest_table([("q1", with_entries)]) is not None
    assert web.latest_table([("q1", with_entries), ("q2", without)]) is None


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


def test_the_prototype_caveat_is_on_the_page_and_stays_there(monkeypatch, repo, config, tmp_path):
    """Not decoration. The page shows entries, identifiers and dimension checks --
    every signal a reader uses to decide a number is solid -- so the one thing it
    must also say is that this has not been evaluated. In the side panel as well as
    under the title: a long conversation scrolls the title away, and a caveat only
    the first question sees is not a caveat.
    """
    at = app(monkeypatch, repo, agent_with(repo, config, tmp_path, scripted(says("a")))).run()
    banner = [m.value for m in at.markdown if '<div class="bn-caveat"' in m.value]
    assert banner, "the pinned banner was not drawn"
    # The words survive the markdown-to-HTML rendering: `**` inside a raw HTML
    # element renders as two asterisks, so the emphasis has to be translated.
    assert "not scientifically trustworthy" in banner[0]
    assert "original source" in banner[0]
    assert "**" not in banner[0], "markdown emphasis left unrendered inside raw HTML"
    assert "position: fixed" in "".join(m.value for m in at.markdown), (
        "drawn as an ordinary element it scrolls away with the first answer, and the "
        "reader who has seen several answers is the one who most needs it"
    )
    assert any(web.PROTOTYPE_SHORT in c.value for c in at.sidebar.caption), "missing in the panel"


def test_the_page_and_the_readme_both_say_it_is_not_trustworthy_yet():
    """Two statements of one fact drift, and the README is what a reviewer reads
    first. Checks the claim survives in both, not that the wording matches."""
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    assert "prototype, not an instrument" in readme.lower()
    assert "not scientifically trustworthy" in readme
    assert "not scientifically trustworthy" in web.PROTOTYPE_NOTE
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
    monkeypatch.delenv("SCINUMBERS_CORPUS", raising=False)
    monkeypatch.setenv("BIONUMBERS_ASK_CORPUS", "/somewhere/corpus.jsonl")

    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    errors = [e.value for e in at.error]
    assert any("SCINUMBERS_CORPUS" in text for text in errors), errors
    assert not any("No corpus path supplied" in text for text in errors), errors
    assert not at.exception, "the page raised instead of explaining"
