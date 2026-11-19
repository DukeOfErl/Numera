"""Every record the pipeline passes between its steps and writes to disk.

One module, because the same shapes cross three boundaries: the extraction call's structured
output, the JSONL a run writes under `data/runs/<run-id>/`, and the rows the store loads. Pydantic
rather than dataclasses so that one definition serves all three -- the extraction call hands
`ExtractionOutput` to the SDK as its output schema, and `model_validate_json` reads a run back
without a hand-written decoder that could drift from the encoder.

The states are the design's D2 (ADR-1530): a closed set per paper, per condition field and per
candidate value, in place of any confidence score. Adding a member here is a decision, not a
convenience -- each one exists because a real paper showed the shape.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PaperState(StrEnum):
    """Exactly one per article, at the end of extraction."""

    CLAIMS_FOUND = "CLAIMS_FOUND"
    NOTHING_TO_EXTRACT = "NOTHING_TO_EXTRACT"
    """Read in full; states no measured value for the property. A fact about the paper."""
    NOT_A_RESEARCH_ARTICLE = "NOT_A_RESEARCH_ARTICLE"
    """No methods section: a perspective or essay under research-article metadata."""
    UNREADABLE = "UNREADABLE"
    """Discovery obtained no full text. A fact about access, never about the paper."""
    CEILING_REACHED = "CEILING_REACHED"
    FAILED = "FAILED"


class Provenance(StrEnum):
    """Where a condition or method field's quote came from."""

    BESIDE_VALUE = "BESIDE_VALUE"
    FROM_METHODS = "FROM_METHODS"
    BY_REFERENCE = "BY_REFERENCE"
    """The paper says its conditions were described elsewhere and cites that work."""
    SUPPLEMENTARY_ONLY = "SUPPLEMENTARY_ONLY"
    """The paper points at supplementary material, which this prototype does not read."""
    NOT_STATED = "NOT_STATED"


class CandidateKind(StrEnum):
    """What a number in the paper is doing there. The first three are claims; the rest are
    rejected candidates, kept because the second text is drawn from them."""

    MEASURED = "MEASURED"
    DERIVED = "DERIVED"
    DERIVED_FROM_PUBLISHED = "DERIVED_FROM_PUBLISHED"
    """Computed by this article from other publications' data: its own result, flagged so it
    is never read as its own measurement. Added 2026-10-04 (ADR-0950): such papers are often
    the cited source of a number, BioNumbers keeps them, and with no category for them the
    models split between calling them derived and refusing the paper."""
    CITED = "CITED"
    PARAMETER = "PARAMETER"
    COMPILED = "COMPILED"


class ClaimKind(StrEnum):
    SINGLE = "SINGLE"
    WITH_UNCERTAINTY = "WITH_UNCERTAINTY"
    RANGE_OVER_CONDITIONS = "RANGE_OVER_CONDITIONS"
    """Endpoints belong to different conditions. Never a measurement with uncertainty."""


class SecondTextKind(StrEnum):
    DISTRACTOR = "DISTRACTOR"
    SECOND_OCCURRENCE = "SECOND_OCCURRENCE"


class DistractorType(StrEnum):
    """In preference order, hardest first (design D5)."""

    ADJACENT_CONDITION = "ADJACENT_CONDITION"
    CITED = "CITED"
    DIFFERENT_QUANTITY = "DIFFERENT_QUANTITY"
    PARAMETER = "PARAMETER"
    DERIVATION_HALF = "DERIVATION_HALF"


DISTRACTOR_PREFERENCE: tuple[DistractorType, ...] = tuple(DistractorType)

#: The condition fields every claim carries, in the order the review page lists them. `method`
#: sits among them because it is quoted and provenanced the same way.
CONDITION_FIELDS: tuple[str, ...] = (
    "organism",
    "strain",
    "medium",
    "temperature",
    "growth_phase",
    "culture_mode",
    "normalisation_basis",
    "method",
)


class Location(Frozen):
    """Where in the paper a passage sits. `passage_id` is the JATS reader's id, and the
    headers are filled only for a table cell (`kind == "td"`)."""

    passage_id: str
    section_path: tuple[str, ...] = ()
    kind: str = "p"
    """One of `p`, `td`, `caption`, `title`."""
    row_headers: tuple[str, ...] = ()
    column_headers: tuple[str, ...] = ()


class Quote(Frozen):
    """Verbatim text from the paper, and where. Nothing reaches a reviewer or the record
    unless `quotes.verify` has passed it."""

    text: str
    location: Location


class TableCell(Frozen):
    """One cell of a table as the paper laid it out: its text, whether it is a header, the
    columns and rows it spans, and the passage it became -- empty for a header cell, an empty
    cell, or a cell that is the same passage as none."""

    text: str
    header: bool = False
    colspan: int = 1
    rowspan: int = 1
    passage_id: str = ""


class TableView(Frozen):
    """A whole table as the paper printed it, for the review page to draw beneath the two texts
    when one of them is a cell (ADR-0940). `rows` are the `<tr>` rows in order, header rows
    first, each cell with its spans, so the page can lay the grid out as the paper did."""

    label: str
    caption: str = ""
    foot: str = ""
    rows: tuple[tuple[TableCell, ...], ...] = ()

    def holds(self, passage_id: str) -> bool:
        return any(cell.passage_id == passage_id for row in self.rows for cell in row)


class ConditionField(Frozen):
    name: str
    """One of `CONDITION_FIELDS`."""
    provenance: Provenance
    quote: str = ""
    """Empty when `provenance` is `NOT_STATED`."""
    location: Location | None = None
    reference: str = ""
    """For `BY_REFERENCE`: the citation marker or reference text the paper points at."""


class Fingerprint(Frozen):
    """What produced a claim or a state, so items are never compared across generators."""

    model: str
    instruction_sha256: str
    article_id: str
    run_id: str
    scope: str = ""
    """Harvest mode only: the domain the paper was asked in (`numera_validator.harvest.SCOPES`)."""
    answered_by: str = ""
    """The model the provider says answered, where it says: a router or a dated build answers
    under another name than `model`, the one asked for. Comma-joined if the retry differed."""


class Claim(Frozen):
    claim_id: str
    property_asked: str
    property_in_paper: str
    property_class: str = ""
    """Harvest mode only: the class of quantity (`numera_validator.harvest.PROPERTY_CLASSES`)."""
    organism_name: str = ""
    """Harvest mode only: the species, as a label. The quoted organism is in `conditions`."""
    value: str
    """As the paper states it: `39 ± 1`, `20–40`, `2.1`."""
    unit: str
    kind: ClaimKind
    candidate_kind: CandidateKind
    """`MEASURED` or `DERIVED`; anything else is a `RejectedCandidate`, not a claim."""
    quote: Quote
    """The most precise statement of the value."""
    occurrences: tuple[Quote, ...] = ()
    """Restatements of the same value elsewhere in the paper, at any precision."""
    conditions: tuple[ConditionField, ...] = ()
    inputs: tuple[Quote, ...] = ()
    """For a derived value: the quoted measurements it was computed from."""
    endpoint_conditions: tuple[str, ...] | None = None
    """For a range over conditions: the conditions the range spans, in the paper's order. A tuple
    of any length, not a pair: the first live run met a range over five antibiotic
    concentrations, and a pair type made that paper FAILED rather than a claim."""
    fingerprint: Fingerprint


class RejectedCandidate(Frozen):
    value: str
    unit: str
    kind: CandidateKind
    quote: Quote
    reason: str


class Spend(Frozen):
    """Provider-reported tokens and the cost derived from the price table."""

    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0
    calls: int = 0

    def plus(self, other: Spend) -> Spend:
        return Spend(
            input_tokens=self.input_tokens + other.input_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            usd=self.usd + other.usd,
            calls=self.calls + other.calls,
        )


UNLICENSED = "UNLICENSED"


class Paper(Frozen):
    """A discovered article: enough to cite it, and whether its text may be kept."""

    pmcid: str
    pmid: str = ""
    doi: str = ""
    title: str = ""
    year: int | None = None
    licence: str = UNLICENSED
    """A licence URL or name as the index or the document states it, else `UNLICENSED`, in
    which case no text from the paper is written past the disk cache."""
    source_url: str = ""
    """Where the full text came from, empty when none was obtained."""
    full_text_status: str = ""
    """Discovery's typed reason when no full text was obtained, e.g. `no XML (HTTP 500)`."""
    topic: str = ""
    """Harvest mode only: what the paper is about, as whoever chose it named it ("planarians",
    "cytoskeleton"). Free text, finer than the scope, and never shown to the model; the review
    page offers it to a person choosing what to review."""
    csl_json: str = ""
    """The bibliographic record as one CSL-JSON item, serialised (ADR-1750): authors, journal,
    volume, issue, pages, date and identifiers, read from the paper's own front matter. The
    application formats a citation from it; no model writes one. Empty for a paper read before
    this field existed, or whose full text was never fetched."""


class PaperResult(Frozen):
    """One article's extraction, whatever its ending."""

    paper: Paper
    state: PaperState
    reason: str = ""
    claims: tuple[Claim, ...] = ()
    rejected: tuple[RejectedCandidate, ...] = ()
    unverifiable: tuple[str, ...] = ()
    """Claim ids dropped after a quote failed verification twice."""
    spend: Spend = Spend()
    fingerprint: Fingerprint


class ReviewItem(Frozen):
    """What one screen shows, and what is stored about it that the screen never shows."""

    item_id: str
    question: str
    claim: Claim
    paper: Paper
    supporting: Quote
    second: Quote
    second_kind: SecondTextKind
    distractor_type: DistractorType | None = None
    tables: tuple[TableView, ...] = ()
    """The tables the two texts sit in, when either is a cell: shown whole beneath them, in
    document order, with both texts' cells marked alike. Empty for two prose texts."""


class NotReviewable(Frozen):
    claim_id: str
    reason: str


class Discovery(Frozen):
    """What a discovery run recorded about itself."""

    run_id: str
    question: str
    query: str
    limit: int
    more_existed: bool = False
    kept: tuple[Paper, ...] = ()
    excluded: tuple[tuple[str, str], ...] = Field(default=())
    """(identifier, reason) for every record dropped before any fetch."""


class ReviewerRole(StrEnum):
    """The rung of the trust ladder a decision was made on, lowest first.

    `AI` is a model reviewing as itself. The other three are people -- or, in a simulated review,
    a model standing in for one, which the decision's `reviewer_model` then says. An entry's trust
    tier is read off the roles of the decisions that approved it and is stored nowhere (ADR-0960).
    """

    AI = "AI"
    STUDENT = "STUDENT"
    SCIENTIST = "SCIENTIST"
    SENIOR_SCIENTIST = "SENIOR_SCIENTIST"
