"""The output satisfies the ask agent's corpus loader.

That loader lives on `feat/ask-agent` and cannot be imported here, so the contract
is verified in three layers (ADR-0210): this file states the required keys and
types as one literal and asserts every emitted line against them; the round-trip
at the bottom activates the moment the two branches meet on `dev`; and a one-off
extraction of the real loader is run by hand during implementation and recorded in
`tasks.md`.

Its traps are the interesting part, and none of them is caught by checking that
keys are present.
"""

import json

import pytest

from bionumbers_ingest.cleaning import clean_row, is_data_row
from bionumbers_ingest.io import write_corpus
from bionumbers_ingest.model import BioNumberRecord
from bionumbers_ingest.parsing import iter_rows

# The twelve keys the consumer models, and the JSON types it accepts for each.
#
# SOURCE: `scinumbers_ask.corpus.Entry` and its `_number` / `_keywords` coercions,
# on branch `feat/ask-agent`. Restated here as a literal rather than imported,
# because that branch is not on this one. Two copies of a contract drift, so this
# list is deliberately the ONLY copy in this branch, and the round-trip test at
# the bottom takes over as the authority once the branches merge.
REQUIRED = {
    "entry_id": (int,),
    "property": (str, type(None)),
    "organism": (str, type(None)),
    "units": (str, type(None)),
    "value": (int, float, type(None)),
    "range_low": (int, float, type(None)),
    "range_high": (int, float, type(None)),
    "reference": (str, type(None)),
    "reference_pubmed_id": (str, type(None)),
    "measurement_method": (str, type(None)),
    "comments": (str, type(None)),
    "keywords": (list,),
}

SCALARS = ("value", "range_low", "range_high")


@pytest.fixture
def corpus(tmp_path, sample_html):
    out = tmp_path / "corpus.jsonl"
    write_corpus((clean_row(raw) for raw in iter_rows(sample_html) if is_data_row(raw)), out)
    return [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]


def test_every_line_carries_every_required_key_with_an_accepted_type(corpus):
    assert corpus
    for obj in corpus:
        for key, accepted in REQUIRED.items():
            assert key in obj, f"entry_id {obj.get('entry_id')} is missing {key}"
            assert isinstance(obj[key], accepted), (
                f"entry_id {obj.get('entry_id')}: {key} is {type(obj[key]).__name__}, "
                f"not one of {[t.__name__ for t in accepted]}"
            )


def test_entry_id_is_a_number_not_a_string(corpus):
    # the loader coerces, but a string identifier would sort and compare wrongly
    for obj in corpus:
        assert isinstance(obj["entry_id"], int)
        assert not isinstance(obj["entry_id"], bool)


@pytest.mark.parametrize("key", SCALARS)
def test_an_absent_scalar_is_null_and_never_an_empty_string(corpus, key):
    # THE trap. `_number` treats "" as None, but "" is not None: an emitted ""
    # satisfies the loader's has-a-value branch and blanks out the measurement of
    # every range-only entry, which is 4,985 entries of the real corpus.
    for obj in corpus:
        assert obj[key] != "", f"entry_id {obj['entry_id']}: {key} is an empty string"
        assert obj[key] is None or isinstance(obj[key], (int, float))


def test_keywords_is_an_array_never_a_joined_string(corpus):
    # `tuple()` over a string yields one entry per character, silently, so a
    # joined string becomes a keyword list of letters.
    for obj in corpus:
        kws = obj["keywords"]
        assert isinstance(kws, list)
        assert all(isinstance(k, str) for k in kws)
        # a joined string passed to tuple() becomes a list of single characters
        looks_per_character = len(kws) > 3 and all(len(k) == 1 for k in kws)
        assert not looks_per_character, f"entry_id {obj['entry_id']}: keywords are letters: {kws}"


def test_the_predicate_and_the_flags_are_present_on_every_line(corpus):
    # Not part of the twelve, but a consumer models `range_fused` as one required
    # field with a default — so it must never be absent.
    for obj in corpus:
        assert isinstance(obj["range_fused"], bool)
        assert isinstance(obj["parse_flags"], list)


def test_extra_keys_are_permitted_by_construction(corpus):
    # The consumer ignores what it does not model; this records that we rely on it.
    extra = set(corpus[0]) - set(REQUIRED)
    assert "range_fused" in extra and "parse_flags" in extra


def test_one_unusable_line_costs_the_whole_corpus(tmp_path):
    """Why every emitted line must already be a complete record.

    The consumer raises on the *first* line it cannot read and returns nothing, so
    a single malformed line does not cost one entry — it costs all of them. This
    test states the stake; the writer's job is to make it unreachable by never
    emitting a partially-built record.
    """
    out = tmp_path / "corpus.jsonl"
    write_corpus([BioNumberRecord(entry_id=1), BioNumberRecord(entry_id=2)], out)
    good = out.read_text(encoding="utf-8").splitlines()
    out.write_text("\n".join([good[0], "{not json", good[1]]) + "\n", encoding="utf-8")

    loaded = []
    for line in out.read_text(encoding="utf-8").splitlines():
        try:
            loaded.append(json.loads(line))
        except json.JSONDecodeError:
            loaded = []  # what the real loader does: abandon the whole corpus
            break
    assert loaded == [], "a malformed line must abandon the corpus, not be skipped"


def test_round_trip_through_the_real_loader(tmp_path, sample_html):
    """Live only once `scinumbers_ask` is importable — i.e. after the merge to dev.

    Skipped on this branch by design. It becomes the authority over the literal
    above at exactly the moment loader drift would otherwise start going unnoticed.
    Verified by hand in the meantime; see task 5.5.
    """
    corpus_mod = pytest.importorskip(
        "scinumbers_ask.corpus",
        reason="the consumer lives on feat/ask-agent; live after the merge to dev",
    )
    out = tmp_path / "corpus.jsonl"
    written = write_corpus(
        (clean_row(raw) for raw in iter_rows(sample_html) if is_data_row(raw)), out
    )
    entries = corpus_mod.load(out)
    assert len(entries) == written
    for entry in entries:
        assert entry.value_display, f"entry_id {entry.entry_id} renders as an empty measurement"
        assert isinstance(entry.keywords, tuple)


def test_the_two_hedge_kinds_partition_the_qualified_field(sample_html, tmp_path):
    """`range_qualified` is true exactly when one of the two kinds is.

    Derived from the two sets rather than listed beside them, so a third kind of
    hedge cannot be added to one and forgotten in the other. `add-ask-agent`
    asserts the same partition from its side; this holds up its end.
    """
    from bionumbers_ingest.ingest import build_records

    records, *_ = build_records(sample_html)
    assert records
    for record in records:
        assert record.range_qualified == (record.range_one_sided or record.range_approximate)


def test_the_hedge_kind_is_a_field_not_a_flag_name():
    """The kind decides the words a reader is shown, so it is contract.

    Read out of `parse_flags` by name, a rename here turned the consumer's field
    silently false -- its fallback wording kept working, which is what would have
    hidden it.
    """
    from bionumbers_ingest.cleaning import clean_row

    bound = clean_row({"bion_id": "1", "Range": "'<0.001"})
    assert bound.range_one_sided is True
    assert bound.range_approximate is False

    about = clean_row({"bion_id": "1", "Range": "'~5"})
    assert about.range_approximate is True
    assert about.range_one_sided is False

    plain = clean_row({"bion_id": "1", "Range": "'5 - 10"})
    assert plain.range_one_sided is False and plain.range_approximate is False
