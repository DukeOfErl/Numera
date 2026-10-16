"""The harvest store through a whole run of the real page (`.claude/rules/streamlit-driver.md`).

What the page draws for a store -- stars in the citation superscript, the legend under the answer,
the caveat column first and the Trust column before the ID -- and that a corpus file draws none of
the store's additions. Over the invented store in `store_double`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import store_double
from conftest import FIXTURE, agent_with, ask_question
from streamlit.testing.v1 import AppTest

from agent_doubles import says, scripted, tool_call
from scinumbers_ask import autobuild, store_corpus, trust_marks, web
from scinumbers_ask.corpus import load
from scinumbers_ask.repository import CorpusRepository

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
TIMEOUT = 30


@pytest.fixture
def store_path(tmp_path):
    return store_double.build(tmp_path / "store.sqlite")


def _page(monkeypatch, repo, agent) -> AppTest:
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


def test_a_store_answer_carries_its_stars_its_legend_and_both_new_columns(
    monkeypatch, store_path, config, tmp_path
):
    repo, agent = _store_answer(store_path, config, tmp_path)
    at = ask_question(_page(monkeypatch, repo, agent).run(), "F-actin in lamellipodia?")
    assert not at.exception

    drawn = " ".join(m.value for m in at.markdown)
    assert ">PMC1000001-1 #★★★☆☆⚠</sup>" in drawn
    assert ">PMC1000001-1.2 ☆☆☆☆☆</sup>" in drawn

    captions = [c.value for c in at.caption]
    assert trust_marks.SCALE_LEGEND in captions
    # The simulated mark's line begins with `#`; escaped, it is not drawn as a heading.
    assert "\\" + trust_marks.SIMULATED_LEGEND in captions
    assert trust_marks.DISPUTED_LEGEND in captions

    table = at.dataframe[0].value
    assert list(table.columns) == [
        "",
        "Property",
        "Organism",
        "Value",
        "Units",
        "Trust",
        "ID",
        "Reference",
    ]
    assert dict(zip(table["ID"], table["Trust"], strict=True)) == {
        "PMC1000001-1": "#★★★☆☆⚠",
        "PMC1000001-1.2": "☆☆☆☆☆",
    }


def test_a_corpus_file_answer_draws_none_of_the_store_s_additions(monkeypatch, config, tmp_path):
    repo = CorpusRepository(load(FIXTURE))
    model = scripted(tool_call("search_entries", property="Cell"), says("1 μm [[100002]]"))
    agent = agent_with(repo, config, tmp_path, model)
    at = ask_question(_page(monkeypatch, repo, agent).run(), "how wide?")
    assert not at.exception

    drawn = " ".join(m.value for m in at.markdown)
    assert ">100002</sup>" in drawn
    assert "★" not in drawn and "☆" not in drawn
    assert trust_marks.SCALE_LEGEND not in [c.value for c in at.caption]
    table = at.dataframe[0].value
    assert "Trust" not in table.columns
    assert list(table.columns)[0] == ""


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
