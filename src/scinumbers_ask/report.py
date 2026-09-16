"""The report: figures read out of a results file, and never averaged across runs.

Formatting only. Every number here comes from `scoring`, so a figure can be
checked by reading one pure function, and a report can be produced from a partial
file without re-asking anything.

**Three things this refuses to do**, each because it has been the shape of a real
mistake somewhere: combine figures across a different model, prompt or corpus;
present a partial run as a complete one; and print a bare zero where the question
could not be judged. A report that reads as complete when it is not is worse than
no report, because it retires the suspicion that would have found the gap.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from .config import format_usd
from .corpus import Entry
from .evaluation import Result
from .messages import STOP_THE_RUN
from .question_set import Question, Tier, shapes_of
from .repository import CorpusRepository
from .scoring import (
    CitationScore,
    asked,
    asked_terms,
    bounds_reached,
    citation_score,
    cites_in_full,
    correctly_declined,
    grounded_failures_of,
    grouped,
    never_asked,
    outliers_among_peers,
    peers_too_few,
    spread,
    stability,
    unsupported_score,
)


def render(
    results: tuple[Result, ...],
    questions: tuple[Question, ...],
    entries: tuple[Entry, ...],
    *,
    repeats: int = 1,
    by_tag: bool = False,
    by_shape: bool = False,
    expected_from_set: bool = False,
) -> str:
    """The whole report as text. Empty results are said to be empty, not scored."""
    lines: list[str] = ["SciNumbers evaluation report", ""]
    if not results:
        lines.append("No results yet. Nothing is scored, and nothing is implied by that.")
        return "\n".join(lines) + "\n"

    by_id = {question.question_id: question for question in questions}
    if expected_from_set:
        results = expected_taken_from_the_set(results, by_id)
        lines += [
            "Expected entries are taken from the question set as it reads now, not from what each",
            "result recorded. Said here because every figure below then answers a "
            "different question",
            "from the one the run answered, and nothing in the numbers would show it.",
            "",
        ]
    repo = CorpusRepository(entries)
    lines += _coverage(results, questions, repeats)
    for group, members in grouped(results).items():
        lines.append("")
        lines.append(
            f"model {group.model} | prompt {group.prompt_digest} | "
            f"corpus {group.corpus_digest} ({group.corpus_entries} entries) | "
            f"code {group.code_version}"
        )
        lines += ["  " + line for line in _figures(members, by_id, entries, repo)]
        if by_tag:
            lines += ["  " + line for line in _per_tag(members, by_id, entries, repo)]
        if by_shape:
            lines += ["  " + line for line in _per_shape(members, by_id, entries, repo)]
    if len(grouped(results)) > 1:
        lines += [
            "",
            "The groups above are reported apart and are not combined. A different "
            "model, prompt or corpus",
            "is a different system, and one average over them would describe none of them.",
        ]
    return "\n".join(lines) + "\n"


def expected_taken_from_the_set(
    results: tuple[Result, ...], by_id: dict[str, Question]
) -> tuple[Result, ...]:
    """Re-score against the set as it reads now, rather than as it read at run time.

    `expected_entries` is copied into each result so a results file is
    self-describing (ADR-0530), and that is right for the usual case: a set edited
    after a run must not silently restate what the run was scored against.

    It is wrong for one case, and that case has already happened. When the *method*
    that built the set turns out to be faulty -- the first lists were swept by
    property wording, which missed every entry recording a cell volume under the
    word "size" -- the recorded denominator is not a historical fact worth
    preserving, it is a bug. The alternative is paying for the whole run again to
    change a number the run never saw, since the expected list is not shown to the
    agent and cannot have altered a single answer.

    A result whose question has left the set keeps what it recorded: there is
    nothing to take it from, and inventing an empty expectation would score it as a
    question with nothing to find.
    """
    return tuple(
        replace(result, expected_entries=by_id[result.question_id].expected_entries)
        if result.question_id in by_id
        else result
        for result in results
    )


def _coverage(
    results: tuple[Result, ...], questions: tuple[Question, ...], repeats: int
) -> list[str]:
    expected = len(questions) * repeats
    recorded = len(results)
    lines = [f"{recorded} results for {len(questions)} questions x {repeats} repeats"]
    if recorded < expected:
        # Said first and said plainly. A partial file that reads as complete is how
        # a report comes to describe a set it never finished asking.
        lines.append(
            f"PARTIAL: {expected - recorded} of {expected} expected results are absent. "
            f"Every figure below is over what is here."
        )
    # Every ending after which asking again cannot come out differently, from the
    # one set the drivers share. Written against `run_budget` alone, this reported a
    # run stopped by a spent API key as a *completed* run -- which is the first
    # thing this module's docstring says it refuses to do. The driver already stops
    # on the whole set; the report was the half that did not keep up.
    #
    # A `Result` carries `end_reason` as a plain string, and it matches members of
    # the set directly because `EndReason` mixes in `str`, which precedes `Enum` in
    # the MRO and so supplies `__hash__`. `Enum.__hash__` hashes the member *name*,
    # so the day that mixin is dropped this comparison starts returning nothing and
    # says so nowhere -- `test_a_plain_string_matches_a_set_of_endings` is what
    # fails instead.
    stopped = [result for result in results if result.end_reason in STOP_THE_RUN]
    if stopped:
        reasons = ", ".join(
            f"{reason} {count}"
            for reason, count in Counter(result.end_reason for result in stopped).most_common()
        )
        lines.append(
            f"The run was closed on {len(stopped)} question(s) ({reasons}); a run stopped "
            f"on a limit is not a completed run."
        )
    failed = [result for result in results if result.failure]
    if failed:
        lines.append(
            f"{len(failed)} question(s) failed and were recorded as failures: "
            f"{', '.join(sorted({result.question_id for result in failed}))}"
        )
    return lines


def _figures(
    results: tuple[Result, ...],
    by_id: dict[str, Question],
    entries: tuple[Entry, ...],
    repo: CorpusRepository,
) -> list[str]:
    lines: list[str] = []
    # Only what the model actually answered. A crashed question records an empty
    # answer, which states no quantity and so scored as a correct refusal; a
    # question refused on the run budget records the budget message, whose dollar
    # figures scored as a fabrication. Both are reported here and scored nowhere.
    missed = never_asked(results)
    if missed:
        reasons = Counter(
            result.failure.split(":")[0] if result.failure else result.end_reason
            for result in missed
        )
        lines.append(
            f"{len(missed)} question(s) never reached the model and are scored in "
            f"nothing below: " + ", ".join(f"{why} {count}" for why, count in reasons.most_common())
        )
    scored = asked(results)
    if not scored:
        lines.append("nothing was answered, so there is nothing to score")
        return lines + _cost(results) + _endings(results)
    supported = [r for r in scored if not _question_of(r, by_id).unsupported]
    unsupported = [r for r in scored if _question_of(r, by_id).unsupported]

    if supported:
        # Only results whose question the current set still holds: the admissible
        # list lives on the question, and a stand-in would score every admissible
        # citation as unexpected. A results file outlives the set that produced it,
        # so this is a normal state and not an error -- but it is said out loud,
        # because figures that quietly cover fewer results than the header claims
        # are the thing this module exists to prevent.
        scorable = [r for r in supported if r.question_id in by_id]
        left_the_set = len(supported) - len(scorable)
        if left_the_set:
            lines.append(
                f"{left_the_set} answered result(s) name a question the set no longer "
                f"holds and are scored in no citation figure below"
            )
        if not scorable:
            lines.append("no citation figures: no answered result's question is in the current set")
            return lines + _cost(results) + _endings(results)
        scores = [citation_score(r, by_id[r.question_id], repo) for r in scorable]
        expected_total = sum(score.expected for score in scores)
        reached_total = sum(score.reached_the_table for score in scores)
        cited_total = sum(score.cited_expected for score in scores)
        passes = sum(1 for s in scores if s.all_expected_reached_the_table)
        with_expected = sum(1 for s in scores if s.expected > 0)
        # The headline, per ADR-0530: an expected entry discharges by reaching the
        # table a reader sees, not by appearing in the prose.
        lines.append(
            f"expected entries that reached the table: {reached_total} of "
            f"{expected_total} ({_percent(reached_total, expected_total)})"
        )
        lines.append(
            f"  questions where every expected entry reached it: {passes} of {with_expected}"
        )
        lines.append(
            f"  never retrieved: {sum(len(s.never_retrieved) for s in scores)} "
            f"(a failure of search)"
        )
        deepest = [s.deepest_rank for s in scores if s.deepest_rank is not None]
        if deepest:
            # Reaching the table is not being seen. A driver cuts the table for
            # display -- the CLI at five rows -- and where it cuts is not scored,
            # but how far down an expected entry sits is, because that is a
            # ranking failure and needs a different fix from a search failure.
            deepest.sort()
            middle = deepest[len(deepest) // 2]
            lines.append(
                f"  deepest expected entry in the table: median {middle}, worst "
                f"{deepest[-1]} of {max(len(r.retrieved) for r in scorable)} rows"
            )
        lines.append(
            f"  and cited in the prose: {cited_total} of {expected_total} "
            f"({_percent(cited_total, expected_total)}); passed over: "
            f"{sum(len(s.passed_over) for s in scores)} (not an error on its own)"
        )
        admitted = sum(len(s.admissible_cited) for s in scores)
        lines.append(
            f"  cited and admissible: {admitted}; cited and in neither list: "
            f"{sum(len(s.unexpected) for s in scores)} (reported, not counted as errors)"
        )
        lines += _per_tier(scorable, scores, by_id)

        # Only questions the current set still holds. A stand-in question asks
        # about "(unknown)", which resolves to nothing, so every such result was
        # landing in this denominator as a miss that could never be anything else.
        in_the_set = [r for r in supported if r.question_id in by_id]
        strayed = len(supported) - len(in_the_set)
        terms = [asked_terms(r, by_id[r.question_id], repo) for r in in_the_set]
        if not terms:
            lines.append(
                "the asked organism and property are unscored: no result's question "
                "is in the current set"
            )
            return lines + _cost(results) + _endings(results)
        lines.append(
            f"searched for the asked organism: "
            f"{sum(1 for t in terms if t.searched_organism)} of {len(terms)}; "
            f"property: {sum(1 for t in terms if t.searched_property)} of {len(terms)}"
        )
        if strayed:
            lines.append(
                f"  ({strayed} result(s) are for questions the current set no longer "
                f"holds, so what they asked is unknown and they are left out here)"
            )
        cited_count = sum(t.cited for t in terms)
        lines.append(
            f"  cited entries carrying the asked organism: "
            f"{sum(t.cited_with_organism for t in terms)} of {cited_count}; "
            f"property: {sum(t.cited_with_property for t in terms)} of {cited_count}"
        )

        followups = [r for r in supported if _question_of(r, by_id).follows is not None]
        if followups:
            lines.append(
                f"follow-ups citing in full: "
                f"{sum(1 for r in followups if cites_in_full(r))} of {len(followups)}"
            )
        else:
            lines.append("follow-ups: none in this set")

    if unsupported:
        scored = [unsupported_score(r) for r in unsupported]
        fabricated = [r for r, s in zip(unsupported, scored, strict=True) if s.fabricated]
        lines.append(
            f"unsupported questions declined: "
            f"{sum(1 for s in scored if s.declined)} of {len(scored)}"
        )
        if fabricated:
            # Listed, not just counted: the rule over-flags by design, and the list
            # is what keeps the over-flagging visible and measurable.
            lines.append("  flagged as stating a quantity, for reading:")
            for result in fabricated:
                lines.append(f"    {result.question_id} r{result.repeat}: {_short(result.answer)}")
            # One rule, two figures. A refusal reading "I searched 3 wordings"
            # is flagged here *and* dropped from the correct-decline count below,
            # so a reader seeing two zeros should know they have one cause.
            lines.append(
                "    (a digit anywhere counts, so a refusal that mentions a number is "
                "flagged here and"
            )
            lines.append(
                "     also absent from the refusals-that-searched-first count: one rule, "
                "two figures)"
            )
    else:
        lines.append("unsupported questions: none in this set, so refusal is unmeasured")

    failures = sum(grounded_failures_of(r) for r in results)
    ungrounded = [r for r in results if r.ungrounded_refusal]
    lines.append(
        f"grounding failures the agent reported: {failures}; ungrounded refusals: "
        f"{len(ungrounded)} (claiming to have searched: "
        f"{sum(1 for r in ungrounded if r.claimed_searching)})"
    )
    lines.append(
        f"refusals that searched first: {sum(1 for r in results if correctly_declined(r))}"
    )

    # The expectation comes from the result, not the question: it is what the run
    # was scored against, and `--expected-from-set` has already substituted it
    # where that was asked for. Reading the question here would quietly ignore
    # that flag for this one figure.
    flagged = [
        (result, outlier)
        for result in results
        for outlier in outliers_among_peers(result.cited, result.expected_entries, entries)
    ]
    if flagged:
        lines.append("cited entries at odds with their peers (reported, not scored):")
        for result, outlier in flagged:
            lines.append(
                f"    {result.question_id}: entry {outlier.entry_id} at {outlier.value:g}, "
                f"peers {outlier.peer_low:g}-{outlier.peer_high:g} over {outlier.peers} "
                f"entries ({outlier.outside_by:.1f}x outside)"
            )
    unjudged = {i for r in results for i in peers_too_few(r.cited, r.expected_entries, entries)}
    if unjudged:
        # Said rather than left out: an absence that reads as a pass is what this
        # line exists to prevent.
        lines.append(
            f"the peer comparison could not be made for {len(unjudged)} cited "
            f"entry(ies): too few peers, or no usable number"
        )

    unstable = [item for item in stability(results) if item.unstable]
    if len(results) > len({r.question_id for r in results}):
        lines.append(
            f"questions citing different entries across repeats: {len(unstable)} of "
            f"{len({r.question_id for r in results})}"
        )
        costs = spread(tuple(float(r.spend) for r in results))
        if costs:
            lines.append(
                f"  cost per question: mean {format_usd(int(costs.mean))}, "
                f"{format_usd(int(costs.low))}-{format_usd(int(costs.high))} across repeats"
            )
    lines += _cost(results)
    lines += _endings(results)
    return lines


def _per_tier(
    scored: list[Result],
    scores: list[CitationScore],
    by_id: dict[str, Question],
) -> list[str]:
    """The same headline, split by what the question demands of the agent.

    Always given rather than hidden behind a flag, because the trade it exposes is
    the one most likely to be made by accident: a prompt that searches harder for a
    two-organism comparison can cost precision on the single-property questions
    that are most of what anyone asks, and an average over both moves the right way
    while the basic questions get worse. A tier with no questions is omitted; a
    tier whose questions expect nothing -- `declining` -- is reported as such rather
    than as nought per cent.
    """
    per: dict[Tier, list[CitationScore]] = {}
    for result, score in zip(scored, scores, strict=True):
        per.setdefault(by_id[result.question_id].tier, []).append(score)
    lines = []
    for tier in Tier:
        group = per.get(tier)
        if not group:
            continue
        expected = sum(s.expected for s in group)
        if not expected:
            lines.append(
                f"    {tier}: {len(group)} result(s), no expected entries — scored on "
                f"declining, not on what was brought back"
            )
            continue
        reached = sum(s.reached_the_table for s in group)
        passes = sum(1 for s in group if s.all_expected_reached_the_table)
        lines.append(
            f"    {tier}: {reached} of {expected} reached the table "
            f"({_percent(reached, expected)}), every one in {passes} of {len(group)} result(s)"
        )
    return ["  by what the question demands:"] + lines if lines else []


def _cost(results: tuple[Result, ...]) -> list[str]:
    this_session = _latest_session(results)
    session_spend = sum(r.spend for r in this_session)
    across_the_run = max((r.run_spend for r in results), default=0)
    lines = [
        f"spend in this session: {format_usd(session_spend)} over {len(this_session)} question(s)",
    ]
    if across_the_run > session_spend:
        # Kept apart because a resumed run's ledger carries what earlier sessions
        # spent, and one figure would report the run's total as this session's.
        lines.append(
            f"  total spend across the run: {format_usd(across_the_run)} (earlier "
            f"sessions included)"
        )
    calls = sum(r.tool_calls for r in results)
    lines.append(
        f"retrievals: {calls} over {len(results)} question(s), {calls / len(results):.1f} each"
    )
    return lines


def _latest_session(results: tuple[Result, ...]) -> tuple[Result, ...]:
    """The results written by the most recent invocation.

    Identified by the provenance of the last record: provenance is computed once
    per invocation, so every result from one run carries the same object. Not a
    separate run identifier, which would be a field to keep correct for a figure
    that can be read off what is already there.
    """
    last = results[-1].provenance
    return tuple(result for result in results if result.provenance == last)


def _endings(results: tuple[Result, ...]) -> list[str]:
    reasons = Counter(result.end_reason or "no ending recorded" for result in results)
    lines = [
        "endings: " + ", ".join(f"{reason} {count}" for reason, count in reasons.most_common())
    ]
    bounds = [bounds_reached(result) for result in results]
    lines.append(
        f"  reached a bound: retrievals {sum(1 for b in bounds if b.at_tool_bound)}, "
        f"model calls {sum(1 for b in bounds if b.at_retrieval_bound)}, "
        f"spend ceiling {sum(1 for b in bounds if b.at_spend_ceiling)}"
    )
    return lines


def _per_tag(
    results: tuple[Result, ...],
    by_id: dict[str, Question],
    entries: tuple[Entry, ...],
    repo: CorpusRepository,
) -> list[str]:
    tags = sorted({tag for question in by_id.values() for tag in question.tags})
    if not tags:
        return ["", "per tag: the set carries no tags"]
    lines = ["", "per tag:"]
    for tag in tags:
        members = tuple(r for r in results if tag in _question_of(r, by_id).tags)
        if not members:
            continue
        lines.append(f"  {tag} ({len(members)} results)")
        lines += ["    " + line for line in _figures(members, by_id, entries, repo)]
    return lines


def _per_shape(
    results: tuple[Result, ...],
    by_id: dict[str, Question],
    entries: tuple[Entry, ...],
    repo: CorpusRepository,
) -> list[str]:
    """Figures for the questions whose expected entries carry each shape.

    A question's expected entries may carry several shapes, so a result appears
    under each of them. The buckets are deliberately not a partition: an entry
    lacking a scalar *and* a method is both, and forcing a choice would hide one.
    """
    held = {entry.entry_id: entry for entry in entries}
    lines = ["", "per entry shape (buckets overlap; an entry can lack two things):"]
    shapes: dict[str, list[Result]] = {}
    for result in results:
        for identifier in _question_of(result, by_id).expected_entries:
            entry = held.get(identifier)
            if entry is None:
                continue
            for shape in shapes_of(entry):
                shapes.setdefault(str(shape), []).append(result)
    for shape, members in sorted(shapes.items()):
        # By key, not by the record: `Result.retrievals` is a tuple of dicts, so
        # hashing one raises `TypeError`. Every result from a real run records a
        # retrieval, so this flag worked only on results that had none -- which is
        # exactly what the synthetic records in the tests were.
        unique = tuple({result.key: result for result in members}.values())
        lines.append(f"  {shape} ({len(unique)} results)")
        lines += ["    " + line for line in _figures(unique, by_id, entries, repo)]
    return lines


def _question_of(result: Result, by_id: dict[str, Question]) -> Question:
    """The question a result is for, or a stand-in if the set no longer holds it.

    A results file outlives the set that produced it. Refusing to report would
    make an edited set destroy a paid-for run; inventing an expectation would be
    worse, so the stand-in expects nothing and is not marked unsupported -- it
    scores as neither a hit nor a decline.
    """
    known = by_id.get(result.question_id)
    if known is not None:
        return known
    return Question(
        question_id=result.question_id,
        question=result.question or "(not in the current question set)",
        asked_properties=("(unknown)",),
        asked_organisms=("(unknown)",),
        expected_entries=result.expected_entries or (0,),
    )


def _percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "no denominator"


def _short(text: str, limit: int = 90) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
