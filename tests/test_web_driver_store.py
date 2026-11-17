"""The harvest store through a whole run of the real page (`.claude/rules/streamlit-driver.md`).

What the page draws for a store -- stars beside the citation superscript, the legend with the table,
the caveat column first and the Trust column before the ID -- and that a corpus file draws none of
the store's additions. Over the invented store in `store_double`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import store_double
from conftest import FIXTURE, agent_with, ask_question
from streamlit.testing.v1 import AppTest

from agent_doubles import says, scripted, tool_call
from scinumbers_ask import autobuild, objections, store_corpus, trust_marks, web
from scinumbers_ask.corpus import load
from scinumbers_ask.repository import CorpusRepository

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
TIMEOUT = 30


@pytest.fixture
def store_path(tmp_path):
    return store_double.build(tmp_path / "store.sqlite")


def _page(monkeypatch, repo, agent, store="invented-store.sqlite") -> AppTest:
    # The page reads which corpus it is from the setting, as a deployment does; the repository
    # itself is handed in.
    if store:
        monkeypatch.setenv("SCINUMBERS_STORE", store)
        monkeypatch.delenv("SCINUMBERS_CORPUS", raising=False)
    monkeypatch.setattr(web, "resources", lambda corpus=None, store=None: repo)
    monkeypatch.setattr(web, "agent_for", lambda state, repo, admission: agent)
    return AppTest.from_file(APP, default_timeout=TIMEOUT)


def _store_answer(store_path, config, tmp_path):
    repo = CorpusRepository(store_corpus.load(store_path))
    model = scripted(
        tool_call("search_entries", property="F-actin"),
        says("About 488 µM [[PMC1000001-1]], or 500 µM [[PMC1000001-1.2]]."),
    )
    return repo, agent_with(repo, config, tmp_path, model)


def _html(at) -> str:
    return " ".join(element.proto.body for element in at.get("html"))


def test_a_store_answer_carries_pills_an_evidence_list_and_an_opened_entry(
    monkeypatch, store_path, config, tmp_path
):
    """ADR-1850, through a whole run of the real page."""
    repo, agent = _store_answer(store_path, config, tmp_path)
    objections.attach(repo, objections.load(store_path))
    at = ask_question(_page(monkeypatch, repo, agent).run(), "F-actin in lamellipodia?")
    assert not at.exception

    prose = " ".join(m.value for m in at.markdown)
    # Each citation a pill: its number in the session, its stars, `sim` and the caution.
    assert re.sub(r"<[^>]+>", "", prose).count("1 ★★★☆☆ sim ⚠️") == 1
    assert 'title="PMC1000001-1.2"><b>2</b>' in prose
    assert "<sup" not in prose and "[[PMC" not in prose

    evidence = _html(at)
    assert "<th>#</th><th>Entry</th><th>Value</th><th>Trust</th><th>ID</th>" in evidence
    assert ">PMC1000001-1<" in evidence and ">PMC1000001-1.2<" in evidence
    # The whole trust scale, said once and pinned with the question box (2026-10-17).
    legend = [c.value for c in at.caption if trust_marks.SCALE_LEGEND in c.value]
    assert len(legend) == 1
    assert trust_marks.SIMULATED_LEGEND in legend[0] and trust_marks.DISPUTED_LEGEND in legend[0]

    # The entries are chosen by number; nothing is open until one is: then objections included.
    (chooser,) = at.get("button_group")
    assert chooser.options == ["1", "2"]
    assert not at.warning
    chooser.set_value(1).run()
    assert any(w.value.startswith("**A reviewer objected.**") for w in at.warning)
    assert any(store_double.REVIEWER_ISSUE in w.value for w in at.warning)
    # And nothing of it in the sidebar any more.
    assert not at.sidebar.expander


def test_choosing_another_number_opens_that_entry(monkeypatch, store_path, config, tmp_path):
    repo, agent = _store_answer(store_path, config, tmp_path)
    at = ask_question(_page(monkeypatch, repo, agent).run(), "F-actin in lamellipodia?")
    at.get("button_group")[0].set_value(2).run()
    assert not at.exception
    assert "**Entry 2** · `PMC1000001-1.2`" in [m.value for m in at.markdown]


def test_a_corpus_file_answer_has_pills_without_stars(monkeypatch, config, tmp_path):
    repo = CorpusRepository(load(FIXTURE))
    model = scripted(tool_call("search_entries", property="Cell"), says("1 μm [[100002]]"))
    agent = agent_with(repo, config, tmp_path, model)
    at = ask_question(_page(monkeypatch, repo, agent, store=None).run(), "how wide?")
    assert not at.exception

    prose = " ".join(m.value for m in at.markdown)
    assert 'title="BNID 100002"><b>1</b></span>' in prose
    assert "★" not in prose and "☆" not in prose
    # A corpus file has no tiers, so the pinned trust scale is not drawn at all.
    assert trust_marks.SCALE_LEGEND not in " ".join(c.value for c in at.caption)
    assert "<th>Trust</th>" not in _html(at)


def test_the_page_loads_the_store_from_its_setting_without_building_a_corpus(
    monkeypatch, store_path, config, tmp_path
):
    """Through the real cached loader: SCINUMBERS_STORE alone is enough, and the corpus builder
    is never consulted for a store (design D7)."""

    def no_build(*args, **kwargs):
        raise AssertionError("autobuild was asked to build a corpus for a store")

    web.resources.clear()
    monkeypatch.delenv("SCINUMBERS_CORPUS", raising=False)
    monkeypatch.setenv("SCINUMBERS_STORE", str(store_path))
    monkeypatch.setenv("SCINUMBERS_CHECKPOINTS", str(tmp_path / "c.sqlite"))
    monkeypatch.setattr(web.trace, "to_file", lambda spec: None)
    monkeypatch.setattr(autobuild, "corpus_path", no_build)
    seen = {}

    def agent(state, repo, admission):
        seen["repo"] = repo
        return agent_with(repo, config, tmp_path, scripted(says("no answer")))

    monkeypatch.setattr(web, "agent_for", agent)
    try:
        at = ask_question(AppTest.from_file(APP, default_timeout=TIMEOUT).run(), "anything?")
        assert not at.exception
        assert not at.error, [e.value for e in at.error]
        assert seen["repo"].get("PMC1000001-1") is not None
        # The cached loader attached the store's objections for the tables to show.
        item = f"{store_double.RUN_A}-{store_double.ACTIN.pmcid}-1-item"
        assert objections.of(seen["repo"], item) == (f"student: {store_double.REVIEWER_ISSUE}",)
    finally:
        web.resources.clear()


def test_the_page_refuses_both_settings_at_once(monkeypatch, store_path, tmp_path):
    web.resources.clear()
    monkeypatch.setenv("SCINUMBERS_CORPUS", FIXTURE)
    monkeypatch.setenv("SCINUMBERS_STORE", str(store_path))
    monkeypatch.setattr(web.trace, "to_file", lambda spec: None)
    try:
        at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
        assert any("not both" in e.value for e in at.error)
    finally:
        web.resources.clear()


def test_a_harvested_entry_opens_with_its_fields_apart_not_its_keywords(
    monkeypatch, store_path, config, tmp_path
):
    """Its keywords pack the quote and each condition's quote together for search; drawn as
    "Keywords:" they read as one fused field (seen on PMC2064542-2, 2026-10-16)."""
    repo, agent = _store_answer(store_path, config, tmp_path)
    at = ask_question(_page(monkeypatch, repo, agent).run(), "F-actin in lamellipodia?")
    at.get("button_group")[0].set_value(1).run()
    drawn = [m.value for m in at.markdown] + [c.value for c in at.caption]
    text = "\n".join(drawn)
    assert "Keywords:" not in text
    assert (
        "*Quote.* “The lamellipodial F-actin concentration was 488 µM in invented cells.”" in drawn
    )
    assert "*Organism.* “invented mouse cells”" in drawn
    assert "Not stated in the paper: temperature" in drawn
    # The method condition is the measurement method line, not a second condition.
    assert text.count("invented electron microscopy counts") == 1


def _draw_shared_quotes():
    from scinumbers_ask import entries_table, web
    from scinumbers_ask.corpus import Condition, Harvest, Origin, Paper

    said = "Strains and growth conditions were described previously."
    harvest = Harvest(
        item_id="i",
        value_text="1",
        quote="Q",
        conditions=(
            Condition("medium", said),
            Condition("temperature", said),
            Condition("growth_phase", "Cells were in M phase."),
            Condition("culture_mode", said),
        ),
        not_stated=(),
        origin=Origin.MEASURED,
        inputs=(),
        paper=Paper(pmcid="PMC1", title="t", year=2000, doi="", pmid="", licence=""),
        domain="biology",
        topic="cytoskeleton",
        reading_uncertain=False,
    )
    row = entries_table.Row(
        entry_id="PMC1-1",
        property="p",
        organism="o",
        value="1",
        units="",
        reference="",
        cited=True,
        keywords=("biology", "Q", said, said, said),
        harvest=harvest,
    )
    web.draw_record(row, 1)


def test_conditions_quoting_one_passage_are_named_together():
    at = AppTest.from_function(_draw_shared_quotes, default_timeout=TIMEOUT).run()
    assert not at.exception
    drawn = [m.value for m in at.markdown]
    said = "Strains and growth conditions were described previously."
    assert f"*Medium, temperature, culture mode.* “{said}”" in drawn
    assert "*Growth phase.* “Cells were in M phase.”" in drawn
    assert sum(said in d for d in drawn) == 1
