"""The corpus record shape and its loader.

The corpus is an external input with unresolved licensing and must not be
committed, so it is supplied at run time and no copy is bundled. Only the fields
this project actually uses are modelled; anything else in the file is ignored,
so a corpus with extra columns still loads.

`Entry`'s field set and the coercions below are a contract with the
`add-corpus-ingestion` change, whose ingester produces the file this reads. Its
contract test restates these twelve keys as a literal list, so a change here is
invisible to it until the two branches merge. **Changing a field name, adding a
required field, or altering how `_number` or `_keywords` coerce a value needs a
message to that branch**, not just a passing suite here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Annotation only. A corpus-file run never imports `bionumbers` (ADR-1600); the store's
    # loader, which does, is the one thing that puts a `Trust` here.
    from bionumbers.tiers import Trust

#: An entry's identifier: a BNID for a BioNumbers entry, a label such as `PMC2652108-1` for a value
#: harvested from a paper (ADR-1610). One alias, so a reader can find every place that carries one.
EntryId = int | str


def entry_key(value: object) -> EntryId:
    """An identifier as the corpus is keyed, whatever form it arrived in.

    A tool argument typed as a string or a number reaches here either way: a model may send BNID
    100002 as `"100002"`, and a dictionary keyed by the integer would then report the entry missing.
    All digits is a number; anything else is a label, kept as written apart from surrounding space.
    """
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return int(text) if text.isdigit() else text


class Origin(StrEnum):
    """Whether a harvested value was measured, or calculated -- and from whose numbers."""

    MEASURED = "measured"
    #: Calculated by the paper's authors from numbers in the same paper.
    CALCULATED = "calculated"
    #: Calculated from values the paper took from other publications.
    CALCULATED_FROM_PUBLISHED = "calculated_from_published"


@dataclass(frozen=True)
class Condition:
    """A condition the paper states for a value, with the passage that states it."""

    name: str
    quote: str


@dataclass(frozen=True)
class Paper:
    pmcid: str
    title: str
    year: int | None
    doi: str
    pmid: str
    licence: str
    # The paper's bibliographic record as CSL-JSON, where the store holds one (ADR-1640); "" for
    # a store written before it did. Formatted for a reader by `references`, never for the model.
    csl_json: str = ""


@dataclass(frozen=True)
class Harvest:
    """What a value harvested from a paper carries beyond a BioNumbers entry's fields (D2).

    Present only on an entry read from the harvest store; a corpus-file entry has none, which is
    how every surface tells "never reviewed" from "reviewed, and no one approved".
    """

    #: The store's own identifier for the value. Never changes and names one value forever, so it
    #: is what is saved; the entry's label is what the model types (ADR-1610).
    item_id: str
    #: The value as the paper wrote it, which is what is shown in every case.
    value_text: str
    #: The passage the value was taken from.
    quote: str
    conditions: tuple[Condition, ...]
    #: Conditions the extraction looked for and the paper does not state, by name.
    not_stated: tuple[str, ...]
    origin: Origin
    #: For a calculated value, the passages it was calculated from.
    inputs: tuple[str, ...]
    paper: Paper
    domain: str
    topic: str
    #: The numbers read from the value do not fit the kind of value the extraction recorded, so
    #: no number is stated for it (ADR-1620).
    reading_uncertain: bool = False
    #: The property in the paper's own words, kept when the store's full name ("<measure> of
    #: <object>") is the one shown; "" when it is the same.
    property_in_paper: str = ""


#: How many of five a trust tier stands for, keyed by the tier's name (ADR-0990's `Tier` is a string
#: enum, so its name is its value). Keyed by name so that neither the tools nor the drivers import
#: `bionumbers` to read a tier (ADR-1600). One scale for the model's view and the reader's stars.
TRUST_LEVEL = {
    "CURATED": 5,
    "SENIOR_SCIENTIST": 4,
    "SCIENTIST": 3,
    "STUDENT": 2,
    "AI": 1,
    "NONE": 0,
}

#: Who stands behind each tier, in words.
TRUST_ROLE = {
    "CURATED": "curated",
    "SENIOR_SCIENTIST": "senior scientist",
    "SCIENTIST": "scientist",
    "STUDENT": "student",
    "AI": "AI reviewer",
    "NONE": "no reviewer approved it",
}


class CorpusUnavailable(Exception):
    """Raised instead of falling back to bundled data, of which there is none."""


class CorpusOutOfDate(CorpusUnavailable):
    """A corpus whose entries are keyed the way an older ingester wrote them.

    A subclass, so every driver already reporting `CorpusUnavailable` reports this
    without changing -- and a distinct type, so the message can say what to do. It
    arrived as a bare `KeyError('entry_id')` first, which is true and useless: the
    reader is told a key is missing, not that their corpus is a version behind and
    not that the app will not rebuild it for them.
    """


@dataclass(frozen=True)
class Entry:
    entry_id: EntryId
    property: str
    organism: str
    units: str
    value: float | None
    range_low: float | None
    range_high: float | None
    reference: str
    reference_pubmed_id: str | None
    measurement_method: str
    comments: str
    keywords: tuple[str, ...]
    # What the source did not claim, reported by the ingester and never repaired
    # here. Two fields and not one: a record can carry either without the other,
    # and "the source states a bound, not a range" is a different sentence from
    # "these bounds may belong to two different quantities". BNID 100420 carries
    # both -- `~160,000 (21,000 to 195,700)` is hedged *and* fused -- and one flag
    # would have said a single thing about a record wrong in two ways.
    #
    # Default False so a corpus without the fields still loads, at the cost of
    # reporting nothing rather than reporting wrongly. `tests/test_markers_against_corpus.py`
    # is what catches a corpus where they never arrive.
    range_qualified: bool = False
    range_fused: bool = False
    # Which kind of hedge, so the value can say it in the source's own terms. "~20"
    # is an approximation and "<8" is a bound, and calling the first one "bounded"
    # describes it wrongly while claiming to correct a description. The ingester
    # reports the two behind `range_qualified` as `range_approximate` (1,639) and
    # `range_one_sided` (594), and derives `range_qualified` from them, so the
    # partition holds by construction on its side and is asserted against a real
    # corpus on ours.
    range_approximate: bool = False
    range_one_sided: bool = False
    # Present only for an entry read from the harvest store (D2): what a harvested value carries,
    # and its trust tier by ADR-0990's rule. Both None for a corpus-file entry.
    harvest: Harvest | None = None
    trust: Trust | None = None

    @property
    def record_id(self) -> EntryId:
        """The identifier anything saved about this entry is keyed by (ADR-1610).

        A harvested entry's label can shift between loads -- an older extraction of the same
        paper restored later takes the unsuffixed label -- so it is never what is saved. Resolve
        a saved answer by this, never by the label beside it.
        """
        return self.harvest.item_id if self.harvest is not None else self.entry_id

    @property
    def value_display(self) -> str:
        if self.harvest is not None:
            # The paper's words, always: `7.1 ± 0.4` keeps its uncertainty, and a value whose
            # reading is uncertain is shown as written rather than as a number we may have misread.
            return self.harvest.value_text
        if self.value is not None:
            return str(self.value)
        # Both bounds are required: a half-open range rendered as "0.5–None" would
        # be handed to the model as this entry's value and could be cited.
        if self.range_low is not None and self.range_high is not None:
            # 1,403 of the corpus's entries store a single measurement as a range
            # whose bounds are equal. Rendered literally that reads "400.0–400.0",
            # which invites a reader to look for a spread that is not there.
            if self.range_low == self.range_high:
                # A hedged bound is stored as a degenerate interval: `<8` arrives as
                # [8, 8]. Printed as "8.0" it asserts an equality the source never
                # made, which is a different claim rather than a rounder one -- an
                # MIC of `<8` means susceptible at or below 8. The bound is all the
                # corpus kept, so this says a bound was stated without inventing
                # which direction it pointed.
                if self.range_qualified:
                    return f"{self.range_low} ({self.hedge})"
                return str(self.range_low)
            return f"{self.range_low}–{self.range_high}"
        if self.range_low is not None:
            return f"at least {self.range_low}"
        if self.range_high is not None:
            return f"at most {self.range_high}"
        return "(no scalar value)"

    @property
    def hedge(self) -> str:
        """How the source hedged this value, in as few words as the column allows.

        Falls back to the general wording when the kind is not reported, because
        saying less is not the same as saying something untrue.
        """
        if self.range_approximate:
            return "approximate"
        if self.range_one_sided:
            return "a bound, not exact"
        return "bounded, not exact"

    @property
    def spans_implausibly(self) -> bool:
        """Whether the two bounds are too far apart to be one measurement.

        Ours to judge, and deliberately not the ingester's. `range_fused` claims the
        bounds may come from two quantities, which is a statement about provenance;
        this is a judgement about the number, and the ingester does not judge ranges
        (its ADR-0230). So the threshold is this project's to choose and defend.

        A millionfold. Far outside what a measurement of one quantity spans -- cell
        volumes across all life cover about 10^4 -- and the entries above it in this
        corpus are wrong on inspection rather than merely broad. 47 entries span it;
        `range_fused` already marks 42, so this adds five that parsed correctly and
        are still unusable, `0.25-2.5e30` among them.

        Zero and negative bounds are not judged: a ratio is meaningless across zero,
        and a mark firing on arithmetic rather than evidence is worse than no mark.
        """
        low, high = self.range_low, self.range_high
        if low is None or high is None or low <= 0 or high <= 0:
            return False
        return max(low, high) / min(low, high) > IMPLAUSIBLE_SPAN

    @property
    def quotation_text(self) -> str:
        """Where curator quotations live, when an entry carries one."""
        return f"{self.comments}\n{self.measurement_method}".strip()


# See `Entry.spans_implausibly` for why this number and why it is ours.
IMPLAUSIBLE_SPAN = 1_000_000


def _number(value: Any) -> float | None:
    """Coerce to a number, or None.

    A corpus converted from a spreadsheet writes "" for an absent scalar, and may
    write numbers as strings. An empty string is not None, so left uncoerced it
    would satisfy the "has a value" branch and blank out every range-only entry.
    """
    if value is None or value == "":
        return None
    return float(value)


def _keywords(value: Any) -> tuple[str, ...]:
    """Keywords as a tuple, whether the corpus stores a list or a joined string.

    Passing a string to tuple() yields one entry per character, which would make
    every single-letter search match everything and every real term match nothing
    -- silently, since nothing raises.
    """
    if not value:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return tuple(str(v) for v in value)


def _entry(raw: dict) -> Entry:
    if "entry_id" not in raw and "bnid" in raw:
        # Refused by name rather than reinterpreted. The alternative -- reading
        # `bnid` as a fallback -- is a compatibility branch that would outlive its
        # usefulness and quietly keep two wire formats alive; and `autobuild` never
        # rebuilds a corpus that exists (its `is_ready`), so a corpus a version
        # behind would otherwise reach here on every start with nothing to fix it.
        raise CorpusOutOfDate(
            "this corpus was built by an older ingester -- its entries are keyed "
            "'bnid', and this version reads 'entry_id'. Delete the corpus file and "
            "start again -- the app rebuilds it, about a minute, if the export sits "
            "beside it -- or rebuild it yourself with `bionumbers-ingest`."
        )
    return Entry(
        entry_id=int(raw["entry_id"]),
        property=(raw.get("property") or "").strip(),
        organism=(raw.get("organism") or "").strip(),
        units=(raw.get("units") or "").strip(),
        value=_number(raw.get("value")),
        range_low=_number(raw.get("range_low")),
        range_high=_number(raw.get("range_high")),
        reference=(raw.get("reference") or "").strip(),
        reference_pubmed_id=raw.get("reference_pubmed_id") or None,
        measurement_method=(raw.get("measurement_method") or "").strip(),
        comments=(raw.get("comments") or "").strip(),
        keywords=_keywords(raw.get("keywords")),
        range_qualified=bool(raw.get("range_qualified")),
        range_fused=bool(raw.get("range_fused")),
        # Read from the flag list, which is where the ingester reports the kind.
        # Absent, the value still says it was hedged -- less precisely, never wrongly.
        # Fields, not names read out of `parse_flags`. That list is the ingester's
        # own vocabulary and explicitly renameable (its ADR-0230); borrowing from it
        # for a user-visible string meant a rename would turn both False and quietly
        # fall back to the vaguer wording. Promoted to contract on request.
        range_approximate=bool(raw.get("range_approximate")),
        range_one_sided=bool(raw.get("range_one_sided")),
    )


#: The first bytes of every SQLite database: how a harvest store is told from a corpus file.
SQLITE_HEADER = b"SQLite format 3\x00"

STORE_IS_NOT_A_CORPUS = (
    "{path} is a harvest store, not a corpus file. The app reads it through SCINUMBERS_STORE. "
    "Evaluation and the answer sheet read a corpus file only, until the work package "
    '"Evaluation over the store" in docs/roadmap.md lands.'
)


def load(path: str | Path | None) -> tuple[Entry, ...]:
    """Load a JSONL corpus. No path means no corpus -- there is no fallback."""
    if not path:
        raise CorpusUnavailable(
            "No corpus path supplied. The corpus is an external input and is not "
            "bundled with this project; pass its path explicitly."
        )
    p = Path(path)
    if not p.is_file():
        raise CorpusUnavailable(f"No corpus file at {p}.")
    with p.open("rb") as handle:
        is_store = handle.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    if is_store:
        # Named for what it is. Read as lines, a database is "line 1 is not a usable entry",
        # which sends a reader looking for corruption in a file that is fine. Here rather than
        # in the evaluation command, so every caller of a corpus file is told the same.
        raise CorpusUnavailable(STORE_IS_NOT_A_CORPUS.format(path=p))
    entries = []
    with p.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(_entry(json.loads(line)))
            except CorpusOutOfDate as exc:
                # Before the general handler, or the sentence would be flattened into
                # "line 1 is not a usable entry" -- which is how a fixable corpus
                # comes to look like a corrupt one.
                raise CorpusOutOfDate(f"{p}: {exc}") from exc
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise CorpusUnavailable(f"{p}: line {number} is not a usable entry: {exc}") from exc
    if not entries:
        raise CorpusUnavailable(f"{p} contains no entries.")
    return tuple(entries)


def load_configured(corpus: str | Path | None, store: str | Path | None) -> tuple[Entry, ...]:
    """The configured corpus: a corpus file, or the harvest store -- never both.

    Both named is refused rather than resolved by a precedence rule (design D7): a reader who set
    both did not mean one of them, and answering from the other is a wrong-corpus answer that
    looks right. The refusal is here, in the operation every driver calls, so a second driver or a
    test cannot load past it.

    The store's loader is imported only when a store is named, so a corpus-file run never imports
    the validator package (ADR-1600).
    """
    if corpus and store:
        raise CorpusUnavailable(
            f"Both a corpus file ({corpus}) and a harvest store ({store}) are configured. "
            "Set SCINUMBERS_CORPUS or SCINUMBERS_STORE, not both."
        )
    if store:
        from .store_corpus import load as load_store

        return load_store(store)
    return load(corpus)
