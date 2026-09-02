"""The canonical record: one cleaned row of the published export.

Twelve of these fields are a contract with `add-ask-agent`, whose loader models
them and ignores every other key — `entry_id`, `property`, `organism`, `units`,
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

    entry_id: int
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

    source_digest: str | None = None
    """First 12 characters of the SHA-256 of the export this record came from.

    The join key to the run's manifest, so a corpus line separated from its
    manifest can still be traced to the file it came from — which matters because
    the export carries no date of its own (ADR-0240).
    """

    range_qualified: bool = False
    """`True` when the source did not state the range as a closed interval, so the
    stored bounds are not the exact measurement they look like.

    A one-sided bound (`<0.001`, `>100`, `≥10`) or an approximation (`~5`, `≈5`).
    2,233 records of the export carry such a marker. The damaging half is the
    one-sided one: `<0.001` stored as [0.001, 0.001] asserts an exact equality
    where the source said *less than*.

    A second field rather than a redefinition of `range_fused`, which means
    something else — that the bounds may come from two different quantities.
    Widening that one would have changed a contract `add-ask-agent` already reads.
    """

    range_one_sided: bool = False
    """`True` when the hedge is a bound: `<0.001`, `>100`, `≥10`. 594 records.

    Which kind of hedge it is decides the words a consumer puts in front of a
    reader -- "8.0 (a bound, not exact)" is not "8.0 (approximate)" -- so the kind
    is a field like the fact. `add-ask-agent` read it out of `parse_flags` by name
    until this field existed, which meant a rename here would have turned it
    silently false there rather than failing.

    Together with `range_approximate` this partitions `range_qualified`: that
    field is true exactly when one of these two is, by construction rather than by
    coincidence.
    """

    range_approximate: bool = False
    """`True` when the hedge is an approximation marker: `~5`, `≈5`, `about 5`.
    1,639 records. See `range_one_sided` for why the kind is its own field."""

    range_fused: bool = False
    """`True` when `range_low`/`range_high` may fuse numbers that do not belong
    to one quantity, so the range must not be presented as a measurement.

    This is the term `add-ask-agent` consumes. It is not derivable from
    `parse_flags` by a naming rule: five of those names begin with `range_` and
    only two concern fusion — `range_plus_minus` and `range_mean_sd_embedded`
    mark *successful* parses, `range_is_link` and `no_scalar` mark rows with no
    scalar at all.
    """
