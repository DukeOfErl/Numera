"""The canonical record: one cleaned row of the published export.

Twelve of these fields are a contract with `add-ask-agent`, whose loader models
them and ignores every other key — `bnid`, `property`, `organism`, `units`,
`value`, `range_low`, `range_high`, `reference`, `reference_pubmed_id`,
`measurement_method`, `comments`, `keywords`. The scalars are typed
number-or-absent so an empty string cannot be constructed: the consumer coerces
`""` to `None` for scalars but `""` is not `None`, so an emitted `""` would
satisfy its has-a-value branch and blank out every range-only entry.

`range_fused` is the other contract term, and it is a field rather than a rule
over `parse_flags` for a measured reason — see ADR-0230 and `design.md`
decision 9.
"""

from __future__ import annotations

from pydantic import BaseModel

#: The export's 14 columns, in order, as `clean_row` expects to find them.
#:
#: Cleaning reads fields by name, so a renamed column is invisible to it: rename
#: the identifier column and every row fails the is-it-data test, producing an
#: empty corpus from a run that reports no error; rename any other and that field
#: is `None` on every record with nothing flagged. Pass this to `iter_rows` as
#: `expect_headers` and a rename becomes a failure instead of a silent one.
EXPECTED_HEADERS = (
    "bion_id",
    "Properties",
    "Organism",
    "Value",
    "Range",
    "Units",
    "Reference",
    "Reference PubMed ID",
    "Primary Source",
    "Primary Source PubMed ID",
    "Measurement Method",
    "Comments",
    "Entered By",
    "Keywords",
)


class BioNumberRecord(BaseModel):
    """One cleaned BioNumbers row.

    Numeric content may live in `value`, in `range_low`/`range_high`, or nowhere
    at all (a `table_link` row that stands in for a dataset). `parse_flags`
    records what happened during cleaning so the run report and any downstream
    reader can reason about it.
    """

    bnid: int
    property: str | None = None
    organism: str | None = None
    value: float | None = None

    range_raw: str | None = None
    """The source range cell, apostrophe removed — **not** the string the bounds
    were computed from.

    For a link-carrying row this still contains the URL, and that escaped
    filename holds digits an extractor reads as measurements. Recomputing
    anything from this field must strip the link first; `table_link` carries the
    URL separately, so nothing is lost by leaving it here. Measuring the
    fused-range flag against this field rather than against the parse is what
    made two branches report 1,716 and 1,222 for the same population.
    """

    range_low: float | None = None
    range_high: float | None = None
    table_link: str | None = None
    units: str | None = None
    reference: str | None = None
    reference_pubmed_id: str | None = None
    primary_source: str | None = None
    primary_source_pubmed_id: str | None = None
    measurement_method: str | None = None
    comments: str | None = None
    entered_by: str | None = None
    keywords: list[str] = []

    parse_flags: list[str] = []
    """Cleaning's own reporting vocabulary. Internal: names may be renamed,
    split, merged or dropped. Consumers read `range_fused`, never these."""

    range_fused: bool = False
    """`True` when `range_low`/`range_high` may fuse numbers that do not belong
    to one quantity, so the range must not be presented as a measurement.

    This is the term `add-ask-agent` consumes. It is not derivable from
    `parse_flags` by a naming rule: five of those names begin with `range_` and
    only two concern fusion — `range_plus_minus` and `range_mean_sd_embedded`
    mark *successful* parses, `range_is_link` and `no_scalar` mark rows with no
    scalar at all.
    """
