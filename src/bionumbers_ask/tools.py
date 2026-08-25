"""The corpus tools the agent is given, and nothing else.

Descriptions say *when* to reach for each tool, not only what it does: a
description that states only its function leaves the model guessing at the
trigger, which is where tool-use accuracy is won or lost.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.tools import StructuredTool

from .events import Retrieval
from .repository import DEFAULT_LIMIT, CorpusRepository
from .trace import QuestionTrace

Emit = Callable[[Retrieval], None]


def build_tools(repo: CorpusRepository, trace: QuestionTrace, emit: Emit) -> list[StructuredTool]:
    """Bind the repository to a question's trace and event sink."""

    def search_entries(
        property: str | None = None,
        organism: str | None = None,
        keyword: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> str:
        result = repo.search(
            property=property, organism=organism, keyword=keyword, limit=limit, trace=trace
        )
        emit(
            Retrieval(
                question_id=trace.question_id,
                tool="search_entries",
                detail={
                    "property": property,
                    "organism": organism,
                    "keyword": keyword,
                    "matched": result.total_matched,
                    "returned": len(result.rows),
                    # So a citation can be checked against what the agent was
                    # actually shown, and a driver can table these entries without
                    # asking the corpus a second question.
                    "bnids": tuple(row.bnid for row in result.rows),
                },
            )
        )
        if not result.rows:
            return (
                "No entries matched. The corpus may use different wording -- "
                "call list_values before concluding it has nothing on the topic."
            )
        lines = [
            f"{row.bnid}\t{row.property}\t{row.organism}\t{row.value} {row.units}".rstrip()
            for row in result.rows
        ]
        header = (
            f"{result.total_matched} entries matched; showing {len(result.rows)}."
            if result.truncated
            else f"{result.total_matched} entries matched; all shown."
        )
        return "\n".join([header, "bnid\tproperty\torganism\tvalue", *lines])

    def get_entry(bnid: int) -> str:
        found = repo.get(bnid, trace=trace)
        emit(
            Retrieval(
                question_id=trace.question_id,
                tool="get_entry",
                detail={"bnid": bnid, "found": found is not None},
            )
        )
        if found is None:
            return f"No entry {bnid}."
        e = found.entry
        parts = [
            f"bnid: {e.bnid}",
            f"property: {e.property}",
            f"organism: {e.organism}",
            f"value: {e.value_display} {e.units}".rstrip(),
            f"reference: {e.reference}",
        ]
        if e.reference_pubmed_id:
            parts.append(f"pubmed: {e.reference_pubmed_id}")
        if e.measurement_method:
            parts.append(f"method: {e.measurement_method}")
        if e.comments:
            parts.append(f"comments: {e.comments}")
        if found.cited_bnids:
            parts.append("cites: " + ", ".join(str(i) for i in found.cited_bnids))
        return "\n".join(parts)

    def list_values(field: str, contains: str = "") -> str:
        try:
            values = repo.vocabulary(field, contains, limit=20, trace=trace)
        except ValueError as exc:
            # Emitted before returning: a call that happened must appear in the
            # progress events and the tool count, whether or not it succeeded.
            emit(
                Retrieval(
                    question_id=trace.question_id,
                    tool="list_values",
                    detail={"field": field, "contains": contains, "rejected": True},
                )
            )
            trace.record("vocabulary.rejected", field=field)
            return str(exc)
        emit(
            Retrieval(
                question_id=trace.question_id,
                tool="list_values",
                detail={"field": field, "contains": contains, "found": len(values)},
            )
        )
        if not values:
            return f"No {field} values contain {contains!r}. The corpus has nothing under that wording."
        return "\n".join(f"{value}\t{count} entries" for value, count in values)

    return [
        StructuredTool.from_function(
            func=search_entries,
            name="search_entries",
            description=(
                "Find candidate entries. Call this first for any question about a quantity. "
                "Matching is case-insensitive on substrings, so a partial organism or property "
                "works. Returns one compact row per entry plus the total that matched -- read the "
                "total, because the rows are capped and may be a fraction of what exists. Rows do "
                "not contain conditions, methods or references; use get_entry for those."
            ),
        ),
        StructuredTool.from_function(
            func=get_entry,
            name="get_entry",
            description=(
                "Read one entry in full, by its bnid. Call this for every entry you intend to cite, "
                "and whenever you need the conditions, measurement method, reference or "
                "cross-references behind a value. An entry may cite others; those are worth "
                "following when they bear on the question."
            ),
        ),
        StructuredTool.from_function(
            func=list_values,
            name="list_values",
            description=(
                "List the organism or property values the corpus actually stores, optionally "
                "filtered by a fragment. Call this when a search returns nothing, to tell a topic "
                "the corpus does not cover from one it stores under different wording. "
                "field must be 'organism' or 'property'."
            ),
        ),
    ]
