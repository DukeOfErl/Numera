"""The harvest store as the agent's corpus (`add-ask-over-store`).

Test data here is invented. The real store holds passages from papers some of which are licensed
NC or ND, and none of that text may enter the repository; the fixture builds a store with the real
schema and made-up words.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import store_double
from conftest import agent_with
from sqlalchemy import insert

from agent_doubles import says, scripted, tool_call
from bionumbers import store as review_store
from bionumbers.records import ClaimKind
from bionumbers.tiers import Tier, Trust
from scinumbers_ask import corpus, store_corpus
from scinumbers_ask.corpus import Condition, CorpusUnavailable, Origin
from scinumbers_ask.events import CitationWarning
from scinumbers_ask.repository import CorpusRepository
from scinumbers_ask.tools import ToolBudget, build_tools
from scinumbers_ask.trace import configure, start_question

FIXTURES = Path(__file__).parent / "fixtures"


def _loaded_after(statements: str) -> set[str]:
    """Which `bionumbers` modules a fresh interpreter holds after running `statements`.

    A fresh interpreter because this process has imported everything the suite touches, so asking
    `sys.modules` here would report what some other test loaded.
    """
    probe = (
        f"{statements}\n"
        "import sys\n"
        "print(','.join(sorted(m for m in sys.modules "
        "if m == 'bionumbers' or m.startswith('bionumbers.'))))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    return {name for name in result.stdout.strip().split(",") if name}


def test_a_corpus_file_run_never_imports_the_validator_package():
    """ADR-1600: only the store's loader imports `bionumbers`, so a corpus-file run never does."""
    loaded = _loaded_after(
        "from scinumbers_ask import agent, cli, corpus, entries_table, messages\n"
        "from scinumbers_ask import repository, tools\n"
        f"repository.CorpusRepository(corpus.load({str(FIXTURES / 'corpus_sample.jsonl')!r}))\n"
        f"corpus.load_configured({str(FIXTURES / 'corpus_sample.jsonl')!r}, None)\n"
    )
    assert loaded == set()


def test_a_corpus_file_entry_carries_no_harvest_and_no_tier():
    """D2: both parts are None for a corpus-file entry, which is how a surface tells "never
    reviewed" from "reviewed, and no one approved"."""
    entries = corpus.load(FIXTURES / "corpus_sample.jsonl")
    assert entries
    assert all(e.harvest is None and e.trust is None for e in entries)
    assert all(e.record_id == e.entry_id for e in entries)


# -- the store loader ---------------------------------------------------------
#
# Expected values come from what `store_double` was built to hold (its docstrings say which
# decision each item carries), never from running the loader.

A = f"{store_double.RUN_A}-{store_double.ACTIN.pmcid}"


@pytest.fixture
def store_path(tmp_path):
    return store_double.build(tmp_path / "store.sqlite")


@pytest.fixture
def by_label(store_path):
    return {e.entry_id: e for e in store_corpus.load(store_path)}


def test_loading_the_store_imports_the_validator_package():
    """The positive control for the corpus-file test above: the probe sees `bionumbers` when it
    is loaded, so an empty set there means it was not, rather than that the probe sees nothing."""
    assert "bionumbers.tiers" in _loaded_after("from scinumbers_ask import store_corpus")


def test_the_store_is_opened_so_nothing_can_be_written(store_path):
    statement = "insert into review_skip (run_id, pmcid, skipped_at) values ('r', 'p', 't')"
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        store_corpus.connect(store_path).execute(statement)
    # The canary: the same statement through an ordinary connection is accepted, so the refusal
    # above is the connection's mode and not a malformed statement.
    plain = sqlite3.connect(store_path)
    plain.execute(statement)
    plain.rollback()


def test_loading_leaves_the_store_byte_for_byte_as_it_was(store_path):
    before = hashlib.sha256(store_path.read_bytes()).hexdigest()
    store_corpus.load(store_path)
    assert hashlib.sha256(store_path.read_bytes()).hexdigest() == before


def test_the_store_holds_its_curated_entries_and_every_harvested_value(by_label):
    assert set(by_label) == {
        store_double.CURATED_ID,
        "PMC1000001-1",
        "PMC1000001-2",
        "PMC1000001-3",
        "PMC1000001-4",
        "PMC2000002-1",
        "PMC1000001-1.2",
    }
    assert {e.harvest.domain for e in by_label.values() if e.harvest} == {"biology", "physics"}


def test_a_curated_entry_keeps_its_bnid_and_is_curated(by_label):
    entry = by_label[store_double.CURATED_ID]
    assert entry.property == "Invented cell length"
    assert entry.harvest is None
    assert entry.trust == Trust(Tier.CURATED)
    assert entry.record_id == store_double.CURATED_ID


def test_a_harvested_value_carries_what_a_reader_needs_to_judge_it(by_label):
    entry = by_label["PMC1000001-1"]
    assert entry.property == "F-actin concentration"  # the paper's wording, not the one asked
    assert entry.organism == "mouse"
    assert entry.units == "µM"
    assert entry.measurement_method == "invented electron microscopy counts"
    assert entry.reference_pubmed_id == "1000001"
    assert "Invented actin paper (2009)" in entry.reference
    harvest = entry.harvest
    assert harvest.item_id == f"{A}-1-item"
    assert harvest.quote.startswith("The lamellipodial F-actin concentration")
    assert harvest.conditions == (
        Condition("organism", "invented mouse cells"),
        Condition("method", "invented electron microscopy counts"),
    )
    assert harvest.not_stated == ("temperature",)
    assert harvest.origin is Origin.MEASURED
    assert harvest.inputs == ()
    assert (harvest.domain, harvest.topic) == ("biology", "cytoskeleton")
    assert harvest.paper.doi == "10.0000/pmc1000001"


def test_a_calculated_value_says_by_whom_and_from_what(by_label):
    authors = by_label["PMC1000001-2"].harvest
    assert authors.origin is Origin.CALCULATED
    assert authors.inputs == ("Invented input passage one.", "Invented input passage two.")
    published = by_label["PMC1000001-3"].harvest
    assert published.origin is Origin.CALCULATED_FROM_PUBLISHED
    assert published.inputs == ("Invented published count.",)


def test_each_entry_stands_on_the_tier_its_decisions_earned(by_label):
    """The fixture's decisions, per `store_double.build`: the rule is ADR-0990's, not ours."""
    assert by_label["PMC1000001-1"].trust == Trust(Tier.SCIENTIST, disputed=True, simulated=True)
    assert by_label["PMC1000001-2"].trust == Trust(Tier.AI)
    assert by_label["PMC1000001-3"].trust == Trust(Tier.SENIOR_SCIENTIST)
    assert by_label["PMC1000001-4"].trust == Trust(Tier.NONE, disputed=True)
    assert by_label["PMC2000002-1"].trust == Trust(Tier.NONE), "no decision at all"


# -- a value as the paper wrote it (D4, ADR-1620) -----------------------------


def test_a_reading_that_fits_its_kind_gives_numbers(by_label):
    single = by_label["PMC1000001-1"]
    assert (single.value, single.range_low, single.range_high) == (488.0, None, None)
    uncertain = by_label["PMC1000001-2"]
    assert uncertain.value == 7.1 and uncertain.value_display == "7.1 ± 0.4"
    ranged = by_label["PMC1000001-3"]
    assert (ranged.value, ranged.range_low, ranged.range_high) == (None, 1100.0, 2100.0)
    assert not any(by_label[k].harvest.reading_uncertain for k in ("PMC1000001-1", "PMC1000001-2"))


def test_a_reading_that_does_not_fit_its_kind_states_no_number(by_label):
    entry = by_label["PMC1000001-4"]  # recorded as a single value, written as `10–20`
    assert entry.harvest.reading_uncertain
    assert (entry.value, entry.range_low, entry.range_high) == (None, None, None)
    assert entry.value_display == "10–20"


@pytest.mark.parametrize(
    "text, unit, kind, fits",
    [
        # Each negative differs from a positive in the one thing the rule reads: the count of
        # numbers, or whether an uncertainty was read.
        ("488", "µM", "SINGLE", True),
        ("10–20", "s", "SINGLE", False),
        ("7.1 ± 0.4", "nm", "WITH_UNCERTAINTY", True),
        ("103", "filaments per µm", "WITH_UNCERTAINTY", False),
        ("62 (40–100)", "", "WITH_UNCERTAINTY", False),
        ("1,100–2,100", "", "RANGE_OVER_CONDITIONS", True),
        ("0.89 and 1.16", "J/gK", "RANGE_OVER_CONDITIONS", False),
        ("2.3", "μm", "RANGE_OVER_CONDITIONS", False),
    ],
)
def test_the_reading_is_kept_only_where_it_fits_the_recorded_kind(text, unit, kind, fits):
    *_, uncertain = store_corpus._reading(text, unit, ClaimKind(kind))
    assert uncertain is not fits


# -- labels, and the id that is saved (D3, ADR-1610) ---------------------------


def test_a_second_extraction_of_a_paper_is_its_own_entry_with_a_suffixed_label(by_label):
    first, second = by_label["PMC1000001-1"], by_label["PMC1000001-1.2"]
    assert (first.value, second.value) == (488.0, 500.0)
    assert first.record_id != second.record_id
    assert second.record_id == f"{store_double.RUN_B}-PMC1000001-1-item"


def test_a_saved_id_still_names_its_value_after_later_extractions_are_added(tmp_path):
    path = store_double.build(tmp_path / "s.sqlite", with_run_b=False)
    (cited,) = [e for e in store_corpus.load(path) if e.entry_id == "PMC1000001-1"]
    saved = cited.record_id

    engine = review_store.engine_from_url(f"sqlite:///{path}")
    store_double.load(engine, store_double.RUN_B, store_double.run_b())
    # A run named as if made earlier, loaded last: load order decides, so it is the one suffixed.
    older = "invented-run-0"
    store_double.load(
        engine,
        older,
        [
            dataclasses.replace(i)
            if False
            else i.model_copy(
                update={
                    "item_id": f"{older}-PMC1000001-1-item",
                    "claim": i.claim.model_copy(
                        update={"claim_id": f"{older}-PMC1000001-1", "value": "999"}
                    ),
                }
            )
            for i in store_double.run_b()
        ],
    )
    engine.dispose()

    reloaded = {e.record_id: e for e in store_corpus.load(path)}
    assert reloaded[saved].value == 488.0
    assert reloaded[saved].entry_id == "PMC1000001-1", "an existing label does not move"
    assert reloaded[f"{older}-PMC1000001-1-item"].entry_id == "PMC1000001-1.3"


def test_two_values_that_would_share_a_label_stop_the_load(store_path):
    engine = review_store.engine_from_url(f"sqlite:///{store_path}")
    with engine.begin() as conn:
        row = conn.execute(
            review_store.review_item.select().where(
                review_store.review_item.c.item_id == f"{A}-1-item"
            )
        ).one()
        conn.execute(
            insert(review_store.review_item), {**row._mapping, "item_id": f"{A}-1-item-copy"}
        )
    engine.dispose()
    with pytest.raises(CorpusUnavailable, match="PMC1000001-1"):
        store_corpus.load(store_path)


def test_a_missing_store_is_refused_by_name(tmp_path):
    with pytest.raises(CorpusUnavailable, match="nowhere.sqlite"):
        store_corpus.load(tmp_path / "nowhere.sqlite")


def test_a_file_that_is_not_a_store_is_refused(tmp_path):
    path = tmp_path / "notes.sqlite"
    path.write_text("not a database")
    with pytest.raises(CorpusUnavailable, match="not a readable harvest store"):
        store_corpus.load(path)


def test_a_sqlite_url_names_the_same_file(store_path):
    assert store_corpus.path_of(f"sqlite:///{store_path}") == store_path


# -- nothing written for the review reaches an entry ---------------------------


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if dataclasses.is_dataclass(value):
        return [s for f in dataclasses.fields(value) for s in _strings(getattr(value, f.name))]
    if isinstance(value, (tuple, list)):
        return [s for v in value for s in _strings(v)]
    return []


def test_no_entry_holds_the_review_s_test_text_or_a_reviewer_s_words(store_path):
    raw = store_path.read_bytes().decode("utf-8", "ignore")
    planted = (*store_double.NEVER_SHOWN, store_double.VALUE_READ)
    # The canary: every marker is in the store, so finding none in the entries means something.
    assert all(marker in raw for marker in planted)

    text = "\n".join(s for e in store_corpus.load(store_path) for s in _strings(e))
    for marker in planted:
        assert marker not in text, marker


# -- what is saved carries the store's id (ADR-1610) --------------------------


def _trail(stream: io.StringIO, event: str) -> list[dict]:
    rows = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    return [r for r in rows if r["event"] == event]


def test_a_harvested_citation_is_saved_under_the_store_s_id(store_path, config, tmp_path):
    stream = io.StringIO()
    configure(stream)
    repo = CorpusRepository(store_corpus.load(store_path))
    model = scripted(
        tool_call("search_entries", property="F-actin"),
        tool_call("get_entry", entry_id="PMC1000001-1.2"),
        says("About 488 µM [[PMC1000001-1]]."),
    )
    list(agent_with(repo, config, tmp_path, model).ask("s", "F-actin in lamellipodia?"))

    (evidence,) = _trail(stream, "answer.evidence")
    assert evidence["cited"] == ["PMC1000001-1"]
    assert evidence["saved_ids"]["PMC1000001-1"] == f"{A}-1-item"
    assert evidence["saved_ids"]["PMC1000001-1.2"] == f"{store_double.RUN_B}-PMC1000001-1-item"
    (search,) = _trail(stream, "search")
    assert search["saved_ids"]["PMC1000001-1"] == f"{A}-1-item"
    (fetched,) = _trail(stream, "entry.retrieved")
    assert fetched["saved_id"] == f"{store_double.RUN_B}-PMC1000001-1-item"


def test_a_corpus_file_run_saves_what_it_saved_before(repo, config, tmp_path):
    """No `saved_ids` key at all: a BNID is both the label and the saved id."""
    stream = io.StringIO()
    configure(stream)
    model = scripted(
        tool_call("search_entries", property="Cell"),
        tool_call("get_entry", entry_id=100002),
        says("1 μm [[100002]]"),
    )
    list(agent_with(repo, config, tmp_path, model).ask("s", "how wide?"))
    (evidence,) = _trail(stream, "answer.evidence")
    assert evidence["cited"] == [100002]
    assert "saved_ids" not in evidence
    assert all("saved_ids" not in r for r in _trail(stream, "search"))
    assert all("saved_id" not in r for r in _trail(stream, "entry.retrieved"))


def test_a_label_no_loaded_entry_carries_is_reported_unknown(store_path, config, tmp_path):
    repo = CorpusRepository(store_corpus.load(store_path))
    model = scripted(
        tool_call("search_entries", property="F-actin"),
        says("About 488 µM [[PMC1000001-9]]."),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "F-actin?"))
    (warning,) = [e for e in events if isinstance(e, CitationWarning)]
    assert warning.unknown == ("PMC1000001-9",)


# -- what the model is shown (D5) ---------------------------------------------


def _tools(repo):
    built = build_tools(repo, start_question("dev"), lambda event: None, ToolBudget(99))
    return {tool.name: tool for tool in built}


@pytest.fixture
def store_tools(store_path):
    return _tools(CorpusRepository(store_corpus.load(store_path)))


def test_a_corpus_file_s_tool_output_is_what_it_was_before_this_change(repo):
    """The snapshot was taken from the code before the store existed (2026-10-15), not after."""
    before = json.loads((FIXTURES / "tool_output_before_store.json").read_text(encoding="utf-8"))
    tools = _tools(repo)
    for entry_id, text in before["get"].items():
        assert tools["get_entry"].invoke({"entry_id": int(entry_id)}) == text
    assert tools["search_entries"].invoke({"property": "Cell"}) == before["search"]


def test_a_word_only_in_the_passage_finds_the_entry(store_path):
    """`lamellipodial` is in the quote, not in the paper's wording of the property. The repository
    matches a keyword as a substring of each keyword, so a whole passage held as one keyword is
    searched like any other (checked 2026-10-15 before relying on it)."""
    repo = CorpusRepository(store_corpus.load(store_path))
    assert "lamellipodial" not in repo.get("PMC1000001-1").entry.property.lower()
    found = {row.entry_id for row in repo.search(keyword="lamellipodial").rows}
    assert found == {"PMC1000001-1"}
    by_condition = {row.entry_id for row in repo.search(keyword="electron microscopy").rows}
    assert by_condition == {"PMC1000001-1"}
    assert {row.entry_id for row in repo.search(keyword="cytoskeleton").rows} >= {"PMC1000001-2"}
    assert repo.search(keyword="nowhere in any passage").rows == ()


def test_a_harvested_entry_shows_the_model_what_it_needs_to_judge_it(store_tools):
    text = store_tools["get_entry"].invoke({"entry_id": "PMC1000001-1"})
    assert "origin: measured" in text
    assert 'quote: "The lamellipodial F-actin concentration was 488 µM' in text
    assert 'condition: organism -- "invented mouse cells"' in text
    assert "not stated: temperature" in text
    assert "domain: biology / cytoskeleton" in text
    assert "trust: 3 of 5 (scientist, simulated review); disputed" in text


def test_a_calculated_entry_is_shown_as_a_calculation_with_its_inputs(store_tools):
    authors = store_tools["get_entry"].invoke({"entry_id": "PMC1000001-2"})
    assert "origin: calculated by the paper's authors" in authors
    assert 'calculated from: "Invented input passage one."' in authors
    assert "caution: this value was calculated, not measured" in authors
    published = store_tools["get_entry"].invoke({"entry_id": "PMC1000001-3"})
    assert "origin: calculated from values published elsewhere" in published
    measured = store_tools["get_entry"].invoke({"entry_id": "PMC1000001-1"})
    assert "calculated" not in measured


def test_an_uncertain_reading_is_cautioned_and_given_in_the_paper_s_words(store_tools):
    text = store_tools["get_entry"].invoke({"entry_id": "PMC1000001-4"})
    assert "value: 10–20 s" in text
    assert "caution: the value could not be read as a number with certainty" in text
    fitting = store_tools["get_entry"].invoke({"entry_id": "PMC1000001-1"})
    assert "could not be read" not in fitting


def test_every_tier_reads_as_words_on_one_scale(store_tools):
    shown = {
        i: store_tools["get_entry"].invoke({"entry_id": i})
        for i in (100001, "PMC1000001-2", "PMC1000001-3", "PMC1000001-4", "PMC2000002-1")
    }
    assert "trust: 5 of 5 (curated)" in shown[100001]
    assert "trust: 1 of 5 (AI reviewer)" in shown["PMC1000001-2"]
    assert "trust: 4 of 5 (senior scientist)" in shown["PMC1000001-3"]
    assert "trust: 0 of 5 (no reviewer approved it); disputed" in shown["PMC1000001-4"]
    assert "trust: 0 of 5 (not yet reviewed)" in shown["PMC2000002-1"]
    assert "disputed" not in shown["PMC2000002-1"]
    assert "★" not in "".join(shown.values()), "stars are the application's, never the model's"


def test_search_rows_carry_the_tier_for_store_entries(store_tools):
    text = store_tools["search_entries"].invoke({"property": "F-actin"})
    assert "entry_id\tproperty\torganism\tvalue\ttrust" in text
    assert "PMC1000001-1\tF-actin concentration\tmouse\t488 µM\ttrust 3/5, scientist, " in text
    assert (
        "PMC1000001-1.2\tF-actin concentration\tmouse\t500 µM\ttrust 0/5, not yet reviewed" in text
    )


# -- configuration (D7) -------------------------------------------------------


def test_naming_both_a_corpus_file_and_a_store_is_refused_naming_both(store_path):
    corpus_file = FIXTURES / "corpus_sample.jsonl"
    with pytest.raises(CorpusUnavailable) as refused:
        corpus.load_configured(corpus_file, store_path)
    message = str(refused.value)
    assert str(corpus_file) in message and str(store_path) in message
    assert "SCINUMBERS_CORPUS" in message and "SCINUMBERS_STORE" in message


def test_a_store_alone_loads_the_store_and_a_file_alone_loads_the_file(store_path):
    from_store = corpus.load_configured(None, store_path)
    assert any(e.harvest is not None for e in from_store)
    from_file = corpus.load_configured(FIXTURES / "corpus_sample.jsonl", None)
    assert all(e.harvest is None for e in from_file)


def test_a_store_read_as_a_corpus_file_is_refused_by_name(store_path):
    with pytest.raises(CorpusUnavailable, match="is a harvest store, not a corpus file"):
        corpus.load(store_path)
