"""The quote checker's canary, as tests rather than as a table in a README.

`probes/2026-09-09-retrieval/README.md` recorded four canaries observed once, by hand, on
2026-09-10. A verification tool must prove it can fail before anyone believes it passed, and a
proof that ran once is a proof about that afternoon -- so the four are here, over committed
fixtures, running on every commit (design D4).

The documents are built from the fixture XML by the crude helper below rather than by
`bionumbers.jats`: the checker is the instrument every "verified verbatim" claim rests on, and an
instrument that can only be exercised through the reader it checks against shares the reader's
mistakes. The helper only has to produce the shape `verify` was given -- passages with ids, inline
markup flattened, bibliographic markers kept as `[ref N]` tokens.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from bionumbers.quotes import FOLD, Failed, Verified, contains, fold, verify

FIXTURES = Path(__file__).parent / "fixtures" / "europepmc"

_PARAGRAPH = re.compile(r"<p\b[^>]*>(.*?)</p>", re.DOTALL)
_BIBR = re.compile(r'<xref[^>]*ref-type="bibr"[^>]*>.*?</xref>', re.DOTALL)
_RID = re.compile(r'rid="[A-Za-z]*(\d+)"')
_MARKUP = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class _Passage:
    id: str
    text: str


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
    from bionumbers import quotes

    assert Path(quotes.__file__).read_text(encoding="utf-8").isascii()
