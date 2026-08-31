"""Two-tier retrieval, tolerant matching, and the read-only guarantee."""

from __future__ import annotations

import dataclasses
import io

import pytest

from scinumbers_ask.corpus import load
from scinumbers_ask.repository import CorpusRepository
from scinumbers_ask.trace import configure, start_question

FIXTURE = "tests/fixtures/corpus_sample.jsonl"
SECOND, COUNT = 100002, 100020


@pytest.fixture
def repo() -> CorpusRepository:
    return CorpusRepository(load(FIXTURE))


# -- two-tier retrieval ---------------------------------------------------


def test_search_caps_rows_but_reports_the_true_total(repo):
    result = repo.search(property="Cell", limit=2)
    assert len(result.rows) == 2
    # Without the total, a caller cannot tell "that is all" from "that is some".
    assert result.total_matched == 4
    assert result.truncated is True


def test_an_untruncated_search_says_so(repo):
    result = repo.search(property="ribosomes", limit=50)
    assert result.total_matched == 1
    assert result.truncated is False


def test_a_search_matching_nothing_returns_nothing_invented(repo):
    result = repo.search(property="does not occur anywhere")
    assert result.rows == ()
    assert result.total_matched == 0


def test_compact_rows_carry_enough_to_choose_between_entries(repo):
    row = repo.search(property="Cell diameter", organism="cerevisiae").rows[0]
    assert (row.bnid, row.value, row.units) == (100010, "5.0", "μm")
    assert "Saccharomyces" in row.organism


# -- tolerant matching and the alias index --------------------------------


def test_a_substring_of_the_stored_organism_matches(repo):
    assert repo.search(organism="coli").total_matched == 4


def test_matching_ignores_case(repo):
    assert repo.search(organism="BACTERIA").total_matched == 4


def test_an_abbreviated_binomial_resolves_through_the_index(repo):
    # "e. coli" is not a substring of "Bacteria Escherichia coli", so this can
    # only work through the alias index -- which is why the index exists.
    assert "e. coli" not in "Bacteria Escherichia coli".lower()
    assert repo.search(organism="e. coli").total_matched == 4


def test_the_index_is_inspectable_and_deterministic(repo):
    aliases = repo.aliases()
    assert aliases["e. coli"] == frozenset({"Bacteria Escherichia coli"})
    # Rebuilding from the same corpus yields the same mapping.
    assert CorpusRepository(load(FIXTURE)).aliases() == aliases


def test_an_unmapped_term_falls_back_to_plain_matching(repo):
    assert repo.search(organism="Xenopus").total_matched == 1


# -- vocabulary discovery -------------------------------------------------


def test_vocabulary_lists_stored_values_with_counts(repo):
    values = dict(repo.vocabulary("organism", "coli"))
    assert values == {"Bacteria Escherichia coli": 4}


def test_vocabulary_distinguishes_absent_from_differently_worded(repo):
    # Nothing stored for this term at all.
    assert repo.vocabulary("organism", "Drosophila") == ()
    # Stored, but under wording a caller might not guess.
    assert repo.vocabulary("organism", "frog")[0][0].startswith("African clawed frog")


def test_a_keyword_matches_an_entrys_keywords(repo):
    """Found by mutation testing: inverting this match to `not in` survived the
    whole suite. Keyword search is a retrieval path -- matching the wrong entries
    silently changes what the model is allowed to answer from."""
    # "radius" appears only in an entry's keywords, never in a property.
    assert [row.bnid for row in repo.search(keyword="radius").rows] == [SECOND]


def test_a_keyword_matches_a_property_the_keywords_do_not_carry(repo):
    """The second half of the same condition: "ribosomes" is in the property and
    not in the keywords, which are stored singular. Joining the two checks with
    `and` instead of `or` also survived."""
    assert [row.bnid for row in repo.search(keyword="ribosomes").rows] == [COUNT]


@pytest.mark.parametrize("keyword", ["RADIUS", "Radius"])
def test_keyword_matching_ignores_case_on_both_sides(repo, keyword):
    """The model writes the question's wording, not the curator's. Case-folding
    either side away survived every test."""
    assert [row.bnid for row in repo.search(keyword=keyword).rows] == [SECOND]


def test_vocabulary_lists_properties_as_well_as_organisms(repo):
    """Only the organism field was exercised: renaming the property key to
    "PROPERTY" survived. This is how the agent discovers the corpus's wording
    after an empty search, and properties are the harder half to guess."""
    assert repo.vocabulary("property", "cell") == (
        ("Cell diameter", 2),
        ("Cell length", 1),
        ("Cell volume", 1),
    )


def test_vocabulary_leads_with_the_commonest_value(repo):
    """The order carries the meaning -- it tells the agent which wording the
    corpus actually uses. Inverting the sort, and dropping it entirely, both
    survived."""
    counts = [n for _, n in repo.vocabulary("property", "cell")]
    assert counts == sorted(counts, reverse=True)
    # Organisms, because there the count order and the alphabetical order differ.
    # Among properties they coincide, so that listing cannot tell a real sort from
    # no sort at all -- which is how dropping the key entirely went unnoticed.
    values = [value for value, _ in repo.vocabulary("organism", "")]
    assert values[0].startswith("Bacteria"), "the commonest organism should lead"
    assert values != sorted(values), "this is not merely alphabetical"
    # Ties broken by name, so the listing is stable between runs.
    tied = [v for v, n in repo.vocabulary("property", "cell") if n == 1]
    assert tied == sorted(tied)


# -- full entries and cross-references ------------------------------------


def test_a_full_entry_exposes_its_cited_identifiers(repo):
    assert repo.get(100001).cited_bnids == (102065, 104333)


def test_an_entry_citing_nothing_has_an_empty_list(repo):
    assert repo.get(100003).cited_bnids == ()


def test_an_unknown_identifier_returns_nothing(repo):
    assert repo.get(999999) is None


# -- read-only ------------------------------------------------------------


def test_the_repository_exposes_no_way_to_change_the_corpus(repo):
    public = [n for n in dir(repo) if not n.startswith("_")]
    assert sorted(public) == ["aliases", "get", "search", "vocabulary"]


def test_entries_cannot_be_mutated(repo):
    entry = repo.get(100002).entry
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.value = 99.0  # type: ignore[misc]


def test_answering_a_question_leaves_the_corpus_unchanged(repo):
    before = repo.search(property="", limit=1000).total_matched
    repo.search(property="Cell")
    repo.get(100001)
    repo.vocabulary("organism", "coli")
    assert repo.search(property="", limit=1000).total_matched == before


# -- tracing (completes group 2's verification) ---------------------------


def test_a_truncated_search_records_both_figures(repo):
    buf = io.StringIO()
    configure(buf)
    trace = start_question()
    repo.search(property="Cell", limit=2, trace=trace)
    line = buf.getvalue()
    assert '"matched": 4' in line and '"returned": 2' in line
    assert '"truncated": true' in line
    assert trace.question_id in line


def test_records_for_one_question_share_an_identifier(repo):
    buf = io.StringIO()
    configure(buf)
    trace = start_question()
    repo.search(property="Cell", trace=trace)
    repo.get(100001, trace=trace)
    lines = [line for line in buf.getvalue().splitlines() if line]
    assert len(lines) == 2
    assert all(trace.question_id in line for line in lines)


def test_two_questions_are_distinguishable_in_the_trail(repo):
    buf = io.StringIO()
    configure(buf)
    first, second = start_question(), start_question()
    repo.search(property="Cell", trace=first)
    repo.search(property="ribosomes", trace=second)
    assert first.question_id != second.question_id
    assert first.question_id in buf.getvalue()
    assert second.question_id in buf.getvalue()


def test_an_alias_resolution_is_recorded_so_a_wrong_one_is_visible(repo):
    buf = io.StringIO()
    configure(buf)
    repo.search(organism="e. coli", trace=start_question())
    assert "Bacteria Escherichia coli" in buf.getvalue()


# -- hardening found by review --------------------------------------------


def test_repeated_identifiers_are_refused_rather_than_collapsed(tmp_path):
    import json

    path = tmp_path / "dupe.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"bnid": 7, "property": p, "units": "u", "value": 1.0})
            for p in ("first", "second")
        )
        + "\n",
        encoding="utf-8",
    )
    # Otherwise search shows two rows for one identifier while get() returns one,
    # so the agent cites one entry and reads another's data.
    with pytest.raises(ValueError, match="repeated identifiers"):
        CorpusRepository(load(path))


@pytest.mark.parametrize("limit", [-1, 0])
def test_a_nonsensical_limit_does_not_silently_drop_matches(repo, limit):
    # limit arrives from the model as a tool argument. Negative values slice from
    # the end; zero returns nothing against a non-zero total.
    result = repo.search(property="Cell", limit=limit)
    # Exactly one, not "at least one": >= 1 let a clamp to any floor survive.
    assert len(result.rows) == 1
    assert result.total_matched == 4


def test_an_unknown_vocabulary_field_is_recoverable(repo):
    # The agent reaches for this when a search came back empty, so the failure has
    # to be something it can act on rather than a KeyError.
    with pytest.raises(ValueError, match="unknown field"):
        repo.vocabulary("keyword", "x")


def test_a_common_name_phrase_does_not_become_an_abbreviation():
    from scinumbers_ask.repository import _abbreviated_binomials

    # "African clawed frog Xenopus laevis" must not yield "a. clawed".
    assert _abbreviated_binomials("African clawed frog Xenopus laevis") == {"x. laevis"}


def test_a_binomial_followed_by_an_authority_is_still_abbreviated():
    from scinumbers_ask.repository import _abbreviated_binomials

    # Requiring the pair to be the final two tokens would lose this one.
    assert _abbreviated_binomials("Peanut Arachis hypogaea L.") == {"a. hypogaea"}


def test_trace_records_are_emitted_without_explicit_configuration():
    import logging

    # An unconfigured logger would inherit the root's WARNING level and discard
    # every record silently -- the trail vanishing when nobody knows to look.
    assert logging.getLogger("scinumbers_ask").getEffectiveLevel() == logging.INFO


@pytest.mark.parametrize("term", ["E. coli", "E.coli", "e.coli", "E coli", "e coli"])
def test_an_abbreviated_binomial_resolves_however_it_is_punctuated(repo, term):
    """Only the spaced-and-dotted form resolved. The others returned no entries at
    all -- and no entries is the answer that means "the corpus does not cover
    this", which is the one answer that has to be true."""
    assert repo.search(organism=term).total_matched == 4


def test_the_readable_alias_index_keeps_its_punctuation(repo):
    """The index is meant to be read and corrected by a person, so the key stays
    the form a person would write; the punctuation-insensitive lookup sits beside
    it rather than replacing it."""
    assert "e. coli" in repo.aliases()
