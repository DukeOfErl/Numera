"""The `bionumbers` command, driven end to end over fixtures and doubles.

Nothing here reaches a network or a model. Europe PMC is the recorded double behind the command's
`_europepmc` seam; the model is a scripted double behind `_model`, whose answers quote the real
fixture article so the checker between them does its actual job. Every expected figure below is
either read off a fixture or is a count of what the test itself put in.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from europepmc_double import TABLES_PMCID, FakeEuropePMC, fixture
from sqlalchemy import create_engine, func, select

from bionumbers import cli, store
from bionumbers.cache import DocumentCache
from bionumbers.distractor import Candidate, SecondTextOutput
from bionumbers.europepmc import VERSION_OF_RECORD, EuropePMC
from bionumbers.extraction import (
    ClaimDraft,
    ExtractionOutput,
    ProviderRefused,
    QuoteDraft,
    read_results,
)
from bionumbers.jats import read_jats
from bionumbers.openrouter import API_KEY_ENV
from bionumbers.records import (
    UNLICENSED,
    CandidateKind,
    ClaimKind,
    DistractorType,
    NotReviewable,
    Paper,
    PaperState,
    ReviewItem,
)

ARTICLE_XML = fixture(f"fulltext_{TABLES_PMCID}.xml")
ARTICLE = read_jats(ARTICLE_XML)

#: Copied out of the fixture's FIB-SEM methods paragraph: two settings with a number each.
APERTURE_SENTENCE = "an aperture diameter of 100 μm"
DWELL_SENTENCE = "a pixel dwell time of 2 μs"
#: A results sentence with no digit in it at all, so it is admissible beside any value.
DISTRACTOR_SENTENCE = (
    "Taken together, these machine learning-guided analyses enable robust quantification"
)

QUESTION = "aperture diameter"
ORGANISM = "Coxiella burnetii"
RUN = "r1"

#: One of the pmcids the recorded cursor walk keeps; none of them has a full-text fixture, so a
#: test that wants one with text points the double's override at the article above.
A_KEPT_PMCID = "PMC13447829"


def passage_holding(phrase: str) -> str:
    for passage in ARTICLE.passages:
        if phrase in passage.text:
            return passage.id
    raise AssertionError(f"no passage contains {phrase!r}; the fixture has changed")


def claim_draft(sentence: str, value: str, unit: str) -> ClaimDraft:
    return ClaimDraft(
        property_in_paper="aperture",
        value=value,
        unit=unit,
        kind=ClaimKind.SINGLE,
        candidate_kind=CandidateKind.MEASURED,
        quote=QuoteDraft(text=sentence, passage_id=passage_holding(sentence)),
    )


def distractor_output() -> SecondTextOutput:
    passage = ARTICLE.passage(passage_holding(DISTRACTOR_SENTENCE))
    assert passage is not None
    return SecondTextOutput(
        candidates=[
            Candidate(
                passage_id=passage.id, text=passage.text, type=DistractorType.DIFFERENT_QUANTITY
            )
        ]
    )


USAGE = SimpleNamespace(
    input_tokens=61_000,
    cache_creation_input_tokens=0,
    cache_read_input_tokens=0,
    output_tokens=1_200,
)


class ScriptedModel:
    """Answers from a queue -- the extraction output first, then one second-text output per
    claim in order -- and records every call, so a test can say a call never happened."""

    def __init__(self, *answers) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []

    def count_tokens(self, *, system, messages, output_format=None):
        return SimpleNamespace(input_tokens=61_000)

    def parse(self, *, system, messages, output_format, max_tokens):
        self.calls.append({"output_format": output_format})
        return SimpleNamespace(parsed_output=self.answers.pop(0), usage=USAGE)


@pytest.fixture
def api():
    return FakeEuropePMC()


@pytest.fixture
def dirs(tmp_path):
    return SimpleNamespace(runs=tmp_path / "runs", data=tmp_path / "data")


@pytest.fixture
def provider(monkeypatch, api, dirs):
    """The command's Europe PMC, served from the double and caching where the test says."""

    def build(data_dir: Path) -> EuropePMC:
        assert data_dir == dirs.data
        return EuropePMC(api.client(), cache=DocumentCache(data_dir))

    monkeypatch.setattr(cli, "_europepmc", build)
    return api


def scripted(monkeypatch, *answers) -> ScriptedModel:
    model = ScriptedModel(*answers)
    monkeypatch.setattr(cli, "_model", lambda model_id: model)
    return model


def common(dirs) -> list[str]:
    return ["--runs", str(dirs.runs), "--data", str(dirs.data)]


def seed_run(dirs, papers: list[Paper], *, cached: dict[str, str] | None = None) -> Path:
    """A run directory as `discover` leaves it, and the cache as it would be after the fetches."""
    run_dir = dirs.runs / RUN
    run_dir.mkdir(parents=True)
    (run_dir / cli.REQUEST_FILE).write_text(
        json.dumps({"question": QUESTION, "organism": ORGANISM, "since_year": 2005, "sections": []})
    )
    (run_dir / cli.PAPERS_FILE).write_text("".join(p.model_dump_json() + "\n" for p in papers))
    cache = DocumentCache(dirs.data)
    for pmcid, xml in (cached or {}).items():
        cache.put(pmcid, VERSION_OF_RECORD, xml)
    return run_dir


def read_jsonl(path: Path, record: type) -> list:
    return [record.model_validate_json(line) for line in path.read_text().splitlines() if line]


LICENSED = Paper(pmcid=TABLES_PMCID, title="FIB-SEM of Coxiella", year=2026, licence="CC BY 4.0")
TEXTLESS = Paper(pmcid="PMC99999999", title="Never served", year=2025)


# --- discover ---------------------------------------------------------------------------------


def test_discover_records_the_query_and_every_kept_paper_with_its_text_or_its_absence(
    provider, dirs, capsys
):
    provider.full_text_overrides[A_KEPT_PMCID] = httpx.Response(200, text=ARTICLE_XML)

    code = cli.main(
        [
            "discover",
            "doubling time",
            "--organism",
            "Escherichia coli",
            "--since",
            "2020",
            "--limit",
            "8",
            "--sections",
            "RESULTS,TABLE",
            "--run-id",
            RUN,
            *common(dirs),
        ]
    )

    assert code == 0
    discovery = json.loads((dirs.runs / RUN / cli.DISCOVERY_FILE).read_text())
    assert discovery["limit"] == 8
    assert discovery["query"].startswith(
        '(RESULTS:("doubling time" AND "Escherichia coli") OR TABLE:("doubling time" AND '
        '"Escherichia coli")) AND OPEN_ACCESS:Y'
    )
    assert "PUB_YEAR:[2020 TO " in discovery["query"]
    assert discovery["query"] in capsys.readouterr().out

    papers = read_jsonl(dirs.runs / RUN / cli.PAPERS_FILE, Paper)
    assert [p.pmcid for p in papers] == [p["pmcid"] for p in discovery["kept"]]
    assert len(papers) == 8

    (with_text,) = [p for p in papers if p.pmcid == A_KEPT_PMCID]
    assert with_text.licence == "https://creativecommons.org/licenses/by/4.0/"
    assert with_text.source_url.endswith(f"/{A_KEPT_PMCID}/fullTextXML")
    assert with_text.full_text_status == ""
    for paper in papers:
        if paper.pmcid != A_KEPT_PMCID:
            assert paper.full_text_status == "no XML (HTTP 500)"
            assert paper.licence == UNLICENSED


# --- extract ----------------------------------------------------------------------------------


def test_extract_ends_every_paper_in_a_state_and_accounts_for_every_claim(
    monkeypatch, provider, dirs
):
    model = scripted(
        monkeypatch,
        ExtractionOutput(
            state="CLAIMS_FOUND",
            claims=[
                claim_draft(APERTURE_SENTENCE, "100", "μm"),
                claim_draft(DWELL_SENTENCE, "2", "μs"),
            ],
        ),
        distractor_output(),
        SecondTextOutput(candidates=[]),
    )
    seed_run(dirs, [LICENSED, TEXTLESS], cached={TABLES_PMCID: ARTICLE_XML})

    code = cli.main(["extract", RUN, *common(dirs)])

    assert code == 0
    assert len(model.calls) == 3
    results = {r.paper.pmcid: r for r in read_results(dirs.runs / RUN / "results.jsonl")}
    assert results[TEXTLESS.pmcid].state is PaperState.UNREADABLE
    assert "500" in results[TEXTLESS.pmcid].reason
    assert results[TEXTLESS.pmcid].fingerprint.run_id == RUN
    assert results[LICENSED.pmcid].state is PaperState.CLAIMS_FOUND
    assert len(results[LICENSED.pmcid].claims) == 2

    items = read_jsonl(dirs.runs / RUN / cli.ITEMS_FILE, ReviewItem)
    not_reviewable = read_jsonl(dirs.runs / RUN / cli.NOT_REVIEWABLE_FILE, NotReviewable)
    claim_ids = {c.claim_id for c in results[LICENSED.pmcid].claims}
    assert {i.claim.claim_id for i in items} | {n.claim_id for n in not_reviewable} == claim_ids
    assert len(items) == 1 and len(not_reviewable) == 1
    assert items[0].second.text.startswith(DISTRACTOR_SENTENCE)

    summary = json.loads((dirs.runs / RUN / cli.SUMMARY_FILE).read_text())
    assert summary["states"] == {"CLAIMS_FOUND": 1, "UNREADABLE": 1}
    assert summary["papers"] == 2
    assert summary["papers_left_unread"] == 0
    assert summary["items"] == 1 and summary["not_reviewable"] == 1
    assert summary["unlicensed"] == 0
    # The paper's record carries all three calls -- extraction and both second texts -- and the
    # run's spend is that paper's, since the other paper was never sent. The dollar figure is
    # the price table's, not this file's.
    assert results[LICENSED.pmcid].spend.calls == 3
    assert summary["spend_usd"] == pytest.approx(results[LICENSED.pmcid].spend.usd)
    assert summary["spend_usd"] > 0
    assert summary["cached_fraction"] == 0.0


def test_extract_without_a_key_says_which_variable_and_touches_nothing(
    monkeypatch, provider, dirs, capsys
):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    seed_run(dirs, [LICENSED], cached={TABLES_PMCID: ARTICLE_XML})

    code = cli.main(["extract", RUN, *common(dirs)])

    assert code == 2
    assert API_KEY_ENV in capsys.readouterr().err
    assert provider.requests == []
    assert not (dirs.runs / RUN / "results.jsonl").exists()


def test_a_refusal_of_the_account_stops_the_run_and_leaves_the_rest_unread(
    monkeypatch, provider, dirs, capsys
):
    """The 402 of 2026-09-22: the first paper is read, the second meets the refusal and ends
    FAILED with the provider's words, the third is left unread rather than failed too, and the
    command's exit code says the run did not finish."""

    class RefusingOnTheSecond(ScriptedModel):
        def parse(self, **kwargs):
            if len(self.calls) == 1:
                self.calls.append({"refused": True})
                raise ProviderRefused("HTTP 402 from OpenRouter: Insufficient credits")
            return super().parse(**kwargs)

    model = RefusingOnTheSecond(ExtractionOutput(state="NOTHING_TO_EXTRACT", reason="unused"))
    monkeypatch.setattr(cli, "_model", lambda model_id: model)
    trio = [LICENSED.model_copy(update={"pmcid": f"PMC{n}"}) for n in (1, 2, 3)]
    seed_run(dirs, trio, cached={p.pmcid: ARTICLE_XML for p in trio})

    code = cli.main(["extract", RUN, *common(dirs)])

    assert code == 3
    assert "402" in capsys.readouterr().err
    results = read_results(dirs.runs / RUN / "results.jsonl")
    assert [r.state for r in results] == [PaperState.NOTHING_TO_EXTRACT, PaperState.FAILED]
    assert "Insufficient credits" in results[1].reason
    summary = json.loads((dirs.runs / RUN / cli.SUMMARY_FILE).read_text())
    assert summary["papers_left_unread"] == 1
    assert "402" in summary["stopped"]
    assert len(model.calls) == 2, "no call was made for the third paper"


def test_extract_with_an_unpriced_model_refuses_before_any_paper(
    monkeypatch, provider, dirs, capsys
):
    """Left to the ledger, every paper would end FAILED one by one and the run's results would be
    overwritten with a column of failures."""
    model = scripted(monkeypatch, ExtractionOutput(state="NOTHING_TO_EXTRACT", reason="unused"))
    seed_run(dirs, [LICENSED], cached={TABLES_PMCID: ARTICLE_XML})

    code = cli.main(["extract", RUN, "--model", "acme/unknown-model", *common(dirs)])

    assert code == 2
    assert "acme/unknown-model" in capsys.readouterr().err
    assert model.calls == []
    assert provider.requests == []
    assert not (dirs.runs / RUN / "results.jsonl").exists()


def test_a_run_budget_that_affords_nothing_stops_the_run_and_counts_the_papers_left(
    monkeypatch, provider, dirs
):
    model = scripted(monkeypatch, ExtractionOutput(state="NOTHING_TO_EXTRACT", reason="unused"))
    trio = [LICENSED.model_copy(update={"pmcid": f"PMC{n}"}) for n in (1, 2, 3)]
    seed_run(dirs, trio, cached={p.pmcid: ARTICLE_XML for p in trio})

    code = cli.main(["extract", RUN, "--budget", "0.0001", *common(dirs)])

    assert code == 0
    assert model.calls == []
    results = read_results(dirs.runs / RUN / "results.jsonl")
    assert [r.state for r in results] == [PaperState.CEILING_REACHED]
    assert results[0].reason.startswith("run ceiling")
    summary = json.loads((dirs.runs / RUN / cli.SUMMARY_FILE).read_text())
    assert summary["papers_left_unread"] == 2
    assert summary["papers"] == 3
    assert summary["spend_usd"] == 0.0


def test_an_unlicensed_paper_is_read_but_nothing_it_says_leaves_the_cache(
    monkeypatch, provider, dirs
):
    model = scripted(
        monkeypatch,
        ExtractionOutput(
            state="CLAIMS_FOUND", claims=[claim_draft(APERTURE_SENTENCE, "100", "μm")]
        ),
    )
    unlicensed = LICENSED.model_copy(update={"licence": UNLICENSED})
    seed_run(dirs, [unlicensed], cached={TABLES_PMCID: ARTICLE_XML})

    code = cli.main(["extract", RUN, *common(dirs)])

    assert code == 0
    assert len(model.calls) == 1, "no second-text call is made for a paper with no items"
    (result,) = read_results(dirs.runs / RUN / "results.jsonl")
    assert result.claims == () and result.rejected == ()
    assert result.reason.startswith("unlicensed: text not kept; ")
    assert result.spend.calls == 1, "the extraction was made and its spend stands"
    assert read_jsonl(dirs.runs / RUN / cli.ITEMS_FILE, ReviewItem) == []
    summary = json.loads((dirs.runs / RUN / cli.SUMMARY_FILE).read_text())
    assert summary["unlicensed"] == 1


# --- the guard --------------------------------------------------------------------------------


@pytest.mark.parametrize("subcommand", ["discover", "extract"])
def test_a_runs_directory_git_would_track_is_refused_before_anything_happens(
    monkeypatch, provider, dirs, subcommand, capsys
):
    """`tests/` is tracked, so a run written there would carry article text into history."""
    scripted(monkeypatch)
    tracked = Path(__file__).parent / "would-be-committed-runs"
    argv = {
        "discover": [
            "discover",
            "doubling time",
            "--organism",
            "Escherichia coli",
            "--run-id",
            RUN,
        ],
        "extract": ["extract", RUN],
    }[subcommand]

    code = cli.main([*argv, "--runs", str(tracked), "--data", str(dirs.data)])

    assert code == 2
    assert "git would track" in capsys.readouterr().err
    assert not tracked.exists()
    assert provider.requests == []


# --- status and load --------------------------------------------------------------------------


def a_finished_run(monkeypatch, dirs):
    scripted(
        monkeypatch,
        ExtractionOutput(
            state="CLAIMS_FOUND", claims=[claim_draft(APERTURE_SENTENCE, "100", "μm")]
        ),
        distractor_output(),
    )
    seed_run(dirs, [LICENSED, TEXTLESS], cached={TABLES_PMCID: ARTICLE_XML})
    assert cli.main(["extract", RUN, *common(dirs)]) == 0


def test_status_reads_states_and_spend_off_the_run_files(monkeypatch, provider, dirs, capsys):
    a_finished_run(monkeypatch, dirs)
    requests_before = list(provider.requests)
    results = read_results(dirs.runs / RUN / "results.jsonl")
    total = sum(r.spend.usd for r in results)

    code = cli.main(["status", RUN, "--runs", str(dirs.runs)])

    out = capsys.readouterr().out
    assert code == 0
    assert "CLAIMS_FOUND 1" in out and "UNREADABLE 1" in out
    assert f"total: ${total:.4f}" in out
    assert "1 item(s)" in out
    assert provider.requests == requests_before, "status made a request"


def test_load_puts_the_run_s_papers_and_items_in_the_store(monkeypatch, provider, dirs, capsys):
    a_finished_run(monkeypatch, dirs)
    url = f"sqlite:///{dirs.runs / 'review.db'}"
    engine = create_engine(url)
    store.create_all(engine)

    code = cli.main(["load", RUN, "--runs", str(dirs.runs), "--db-url", url])

    assert code == 0
    assert "1 item(s)" in capsys.readouterr().out
    with engine.begin() as conn:
        assert conn.scalar(select(func.count()).select_from(store.review_item)) == 1
        assert conn.scalar(select(func.count()).select_from(store.review_paper)) == 2
    engine.dispose()


def test_load_without_a_database_says_which_variable(monkeypatch, dirs, capsys):
    monkeypatch.delenv(cli.DB_URL_ENV, raising=False)

    code = cli.main(["load", RUN, "--runs", str(dirs.runs)])

    assert code == 2
    assert cli.DB_URL_ENV in capsys.readouterr().err
