"""The harvest store as the agent's corpus: a second adapter onto `Entry` (design D1).

The store is the review's database of record -- curated BioNumbers entries, values harvested from
papers, and reviewers' decisions -- written by the review while the agent runs. This reads it once,
read-only, and returns the same `Entry` records a corpus file yields, so everything downstream
(repository, tools, drivers) keeps one code path. **Ports and adapters**: the corpus file and the
store are two adapters onto the one `Entry` port.

The only module in `numera_ask` that imports `numera_validator` (ADR-1600): the tier rule and the
value parser each have one definition, there, and a corpus-file run never loads this module.

Three things a reader of one function here would not see:

- **Read-only is the connection's, not this module's good behaviour.** The file is opened with
  SQLite's `mode=ro`, so a second caller gets the same refusal (a guard belongs to the operation).
- **What no entry holds cannot leak.** The review's test text (`second`), the kind of distractor,
  the property the extraction was asked about, and everything a reviewer wrote are never put into
  an entry: an item is parsed, the fields an entry needs are copied out, and the rest goes with the
  parsed item. Reviewers' decisions are read only by `tiers.by_item`, which returns a tier, whether
  it is disputed, and whether it was simulated -- all the agent learns of a review.
- **A label is for one load** (ADR-1610). `PMC2652108-1` is what the model types; the store's item
  id is what is saved. Nothing saved is ever resolved by its label.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, select, text

from numera_validator import readings, store, tiers
from numera_validator.quotes import fold
from numera_validator.records import CandidateKind, ClaimKind, Provenance, ReviewItem

from .citations import LABEL
from .corpus import Condition, CorpusUnavailable, Entry, Harvest, Origin, Paper

_ORIGIN = {
    CandidateKind.MEASURED: Origin.MEASURED,
    CandidateKind.DERIVED: Origin.CALCULATED,
    CandidateKind.DERIVED_FROM_PUBLISHED: Origin.CALCULATED_FROM_PUBLISHED,
}


def path_of(setting: str) -> Path:
    """The store's file, from a path or a `sqlite:///` URL."""
    text = setting.strip()
    for prefix in ("sqlite:////", "sqlite:///"):
        if text.startswith(prefix):
            text = ("/" if prefix == "sqlite:////" else "") + text[len(prefix) :]
            break
    return Path(text).expanduser()


def connect(path: Path) -> sqlite3.Connection:
    """The store, opened so that nothing can be written through the connection."""
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def load(setting: str | Path | None) -> tuple[Entry, ...]:
    """Every curated entry and every harvested value in the store, read once and read-only."""
    if not setting:
        raise CorpusUnavailable("No store configured: name the harvest store's file.")
    path = path_of(str(setting))
    if not path.is_file():
        raise CorpusUnavailable(f"No harvest store at {path}.")
    engine = create_engine("sqlite://", creator=lambda: connect(path))
    try:
        with engine.connect() as conn:
            curated = conn.execute(select(store.curated_entry)).all()
            # Only the columns read here: `select(store.review_paper)` names every column the
            # table now defines, and a store written before one was added could not be read.
            paper = store.review_paper.c
            papers = {
                (row.run_id, row.pmcid): row
                for row in conn.execute(
                    select(paper.run_id, paper.pmcid, paper.domain, paper.topic)
                )
            }
            references = _references(conn)
            property_names = _property_names(conn)
            items = conn.execute(
                select(
                    store.review_item.c.item_id,
                    store.review_item.c.run_id,
                    store.review_item.c.pmcid,
                    store.review_item.c.claim_id,
                    store.review_item.c.item_json,
                    store.review_item.c.created_at,
                )
            ).all()
        trust = tiers.by_item(engine)
    except Exception as exc:  # sqlite3 and SQLAlchemy both: the file is not a readable store
        raise CorpusUnavailable(f"{path} is not a readable harvest store: {exc}") from exc
    finally:
        engine.dispose()

    entries = [_curated(row) for row in curated]
    try:
        labels = _labels(items)
    except CorpusUnavailable:
        raise
    except Exception as exc:  # a null claim id, say: a sentence, not a traceback
        raise CorpusUnavailable(f"{path} holds items this reader cannot label: {exc}") from exc
    for row in items:
        paper_row = papers.get((row.run_id, row.pmcid))
        try:
            entries.append(
                _harvested(
                    row,
                    labels[row.item_id],
                    paper_row,
                    trust.get(row.item_id, tiers.Trust(tiers.Tier.NONE)),
                    references.get((row.run_id, row.pmcid), ""),
                    property_names.get(row.item_id, ""),
                )
            )
        except Exception as exc:
            # An item written by another version of the review's records, or a kind this
            # reader does not know: both drivers render CorpusUnavailable as a sentence, and
            # anything else as a traceback.
            raise CorpusUnavailable(
                f"{path} holds an item this reader cannot read ({row.item_id}): {exc}"
            ) from exc
    if not entries:
        raise CorpusUnavailable(f"{path} holds no entries.")
    return tuple(entries)


def _curated(row: Any) -> Entry:
    """A curated BioNumbers entry: its BNID, its fields, and the top tier by construction."""
    return Entry(
        entry_id=int(row.entry_id),
        property=row.property.strip(),
        organism=(row.organism or "").strip(),
        units=(row.units or "").strip(),
        value=row.value,
        range_low=row.range_low,
        range_high=row.range_high,
        reference=(row.reference or "").strip(),
        reference_pubmed_id=row.pubmed_id or None,
        measurement_method=(row.method or "").strip(),
        comments=(row.comments or "").strip(),
        keywords=(),
        # The one hedge the curated table keeps, reported in the corpus's own terms.
        range_qualified=bool(row.approximate),
        range_approximate=bool(row.approximate),
        trust=tiers.CURATED,
    )


def _labels(items: list[Any]) -> dict[str, str]:
    """Each item's label: `PMCID-n`, suffixed `.k` for the k-th extraction of the same paper.

    Extractions are ordered by when they were loaded into the store -- the earliest `created_at`
    of the run's items for that paper, then the run id -- because the store is insert-only, so a
    run loaded later always sorts later and an existing label never moves. Ordering by when a run
    was *made* would relabel the moment an older run was restored (design D3).
    """
    loaded: dict[tuple[str, str], datetime] = {}
    for row in items:
        key = (row.pmcid, row.run_id)
        if key not in loaded or row.created_at < loaded[key]:
            loaded[key] = row.created_at
    runs_of: dict[str, list[str]] = defaultdict(list)
    for pmcid, run_id in sorted(loaded, key=lambda key: (loaded[key], key[1])):
        runs_of[pmcid].append(run_id)

    labels: dict[str, str] = {}
    owner: dict[str, str] = {}
    for row in items:
        prefix = f"{row.run_id}-{row.pmcid}-"
        if not row.claim_id.startswith(prefix):
            raise CorpusUnavailable(
                f"item {row.item_id}: claim id {row.claim_id!r} does not name its run and paper"
            )
        label = f"{row.pmcid}-{row.claim_id[len(prefix) :]}"
        k = runs_of[row.pmcid].index(row.run_id) + 1
        if k > 1:
            label = f"{label}.{k}"
        if not LABEL.fullmatch(label):
            # The form written and the form read are one pattern (`citations.LABEL`); a label the
            # parser cannot read would be a citation the agent can never make.
            raise CorpusUnavailable(f"item {row.item_id}: {label!r} is not a citable label")
        if label in owner:
            raise CorpusUnavailable(
                f"two harvested values would both be cited as {label}: "
                f"{owner[label]} and {row.item_id}"
            )
        owner[label] = row.item_id
        labels[row.item_id] = label
    return labels


def _references(conn: Any) -> dict[tuple[str, str], str]:
    """Each paper's CSL-JSON record, keyed as `review_paper` is; empty for a store without them.

    Read by name rather than through `numera_validator.store`'s table, so a store written before the
    column existed (`add-paper-references`, ADR-1750) still loads, with none.
    """
    if "csl_json" not in {column["name"] for column in inspect(conn).get_columns("review_paper")}:
        return {}
    rows = conn.execute(text("SELECT run_id, pmcid, csl_json FROM review_paper"))
    return {(run_id, pmcid): csl or "" for run_id, pmcid, csl in rows}


def _property_names(conn: Any) -> dict[str, str]:
    """Each item's full property name, "<measure> of <object>"; empty for a store without them.

    Read by name for the reason `_references` gives: the column is `harden-harvest`'s (ADR-1700,
    on `feat/property-names`), and a store written before it simply has none.
    """
    if "property" not in {column["name"] for column in inspect(conn).get_columns("review_item")}:
        return {}
    rows = conn.execute(text("SELECT item_id, property FROM review_item"))
    return {item_id: name or "" for item_id, name in rows}


def _harvested(
    row: Any,
    label: str,
    paper_row: Any,
    trust: tiers.Trust,
    csl_json: str = "",
    property_name: str = "",
) -> Entry:
    """A harvested value as an `Entry`. Reads the claim and the paper; never the review's text."""
    item = ReviewItem.model_validate_json(row.item_json)
    claim = item.claim
    paper = item.paper

    stated: list[Condition] = []
    not_stated: list[str] = []
    for field in claim.conditions:
        if field.provenance is Provenance.NOT_STATED:
            not_stated.append(field.name)
        else:
            stated.append(Condition(name=field.name, quote=field.quote or field.reference))
    method = next((c.quote for c in stated if c.name == "method"), "")

    value, low, high, approximate, uncertain = _reading(claim.value, claim.unit, claim.kind)
    domain = paper_row.domain if paper_row is not None else claim.fingerprint.scope
    topic = paper.topic or (paper_row.topic if paper_row is not None else "")
    reference = paper.title
    if paper.year:
        reference = f"{reference} ({paper.year})"
    if paper.doi:
        reference = f"{reference}. doi:{paper.doi}"

    return Entry(
        entry_id=label,
        # The full name -- the measure and what it is of -- where the store holds one; the
        # paper's own wording ("average length") otherwise.
        property=property_name.strip() or claim.property_in_paper.strip(),
        organism=claim.organism_name.strip(),
        units=claim.unit.strip(),
        value=value,
        range_low=low,
        range_high=high,
        reference=reference,
        reference_pubmed_id=paper.pmid or None,
        measurement_method=method,
        comments="",
        # What a keyword search reaches (design D2): the qualifier a reader searches for often
        # lives in the passage, not in the paper's shorter wording of the property.
        # The paper's own wording of the property too: once the full name replaces it, a search
        # for "average length" must still reach the entry.
        keywords=tuple(
            part
            for part in (
                domain,
                topic,
                claim.property_in_paper.strip(),
                claim.quote.text,
                *(c.quote for c in stated),
            )
            if part
        ),
        range_qualified=approximate,
        range_approximate=approximate,
        harvest=Harvest(
            item_id=row.item_id,
            value_text=claim.value,
            quote=claim.quote.text,
            conditions=tuple(stated),
            not_stated=tuple(not_stated),
            origin=_ORIGIN[claim.candidate_kind],
            inputs=tuple(q.text for q in claim.inputs),
            paper=Paper(
                pmcid=paper.pmcid,
                title=paper.title,
                year=paper.year,
                doi=paper.doi,
                pmid=paper.pmid,
                licence=paper.licence,
                csl_json=csl_json,
            ),
            domain=domain,
            topic=topic,
            reading_uncertain=uncertain,
            property_in_paper=claim.property_in_paper.strip() if property_name.strip() else "",
        ),
        trust=trust,
    )


#: A comparator or a bound in words: the paper gave a limit, not a value.
_BOUND = re.compile(
    r"[<>≤≥≲≳]|\b(?:up to|more than|less than|greater than|fewer than|at least|at most|"
    r"over|under|above|below|exceed(?:s|ing)?)\b",
    re.I,
)
#: An exponent belongs to its number: `5 x 10^2` is one number written with three runs of digits.
_EXPONENT = re.compile(r"(?:x\s*10\s*\^?\s*|\b10\s*\^\s*|(?<=\d)e)[+-]?\d+", re.I)
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
_DIGIT_RUN = re.compile(r"\d+(?:\.\d+)?")


def _numbers_written(text: str) -> int:
    """How many numbers the paper wrote in `text`, through the parser's own fold."""
    folded = _THOUSANDS.sub("", fold(text))
    return len(_DIGIT_RUN.findall(_EXPONENT.sub("", folded)))


def _reading(
    text: str, unit: str, kind: ClaimKind
) -> tuple[float | None, float | None, float | None, bool, bool]:
    """(value, low, high, approximate, uncertain) for a value the paper wrote as text (ADR-1620).

    The numbers are kept only where their shape fits the kind of value the extraction recorded:
    one number for a single value, one number and an uncertainty for a value with one, two numbers
    for a range. Anything else is uncertain, and no number is stated for it.

    **Which direction is cheap.** A correct reading cautioned costs a sentence; a misread number
    stated with confidence is a wrong answer that looks like a right one. So any disagreement
    cautions, whichever side is wrong -- the parser or the recorded kind.
    """
    # The value alone: a unit such as `x 10^6 cells/mL` holds a scale factor, and read together
    # with the value it multiplies a number the unit still states.
    reading = readings.parse(text)
    if reading is None:
        return None, None, None, False, True
    # The parser reads the first number and what follows it, and is lenient by design: `>500`
    # reads as 500 and `70 and 100` as 70. A bound, or a number it did not use, is a reading that
    # does not say what the paper said -- so it is uncertain, whatever the kind.
    used = len(reading.numbers) + (reading.uncertainty is not None)
    if _BOUND.search(text) or _numbers_written(text) > used:
        return None, None, None, False, True
    numbers = [float(n) for n in reading.numbers]
    if kind is ClaimKind.SINGLE and len(numbers) == 1:
        return numbers[0], None, None, reading.approximate, False
    if kind is ClaimKind.WITH_UNCERTAINTY and len(numbers) == 1 and reading.uncertainty is not None:
        return numbers[0], None, None, reading.approximate, False
    if kind is ClaimKind.RANGE_OVER_CONDITIONS and len(numbers) == 2:
        return None, numbers[0], numbers[1], reading.approximate, False
    return None, None, None, False, True
