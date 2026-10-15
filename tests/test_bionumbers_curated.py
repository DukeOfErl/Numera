"""The curated tier: which BioNumbers entries may stand at the top of the trust order (ADR-1510).

Each refusal has a case that differs from an admitted entry in the one field the rule reads, built
from `an_entry` by replacing that field only -- a negative case that varied something else would
pass whether or not the rule held.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, func, select

from bionumbers import cli, curated, store
from bionumbers.curated import Refusal


def an_entry(**changes) -> dict:
    """An entry that is curated: yeast, measured, referenced, a value with a unit, no doubt."""
    raw = {
        "entry_id": 100267,
        "property": "Number of ribosomes",
        "organism": "Budding yeast Saccharomyces cerevisiae",
        "value": 187000.0,
        "range_low": None,
        "range_high": None,
        "units": "Ribosomes/cell",
        "range_fused": False,
        "range_one_sided": False,
        "range_approximate": False,
        "reference": "von der Haar T. BMC Syst Biol. 2008",
        "reference_pubmed_id": "19014594",
        "measurement_method": "Quantitative northern blot of rRNA",
        "comments": "Mean of three cultures.",
        "keywords": ["ribosome"],
    }
    return raw | changes


def test_an_entry_with_nothing_against_it_is_curated():
    assert curated.refusal(an_entry()) is None
    entry = curated.entry(an_entry())
    assert entry.value == 187000.0 and entry.units == "Ribosomes/cell"
    assert entry.url.endswith("id=100267")


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"organism": "Escherichia coli", "property": "Number of ribosomes"}, Refusal.OUT_OF_SCOPE),
        ({"value": None}, Refusal.NO_VALUE),
        ({"value": None, "range_low": 3.0}, Refusal.NO_VALUE),
        ({"measurement_method": ""}, Refusal.NOT_MEASURED),
        ({"measurement_method": "Calculated from cell volume"}, Refusal.NOT_MEASURED),
        ({"reference_pubmed_id": None}, Refusal.NO_REFERENCE),
        ({"range_fused": True}, Refusal.FUSED_RANGE),
        ({"value": None, "range_low": 1.0, "range_high": 2e6}, Refusal.IMPLAUSIBLE_SPAN),
        ({"range_one_sided": True}, Refusal.ONE_SIDED),
        ({"units": "N/A"}, Refusal.NO_UNIT),
        ({"units": ""}, Refusal.NO_UNIT),
        ({"units": "μM^-1хsec^-1"}, Refusal.GARBLED_UNIT),
        ({"comments": "As a rule of thumb, the pH of the cytoplasm is 7.2"}, Refusal.DOUBT),
        ({"comments": "The authors note discrepancies among the ratios"}, Refusal.DOUBT),
        ({"keywords": ["order of magnitude"]}, Refusal.DOUBT),
    ],
)
def test_each_sign_of_doubt_keeps_an_entry_out(changes, reason):
    assert curated.refusal(an_entry(**changes)) is reason
    with pytest.raises(ValueError, match=reason.value):
        curated.entry(an_entry(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        # The scope reads the organism or the property: either alone admits.
        {"organism": "Chicken Gallus gallus", "property": "Persistence length of actin"},
        {"organism": "Fission yeast Schizosaccharomyces pombe"},
        {"organism": "Mouse", "property": "Length", "keywords": ["microtubule"]},
        # A two-sided range is a value; so are bounds a millionfold apart exactly.
        {"value": None, "range_low": 1.0, "range_high": 1e6},
        # Units the slice really holds, written in characters the export keeps.
        {"units": "μm^2/sec"},
        {"units": "Å"},
        {"units": "N×m^2"},
        # Words that read as doubt and were not, in the slice.
        {"comments": "measured in crude cell extracts"},
        {"comments": "most probably results from internalization"},
        # The source's own hedge is kept and recorded, not refused.
        {"range_approximate": True},
    ],
)
def test_what_reads_like_doubt_and_is_not_still_admits(changes):
    assert curated.refusal(an_entry(**changes)) is None


def test_the_approximate_hedge_travels_with_the_entry():
    assert curated.entry(an_entry(range_approximate=True)).approximate is True
    assert curated.entry(an_entry()).approximate is False


def test_select_keeps_the_curated_and_counts_the_rest_by_reason():
    kept, refused = curated.select(
        [an_entry(), an_entry(entry_id=2, range_fused=True), an_entry(entry_id=3, units="N/A")]
    )
    assert [entry.entry_id for entry in kept] == [100267]
    assert refused == {Refusal.FUSED_RANGE: 1, Refusal.NO_UNIT: 1}


def test_the_loader_refuses_by_itself_whatever_its_caller_passed(engine):
    """The refusal belongs to the operation: a caller handing the loader corpus lines directly,
    without the command's selection, still cannot put a doubted entry in the tier."""
    loaded, refused = store.load_curated(
        engine,
        [
            an_entry(),
            an_entry(entry_id=2, range_fused=True),
            an_entry(entry_id=3, comments="As a rule of thumb, about 7.2"),
        ],
    )
    assert loaded == 1
    assert refused == {Refusal.FUSED_RANGE: 1, Refusal.DOUBT: 1}
    with engine.connect() as conn:
        assert list(conn.scalars(select(store.curated_entry.c.entry_id))) == [100267]


# --- the table and the command -------------------------------------------------------------


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'review.sqlite'}")
    store.create_all(engine)
    return engine


def test_a_load_replaces_the_tier_rather_than_adding_to_it(engine):
    assert store.load_curated(engine, [an_entry(), an_entry(entry_id=2)])[0] == 2
    assert store.load_curated(engine, [an_entry(entry_id=3)])[0] == 1

    with engine.connect() as conn:
        ids = list(conn.scalars(select(store.curated_entry.c.entry_id)))
    assert ids == [3]


def test_curate_loads_the_slice_and_says_what_it_left_out(tmp_path, engine, capsys):
    corpus = tmp_path / "bionumbers.jsonl"
    lines = [
        an_entry(),
        an_entry(entry_id=2, range_one_sided=True),
        an_entry(entry_id=3, organism="Human", property="Body temperature", keywords=[]),
    ]
    corpus.write_text("\n".join(json.dumps(line) for line in lines))

    code = cli.main(["curate", "--corpus", str(corpus), "--db-url", str(engine.url)])

    assert code == 0
    out = capsys.readouterr().out
    assert "1 curated entry of 2 in the slice" in out
    assert "1 left out: a bound, not a value" in out
    assert "outside" not in out
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(store.curated_entry)) == 1


def test_curate_without_a_corpus_says_so(monkeypatch, engine, capsys):
    monkeypatch.delenv(cli.CORPUS_ENV, raising=False)
    assert cli.main(["curate", "--db-url", str(engine.url)]) == 2
    assert cli.CORPUS_ENV in capsys.readouterr().err
