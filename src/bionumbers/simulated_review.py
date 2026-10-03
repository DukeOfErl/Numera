"""Models standing in for reviewers: the review task, answered unattended (ADR-0960).

Finding people to review takes longer than the demonstration has, so each rung of the trust ladder
is played by a model. That makes this a **second driver over the review task**, beside
`review_app.py`: it reads one item's screen, answers the same two questions, and writes through the
same store. It is not a step of the extraction pipeline and nothing upstream reads what it writes.

Three things it holds to, each because the alternative would make the dataset say something false:

- **A model sees what a person sees, and nothing more.** The screen is built from
  `bionumbers.review`'s own functions -- the texts in the page's order, the page's condition rows --
  so nothing here reads the second text's kind or type, and no reviewer is shown another's
  decision. Every item has a known right answer, which is what lets a run report how often a model
  picked the supporting text; a screen that leaked the kind would make that figure worthless.
- **One instruction for every role.** A role is a label on the model that plays it, never a
  persona: telling a model to answer "as a student" asks it to invent a student's mistakes, and a
  disagreement manufactured that way is not a finding. Where reviewers contradict each other here,
  two models read the same screen differently.
- **Every row says a model wrote it.** `reviewer_model` is set on each decision and the reviewer's
  name begins `simulated-`, so no query can mistake these for people.

Which items a role reviews is drawn from a hash of the role and the item id (`assigned`): fixed
across runs, independent between roles, so the subsets overlap by chance and an entry can carry
several ratings or none.

This module reaches `bionumbers.review`, which imports the ask app's door, so importing it needs
the `ask` extra as the review page does. `cli` therefore imports it inside its one command.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from bionumbers import review, store
from bionumbers.extraction import ProviderRefused
from bionumbers.records import Frozen, ReviewerRole, ReviewItem, SecondTextKind, TableView
from bionumbers.spend import (
    PRICES,
    Ceiling,
    CeilingReached,
    Ledger,
    Unpriceable,
    cost,
    projected_cost,
)

#: Enough for an answer and for a reasoning model's thinking before it; the answer itself is
#: three fields. Priced in full by the projection, so it is also most of the per-item ceiling.
MAX_OUTPUT_TOKENS = 2000

#: The two bounds of a simulated run, in US dollars: per decision and per run. A decision is one
#: small call -- a screen in, three fields out -- so ten cents means a screen has gone wrong.
DEFAULT_CEILING = Ceiling(per_paper=0.10, per_run=2.00)

ISSUE = "ISSUE"

INSTRUCTION = """\
You are reviewing one entry of a database of numbers extracted from scientific papers.

You are shown what a human reviewer is shown: the quantity, the value, the paper, the conditions \
recorded for the value with the paper's own words for each, and two texts from the paper labelled \
A and B, with any table they sit in. You are not shown the rest of the paper. Judge only from \
what is shown.

Answer two questions.

1. Which text better fits the value: which of A and B states this value for this quantity?
2. Did this value come from this paper under these conditions? Approve when the text you chose \
states the value for the quantity named and nothing shown contradicts the recorded conditions. \
Otherwise disapprove, and say why in the comment.

Raise an issue instead when the entry cannot be judged as it stands: neither text states the \
value, the value or its unit is garbled, or the quantity named is not what the texts are about. \
To raise an issue, set choice to ISSUE and describe the problem in the comment in one or two \
sentences; the approval is then ignored. Do not raise an issue for something a disapproval says.

Both texts may state the value. That is not an issue: choose the one that states it more \
precisely. Keep the comment short, and leave it empty when you approve without reservation.
"""


class Answer(Frozen):
    """What a model returns for one screen. Flat and without nulls on purpose: the weaker
    providers accept a strict schema of enums, booleans and strings and little else, so the
    issue outcome is a third value of `choice` rather than a nullable pair."""

    choice: Literal["A", "B", "ISSUE"]
    approved: bool
    """Ignored when `choice` is `ISSUE`."""
    comment: str
    """The reason for a disapproval, or the issue's text."""


@dataclass(frozen=True)
class Reviewer:
    """One simulated reviewer: the role it plays, the model playing it, its share of the items."""

    role: ReviewerRole
    model: str
    share: float = 1.0
    """The fraction of all items this role reviews, 0 to 1."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.share <= 1.0:
            raise ValueError(f"a share is a fraction between 0 and 1, not {self.share}")

    @property
    def name(self) -> str:
        """What the decision's `reviewer` column holds, and what `undecided_items` is asked by.

        `AI` is a model reviewing as itself, so only the other roles are called simulated.
        """
        prefix = "ai" if self.role is ReviewerRole.AI else f"simulated-{self.role.value.lower()}"
        return f"{prefix}:{self.model}"


@dataclass
class Tally:
    """What one reviewer did in one run."""

    reviewer: Reviewer
    approved: int = 0
    disapproved: int = 0
    issues: int = 0
    distractors: int = 0
    """Decisions on an item whose second text is a distractor: the ones with a right answer."""
    distractors_caught: int = 0
    """Of those, how many chose the supporting text."""
    spend_usd: float = 0.0
    failures: list[tuple[str, str]] = field(default_factory=list)
    """(item id, reason) for every item that got no row. Each is offered again on the next run."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "reviewer": self.reviewer.name,
            "role": self.reviewer.role.value,
            "model": self.reviewer.model,
            "share": self.reviewer.share,
            "approved": self.approved,
            "disapproved": self.disapproved,
            "issues": self.issues,
            "distractors": self.distractors,
            "distractors_caught": self.distractors_caught,
            "spend_usd": self.spend_usd,
            "failures": [list(failure) for failure in self.failures],
        }


@dataclass
class Summary:
    tallies: list[Tally] = field(default_factory=list)
    spend_usd: float = 0.0
    stopped: str = ""
    """Why the run ended early, empty when every assigned item was offered."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "simulated": True,
            "spend_usd": self.spend_usd,
            "stopped": self.stopped,
            "reviewers": [tally.as_dict() for tally in self.tallies],
        }


def assigned(item_id: str, reviewer: Reviewer) -> bool:
    """Whether this role reviews this item: a draw fixed by the role and the item id.

    Keyed on the role and not the model, so trying another model in a role re-reviews the same
    subset and the two can be compared. Independent between roles, so the overlap of two roles is
    the product of their shares -- some entries rated by several, some by one, some by none.
    """
    digest = hashlib.sha256(f"{reviewer.role.value}:{item_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < reviewer.share


def screen(item: ReviewItem) -> str:
    """One item as the page shows it, as text for a model.

    Built from the page's own functions so the two drivers cannot drift: the texts are in
    `texts_in_order`'s order under its labels, which is also what turns the model's "A" back into
    `chosen_supporting`.
    """
    shown = review.texts_in_order(item)
    lines = [
        f"Quantity: {item.question}",
        f"Value: {item.claim.value} {item.claim.unit}".rstrip(),
        f"The paper calls it: {item.claim.property_in_paper}",
        f"Paper: {review.citation_line(item.paper)}",
        "",
        "Conditions (field | where the paper states it | the paper's words):",
    ]
    lines += [" | ".join(row) for row in review.condition_rows(item.claim)]
    for text in shown:
        lines += ["", f"Text {text.label}", f"Where: {text.location_line}", text.text]
    marks = {text.passage_id: text.label for text in shown if text.passage_id}
    for table in item.tables:
        lines += ["", *_table_lines(table, marks)]
    return "\n".join(lines)


def _table_lines(table: TableView, marks: dict[str, str]) -> list[str]:
    """A table row by row, the cells of A and B marked alike with their labels and nothing
    else distinguished -- `review.table_html`'s rule, in text."""
    lines = [" ".join(part for part in (table.label, table.caption) if part) or "Table"]
    for row in table.rows:
        cells = []
        for cell in row:
            label = marks.get(cell.passage_id) if cell.passage_id else None
            cells.append(f"{cell.text} [{label}]" if label else cell.text)
        lines.append(" | ".join(cells))
    if table.foot:
        lines.append(table.foot)
    return lines


def ask(model: Any, item: ReviewItem, reviewer: Reviewer, *, ledger: Ledger) -> Answer:
    """One call for one screen: project, check, call, record -- `spend`'s order.

    The instruction goes as a plain string rather than as content blocks. Nothing here is long
    enough to cache, and a string is the one system form every provider behind the gateway takes.
    """
    entry = f"{reviewer.name}|{item.item_id}"
    messages = [{"role": "user", "content": screen(item)}]
    counted = model.count_tokens(system=INSTRUCTION, messages=messages, output_format=Answer)
    projected = projected_cost(
        reviewer.model, input_tokens=counted.input_tokens, max_tokens=MAX_OUTPUT_TOKENS
    )
    ledger.check(entry, projected)
    try:
        response = model.parse(
            system=INSTRUCTION,
            messages=messages,
            output_format=Answer,
            max_tokens=MAX_OUTPUT_TOKENS,
        )
    except Exception as failure:
        # A call that came back unreadable was still billed (`extraction._one_call`).
        usage = getattr(failure, "usage", None)
        if usage is not None:
            ledger.record(entry, cost(reviewer.model, usage))
        raise
    ledger.record(entry, cost(reviewer.model, response.usage))
    return response.parsed_output


def run(
    engine: Any,
    reviewers: Iterable[Reviewer],
    model_for: Callable[[str], Any],
    *,
    ceiling: Ceiling = DEFAULT_CEILING,
) -> Summary:
    """Each reviewer decides the items assigned to it that it has not decided yet.

    Resumable by construction: what is done is whatever has a row, so a run that stopped -- on the
    budget, on the account, on a crash -- is continued by running it again.

    An item whose call fails gets no row and a line in the tally; the next item is still
    reviewed. Two endings stop the run instead, because the next item would meet the same answer:
    the provider refusing the account, and the run budget. A decision the store cannot save
    raises out of here untouched (ADR-0930): a run that cannot record must not go on spending.

    Raises `Unpriceable` before any call if a reviewer's model has no price, since a run that
    cannot account for its spend has no working budget.
    """
    reviewers = list(reviewers)
    unpriced = sorted({r.model for r in reviewers if r.model not in PRICES})
    if unpriced:
        raise Unpriceable(f"no prices are configured for {unpriced}; known: {sorted(PRICES)}")

    ledger = Ledger(ceiling)
    summary = Summary()
    for reviewer in reviewers:
        tally = Tally(reviewer)
        summary.tallies.append(tally)
        model = model_for(reviewer.model)
        spent_before = ledger.run.usd
        for item in store.undecided_items(engine, reviewer.name):
            if not assigned(item.item_id, reviewer):
                continue
            started = time.monotonic()
            try:
                answer = ask(model, item, reviewer, ledger=ledger)
            except ProviderRefused as refused:
                summary.stopped = str(refused) or "the provider refused the account"
            except CeilingReached as reached:
                if reached.scope == "run":
                    summary.stopped = str(reached)
                else:
                    tally.failures.append((item.item_id, str(reached)))
            except Exception as failure:
                tally.failures.append((item.item_id, f"{type(failure).__name__}: {failure}"))
            else:
                _record(engine, item, reviewer, answer, time.monotonic() - started, tally)
            if summary.stopped:
                break
        tally.spend_usd = ledger.run.usd - spent_before
        if summary.stopped:
            break
    summary.spend_usd = ledger.run.usd
    return summary


def _record(
    engine: Any,
    item: ReviewItem,
    reviewer: Reviewer,
    answer: Answer,
    elapsed_s: float,
    tally: Tally,
) -> None:
    who = {
        "reviewer": reviewer.name,
        "reviewer_role": reviewer.role,
        "reviewer_model": reviewer.model,
        "time_to_decide_s": elapsed_s,
    }
    if answer.choice == ISSUE:
        if not answer.comment.strip():
            # Not written as a decision either: the model said the item cannot be judged, and
            # recording its ignored approval would turn that into a verdict it did not give.
            tally.failures.append((item.item_id, "an issue with no text"))
            return
        store.record_issue(engine, item.item_id, issue=answer.comment, **who)
        tally.issues += 1
        return
    # Through the page's own mapping from a label to `chosen_supporting`, so a person's "A" and
    # a model's "A" are recorded against the same arrangement.
    verdict = review.APPROVE if answer.approved else review.DISAPPROVE
    decision = review.decision_from(item, answer.choice, verdict, answer.comment)
    store.record_decision(
        engine,
        item.item_id,
        chosen_supporting=decision.chosen_supporting,
        approved=decision.approved,
        comment=decision.comment,
        **who,
    )
    if decision.approved:
        tally.approved += 1
    else:
        tally.disapproved += 1
    if item.second_kind is SecondTextKind.DISTRACTOR:
        tally.distractors += 1
        tally.distractors_caught += decision.chosen_supporting
