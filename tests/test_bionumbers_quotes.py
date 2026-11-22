"""The quote checker's canary, as tests rather than as a table in a README.

`probes/2026-09-09-retrieval/README.md` recorded four canaries observed once, by hand, on
2026-09-10. A verification tool must prove it can fail before anyone believes it passed, and a
proof that ran once is a proof about that afternoon -- so the four are here, over committed
fixtures, running on every commit (design D4).

The documents are built from the fixture XML by the crude helper below rather than by
`numera_validator.jats`: the checker is the instrument every "verified verbatim" claim rests on, and
an instrument that can only be exercised through the reader it checks against shares the reader's
mistakes. The helper only has to produce the shape `verify` was given -- passages with ids, inline
markup flattened, bibliographic markers kept as `[ref N]` tokens.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from numera_validator.quotes import (
    FOLD,
    Failed,
    Verified,
    cell_text,
    contains,
    fold,
    numbers_in,
    states_value,
    verify,
)

FIXTURES = Path(__file__).parent / "fixtures" / "europepmc"

_PARAGRAPH = re.compile(r"<p\b[^>]*>(.*?)</p>", re.DOTALL)
_BIBR = re.compile(r'<xref[^>]*ref-type="bibr"[^>]*>.*?</xref>', re.DOTALL)
_RID = re.compile(r'rid="[A-Za-z]*(\d+)"')
_MARKUP = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class _Passage:
    id: str
    text: str
    kind: str = "p"
    row_headers: tuple[str, ...] = ()
    column_headers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Document:
    passages: tuple[_Passage, ...]

    def text(self) -> str:
        return "\n".join(passage.text for passage in self.passages)


def _citation_token(match: re.Match[str]) -> str:
    rid = _RID.search(match.group(0))
    return f"[ref {rid.group(1)}]" if rid else "[ref]"


def _document(name: str) -> _Document:
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    passages = []
    for index, paragraph in enumerate(_PARAGRAPH.finditer(xml)):
        body = _BIBR.sub(_citation_token, paragraph.group(1))
        passages.append(_Passage(id=f"p{index}", text=html.unescape(_MARKUP.sub(" ", body))))
    return _Document(passages=tuple(passages))


def _holding(document: _Document, wanted: str) -> str:
    """The id of the passage a quote really came from, found by search so that renumbering the
    fixture's paragraphs cannot make a test assert the wrong thing."""
    for passage in document.passages:
        if fold(wanted) in fold(passage.text):
            return passage.id
    raise AssertionError(f"no passage of the fixture holds {wanted!r}")


def _some_other_id(document: _Document, than: str) -> str:
    return next(passage.id for passage in document.passages if passage.id != than)


@pytest.fixture(scope="module")
def replication_paper() -> _Document:
    """PMC2288635, the paper the probe's ground truth came from: it states 65 min for a quantity
    the textbook puts at 40, in plain prose once and across inline markup once."""
    return _document("fulltext_PMC2288635.xml")


@pytest.fixture(scope="module")
def micro_sign_paper() -> _Document:
    """PMC13248727, which writes the same unit as both U+00B5 and U+03BC."""
    return _document("fulltext_PMC13248727.xml")


# Copied by hand out of the fixture XML, with the inline tags of the second one removed the way the
# JATS reader removes them. These two sentences are the canary's subject.
PLAIN = (
    "Foci appear either shortly after birth or shortly before birth in a mother cell "
    "and are present for 65 min on average."
)
OVER_MARKUP = (
    "The mean time between replisome appearance at oriC and disappearance in the ter "
    "region is 65 min"
)
# The paper's own sentence, carrying both micro-sign code points.
BOTH_MICRO_SIGNS = "CCV volumes ranged from ~8 µm³ to more than 2,000 μm³"


def test_a_real_quote_is_verified_in_the_passage_it_was_taken_from(replication_paper):
    where = _holding(replication_paper, PLAIN)

    result = verify(PLAIN, replication_paper, where)

    assert result == Verified(passage_id=where, in_named_passage=True)


def test_one_changed_digit_is_refused(replication_paper):
    # Canary 2. The whole design rests on this failing: everything a reviewer sees is a quote this
    # check passed, so a check that cannot see a changed digit is worse than no check.
    result = verify(PLAIN.replace("65 min", "66 min"), replication_paper)

    assert isinstance(result, Failed)


def test_a_quote_spanning_inline_markup_is_verified(replication_paper):
    where = _holding(replication_paper, OVER_MARKUP)

    result = verify(OVER_MARKUP, replication_paper, where)

    assert result == Verified(passage_id=where, in_named_passage=True)


def test_one_changed_digit_across_inline_markup_is_refused(replication_paper):
    # Canary 4b: the pair that exercises markup flattening and the digit rule at once. The probe's
    # README says this is the case that breaks first when the normalisation is widened.
    result = verify(OVER_MARKUP.replace("65 min", "66 min"), replication_paper)

    assert isinstance(result, Failed)


def test_a_paraphrase_is_refused(replication_paper):
    result = verify(
        "Foci are present for about 65 minutes on average in a mother cell.",
        replication_paper,
    )

    assert isinstance(result, Failed)


def test_a_changed_unit_is_refused(replication_paper):
    result = verify(PLAIN.replace("65 min", "65 h"), replication_paper)

    assert isinstance(result, Failed)


def test_whitespace_alone_never_decides(replication_paper):
    respaced = PLAIN.replace(" are present for ", "\n   are\tpresent  for\n")

    assert isinstance(verify(respaced, replication_paper), Verified)


def test_the_two_micro_signs_are_the_same_unit(micro_sign_paper):
    """The fold this project added to the probe's table, and the paper that forced it: quoting the
    U+00B5 half with U+03BC, or the U+03BC half with U+00B5, is not a different quote."""
    as_greek_mu = BOTH_MICRO_SIGNS.replace("µ", "μ")
    as_micro_sign = BOTH_MICRO_SIGNS.replace("μ", "µ")

    assert isinstance(verify(as_greek_mu, micro_sign_paper), Verified)
    assert isinstance(verify(as_micro_sign, micro_sign_paper), Verified)


def test_a_typographic_dash_in_the_paper_is_quoted_with_a_hyphen(micro_sign_paper):
    """A real en dash and a real micro sign in one sentence of the fixture, quoted in ASCII."""
    result = verify(
        "the SCV is markedly shorter than the LCV (0.2-0.5 μm vs ~1 μm, respectively)",
        micro_sign_paper,
    )

    assert isinstance(result, Verified)


@pytest.mark.parametrize(("typographic", "plain"), sorted(FOLD.items()))
def test_every_folded_character_folds_in_both_directions(typographic: str, plain: str):
    """One case per entry of the looseness budget, in both directions: the model may paste the
    typographic form into a quote of an ASCII paper as easily as the reverse."""
    typographic_paper = _Document((_Passage(id="p0", text=f"a{typographic}b"),))
    plain_paper = _Document((_Passage(id="p0", text=f"a{plain}b"),))

    assert isinstance(verify(f"a{plain}b", typographic_paper), Verified)
    assert isinstance(verify(f"a{typographic}b", plain_paper), Verified)


class TestSuperscripts:
    """An exponent is part of the number. Folded flat, `10` followed by a superscript `8` is `108`,
    and a quote of the wrong number matches (the 2026-09-21 review's finding 3)."""

    TEN_TO_THE_EIGHTH = "2.5 " + chr(0x00D7) + " 10" + chr(0x2078)
    PER_ML = "mL" + chr(0x207B) + chr(0x00B9)

    def test_a_superscript_run_folds_to_a_caret_and_the_plain_characters(self):
        assert fold(self.TEN_TO_THE_EIGHTH) == "2.5 x 10^8"
        assert fold(self.PER_ML) == "mL^-1"

    def test_the_caret_form_is_its_own_fold(self):
        assert fold("2.5 x 10^8") == "2.5 x 10^8"

    def test_a_quote_in_either_form_is_verified(self):
        paper = _Document((_Passage(id="p0", text=f"a density of {self.TEN_TO_THE_EIGHTH} cells"),))
        assert isinstance(verify("a density of 2.5 x 10^8 cells", paper), Verified)
        assert isinstance(verify(f"a density of {self.TEN_TO_THE_EIGHTH} cells", paper), Verified)

    def test_the_flattened_number_is_refused(self):
        """The canary: the defect made this quote pass."""
        paper = _Document((_Passage(id="p0", text=f"a density of {self.TEN_TO_THE_EIGHTH} cells"),))
        assert isinstance(verify("a density of 2.5 x 108 cells", paper), Failed)

    def test_the_value_check_sees_the_exponent(self):
        assert states_value(self.TEN_TO_THE_EIGHTH, "2.5 x 10^8")
        assert not states_value(self.TEN_TO_THE_EIGHTH, "2.5 x 108")
        assert not states_value(self.TEN_TO_THE_EIGHTH, "2.5 x 10^7")


def test_a_character_outside_the_fold_table_is_not_folded():
    # The negative the parametrised case above cannot give: what separates a tolerated character
    # from an intolerable one is membership of FOLD, so the negative has to vary membership.
    assert "±" not in FOLD
    paper = _Document((_Passage(id="p0", text="a ± b"),))

    assert isinstance(verify("a +/- b", paper), Failed)


# The intro sentence whose clause carries a bibliographic marker, which the reader renders as a
# token. A model quoting the rendered passage may keep the token or drop it.
WITH_TOKEN = (
    "at least 13 proteins that form a functional unit, the replisome ([ref 31]). "
    "A replisome associates with each fork"
)
WITHOUT_TOKEN = WITH_TOKEN.replace(" ([ref 31])", " ()")


def test_a_quote_keeping_a_citation_token_is_verified(replication_paper):
    assert isinstance(verify(WITH_TOKEN, replication_paper), Verified)


def test_a_quote_dropping_a_citation_token_is_verified(replication_paper):
    assert isinstance(verify(WITHOUT_TOKEN, replication_paper), Verified)


def test_the_number_inside_a_citation_token_is_not_checked(replication_paper):
    """The tolerated direction, stated so it is a decision rather than an accident: the token is
    the reader's rendering of a marker, not the paper's words, so its digits are not the paper's
    either. The marker's *presence* is read off the passage, which this cannot touch."""
    misnumbered = WITH_TOKEN.replace("[ref 31]", "[ref 99]")

    assert isinstance(verify(misnumbered, replication_paper), Verified)


def test_a_citation_token_does_not_excuse_a_changed_digit(replication_paper):
    # The tolerance above is exactly one token wide: the paper's own digits are still the paper's.
    wrong_count = WITH_TOKEN.replace("13 proteins", "14 proteins")

    assert isinstance(verify(wrong_count, replication_paper), Failed)


def test_a_quote_that_is_only_a_citation_token_is_empty(replication_paper):
    # Dropping the tokens can empty a quote, and an empty quote must land on the refusal that
    # names it rather than matching everything.
    result = verify("[ref 31]", replication_paper)

    assert result == Failed(reason="empty quote", longest_prefix=0)


def test_an_empty_quote_is_refused(replication_paper):
    assert verify("", replication_paper) == Failed(reason="empty quote", longest_prefix=0)
    assert verify("   \n ", replication_paper) == Failed(reason="empty quote", longest_prefix=0)


def test_a_right_quote_with_a_wrong_passage_id_is_a_location_error(replication_paper):
    where = _holding(replication_paper, PLAIN)

    result = verify(PLAIN, replication_paper, _some_other_id(replication_paper, where))

    assert result == Verified(passage_id=where, in_named_passage=False)


def test_a_quote_spanning_two_passages_is_refused(replication_paper):
    """A location names one container, so a span that fits none has no location to record -- even
    though the text of both halves is in the paper."""
    first, second = replication_paper.passages[0], replication_paper.passages[1]
    across = f"{fold(first.text)[-40:]} {fold(second.text)[:40]}"

    assert isinstance(verify(across, replication_paper), Failed)


def test_the_failure_names_where_the_quote_left_the_paper(replication_paper):
    wrong = PLAIN.replace("65 min", "66 min")

    result = verify(wrong, replication_paper)

    assert isinstance(result, Failed)
    whole = fold(replication_paper.text())
    folded = fold(wrong)
    # The definition of "longest matching prefix": that many characters are in the paper and one
    # more is not. Asserted rather than compared to a remembered number, which would only record
    # what the code did today.
    assert folded[: result.longest_prefix] in whole
    assert folded[: result.longest_prefix + 1] not in whole
    assert "not verbatim" in result.reason
    assert f"{result.longest_prefix}/{len(folded)} chars" in result.reason
    assert folded[max(0, result.longest_prefix - 20) : result.longest_prefix] in result.reason


def test_contains_can_fail(replication_paper):
    """The canary in reverse. If this ever passes, every other test in this file is meaningless."""
    assert contains(replication_paper.text(), "65 min")
    # Not "60 min": the paper does say that, of a time-lapse ("every 5 min for 60 min"), which
    # is exactly the kind of fact a canary has to be checked against the source before it is
    # asserted. "66 min" appears nowhere in it (grep, 2026-09-18).
    assert not contains(replication_paper.text(), "66 min")


def test_an_empty_needle_is_contained_in_nothing():
    assert not contains("anything at all", "")
    assert not contains("anything at all", "   ")


def test_the_fold_table_is_fifteen_entries_and_the_micro_sign():
    """The probe's README asks for two properties after any edit, and the reason is not fussiness:
    a duplicate key collapsed by an editor's own normalisation is legal Python that loosens the
    check in silence. The count moved from 15 to 16 exactly once, for U+00B5."""
    assert len(FOLD) == 16
    assert all(not key.isascii() for key in FOLD)
    assert "µ" in FOLD


def test_the_checker_is_written_in_ascii():
    """The table is escapes, and the file is pure ASCII, so it survives a clipboard, a message and
    an editor unchanged -- these artifacts have already been reconstructed from a message once."""
    from numera_validator import quotes

    assert Path(quotes.__file__).read_text(encoding="utf-8").isascii()


class TestARenderedCell:
    """The model is shown a cell as 'row: … | column: … | cell: X'. Quoting that line is quoting
    our rendering plus the paper's cell; only the cell is the paper's, and only a table cell under
    the headers quoted may hold it (code review of 2026-10-15)."""

    CELL = _Passage(
        id="t3r2c8",
        text="693.0",
        kind="td",
        row_headers=("Dt (h)",),
        column_headers=("NLC-CIP (ng/mL)", "500"),
    )

    def test_a_quote_carrying_its_headers_is_checked_on_its_cell(self):
        doc = _Document(passages=(self.CELL,))
        outcome = verify("row: Dt (h) | column: NLC-CIP (ng/mL) / 500 | cell: 693.0", doc, "t3r2c8")
        assert isinstance(outcome, Verified) and outcome.in_named_passage

    def test_the_cell_part_is_still_held_to_the_digit(self):
        doc = _Document(passages=(self.CELL,))
        assert isinstance(verify("row: Dt (h) | cell: 693.5", doc, "t3r2c8"), Failed)

    def test_a_sentence_that_merely_mentions_a_cell_is_not_reduced(self):
        assert cell_text("the cell: count was 693") == "the cell: count was 693"

    def test_a_cell_quote_never_matches_a_paragraph(self):
        """The reproduction: 'cell: 39' under a Kd column, against a cell reading 12 and a
        paragraph saying 'isolated in 1939'."""
        doc = _Document(
            passages=(
                _Passage(id="p1", text="The strain was isolated in 1939 from soil."),
                _Passage(
                    id="t1r2c2",
                    text="12",
                    kind="td",
                    row_headers=("mut",),
                    column_headers=("Kd (nM)",),
                ),
            )
        )
        assert isinstance(verify("row: mut | column: Kd (nM) | cell: 39", doc, "t1r2c2"), Failed)

    def test_a_cell_quote_never_matches_another_number_s_digits(self):
        doc = _Document(passages=(replace(self.CELL, text="1693.0"),))
        quote = "row: Dt (h) | column: NLC-CIP (ng/mL) / 500 | cell: 693.0"
        assert isinstance(verify(quote, doc, "t3r2c8"), Failed)

    @pytest.mark.parametrize(
        "quote",
        [
            "row: Dt (h) | column: CIP (ng/mL) / 500 | cell: 693.0",
            "row: Dt (min) | column: NLC-CIP (ng/mL) / 500 | cell: 693.0",
        ],
        ids=["column", "row"],
    )
    def test_a_cell_quote_under_other_headers_is_refused_and_says_why(self, quote):
        outcome = verify(quote, _Document(passages=(self.CELL,)), "t3r2c8")
        assert isinstance(outcome, Failed) and "headers" in outcome.reason

    def test_a_cell_quote_naming_no_headers_matches_any_cell(self):
        doc = _Document(passages=(self.CELL,))
        assert isinstance(verify("cell: 693.0", doc, "t3r2c8"), Verified)

    def test_a_plain_quote_of_a_cell_is_still_verified(self):
        assert isinstance(verify("693.0", _Document(passages=(self.CELL,)), "t3r2c8"), Verified)


class TestNumberBoundaries:
    """A quote that starts or ends on a digit starts or ends where the paper's number does."""

    DOC = _Document(passages=(_Passage(id="p1", text="Doubling took 139 min, or 39.4 in LB."),))

    @pytest.mark.parametrize("quote", ["39 min", "took 13", "or 39", "9.4 in"])
    def test_a_quote_cutting_a_number_is_refused(self, quote):
        assert isinstance(verify(quote, self.DOC, "p1"), Failed)

    @pytest.mark.parametrize("quote", ["139 min", "or 39.4 in LB.", "39.4", "took 139"])
    def test_a_quote_on_whole_numbers_is_verified(self, quote):
        assert isinstance(verify(quote, self.DOC, "p1"), Verified)

    def test_a_number_ending_a_sentence_is_read(self):
        """Code review of 2026-10-15: '(?![\\d.])' made 'was 2.4.' state no number at all."""
        text = "The Hill coefficient was 2.4. Doubling took 39."
        assert numbers_in(text) == ("2.4", "39")
        assert states_value(text, "2.4") and states_value(text, "39")
        assert not states_value("The coefficient was 2.45.", "2.4")


class TestStatesValue:
    def test_a_written_decimal_matches_the_paper_s_integer(self):
        assert states_value("Dt of 346 h under CIP", "346.0")

    def test_both_ends_of_a_range_are_required(self):
        assert states_value("doubling times (10–50 min)", "10–50")
        assert not states_value("doubling times of 10 min", "10–50")

    def test_the_uncertainty_is_not_required(self):
        assert states_value("39 min", "39 ± 1")

    def test_a_longer_number_is_a_different_number(self):
        assert not states_value("139 min and 39.4 min", "39")

    def test_the_first_live_run_s_arithmetic_is_refused(self):
        quote = "NLC-CIP increasing doubling time by nearly 200-fold at the highest concentration"
        assert not states_value(quote, "346.0")

    def test_a_sign_is_part_of_the_value(self):
        """A wrong sign is a wrong value that looks verified (code review of 2026-10-07): the
        negative case differs from the positive only in the sign."""
        assert states_value("ΔH = −16.6 kcal mol⁻¹", "−16.6")
        assert not states_value("ΔH = 16.6 kcal mol⁻¹", "−16.6")
        assert not states_value("a binding enthalpy of −16.6 kcal", "16.6")
        assert not states_value("+0.32 V", "-0.32")
        assert states_value("+0.32 V", "0.32")

    def test_an_exponent_keeps_its_sign(self):
        assert states_value("a rate of 1.2 × 10⁻³ s⁻¹", "1.2 × 10^-3")
        assert not states_value("a rate of 1.2 × 10³ s⁻¹", "1.2 × 10^-3")
        assert not states_value("a rate of 1.2 × 10⁻³ s⁻¹", "1.2 × 10^3")

    def test_a_dash_between_numbers_or_inside_a_name_is_not_a_sign(self):
        assert states_value("doubling times (10 – 50 min)", "10–50")
        # A dash spaced on one side only still joins two numbers when a digit precedes it.
        assert states_value("a cytoplasmic pH of 7.2 -7.4", "7.2–7.4")
        assert states_value("after IL-6 at 5 ng/ml", "5")
        assert states_value("39 +/- 1 min", "39 ± 1")
        assert states_value("from −5 to −10 °C", "−5 to −10")

    def test_a_value_with_no_number_is_stated_by_nothing(self):
        assert not states_value("some text", "n.d.")
