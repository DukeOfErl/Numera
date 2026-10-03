"""One article in, verified claims out: the extraction call, its one retry, and the ending.

The pipeline's only model calls live here (design D1, ADR-0900): one structured-output
call over the whole paper, one bounded retry when a quote does not check out, and nothing
else. No tools, no loop, no chunking -- a chunked paper loses the Methods-to-Results link,
which the scientist report says is the whole difficulty of the task, and a loop has no exit
that a fixed step count does not already give.

**Nothing the model is shown comes from anywhere but the paper, the question and the
organism.** Not a decision, not a reviewer's comment, not an expected value. The instruction
names the property and the organism only through the user turn, and carries no unit,
magnitude or canonical figure (design D7): ADR-0040's blind arm was confidently wrong on the
most famous number in the corpus, and the instruction is the only place that can be
countered.

**The checker is the arbiter, not the model.** Every quote goes through `quotes.verify`; a
failure is named back once, and a second failure drops the claim. A dropped claim is
recorded by id in `unverifiable` rather than deleted silently, because "the model invented
quotes" and "the paper says nothing" are different facts about a run, and the rebuild has to
tell them apart.

`Ledger.check` is asked before every call, and every call goes through `_one_call` for the
reason that module's docstring gives: the bound is only as good as its call sites, so it has
one place to be missing from instead of three.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NamedTuple, Protocol

import anthropic

from bionumbers import quotes
from bionumbers.jats import Document, render_for_model
from bionumbers.records import (
    CONDITION_FIELDS,
    CandidateKind,
    Claim,
    ClaimKind,
    ConditionField,
    Fingerprint,
    Frozen,
    Location,
    Paper,
    PaperResult,
    PaperState,
    Provenance,
    Quote,
    RejectedCandidate,
)
from bionumbers.spend import (
    MODEL,
    CeilingReached,
    Ledger,
    cost,
    count_input_tokens,
    projected_cost,
)

MAX_TOKENS = 16000
"""The output bound, and the figure every projection prices output at.

Generous on purpose: a paper with a dozen values, each carrying eight condition quotes, is
a long answer, and an answer truncated mid-JSON is a `FAILED` paper rather than a cheap one.
It was 8,000 until the first live run (2026-09-18) cut off a correction call on a paper with
three claims at exactly that figure -- the correction replays the first answer, so it is the
longer of the two. At $25 per million output tokens this is $0.40 of worst case per call,
priced into the projection, against a $2 ceiling.
"""

#: What a claim may be. Anything else the model hands back as a claim is a candidate rather
#: than a claim, and is moved rather than kept -- the spec's "only a value the paper
#: measured or derived from its own measurements".
CLAIMABLE = (CandidateKind.MEASURED, CandidateKind.DERIVED)

INSTRUCTION = f"""You are given one research article, passage by passage, each passage with
an id. The user turn names the property and the organism asked about. Report what this
article states about that property, using only the passages you were given.

QUOTE VERBATIM. Every value, condition, method and input you report carries a quote copied
character for character from one passage, and the id of the passage you copied it from.
Quotes are checked mechanically against the article. A quote that cannot be found is not a
small error: the claim carrying it is thrown away.

NOTHING TO EXTRACT IS A CORRECT ANSWER. An article can be about the property and state no
value for it -- stating it only as a figure curve, or only in supplementary material, or
not at all. Answer NOTHING_TO_EXTRACT and give your reason in one sentence. That is a
correct answer and not a failure. Producing a claim you cannot quote is a failure.

WHAT COUNTS AS A CLAIM. Only a value this article MEASURED itself, or DERIVED from its own
measurements, is a claim. A DERIVED value carries the quoted measurements it was computed
from. Every other number for the property goes to the rejected list, with its category:
- CITED: the value comes from other work.
- PARAMETER: the value is assumed, fixed, or used as an input to a model rather than
  measured here.
- COMPILED: the value sits in a table or list gathering other publications' numbers.

CITATION MARKERS DECIDE. A bibliographic marker of the form [ref N] attached to the clause
holding a number is decisive evidence that the value is CITED, and outranks the verb of the
sentence. "We measured" beside such a marker does not make the number this article's own.

ONE CLAIM PER MEASUREMENT. An article usually states the same measurement more than once,
and the restatements are less precise than the original. That is one claim: quote the most
precise statement, and list the restatements as occurrences of it. Never report one
measurement as two claims.

RANGES. A range whose two ends are different conditions of the experiment is
RANGE_OVER_CONDITIONS, and names the condition at each end. Such a range is never a single
value with uncertainty. A value stated with its own stated error is WITH_UNCERTAINTY.
Anything else is SINGLE.

CONDITIONS. For each claim report these fields: {", ".join(CONDITION_FIELDS)}. Each carries
a quote from the article and exactly one state:
- BESIDE_VALUE: stated in or beside the sentence or the cell that holds the value.
- FROM_METHODS: stated in the methods section.
- BY_REFERENCE: the article says the conditions were described in another publication and
  cites it. Quote the sentence that points there, and give the citation marker as the
  reference.
- SUPPLEMENTARY_ONLY: the article says this is in supplementary material, which you were
  not given.
- NOT_STATED: the article states it nowhere. Leave the quote empty.

NEVER FILL A FIELD FROM WHAT YOU KNOW. You know things about this property and this
organism that this article does not state, including what a typical value is. None of that
belongs in this answer. If the article does not state it, the state is NOT_STATED and the
quote is empty. A field filled from general knowledge is a fabrication however true it is
elsewhere."""


def instruction_sha256(instruction: str = INSTRUCTION) -> str:
    """The fingerprint that groups items by the instruction that produced them.

    Over the instruction alone, not the whole request: the paper and the question vary per
    item by construction, so folding them in would give every item its own fingerprint and
    group nothing. Harvest mode (`bionumbers.harvest`) passes its own instruction, so its
    items are never grouped with a question's.
    """
    return hashlib.sha256(instruction.encode("utf-8")).hexdigest()


class ConditionDraft(Frozen):
    name: str
    provenance: Provenance
    quote: str = ""
    passage_id: str = ""
    reference: str = ""


class QuoteDraft(Frozen):
    text: str
    passage_id: str


class ClaimDraft(Frozen):
    property_in_paper: str
    property_name: str = ""
    """Harvest mode's labels, written by the model rather than quoted: a general name for the
    quantity, its class and the species. Empty when a question was asked."""
    property_class: str = ""
    organism_name: str = ""
    value: str
    unit: str
    kind: ClaimKind
    candidate_kind: CandidateKind
    quote: QuoteDraft
    occurrences: list[QuoteDraft] = []
    conditions: list[ConditionDraft] = []
    inputs: list[QuoteDraft] = []
    endpoint_conditions: tuple[str, ...] | None = None


class RejectedDraft(Frozen):
    value: str
    unit: str
    kind: CandidateKind
    quote: QuoteDraft
    reason: str


class ExtractionOutput(Frozen):
    """What the model is asked for, and the only thing it decides.

    Two states, not the six of `PaperState`: the other four are facts about the run rather
    than about the paper -- whether it has a methods section, whether the ceiling stopped
    it, whether the service answered, whether discovery got any text at all -- and a model
    asked to report those would be reporting on itself.
    """

    state: Literal["CLAIMS_FOUND", "NOTHING_TO_EXTRACT"]
    reason: str = ""
    claims: list[ClaimDraft] = []
    rejected: list[RejectedDraft] = []


class ProviderRefused(Exception):
    """The provider refused the *account*, not the paper: no credit, a bad key, a rate limit.

    Raised by an adapter in place of a generic HTTP error so the run can stop. Left to the
    per-paper `FAILED` handling, a 402 marked ten papers FAILED at $0 in a row on 2026-09-22 and
    the run looked complete; every one of them had to be extracted again.
    """


class Model(Protocol):
    """The provider, narrowed to the two calls this module makes.

    A protocol rather than the SDK client so a test can script the answers: what the
    pipeline does with a fabricated quote is the behaviour most worth pinning and the least
    testable against a real model, which will not fabricate on demand.
    """

    def parse(
        self,
        *,
        system: list[dict],
        messages: list[dict],
        output_format: type,
        max_tokens: int,
    ) -> Any: ...

    def count_tokens(
        self,
        *,
        system: list[dict],
        messages: list[dict],
        output_format: type | None = None,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class _Counted:
    """A token count in the shape the SDK answers in, so the protocol has one shape."""

    input_tokens: int


class AnthropicModel:
    """The real adapter: `messages.parse` and `messages.count_tokens` on one model.

    No temperature and no thinking budget are passed. Both are absent by decision rather
    than by oversight: the task is transcription under a schema, where a sampling knob
    changes what gets quoted for no stated reason, and an unset parameter is the provider's
    current default rather than a number this repository would have to keep true.
    """

    def __init__(self, client: Any | None = None, model: str = MODEL) -> None:
        self._client = client if client is not None else anthropic.Anthropic()
        self._model = model

    def parse(
        self,
        *,
        system: list[dict],
        messages: list[dict],
        output_format: type,
        max_tokens: int,
    ) -> Any:
        return self._client.messages.parse(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            output_format=output_format,
        )

    def count_tokens(
        self,
        *,
        system: list[dict],
        messages: list[dict],
        output_format: type | None = None,
    ) -> Any:
        # Through `spend.count_input_tokens` rather than the SDK directly: the rule that a
        # null output format is omitted rather than sent lives there with its test, and a
        # second copy here is the copy that would not get fixed.
        counted = count_input_tokens(
            self._client,
            self._model,
            system=system,
            messages=messages,
            output_format=output_format,
        )
        return _Counted(input_tokens=counted)


def system_blocks(doc: Document, instruction: str = INSTRUCTION) -> list[dict]:
    """The paper first, carrying the cache breakpoint; the instruction after it.

    Order is load-bearing. The cached prefix is a byte prefix ending at the block carrying
    `cache_control`, and the *second-text* call (`distractor.py`) sends the same paper under a
    different instruction. Paper first means both calls -- and the retry -- share one cached
    prefix; instruction first would give each call its own, and the paper would be written to
    the cache twice and read from it never. The instruction is re-sent at full rate each time
    (about two thousand tokens against a paper of fifty thousand), which is the small half of
    the cost and the price of sharing the large half.
    """
    return [
        {
            "type": "text",
            "text": render_for_model(doc),
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": instruction},
    ]


def user_turn(question: str, organism: str) -> dict:
    """The property and the organism, and nothing else about either.

    In the user turn rather than in the instruction so that the cached prefix does not
    change when the question does -- and so that the one place a value could leak in is the
    one place this module builds from its arguments rather than from a constant.
    """
    return {"role": "user", "content": f"Property: {question}\nOrganism: {organism}"}


REJECTED_CANDIDATE = -1
"""The claim index of a failure belonging to a rejected candidate rather than to a claim."""


class QuoteFailure(NamedTuple):
    """One quote the article does not contain, named as the correction turn names it."""

    claim: int
    """The claim's index in the model's list, or `REJECTED_CANDIDATE`."""
    field: str
    """Which quote of that record: `quote`, `occurrence n`, `condition medium`, `input n`."""
    reason: str
    """The checker's own words, including where the quote left the article's text."""


@dataclass(frozen=True, slots=True)
class Checked:
    """What the checker found, in the shapes the rest of the step needs.

    `passage_of` carries the passage each quote was *found* in, not the one the model
    named. That is the location correction (design D3): a right quote with a wrong id is a
    location error, and recording where it was found repairs it without refusing the claim.
    """

    failures: tuple[QuoteFailure, ...] = ()
    passage_of: dict[tuple[str, int, str], str] = field(default_factory=dict)
    failed_claims: frozenset[int] = frozenset()
    failed_rejected: frozenset[int] = frozenset()


def verify_drafts(output: ExtractionOutput, doc: Document) -> Checked:
    """Put every quote in the output through `quotes.verify`.

    Every quote: the value's, every occurrence, every condition that has one, every
    derivation input, and every rejected candidate's. A rejected candidate is a second text
    a reviewer will be shown (design D5), so an unverified one reaches a person exactly as
    an unverified claim would.
    """
    failures: list[QuoteFailure] = []
    passage_of: dict[tuple[str, int, str], str] = {}
    failed_claims: set[int] = set()
    failed_rejected: set[int] = set()

    def check(kind: str, index: int, where: str, text: str, passage_id: str) -> None:
        # `passage_id or None` rather than the empty string: a model that named no passage
        # cannot be told its passage was wrong, and `verify` takes that from None.
        outcome = quotes.verify(text, doc, passage_id or None)
        if isinstance(outcome, quotes.Failed):
            claim = index if kind == "claim" else REJECTED_CANDIDATE
            named = where if kind == "claim" else f"rejected candidate {index + 1}, {where}"
            failures.append(QuoteFailure(claim=claim, field=named, reason=outcome.reason))
            (failed_claims if kind == "claim" else failed_rejected).add(index)
            return
        passage_of[(kind, index, where)] = outcome.passage_id

    for index, claim in enumerate(output.claims):
        check("claim", index, "quote", claim.quote.text, claim.quote.passage_id)
        if not quotes.states_value(quotes.cell_text(claim.quote.text), claim.value):
            # Verbatim is not enough: the first live run produced two claims of 346 h and
            # 693 h whose quote said "nearly 200-fold". Both figures were the model's
            # arithmetic over a table it did not quote. The spec's quote *contains the
            # value*, and a quote that does not is named back like any other failure.
            # On the cell part, as `verify` and the stored `Quote` are: a rendered cell line
            # carries its headers, and a value that is only in a header ("500" from
            # "column: CIP (ng/mL) / 500") would otherwise pass and be stored with a cell
            # that reads something else (code review of 2026-09-21, finding 1).
            failures.append(
                QuoteFailure(
                    claim=index,
                    field="quote",
                    reason=(
                        f"the quote does not state the value {claim.value!r}: quote the "
                        "passage that carries this number, as written there"
                    ),
                )
            )
            failed_claims.add(index)
        for position, occurrence in enumerate(claim.occurrences, start=1):
            check(
                "claim",
                index,
                f"occurrence {position}",
                occurrence.text,
                occurrence.passage_id,
            )
        for condition in claim.conditions:
            # An empty quote is what NOT_STATED looks like, so it is not a failed quote:
            # `verify` refuses the empty string, and refusing it here would make "the
            # article does not say" unreportable.
            if not condition.quote:
                continue
            where = f"condition {condition.name}"
            check("claim", index, where, condition.quote, condition.passage_id)
        for position, derived_from in enumerate(claim.inputs, start=1):
            check(
                "claim",
                index,
                f"input {position}",
                derived_from.text,
                derived_from.passage_id,
            )

    for index, candidate in enumerate(output.rejected):
        check(
            "rejected",
            index,
            "quote",
            candidate.quote.text,
            candidate.quote.passage_id,
        )

    return Checked(
        failures=tuple(failures),
        passage_of=passage_of,
        failed_claims=frozenset(failed_claims),
        failed_rejected=frozenset(failed_rejected),
    )


def _assistant_turn(output: ExtractionOutput) -> dict:
    """The model's own answer, handed back so the correction is an edit and not a re-run.

    Its own JSON and nothing added: everything in this turn came out of the model, so no
    decision, choice or comment of ours can enter the conversation through it.
    """
    return {"role": "assistant", "content": output.model_dump_json()}


CORRECTION_OPENING = (
    "These quotes are not in the article. Each line names the quote and where it stopped "
    "matching the article's text:"
)

CORRECTION_CLOSING = (
    "A quote must be copied character for character from the passage you name. Return the "
    "whole output again, corrected: keep what was right, and drop anything you cannot "
    "quote from the article rather than rewording it. Reporting nothing is a correct "
    "answer; an invented quote is not."
)


def _correction_turn(failures: Iterable[QuoteFailure]) -> dict:
    """Name every failed quote once, in the checker's words, and ask for the whole output.

    The whole output rather than the failed parts: a patch would have to be merged into the
    first answer by us, and a merge is a place for an unverified quote to survive by being
    carried across rather than re-checked.
    """
    lines = [
        f"- claim {failure.claim + 1}, {failure.field}: {failure.reason}"
        if failure.claim != REJECTED_CANDIDATE
        else f"- {failure.field}: {failure.reason}"
        for failure in failures
    ]
    content = "\n".join([CORRECTION_OPENING, *lines, "", CORRECTION_CLOSING])
    return {"role": "user", "content": content}


def _one_call(
    model: Model,
    *,
    system: list[dict],
    messages: list[dict],
    article_id: str,
    ledger: Ledger,
    model_id: str,
) -> ExtractionOutput:
    """Project, ask the ledger, call, record. Every model call comes through here.

    The projection assumes nothing is cached, even on the retry where most of the prefix
    will be. That over-projects, and over-projecting stops a paper early while
    under-projecting lets a runaway through -- and the cache can expire between two calls,
    so the cheap-looking figure is also the one that can be wrong. A ceiling's job is to
    fail expensive.
    """
    counted = model.count_tokens(
        system=system, messages=messages, output_format=ExtractionOutput
    ).input_tokens
    projected = projected_cost(model_id, input_tokens=counted, max_tokens=MAX_TOKENS)
    ledger.check(article_id, projected)
    try:
        response = model.parse(
            system=system,
            messages=messages,
            output_format=ExtractionOutput,
            max_tokens=MAX_TOKENS,
        )
    except Exception as failure:
        # A response the adapter could not read into the schema was still billed. The first
        # live run had one such paper showing $0.00 and no call, which is the one figure a
        # ceiling must never under-count. Adapters that know the usage attach it to the error.
        usage = getattr(failure, "usage", None)
        if usage is not None:
            ledger.record(article_id, cost(model_id, usage))
        raise
    ledger.record(article_id, cost(model_id, response.usage))
    return response.parsed_output


def _location(doc: Document, passage_id: str) -> Location:
    """Where a verified quote sits, taken from the passage it was found in.

    A table cell brings its row and column headers with it: the scientist report's clearest
    finding is that the cell is the authoritative statement and the prose paraphrases it,
    so a cell shown without its headers is a number with no property and no condition.
    """
    passage = doc.passage(passage_id)
    if passage is None:  # pragma: no cover - the checker returns ids it read off the paper
        return Location(passage_id=passage_id)
    return Location(
        passage_id=passage_id,
        section_path=tuple(passage.section_path),
        kind=passage.kind,
        row_headers=tuple(passage.row_headers),
        column_headers=tuple(passage.column_headers),
    )


def _quote(doc: Document, checked: Checked, slot: tuple[str, int, str], text: str) -> Quote:
    # The record holds the paper's words. A model that quoted a cell as the rendered line it was
    # shown ("row: ... | column: ... | cell: 346.0") gets the cell kept and the headers dropped:
    # they are already on the Location, and a "verbatim quote" that carries our rendering is not
    # one. The first live run stored eleven such lines before this.
    return Quote(text=quotes.cell_text(text), location=_location(doc, checked.passage_of[slot]))


def _quotes(
    doc: Document,
    checked: Checked,
    index: int,
    label: str,
    drafts: Iterable[QuoteDraft],
) -> tuple[Quote, ...]:
    """The numbered quotes of one claim: its occurrences, or its derivation inputs.

    Numbered from one, and numbered the way the correction turn numbers them: "occurrence
    2" has to mean the same thing to the model, to the checker and here.
    """
    return tuple(
        _quote(doc, checked, ("claim", index, f"{label} {position}"), draft.text)
        for position, draft in enumerate(drafts, start=1)
    )


def _condition(
    doc: Document,
    checked: Checked,
    index: int,
    draft: ConditionDraft,
) -> ConditionField:
    """One condition field, located only when it has a quote to locate.

    NOT_STATED and SUPPLEMENTARY_ONLY carry no quote by construction, and a location on
    them would point at a passage that says nothing about the field.
    """
    slot = ("claim", index, f"condition {draft.name}")
    return ConditionField(
        name=draft.name,
        provenance=draft.provenance,
        quote=draft.quote,
        location=_location(doc, checked.passage_of[slot]) if draft.quote else None,
        reference=draft.reference,
    )


def _assemble(
    output: ExtractionOutput,
    checked: Checked,
    doc: Document,
    paper: Paper,
    question: str,
    fingerprint: Fingerprint,
) -> tuple[tuple[Claim, ...], tuple[RejectedCandidate, ...], tuple[str, ...]]:
    """Build the records out of what verified, and account for what did not.

    A claim with any failed quote is dropped whole and its id recorded: a claim missing its
    temperature quote is not a claim one field short, it is a claim whose conditions nobody
    checked. A rejected candidate is dropped silently, because it is a pool the second-text
    step draws from, and a pool coming up short costs a reviewer nothing.
    """
    claims: list[Claim] = []
    rejected: list[RejectedCandidate] = []
    unverifiable: list[str] = []

    for index, draft in enumerate(output.claims):
        # The run first: a claim id, and the item id built on it, are the store's keys, and a
        # second question asked of the same paper must not collide with the first
        # (code review of 2026-09-21, finding 4).
        claim_id = f"{fingerprint.run_id}-{paper.pmcid}-{index + 1}"
        if index in checked.failed_claims:
            unverifiable.append(claim_id)
            continue
        quote = _quote(doc, checked, ("claim", index, "quote"), draft.quote.text)
        if draft.candidate_kind not in CLAIMABLE:
            # The spec's rule, enforced here rather than trusted to the instruction: a
            # cited or assumed value is not this paper's claim, whichever list the model
            # put it in. Moved rather than dropped -- it is a legitimate second text, and
            # dropping it would reward dressing such sentences as claims to keep them.
            rejected.append(
                RejectedCandidate(
                    value=draft.value,
                    unit=draft.unit,
                    kind=draft.candidate_kind,
                    quote=quote,
                    reason=(
                        f"returned as a claim of category {draft.candidate_kind}: only a "
                        f"value the article measured or derived is a claim"
                    ),
                )
            )
            continue
        claims.append(
            Claim(
                claim_id=claim_id,
                # No question in harvest mode: the claim is named by the model's label for
                # the quantity, falling back to the article's own term.
                property_asked=question or draft.property_name or draft.property_in_paper,
                property_in_paper=draft.property_in_paper,
                property_class=draft.property_class,
                organism_name=draft.organism_name,
                value=draft.value,
                unit=draft.unit,
                kind=draft.kind,
                candidate_kind=draft.candidate_kind,
                quote=quote,
                occurrences=_quotes(doc, checked, index, "occurrence", draft.occurrences),
                conditions=tuple(
                    _condition(doc, checked, index, condition) for condition in draft.conditions
                ),
                inputs=_quotes(doc, checked, index, "input", draft.inputs),
                endpoint_conditions=draft.endpoint_conditions,
                fingerprint=fingerprint,
            )
        )

    for index, candidate in enumerate(output.rejected):
        if index in checked.failed_rejected:
            continue
        rejected.append(
            RejectedCandidate(
                value=candidate.value,
                unit=candidate.unit,
                kind=candidate.kind,
                quote=_quote(doc, checked, ("rejected", index, "quote"), candidate.quote.text),
                reason=candidate.reason,
            )
        )

    return tuple(claims), tuple(rejected), tuple(unverifiable)


def extract(
    model: Model,
    doc: Document,
    paper: Paper,
    *,
    question: str,
    organism: str,
    run_id: str,
    ledger: Ledger,
    model_id: str = MODEL,
    instruction: str = INSTRUCTION,
    user: dict | None = None,
) -> PaperResult:
    """One paper, one named ending, whatever happened.

    Every return below goes through `ending`, so the fingerprint and the paper's spend are
    on the record by construction. There are six endings and a seventh is easy to add; a
    per-ending copy of that line is the one the seventh forgets.

    `instruction` and `user` are harvest mode's way in (`bionumbers.harvest`): another
    instruction over the same paper, and a user turn that states a scope instead of a
    question. With an empty `question` each claim is named by the model's own label.
    """
    fingerprint = Fingerprint(
        model=model_id,
        instruction_sha256=instruction_sha256(instruction),
        article_id=paper.pmcid,
        run_id=run_id,
    )

    def ending(
        state: PaperState,
        reason: str = "",
        claims: tuple[Claim, ...] = (),
        rejected: tuple[RejectedCandidate, ...] = (),
        unverifiable: tuple[str, ...] = (),
    ) -> PaperResult:
        return PaperResult(
            paper=paper,
            state=state,
            reason=reason,
            claims=claims,
            rejected=rejected,
            unverifiable=unverifiable,
            spend=ledger.paper(paper.pmcid),
            fingerprint=fingerprint,
        )

    if not doc.has_methods_section:
        # Before any call, because the cheapest paper is the one not sent: a perspective
        # essay under research-article metadata measured nothing, and the whole ceiling
        # would go on buying its reference list back as claims. A coarse filter by
        # admission (design's risk list); the COMPILED category and the citation-marker
        # rule are what catch the essays that get through.
        return ending(
            PaperState.NOT_A_RESEARCH_ARTICLE,
            reason="no methods section: nothing here was measured by this article",
        )

    system = system_blocks(doc, instruction)
    messages = [user if user is not None else user_turn(question, organism)]
    try:
        output = _one_call(
            model,
            system=system,
            messages=messages,
            article_id=paper.pmcid,
            ledger=ledger,
            model_id=model_id,
        )
        checked = verify_drafts(output, doc)
        if checked.failures:
            # Exactly one retry, and the count is the design's rather than a tuning
            # choice: a second correction is a model negotiating with the checker, and the
            # checker is the instrument every "verified" claim in this project rests on.
            corrected = [
                *messages,
                _assistant_turn(output),
                _correction_turn(checked.failures),
            ]
            output = _one_call(
                model,
                system=system,
                messages=corrected,
                article_id=paper.pmcid,
                ledger=ledger,
                model_id=model_id,
            )
            checked = verify_drafts(output, doc)
    except CeilingReached as reached:
        # Nothing kept, not even what verified before the stop: half a paper's claims, with
        # no second texts and nothing in the record saying they are half, would enter the
        # review looking like the paper. The spec's "rather than half-kept".
        return ending(PaperState.CEILING_REACHED, reason=str(reached))
    except ProviderRefused:
        # Not this paper's failure: the next paper would meet the same answer. The caller
        # stops the run and says so.
        raise
    except Exception as failure:
        # Broad by decision. A run is tens of papers, and any one may meet a timeout, a
        # response the SDK could not parse, or an overloaded service; each is one FAILED
        # paper and the run goes on. The class name is in the reason because "FAILED"
        # alone cannot be triaged.
        return ending(PaperState.FAILED, reason=f"{type(failure).__name__}: {failure}")

    claims, rejected, unverifiable = _assemble(output, checked, doc, paper, question, fingerprint)
    if not claims:
        # Decided by what survived verification, not by what the model called its answer:
        # a claim that verified is what CLAIMS_FOUND means, and a paper whose every claim
        # was invented states nothing extractable however confidently it was answered. The
        # reason says which of the three routes was taken, because they are three
        # different facts about the run.
        if unverifiable:
            reason = (
                f"every claim was dropped: {len(unverifiable)} claim(s) carried a quote "
                f"the article does not contain, after one correction"
            )
        elif output.state == "NOTHING_TO_EXTRACT":
            reason = output.reason
        else:
            reason = "the model reported claims found and returned none"
        return ending(
            PaperState.NOTHING_TO_EXTRACT,
            reason=reason,
            rejected=rejected,
            unverifiable=unverifiable,
        )

    return ending(
        PaperState.CLAIMS_FOUND,
        reason=f"{len(claims)} claim(s) verified",
        claims=claims,
        rejected=rejected,
        unverifiable=unverifiable,
    )


RESULTS_FILE = "results.jsonl"
PARTIAL_SUFFIX = ".partial"


class RunFileWouldBeCommitted(Exception):
    """The run file's path is one git would track, and a run file carries article text.

    Its own type rather than `ValueError`, so a caller can tell "this cannot be written
    here" from "this could not be serialised" and say something a person can act on.
    """


def _refuse_a_committable_run_path(path: Path) -> None:
    """Refuse to write a run where git would track it.

    A run file quotes the article -- claims, occurrences, conditions, rejected candidates,
    and the checker's own excerpts in a reason -- so it holds someone else's text. Openly
    licensed, and the refusal still costs nothing next to a committed article in a
    permanent history shared by three checkouts of one origin (ADR-0170, ADR-0250).

    The ingester's guard, imported rather than reimplemented: two copies of a guard against
    an irreversible mistake is one copy that gets fixed and one that does not. **No guard
    available means no write** -- the ingester lives in a sibling package a branch may not
    have installed, and the cheap direction for an irreversible mistake is to stop.
    """
    try:
        from bionumbers_ingest.guard import committable_repo_for
    except ImportError as absent:  # pragma: no cover - both packages are installed here
        raise RunFileWouldBeCommitted(
            f"Cannot check whether {path} is committable: the guard lives in "
            f"`bionumbers_ingest`, which is not installed. A run file quotes the article, "
            f"so this refuses rather than writing unchecked."
        ) from absent

    # The scratch file as well as the final one: it is renamed into place on success, but a
    # SIGKILL or a power cut leaves it on disk under a name the final file's ignore rule
    # may not cover.
    for candidate in (path, path.with_name(path.name + PARTIAL_SUFFIX)):
        repo = committable_repo_for(candidate)
        if repo is not None:
            raise RunFileWouldBeCommitted(
                f"git would track {candidate} in {repo}. A run file carries the article's "
                f"text verbatim in every quote, and history is permanent. Write it outside "
                f"the repository, or add its directory to .gitignore."
            )


def write_results(results: Iterable[PaperResult], directory: Path) -> Path:
    """Write one run as JSONL, whole, through a scratch file.

    Whole and renamed rather than appended per paper, unlike the ask app's evaluation
    results: that file is a resume point written over hours, and this one is the end of a
    run that already holds everything in memory. So a reader never meets a torn last line
    and does not carry the tolerance for one.

    The guard runs before the directory is created, so a refused path leaves nothing at all
    behind.
    """
    directory = Path(directory)
    path = directory / RESULTS_FILE
    _refuse_a_committable_run_path(path)
    directory.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + PARTIAL_SUFFIX)
    with partial.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(result.model_dump_json() + "\n")
    partial.replace(path)
    return path


def read_results(path: Path) -> list[PaperResult]:
    """Read a run back. A line this version cannot validate stops the read.

    Pydantic's own validation is the decoder, which is why `records.py` is pydantic at all:
    a hand-written reader is a second description of the record, and it drifts from the
    writer as a silently missing field rather than as an error.
    """
    text = Path(path).read_text(encoding="utf-8")
    return [PaperResult.model_validate_json(line) for line in text.splitlines() if line.strip()]
