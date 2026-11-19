"""An invented harvest store, built through the review package's own models and loader.

Every word here is made up. The real store holds passages from papers some of which are licensed
NC or ND, and none of that text may enter the repository. What is real is the shape: items are
`numera_validator.records.ReviewItem`s loaded by `numera_validator.store.load_run`, so a change to
either is a change this fixture meets, rather than a hand-written JSON that keeps agreeing with the
loader that was written beside it.

Planted markers: every string the agent must never see carries one of `NEVER_SHOWN`, so a test can
look for them in everything an entry holds.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert

from numera_validator import store
from numera_validator.records import (
    CandidateKind,
    Claim,
    ClaimKind,
    ConditionField,
    DistractorType,
    Fingerprint,
    Location,
    Paper,
    PaperResult,
    PaperState,
    Provenance,
    Quote,
    ReviewItem,
    SecondTextKind,
)

LICENCE = "https://creativecommons.org/licenses/by/4.0/"

#: Text written for the review and never for the agent: the second (test) text, the property the
#: extraction was asked about, and each thing a reviewer wrote.
SECOND_TEXT = "SECOND-TEXT-MARKER: a passage chosen to look like the right one"
PROPERTY_ASKED = "PROPERTY-ASKED-MARKER"
REVIEWER_COMMENT = "REVIEWER-COMMENT-MARKER"
REVIEWER_ISSUE = "REVIEWER-ISSUE-MARKER: the value is from another condition"
VALUE_READ = "VALUE-READ-MARKER"
NEVER_SHOWN = ("SECOND-TEXT-MARKER", PROPERTY_ASKED, REVIEWER_COMMENT, "REVIEWER-ISSUE-MARKER")
# `VALUE_READ` is checked separately: a reviewer reads the value the paper wrote, so its marker is
# planted as the reviewer's reading of a different number.

RUN_A = "invented-run-a"
RUN_B = "invented-run-b"
CURATED_ID = 100001


def _quote(text: str, passage: str = "p1") -> Quote:
    return Quote(text=text, location=Location(passage_id=passage, section_path=("Results",)))


def _paper(pmcid: str, *, title: str, year: int, topic: str) -> Paper:
    return Paper(
        pmcid=pmcid,
        pmid=pmcid.removeprefix("PMC"),
        doi=f"10.0000/{pmcid.lower()}",
        title=title,
        year=year,
        licence=LICENCE,
        topic=topic,
    )


def _item(
    paper: Paper,
    run_id: str,
    n: int,
    *,
    property_in_paper: str,
    organism: str,
    value: str,
    unit: str,
    kind: ClaimKind,
    candidate_kind: CandidateKind,
    quote: str,
    conditions: tuple[tuple[str, Provenance, str], ...] = (),
    inputs: tuple[str, ...] = (),
    domain: str = "biology",
) -> ReviewItem:
    claim_id = f"{run_id}-{paper.pmcid}-{n}"
    fingerprint = Fingerprint(
        model="invented/model",
        instruction_sha256="0" * 64,
        article_id=paper.pmcid,
        run_id=run_id,
        scope=domain,
    )
    claim = Claim(
        claim_id=claim_id,
        property_asked=PROPERTY_ASKED,
        property_in_paper=property_in_paper,
        organism_name=organism,
        value=value,
        unit=unit,
        kind=kind,
        candidate_kind=candidate_kind,
        quote=_quote(quote),
        conditions=tuple(
            ConditionField(
                name=name,
                provenance=provenance,
                quote="" if provenance is Provenance.NOT_STATED else said,
                location=None if provenance is Provenance.NOT_STATED else Location(passage_id="p2"),
            )
            for name, provenance, said in conditions
        ),
        inputs=tuple(_quote(text, f"p{3 + i}") for i, text in enumerate(inputs)),
        fingerprint=fingerprint,
    )
    return ReviewItem(
        item_id=f"{claim_id}-item",
        question=PROPERTY_ASKED,
        claim=claim,
        paper=paper,
        supporting=_quote(quote),
        second=_quote(SECOND_TEXT, "p9"),
        second_kind=SecondTextKind.DISTRACTOR,
        distractor_type=DistractorType.ADJACENT_CONDITION,
    )


def _result(paper: Paper, run_id: str, domain: str) -> PaperResult:
    return PaperResult(
        paper=paper,
        state=PaperState.CLAIMS_FOUND,
        fingerprint=Fingerprint(
            model="invented/model",
            instruction_sha256="0" * 64,
            article_id=paper.pmcid,
            run_id=run_id,
            scope=domain,
        ),
    )


ACTIN = _paper("PMC1000001", title="Invented actin paper", year=2009, topic="cytoskeleton")
OPTICS = _paper("PMC2000002", title="Invented optics paper", year=2015, topic="optics")


def run_a() -> list[ReviewItem]:
    """The first run: four values from a biology paper, one from a physics paper."""
    stated = Provenance.BESIDE_VALUE
    return [
        _item(
            ACTIN,
            RUN_A,
            1,
            property_in_paper="F-actin concentration",
            organism="mouse",
            value="488",
            unit="µM",
            kind=ClaimKind.SINGLE,
            candidate_kind=CandidateKind.MEASURED,
            quote="The lamellipodial F-actin concentration was 488 µM in invented cells.",
            conditions=(
                ("organism", stated, "invented mouse cells"),
                ("method", Provenance.FROM_METHODS, "invented electron microscopy counts"),
                ("temperature", Provenance.NOT_STATED, ""),
            ),
        ),
        _item(
            ACTIN,
            RUN_A,
            2,
            property_in_paper="Filament spacing",
            organism="mouse",
            value="7.1 ± 0.4",
            unit="nm",
            kind=ClaimKind.WITH_UNCERTAINTY,
            candidate_kind=CandidateKind.DERIVED,
            quote="Filaments were spaced 7.1 ± 0.4 nm apart in the invented sheet.",
            inputs=("Invented input passage one.", "Invented input passage two."),
        ),
        _item(
            ACTIN,
            RUN_A,
            3,
            property_in_paper="Filament count",
            organism="mouse",
            value="1,100–2,100",
            unit="",
            kind=ClaimKind.RANGE_OVER_CONDITIONS,
            candidate_kind=CandidateKind.DERIVED_FROM_PUBLISHED,
            quote="Counts ranged from 1,100 to 2,100 across invented conditions.",
            inputs=("Invented published count.",),
        ),
        _item(
            ACTIN,
            RUN_A,
            4,
            property_in_paper="Invented burst length",
            organism="mouse",
            value="10–20",
            unit="s",
            kind=ClaimKind.SINGLE,
            candidate_kind=CandidateKind.MEASURED,
            quote="Bursts lasted 10–20 s in invented recordings.",
        ),
        _item(
            OPTICS,
            RUN_A,
            1,
            property_in_paper="Invented band gap",
            organism="",
            value="3.2",
            unit="eV",
            kind=ClaimKind.SINGLE,
            candidate_kind=CandidateKind.MEASURED,
            quote="The invented crystal had a band gap of 3.2 eV.",
            domain="physics",
        ),
    ]


def run_b() -> list[ReviewItem]:
    """A second extraction of the actin paper, loaded later: its first value differs."""
    return [
        _item(
            ACTIN,
            RUN_B,
            1,
            property_in_paper="F-actin concentration",
            organism="mouse",
            value="500",
            unit="µM",
            kind=ClaimKind.SINGLE,
            candidate_kind=CandidateKind.MEASURED,
            quote="The F-actin concentration was roughly 500 µM in invented cells.",
        ),
    ]


def load(engine, run_id: str, items: list[ReviewItem]) -> None:
    papers = {item.paper.pmcid: item for item in items}
    results = [
        _result(item.paper, run_id, item.claim.fingerprint.scope) for item in papers.values()
    ]
    store.load_run(engine, results, items, question="", run_id=run_id)


def decide(
    engine,
    item_id: str,
    role: str,
    *,
    approved: bool | None,
    issue: str = "",
    model: str | None = None,
) -> None:
    """One decision row, written directly so every field a reviewer fills can carry a marker."""
    with engine.begin() as conn:
        conn.execute(
            insert(store.review_decision),
            {
                "item_id": item_id,
                "reviewer": f"invented-{role.lower()}",
                "chosen_supporting": True,
                "approved": approved,
                "comment": REVIEWER_COMMENT,
                "decided_at": datetime.now(UTC),
                "issue": issue,
                "value_read": VALUE_READ,
                "reviewer_role": role,
                "reviewer_model": model,
            },
        )


def build(path: Path, *, with_run_b: bool = True) -> Path:
    """The standard invented store. Returns its path."""
    engine = store.engine_from_url(f"sqlite:///{path}")
    store.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(store.curated_entry),
            {
                "entry_id": CURATED_ID,
                "property": "Invented cell length",
                "organism": "Escherichia coli",
                "value": 2.0,
                "units": "µm",
                "approximate": False,
                "reference": "Invented reference",
                "pubmed_id": "1",
                "method": "invented microscopy",
                "comments": "",
                "loaded_at": datetime.now(UTC),
            },
        )
    load(engine, RUN_A, run_a())
    a = f"{RUN_A}-{ACTIN.pmcid}"
    # -1: approved by a student and a simulated scientist, objected to by another student.
    decide(engine, f"{a}-1-item", "STUDENT", approved=True)
    decide(engine, f"{a}-1-item", "SCIENTIST", approved=True, model="invented/reviewer")
    decide(engine, f"{a}-1-item", "STUDENT", approved=None, issue=REVIEWER_ISSUE)
    # -2: approved by a model reviewing as itself.
    decide(engine, f"{a}-2-item", "AI", approved=True, model="invented/reviewer")
    # -3: approved by a senior scientist, a person.
    decide(engine, f"{a}-3-item", "SENIOR_SCIENTIST", approved=True)
    # -4: disapproved, and approved by no one.
    decide(engine, f"{a}-4-item", "STUDENT", approved=False)
    # The optics value has no decision at all.
    if with_run_b:
        load(engine, RUN_B, run_b())
    engine.dispose()
    return path


#: The actin paper's bibliographic record, invented, in the shape `add-paper-references` writes
#: (ADR-1750): keys present only where the front matter states them.
ACTIN_CSL = {
    "type": "article-journal",
    "id": "PMC1000001",
    "title": "Invented actin in S. pombe cdc15 mutants",
    "author": [
        {"family": "Inventa", "given": "Ada"},
        {"family": "Fictor", "given": "Ben Carl"},
        {"family": "Madeup", "given": "Cleo"},
    ],
    "container-title": "Journal of Invented Biology",
    "volume": "12",
    "issue": "3",
    "page": "101-109",
    "issued": {"date-parts": [[2009, 5]]},
    "DOI": "10.0000/invented.1",
    "PMID": "1000001",
    "PMCID": "PMC1000001",
}


def with_references(path: Path, records: dict[str, dict]) -> Path:
    """Give the store `review_paper.csl_json`, as `upgrade-store` does, and fill it per PMCID.

    Added here rather than through `numera_validator.store`, whose table on this branch predates the
    column: the ask side must read a store with it and a store without it alike.
    """
    with sqlite3.connect(path) as conn:
        # `numera_validator.store` creates the column since `add-paper-references` (ADR-1750); a
        # store built before it, the case `store_corpus` must also read, lacks it.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(review_paper)")}
        if "csl_json" not in columns:
            conn.execute("ALTER TABLE review_paper ADD COLUMN csl_json TEXT NOT NULL DEFAULT ''")
        for pmcid, record in records.items():
            conn.execute(
                "UPDATE review_paper SET csl_json = ? WHERE pmcid = ?", (json.dumps(record), pmcid)
            )
    return path


def with_property_names(path: Path, names: dict[str, str]) -> Path:
    """Give the store `review_item.property`, as `harden-harvest`'s backfill does, keyed by item id.

    Added by hand for the reason `with_references` gives: this branch's table predates the column.
    """
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(review_item)")}
        if "property" not in columns:  # `feat/property-names` will create it, as above
            conn.execute("ALTER TABLE review_item ADD COLUMN property TEXT NOT NULL DEFAULT ''")
        for item_id, name in names.items():
            conn.execute("UPDATE review_item SET property = ? WHERE item_id = ?", (name, item_id))
    return path
