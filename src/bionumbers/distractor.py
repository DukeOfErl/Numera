"""The second text: what goes on the screen beside the claim's own quote, and why it is admissible.

Design D5 (ADR-0920). A reviewer is always shown two texts and always has to say which one fits
the value, so the second text carries the whole weight of the task: if it can be told apart without
reading -- because it restates the value in another unit, or because it is the supporting sentence
again -- the item measures nothing. The model proposes candidates; **selection is mechanical**, in
`admissible` and `excluded_forms`, because a model asked not to restate a value will restate it
rounded, and the only thing that can see that is arithmetic.

Which direction each rule fails in, since both directions exist and only one is cheap. Rejecting a
sound candidate costs a candidate, and there are up to fifteen plus the second-occurrence fallback
plus `NotReviewable`, which is a recorded, countable ending. Admitting a candidate that restates
the value costs an item that looks ordinary, is answered correctly by a reviewer who read nothing,
and is then averaged into the figure this whole task exists to produce. So the exclusion is
deliberately wide: every rounding, every conversion into a common unit of the same dimension, at
two precisions.

**The system block's order is load-bearing, and both model-facing modules carry the same one.**
Prompt caching is a prefix match from the first token, so two calls share the article only if the
article is the *first* block in both and each caller's own instruction comes after it. That is the
order here and in `extraction.system_blocks`, and a test in `test_bionumbers_extraction.py`
holds the two first blocks byte-identical. Whether the cache was actually hit is a fact the run
reports rather than assumes: `Ledger.cached_fraction` reads it off the provider's usage blocks, and
a run whose fraction is zero has been paying full rate.

Nothing about a decision, a choice or a comment is ever built into these messages (the spec's last
requirement): decisions measure the extractor and this selector, so they cannot also be their
input.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

import pint

from bionumbers.jats import Document, render_for_model
from bionumbers.quotes import Verified, cell_text, fold, verify
from bionumbers.records import (
    DISTRACTOR_PREFERENCE,
    Claim,
    DistractorType,
    Frozen,
    Location,
    NotReviewable,
    Paper,
    Quote,
    ReviewItem,
    SecondTextKind,
    TableView,
)
from bionumbers.spend import MODEL, CeilingReached, Ledger, cost, projected_cost

#: Enough for fifteen candidates of a few sentences each, and the figure the projection prices the
#: output at before the call is made. Raising it raises every projection, not just the calls that
#: would have used it.
MAX_OUTPUT_TOKENS = 4096

# The spec's five definitions, one per `DistractorType`, in the model's words rather than the
# spec's where the spec is written for a reader of the spec. Built by iterating the enum below, so
# a sixth type added to `records.py` without a definition here fails at import rather than
# producing an instruction that silently asks for four kinds and a name the model invents.
#
# PARAMETER is the one place the spec pulls against itself: it defines the type as "the same number
# used as a parameter or assumption rather than measured", while the exclusion rule forbids a
# distractor that contains the value at all. The exclusion wins, because it is the rule that is
# enforced mechanically and because a distractor carrying the value is the failure this module
# exists to prevent -- so the type is asked for as a number used as an assumption, not *the*
# number.
_TYPE_DEFINITIONS: dict[DistractorType, str] = {
    DistractorType.ADJACENT_CONDITION: (
        "the same property measured under an adjacent condition -- another strain, medium, "
        "temperature, substrate or time point; typically the neighbouring row or column of the "
        "same table"
    ),
    # Never the same property for the same organism: that is another source's answer to the same
    # question, not a text that fails to support the value, and a reviewer cannot tell the two
    # apart (Yoav, 2026-09-23, on PMC13447829). Asked for in the instruction only -- nothing here
    # can read an organism out of a passage, so the model's compliance is what holds it.
    DistractorType.CITED: (
        "the same property for a DIFFERENT organism, cell type or system, taken from other work "
        "rather than measured here, with a bibliographic marker in the clause that carries the "
        "number. A value other work reports for this property in the SAME organism is not "
        "wanted, under this kind or any other"
    ),
    DistractorType.DIFFERENT_QUANTITY: (
        "a different quantity sharing this value's unit and subject -- a lag time beside a "
        "doubling time, a width beside a length"
    ),
    DistractorType.PARAMETER: (
        "a number the article assumes, sets or thresholds on rather than measures: a model "
        "parameter, a detection limit, a cut-off"
    ),
    DistractorType.DERIVATION_HALF: (
        "one of the measurements a derived value was computed from, rather than the derived value"
    ),
}

SECOND_TEXT_INSTRUCTION = "\n".join(
    [
        "You are given one research article and one quantitative claim taken from it.",
        "",
        "Return passages from the SAME article that could stand beside the claim's own quote as "
        "the second of two texts about the value.",
        "",
        "Every candidate must:",
        "- be a verbatim span of ONE passage of the article above, copied exactly, together with "
        "the id of that passage; a span you had to paraphrase, or that runs across two passages, "
        "is worth nothing here;",
        "- be at most a few sentences, or one table cell with its row and column headers;",
        "- NOT restate the claim's value -- not at another precision, not rounded, not converted "
        "to another unit, and not the same measurement reported a second time;",
        "- differ from the claim's quote in something a reader can see in the text itself: a "
        "different condition, a different quantity, a citation, an assumption.",
        "",
        "Return up to three candidates of each of the following kinds, naming the kind exactly as "
        "it is written here:",
        *[f"- {kind.value}: {_TYPE_DEFINITIONS[kind]}" for kind in DistractorType],
        "",
        "Return the passages only. No commentary, no ranking, no reasoning.",
    ]
)


class Candidate(Frozen):
    """One passage the model offers, with the id it says it came from.

    `passage_id` is what the model claims; `quotes.verify` decides where the text really is, and
    the location recorded on the item comes from the verification rather than from here.
    """

    passage_id: str
    text: str
    type: DistractorType


class SecondTextOutput(Frozen):
    candidates: list[Candidate] = []


class _Counted(Protocol):
    input_tokens: int


class _Parsed(Protocol):
    parsed_output: Any
    usage: Any


class Model(Protocol):
    """The two provider calls this module needs, structurally.

    Deliberately not an import of `extraction`'s identical protocol: that module is being written
    in parallel, and a shared name would be a dependency between two steps that only share a
    client. The orchestrator may fold them into one; until then the two must stay identical, which
    is why the signatures are written out rather than inferred.
    """

    def parse(
        self, *, system: Any, messages: Any, output_format: Any, max_tokens: int
    ) -> _Parsed: ...

    def count_tokens(self, *, system: Any, messages: Any, output_format: Any) -> _Counted: ...


_PREFERENCE_RANK: dict[DistractorType, int] = {
    kind: rank for rank, kind in enumerate(DISTRACTOR_PREFERENCE)
}

_NUMBER = re.compile(r"\d+(?:\.\d+)?")

# Both the typographic and the ASCII way a value's uncertainty is written. Everything after it is
# dropped: "39 +/- 1 min" is a claim about 39, and excluding "1" would refuse every candidate
# mentioning a single anything.
_UNCERTAINTY = re.compile(r"±|\+/-")

# The units a converted form is offered in: the common members of each dimension this prototype has
# met in a life-science paper. The list is tried whole and mismatched dimensions fall out of
# `Quantity.to`, so adding a family costs one line and no dispatch. A unit that pint does not know
# is skipped rather than raised on -- the cost of a missing entry is one form not excluded, which
# is why the entries that matter (time, length, concentration) are the ones a value most often gets
# restated in.
_COMMON_UNITS: tuple[str, ...] = (
    "s",
    "min",
    "h",
    "day",
    "nm",
    "µm",
    "mm",
    "cm",
    "m",
    "nM",
    "µM",
    "mM",
    "M",
    "g/L",
    "mg/mL",
    "µg/mL",
    "mg/L",
    "fg",
    "pg",
    "ng",
    "µg",
    "mg",
    "g",
    "fL",
    "µL",
    "mL",
    "L",
    "1/s",
    "1/min",
    "1/h",
)

_REGISTRY: Any = None


def _registry() -> Any:
    """pint's registry, built on first use.

    Constructing it parses the whole default definition file, which is most of a second; a paper
    whose every candidate is refused on the numeric forms alone should not pay that, and neither
    should a test of the rules that need no unit.
    """
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = pint.UnitRegistry()
    return _REGISTRY


def _numbers_as_written(value: str) -> tuple[str, ...]:
    """The numbers a value asserts: the central value, or both ends of a range.

    An uncertainty is not one of them (see `_UNCERTAINTY`); a range's endpoints both are, because a
    candidate restating either end is restating the claim.
    """
    head = _UNCERTAINTY.split(fold(value), maxsplit=1)[0]
    return tuple(match.group(0) for match in _NUMBER.finditer(head))


def _significant_digits(number: str) -> int:
    """How many significant figures the paper wrote, read off the string rather than the float.

    Trailing zeros of an integer are counted as significant ("2340" reads as four), which is
    generous in the direction that produces *more* roundings and so more exclusions.
    """
    return len(number.replace(".", "").lstrip("0")) or 1


def _at_significant_figures(number: Decimal | float, digits: int) -> str:
    """`number` rounded to `digits` significant figures, written the way a paper writes it.

    Not `f"{x:.{digits}g}"`: that renders 39 at one significant figure as "4e+01", and no paper
    writes that, so the form would never match any text. Decimal rather than float so that the
    rounding is the decimal one a paper performed, half away from zero rather than half to even --
    a value stated as 2.5 is restated as 3, not as 2.
    """
    quantity = number if isinstance(number, Decimal) else Decimal(repr(number))
    if quantity == 0:
        return "0"
    step = Decimal(1).scaleb(quantity.adjusted() - digits + 1)
    text = format(quantity.quantize(step, rounding=ROUND_HALF_UP), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _converted_forms(number: str, unit: str) -> set[str]:
    """The same quantity written in the other common units of its dimension, at 2 and 3 s.f.

    Two precisions because a paper converting a number rounds it, and the rounding it chose is not
    knowable: 39 min is "0.65 h" at both, but 2340 s at three significant figures and 2300 s at
    two. Anything the registry cannot parse or convert is skipped, which leaves the numeric forms
    as the whole of the exclusion -- stated in `excluded_forms`, and the reason unit strings are
    taken from the paper rather than normalised first.
    """
    try:
        quantity = _registry().Quantity(float(number), unit)
    except Exception:  # pint raises several unrelated types for a unit string a paper wrote
        return set()
    forms: set[str] = set()
    for name in _COMMON_UNITS:
        try:
            converted = quantity.to(name)
        except Exception:  # a different dimension, or a unit this pint does not define
            continue
        forms.update(_at_significant_figures(converted.magnitude, digits) for digits in (2, 3))
    return forms


def excluded_forms(value: str, unit: str) -> frozenset[str]:
    """Every string a second text may not contain if it is to be a distractor.

    The value as the paper wrote it, each number in it, each of those rounded to every smaller
    number of significant figures, and each converted into the common units of its dimension. The
    empty string is never a form: it is contained in every text, so one would refuse the whole
    paper -- the same input `quotes.contains` refuses loudest, for the same reason.
    """
    forms = {fold(value)}
    for number in _numbers_as_written(value):
        forms.add(number)
        for digits in range(_significant_digits(number) - 1, 0, -1):
            forms.add(_at_significant_figures(Decimal(number), digits))
        forms |= _converted_forms(number, unit)
    return frozenset(form for form in forms if form)


def _contains_standalone(folded_text: str, form: str) -> bool:
    """Is `form` in `folded_text` as a number in its own right?

    A digit on either side means a longer number, and a longer number is a different number: "39"
    is not in "139" and not in "2390". A decimal point is *not* a boundary, so "39" is found in
    "39.4" and in "0.39". That direction is deliberate and it is the wide one: a candidate saying
    39.4 for a claim of 39 is restating it at a precision the claim does not have, and refusing it
    costs a candidate. What this cannot see is the reverse, "2.13" for a claim of "2.1" -- the
    roundings only run downwards, because the extra digit the paper did not state cannot be
    guessed.
    """
    needle = fold(form)
    if not needle:
        return False
    start = 0
    while (found := folded_text.find(needle, start)) != -1:
        before = folded_text[found - 1] if found else ""
        after = folded_text[found + len(needle) : found + len(needle) + 1]
        if not before.isdigit() and not after.isdigit():
            return True
        start = found + 1
    return False


def admissible(text: str, claim: Claim) -> bool:
    """May this text be the claim's distractor?

    Three refusals: an empty text, a text that is one of the claim's own recorded statements of the
    value, and a text carrying the value in any of `excluded_forms`. The second is not covered by
    the third -- an occurrence may state the value in words ("about forty minutes") and carry no
    excluded form at all, and it is still the same measurement, which is a second occurrence rather
    than a distractor.

    The guard is here rather than in `choose_second_text` because a second caller -- a re-selection
    over stored candidates, a review page offering an alternative -- must not be able to build an
    item that skips it.
    """
    folded = fold(text)
    if not folded:
        return False
    if any(folded == fold(quote.text) for quote in (claim.quote, *claim.occurrences)):
        return False
    return not any(
        _contains_standalone(folded, form) for form in excluded_forms(claim.value, claim.unit)
    )


def _claim_brief(claim: Claim, question: str) -> str:
    """What the model is told about the claim: the value, its unit, its quote and where it sits,
    the occurrences already recorded, and the conditions. Nothing about any decision, and nothing
    about what a reviewer will be asked."""
    lines = [
        f"Property question: {question}",
        f"The article's own term for the property: {claim.property_in_paper}",
        f"Value under review: {claim.value} {claim.unit}".rstrip(),
        f"Stated in passage {claim.quote.location.passage_id}: {claim.quote.text}",
    ]
    if claim.occurrences:
        lines.append("The same value is already recorded in these passages, which are not wanted:")
        lines += [f"- {quote.location.passage_id}: {quote.text}" for quote in claim.occurrences]
    if claim.conditions:
        lines.append("Conditions recorded with the value:")
        lines += [f"- {field.name}: {field.quote or '(not stated)'}" for field in claim.conditions]
    return "\n".join(lines)


def _location_of(doc: Document, passage_id: str) -> Location:
    """The passage's own location, so a table cell reaches the page with its headers (the spec's
    "shown as its row and column headers with the cell, not as the whole table")."""
    passage = doc.passage(passage_id)
    return Location(
        passage_id=passage_id,
        section_path=tuple(passage.section_path),
        kind=passage.kind,
        row_headers=tuple(passage.row_headers),
        column_headers=tuple(passage.column_headers),
    )


def _item(
    claim: Claim,
    paper: Paper,
    question: str,
    *,
    doc: Document,
    second: Quote,
    kind: SecondTextKind,
    distractor_type: DistractorType | None,
) -> ReviewItem:
    return ReviewItem(
        item_id=f"{claim.claim_id}-item",
        question=question,
        claim=claim,
        paper=paper,
        supporting=claim.quote,
        second=second,
        second_kind=kind,
        distractor_type=distractor_type,
        tables=_tables_of(doc, claim.quote, second),
    )


def _tables_of(doc: Document, *texts: Quote) -> tuple[TableView, ...]:
    """The tables the texts are cells of, each once, in document order (ADR-0940).

    Carried on the item rather than looked up by the page, so the page needs no access to the
    paper and what a reviewer was shown is in the record. Document order, not supporting-first:
    an order derived from which text supports the value would tell the reviewer which that is.
    """
    wanted = {text.location.passage_id for text in texts if text.location.kind == "td"}
    return tuple(
        table
        for table in getattr(doc, "tables", ())
        if any(table.holds(passage_id) for passage_id in wanted)
    )


def system_blocks(doc: Document) -> list[dict]:
    """The paper first, carrying the cache breakpoint; this module's instruction after it.

    Byte-identical in its first block to `extraction.system_blocks`, and tested to be: the cached
    prefix ends at the breakpoint, so only a paper-first order lets the extraction call, its retry
    and this call read one cached copy of the article.
    """
    return [
        {"type": "text", "text": render_for_model(doc), "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": SECOND_TEXT_INSTRUCTION},
    ]


def choose_second_text(
    model: Model,
    doc: Document,
    claim: Claim,
    paper: Paper,
    *,
    question: str,
    ledger: Ledger,
    model_id: str = MODEL,
) -> ReviewItem | NotReviewable:
    """One call on the cached article, then a mechanical selection, then an item or a reason.

    The order -- project, check, call, record -- is `spend`'s, and this is one of the up-to-three
    call sites per paper its ledger warns about: a path that reaches `model.parse` without passing
    `ledger.check` spends outside both ceilings and nothing would show it.

    The projection passes no `cached_tokens`, so the whole article is priced at full input rate
    even though the extraction call has already cached it. That over-projects by design: the figure
    guards a ceiling, and a ceiling checked against an optimistic projection is the one that lets a
    runaway through.
    """
    system = system_blocks(doc)
    messages = [{"role": "user", "content": _claim_brief(claim, question)}]

    counted = model.count_tokens(system=system, messages=messages, output_format=SecondTextOutput)
    projected = projected_cost(
        model_id, input_tokens=counted.input_tokens, max_tokens=MAX_OUTPUT_TOKENS
    )
    try:
        ledger.check(paper.pmcid, projected)
    except CeilingReached:
        # The paper's ending is the extraction step's to record; here the claim simply has no
        # reviewable item, with the reason that stops it being read as "the paper had nothing".
        return NotReviewable(claim_id=claim.claim_id, reason="ceiling reached")

    try:
        response = model.parse(
            system=system,
            messages=messages,
            output_format=SecondTextOutput,
            max_tokens=MAX_OUTPUT_TOKENS,
        )
    except Exception as failure:
        # The same clause as `extraction._one_call`: an output the adapter could not read was
        # still billed, and a ceiling that never hears of it is a ceiling with a hole in it
        # (code review of 2026-09-21, finding 2). Adapters that know the usage attach it.
        usage = getattr(failure, "usage", None)
        if usage is not None:
            ledger.record(paper.pmcid, cost(model_id, usage))
        raise
    ledger.record(paper.pmcid, cost(model_id, response.usage))

    output = response.parsed_output
    candidates = list(output.candidates) if output is not None else []

    order = {passage.id: index for index, passage in enumerate(doc.passages)}
    survivors: list[tuple[Candidate, str]] = []
    unverified = 0
    for candidate in candidates:
        verified = verify(candidate.text, doc, candidate.passage_id)
        if not isinstance(verified, Verified):
            # An invented passage never reaches a reviewer, however good a distractor it would
            # make: the whole design is that everything on the screen is a checked quote.
            unverified += 1
            continue
        if admissible(candidate.text, claim):
            survivors.append((candidate, verified.passage_id))

    def _rank(pair: tuple[Candidate, str]) -> tuple[int, int]:
        """Hardest type first (`DISTRACTOR_PREFERENCE`), then the order the passages appear in the
        article -- a total order, so re-running the selection over the same candidates yields the
        same item and two records stay comparable."""
        candidate, passage_id = pair
        return (_PREFERENCE_RANK[candidate.type], order.get(passage_id, len(order)))

    survivors.sort(key=_rank)

    if survivors:
        candidate, passage_id = survivors[0]
        return _item(
            claim,
            paper,
            question,
            doc=doc,
            second=Quote(text=cell_text(candidate.text), location=_location_of(doc, passage_id)),
            kind=SecondTextKind.DISTRACTOR,
            distractor_type=candidate.type,
        )

    for occurrence in claim.occurrences:
        if isinstance(verify(occurrence.text, doc, occurrence.location.passage_id), Verified):
            return _item(
                claim,
                paper,
                question,
                doc=doc,
                second=occurrence,
                kind=SecondTextKind.SECOND_OCCURRENCE,
                distractor_type=None,
            )

    return NotReviewable(
        claim_id=claim.claim_id,
        reason=(
            f"no admissible second text: {len(candidates)} candidates, {unverified} not verbatim, "
            f"the rest carrying the value; {len(claim.occurrences)} recorded occurrences, none "
            "verifiable"
        ),
    )


def texts_on_the_page(item: ReviewItem) -> tuple[str, str]:
    """The two texts and nothing else -- the whole of what a reviewer reads of the item.

    Here so that "the kind is recorded and never shown" is checkable by a test rather than by
    reading the page, and so a later page change cannot quietly widen what is rendered without
    that test noticing.

    The pair is returned supporting-first. The *order on the screen* must carry no information
    about which is which, and that is the page's to decide per item: shuffling here would reorder
    the pair on every rerun of a Streamlit script, so a reviewer would watch the two texts swap
    while reading them.
    """
    return (item.supporting.text, item.second.text)
