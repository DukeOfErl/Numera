"""What a run did, and what it could not interpret.

Structural accounting of the *dataset*, not of an answer: are the identifiers
unique, what failed to parse, how much of the corpus carries a caveat. Nothing
here drops a row — it counts, and the counts are stated even when zero.

A zero is the interesting case. `injected_html_removed` once reported zero across
a corpus where 71% of records were contaminated, because its condition was
evaluated before the unescape that created the markup and so could never hold.
Nothing was red; the corpus simply said the problem did not occur. So a report
that omits its zeroes is worse than one that states them, and a zero is a claim
that needs an argument from the code before anyone believes it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from bionumbers_ingest.model import BioNumberRecord


@dataclass
class RunReport:
    rows_read: int = 0
    rows_skipped_non_data: int = 0
    records_written: int = 0
    duplicate_bnids: list[int] = field(default_factory=list)
    flag_counts: dict[str, int] = field(default_factory=dict)
    range_fused_count: int = 0
    range_qualified_count: int = 0
    link_records: int = 0
    records_with_no_scalar: int = 0
    row_limit: int | None = None

    @property
    def rows_accounted_for(self) -> bool:
        """Every row read became a record or was counted as skipped."""
        return self.records_written + self.rows_skipped_non_data == self.rows_read

    def format(self) -> str:
        lines = [
            "BioNumbers ingestion report",
            f"  rows read:              {self.rows_read}",
            f"  records written:        {self.records_written}",
            f"  rows skipped non-data:  {self.rows_skipped_non_data}",
            f"  duplicate identifiers:  {len(self.duplicate_bnids)}"
            + (f" {self.duplicate_bnids[:10]}" if self.duplicate_bnids else ""),
            f"  records carrying a link:{self.link_records:>6}",
            f"  records with no scalar: {self.records_with_no_scalar}",
            f"  ranges that may fuse two quantities (range_fused):  {self.range_fused_count}",
            f"  ranges the source hedged (range_qualified):        {self.range_qualified_count}",
        ]
        if self.row_limit:
            lines.append(f"  ROW LIMIT APPLIED:      {self.row_limit} — this corpus is a sample")
        lines.append("  parse flags:")
        if self.flag_counts:
            for flag, n in sorted(self.flag_counts.items(), key=lambda kv: (-kv[1], kv[0])):
                lines.append(f"    {flag}: {n}")
        else:
            lines.append("    (none raised)")
        if not self.rows_accounted_for:
            lines.append(
                f"  WARNING: {self.rows_read} rows read but "
                f"{self.records_written} written + {self.rows_skipped_non_data} skipped"
            )
        return "\n".join(lines)


def report_for(
    records: list[BioNumberRecord],
    rows_read: int,
    rows_skipped_non_data: int,
    row_limit: int | None = None,
) -> RunReport:
    """Count what the run produced. Reports zeroes rather than omitting them."""
    seen: Counter[int] = Counter(r.entry_id for r in records)
    flags: Counter[str] = Counter()
    for record in records:
        flags.update(record.parse_flags)
    return RunReport(
        rows_read=rows_read,
        rows_skipped_non_data=rows_skipped_non_data,
        records_written=len(records),
        duplicate_bnids=sorted(b for b, n in seen.items() if n > 1),
        flag_counts=dict(flags),
        range_fused_count=sum(1 for r in records if r.range_fused),
        range_qualified_count=sum(1 for r in records if r.range_qualified),
        # Counted from the flag, not from `table_link`. A "Table link" cell whose
        # URL has no scheme raises the flag but yields no URL, and counting the two
        # differently printed `range_is_link: 1` beside `records carrying a link: 0`
        # — two counts of the same thing, disagreeing, with nothing explaining why.
        link_records=sum(1 for r in records if "range_is_link" in r.parse_flags),
        records_with_no_scalar=sum(1 for r in records if r.value is None and r.range_low is None),
        row_limit=row_limit,
    )
