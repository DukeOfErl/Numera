"""The corpus tools the agent is given, and nothing else.

Descriptions say *when* to reach for each tool, not only what it does: a
description that states only its function leaves the model guessing at the
trigger, which is where tool-use accuracy is won or lost.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.tools import StructuredTool

from .bionumbers import rewrite
from .citations import format_citation
from .events import Retrieval
from .repository import DEFAULT_LIMIT, CorpusRepository
from .trace import QuestionTrace
from .units import dimensions_of

Emit = Callable[[Retrieval], None]


class ToolBudget:
    """How many retrievals one question may make.

    Enforced here rather than by the model-call limit, which does not bound it: a
    model batches several tool calls into one hop, so twelve model calls bought
    twenty-nine retrievals across seventeen searches in one observed question --
    $0.27, a fifth of the run budget, with cost the only thing that stopped it.

    Exhaustion is returned to the model as a tool result rather than raised. The
    model then answers with what it has and says it is incomplete, which is worth
    more to a reader than a question killed mid-search: what was established so far
    is still presented with its citations (`grounded-answering`).
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def spend(self) -> bool:
        """Take one call, or report that there is none left."""
        if self.used >= self.limit:
            return False
        self.used += 1
        return True

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit


EXHAUSTED = (
    "No retrieval calls remain for this question. Answer now from the entries you "
    "have already retrieved, cite them, and say plainly that the answer may be "
    "incomplete because the search was cut short. Do not state any quantity you "
    "have not already retrieved."
)


def build_tools(
    repo: CorpusRepository,
    trace: QuestionTrace,
    emit: Emit,
    budget: ToolBudget | None = None,
) -> list[StructuredTool]:
    """Bind the repository to a question's trace, event sink and retrieval budget."""

    def afford(tool: str, detail: dict) -> bool:
        """Whether this call may run, recording the refusal where it does not.

        Emitted as a Retrieval so a declined call still appears in the progress
        the reader sees and in the tool count: a call the model made and was
        refused is part of what happened to the question.
        """
        if budget is None or budget.spend():
            return True
        trace.record("tools.budget_exhausted", tool=tool, limit=budget.limit)
        emit(
            Retrieval(
                question_id=trace.question_id,
                tool=tool,
                detail={**detail, "declined": "no retrieval calls left"},
            )
        )
        return False

    def search_entries(
        property: str | None = None,
        organism: str | None = None,
        keyword: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> str:
        if not afford(
            "search_entries", {"property": property, "organism": organism, "keyword": keyword}
        ):
            return EXHAUSTED
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
                    "entry_ids": tuple(row.entry_id for row in result.rows),
                },
            )
        )
        if not result.rows:
            return (
                "No entries matched. The corpus may use different wording -- "
                "call list_values before concluding it has nothing on the topic."
            )
        lines = [
            f"{row.entry_id}\t{row.property}\t{row.organism}\t{row.value} {row.units}".rstrip()
            for row in result.rows
        ]
        header = (
            f"{result.total_matched} entries matched; showing {len(result.rows)}."
            if result.truncated
            else f"{result.total_matched} entries matched; all shown."
        )
        out = [header, "entry_id\tproperty\torganism\tvalue", *lines]
        spanned = dimensions_of([row.units for row in result.rows])
        if len(spanned) > 1:
            # Said here rather than left to the system prompt. The prompt's rule
            # about not presenting a mass and a count as one range is a paragraph
            # read before the question; this is the same rule at the moment of
            # choosing, against the rows it applies to.
            out.append(
                f"NOTE: these rows measure {len(spanned)} different kinds of quantity "
                f"({', '.join(spanned)}). Values of different kinds are not "
                "alternative estimates of one quantity and must not be presented as "
                "a range or an average."
            )
        return "\n".join(out)

    def get_entry(entry_id: int) -> str:
        if not afford("get_entry", {"entry_id": entry_id}):
            return EXHAUSTED
        found = repo.get(entry_id, trace=trace)
        emit(
            Retrieval(
                question_id=trace.question_id,
                tool="get_entry",
                detail={"entry_id": entry_id, "found": found is not None},
            )
        )
        if found is None:
            return f"No entry {entry_id}."
        e = found.entry
        parts = [
            f"entry_id: {e.entry_id}",
            f"property: {e.property}",
            f"organism: {e.organism}",
            f"value: {e.value_display} {e.units}".rstrip(),
            f"reference: {e.reference}",
        ]
        # Said to the model, not only drawn in the table. The prose is what people
        # read, and a model that does not know will state a hedged or fused range as
        # a measurement while only the table contradicts it -- which is how "<8"
        # reached a reader as "is 8.0 mg/L" with both surfaces agreeing.
        #
        # Written as an instruction rather than a field name: `range_qualified: true`
        # is a flag the model may or may not act on, where a sentence saying what the
        # source did claim leaves less room to round it away.
        for caveat in _caveats(e):
            parts.append(f"caution: {caveat}")
        if e.reference_pubmed_id:
            parts.append(f"pubmed: {e.reference_pubmed_id}")
        # The source's own cross-references, restated in the notation the model is
        # asked to write. An entry's prose saying "See BNID 102065" is the likeliest
        # reason for a model to answer in a form the parser was not told to expect,
        # and it is the corpus that puts it there. A rendering only: the stored entry
        # and everything shown to a person keep the source's words (ADR-0420).
        if e.measurement_method:
            parts.append(f"method: {rewrite(e.measurement_method, format_citation)}")
        if e.comments:
            parts.append(f"comments: {rewrite(e.comments, format_citation)}")
        if found.cited_ids:
            # Bare numbers here were citations in no notation at all -- unusable by a
            # model told to cite in one, and unparsable if it copied them.
            parts.append(
                "cites: " + ", ".join(format_citation(i) for i in found.cited_ids)
            )
        return "\n".join(parts)

    def _caveats(e) -> list[str]:
        """What the source did not claim about this value, in words the model reads.

        Never repairs and never withholds: the entry is still returned and still
        citable, because a citation claims provenance and that stays true of a
        marked entry. What changes is that the model cannot state the number as a
        measurement without contradicting a line it was given.
        """
        out = []
        if e.range_approximate:
            out.append(
                "the source gave this as an approximation, not an exact value -- report "
                "it as approximate; do not state it as a measured quantity"
            )
        elif e.range_one_sided:
            out.append(
                "the source stated a bound (a less-than or greater-than), not a value -- "
                "say that the source gives a bound; do not report this number as a "
                "measured quantity"
            )
        elif e.range_qualified:
            out.append(
                "the source did not state this as an exact value -- do not report this "
                "number as a measured quantity"
            )
        if e.range_fused:
            out.append(
                "the two bounds of this range may have been taken from different "
                "quantities in the source, so the range may not be a real interval"
            )
        if e.spans_implausibly:
            out.append(
                "these bounds span more than a millionfold, which no single measurement "
                "does -- treat the range as unreliable"
            )
        return out

    def list_values(field: str, contains: str = "") -> str:
        if not afford("list_values", {"field": field, "contains": contains}):
            return EXHAUSTED
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
                "Read one entry in full, by its entry_id. "
                "Call this for every entry you intend to cite, "
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
