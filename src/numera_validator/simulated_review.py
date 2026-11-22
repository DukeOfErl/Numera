"""Models standing in for reviewers: the review task, answered unattended (ADR-0960, ADR-0970).

Finding people to review takes longer than the demonstration has, so each rung of the trust ladder
is played by a model. That makes this a **second driver over the review task**, beside
`review_app.py`: it reads one item's screen, answers the same questions in the same two steps, and
writes through the same store. It is not a step of the extraction pipeline and nothing upstream
reads what it writes.

Four things it holds to, each because the alternative would make the dataset say something false:

- **A model sees what a person sees, and nothing more.** The screen is built from
  `numera_validator.review`'s own functions -- the texts in the page's order, the page's condition
  rows -- so nothing here reads the second text's kind or type, and no reviewer is shown another's
  decision. Every item has a known right answer, which is what lets a run report how often a model
  picked the supporting text; a screen that leaked the kind would make that figure worthless.
- **The value is withheld until the text is chosen** (ADR-0970). The first step shows the
  quantity, the paper and the two texts, and asks which text states a value for the quantity and
  what that value is. Only then are the stored value and conditions revealed for the verdict. A
  reviewer shown the answer first has nothing left to judge; shown the texts first, their reading
  is a measurement of the entry the extractor's answer cannot have steered.
- **One instruction for every role.** A role is a label on the model that plays it, never a
  persona: telling a model to answer "as a student" asks it to invent a student's mistakes, and a
  disagreement manufactured that way is not a finding. Where reviewers contradict each other here,
  two models read the same screen differently.
- **Every row says a model wrote it, and which one answered.** `reviewer_model` is the model asked
  for and `answered_by` the one the provider says replied -- for a router, a different name -- and
  the reviewer's name begins `simulated-`, so no query can mistake these for people.

Which items a role reviews is drawn from a hash of the role and the item id (`assigned`): fixed
across runs, independent between roles, so the subsets overlap by chance and an entry can carry
several ratings or none.

Needs nothing from the ask app: the screens come from `numera_validator.review`, which is core, and
the model call goes through `spend.call` as the extractor's does.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Literal

from numera_validator import readings, review, spend, store
from numera_validator.extraction import ProviderRefused
from numera_validator.records import Frozen, ReviewerRole, ReviewItem, SecondTextKind, TableView
from numera_validator.spend import (
    PRICES,
    Ceiling,
    CeilingReached,
    Ledger,
    Unpriceable,
)

#: Enough for an answer and for a reasoning model's thinking before it; the answer itself is
#: three fields. 2,000 cut off a routed DeepSeek V4.1 Flash on two of twelve steps and GPT-6.1
#: Sol on three of sixty (2026-10-07), so it is doubled. Priced in full by the projection, so it
#: is also most of the per-item ceiling.
MAX_OUTPUT_TOKENS = 4000

#: The two bounds of a simulated run, in US dollars: per decision and per run. A decision is two
#: small calls -- a screen in, three fields out, twice -- so ten cents means a screen has gone
#: wrong.
DEFAULT_CEILING = Ceiling(per_paper=0.10, per_run=2.00)

ISSUE = "ISSUE"

CHOICE_INSTRUCTION = """\
You are reviewing one entry of a database of numbers extracted from scientific papers.

You are shown what a human reviewer is shown at this step: the quantity the entry is about, with \
its organism, the paper, and two texts from the paper labelled A and B, with any table they sit \
in. You are not shown the value that was extracted, and you are not shown the rest of the paper. \
Judge only from what is shown.

Choose which text states a value for this quantity: A or B. Then give the value that text states \
for the quantity, with its unit, exactly as the text writes it.

Both texts may state a value for it; choose the one that states it more directly. Raise an issue \
instead when neither text states a value for this quantity, or when you cannot tell from what is \
shown which of the two the entry means: set choice to ISSUE, leave value_read empty, and say \
which in the comment. Keep the comment to one or two sentences, and leave it empty when the \
choice was plain.
"""

VERDICT_INSTRUCTION = """\
You are reviewing one entry of a database of numbers extracted from scientific papers.

You have already chosen which of two texts from the paper states a value for the quantity, and \
written down the value you read. You are now shown the entry as it is stored: its value, the \
paper's own name for the quantity, and the conditions recorded for it with the paper's words for \
each. You are not shown the rest of the paper. Judge only from what is shown.

Did this value come from this paper under these conditions? Approve when the stored value is the \
one your chosen text states, for the quantity named, and nothing shown contradicts the recorded \
conditions. Otherwise disapprove, and say why in the comment.

Raise an issue instead when the entry cannot be judged as it stands: the stored value or its \
unit is garbled, or the quantity named is not what the texts are about. Set verdict to ISSUE and \
describe the problem in the comment in one or two sentences. Do not raise an issue for something \
a disapproval says. Leave the comment empty when you approve without reservation.
"""


class Chosen(Frozen):
    """The first step's answer. Flat and without nulls on purpose: the weaker providers accept a
    strict schema of enums and strings and little else, so the issue outcome is a third value of
    `choice` rather than a nullable pair."""

    choice: Literal["A", "B", "ISSUE"]
    value_read: str
    """The value the chosen text states, as written; empty with an issue."""
    comment: str


class Judged(Frozen):
    """The second step's answer."""

    verdict: Literal["APPROVE", "DISAPPROVE", "ISSUE"]
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
    """Choices on an item whose second text is a distractor: the ones with a right answer."""
    distractors_caught: int = 0
    """Of those, how many chose the supporting text."""
    values_agreed: int = 0
    """Choices of the supporting text whose value read agrees with the stored value."""
    spend_usd: float = 0.0
    failures: list[tuple[str, str]] = field(default_factory=list)
    """(item id, reason) for every step that got no row. Each is offered again on the next run."""

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
            "values_agreed": self.values_agreed,
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
    """The first step's screen, as text for a model: the quantity, the paper, the two texts.

    Built from the page's own functions so the two drivers cannot drift: the texts are in
    `texts_in_order`'s order under its labels, which is also what turns the model's "A" back into
    `chosen_supporting`. No value, no condition and not the paper's own name for the quantity:
    each of those is a clue to which text is meant, and the choice is the judgement being asked
    for (ADR-0970).
    """
    shown = review.texts_in_order(item)
    lines = [
        f"Quantity: {item.question}",
        f"Paper: {review.citation_line(item.paper)}",
    ]
    for text in shown:
        lines += ["", f"Text {text.label}", f"Where: {text.location_line}", text.text]
    marks = {text.passage_id: text.label for text in shown if text.passage_id}
    for table in item.tables:
        lines += ["", *_table_lines(table, marks)]
    return "\n".join(lines)


def reveal(item: ReviewItem, choice: store.Choice) -> str:
    """The second step's screen: the first step's, what the reviewer answered, and the entry as
    stored -- value, the paper's name for it, every condition row the page shows."""
    label = review.chosen_label(item, choice.chosen_supporting)
    lines = [
        screen(item),
        "",
        f"You chose Text {label} and read the value as: {choice.value_read or '(nothing)'}",
        "",
        "The entry as stored:",
        f"Value: {item.claim.value} {item.claim.unit}".rstrip(),
        readings.line_for(choice.value_agreement),
        f"The paper calls it: {item.claim.property_in_paper}",
        "Conditions (field | where the paper states it | the paper's words):",
    ]
    lines += [
        " | ".join(row) for row in review.condition_rows(item.claim, item.claim.fingerprint.scope)
    ]
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


def ask(
    model: Any,
    reviewer: Reviewer,
    *,
    system: str,
    content: str,
    output_format: type,
    ledger: Ledger,
    entry: str,
) -> tuple[Any, str]:
    """One call for one step, through `spend.call` like the extractor's. Returns the parsed
    answer and the model the provider says answered (empty where it says nothing).

    The instruction goes as a plain string rather than as content blocks. Nothing here is long
    enough to cache, and a string is the one system form every provider behind the gateway takes.
    """
    return spend.call(
        model,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=output_format,
        max_tokens=MAX_OUTPUT_TOKENS,
        ledger=ledger,
        entry=entry,
        model_id=reviewer.model,
    )


def run(
    engine: Any,
    reviewers: Iterable[Reviewer],
    model_for: Callable[[str], Any],
    *,
    ceiling: Ceiling = DEFAULT_CEILING,
) -> Summary:
    """Each reviewer decides the items assigned to it that it has not decided yet.

    Resumable by construction: what is done is whatever has a completed row, so a run that
    stopped -- on the budget, on the account, on a crash -- is continued by running it again; an
    item left with its first step taken gets only its second.

    A step whose call fails gets no row and a line in the tally; the next item is still reviewed.
    Two endings stop the run instead, because the next item would meet the same answer: the
    provider refusing the account, and the run budget. A row the store cannot write raises out of
    here untouched (ADR-0930): a run that cannot record must not go on spending.

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
        mine = store.undecided_items(
            engine, reviewer.name, keep=partial(assigned, reviewer=reviewer)
        )
        for item in mine:
            try:
                _review_one(engine, model, item, reviewer, ledger, tally)
            except ProviderRefused as refused:
                summary.stopped = str(refused) or "the provider refused the account"
            except CeilingReached as reached:
                if reached.scope == "run":
                    summary.stopped = str(reached)
                else:
                    tally.failures.append((item.item_id, str(reached)))
            except _StepFailed as failed:
                tally.failures.append((item.item_id, str(failed)))
            if summary.stopped:
                break
        tally.spend_usd = ledger.run.usd - spent_before
        if summary.stopped:
            break
    summary.spend_usd = ledger.run.usd
    return summary


class _StepFailed(Exception):
    """A step's call or answer could not be used; the item is offered again next run."""


def _call(model: Any, reviewer: Reviewer, ledger: Ledger, item: ReviewItem, **request: Any):
    """`ask`, with a failure of the model's -- not the account's, not a ceiling -- made a step
    failure, so the loop above records it against the item and goes on."""
    entry = f"{reviewer.name}|{item.item_id}"
    try:
        return ask(model, reviewer, ledger=ledger, entry=entry, **request)
    except (ProviderRefused, CeilingReached):
        raise
    except Exception as failure:
        raise _StepFailed(f"{type(failure).__name__}: {failure}") from failure


def _review_one(
    engine: Any, model: Any, item: ReviewItem, reviewer: Reviewer, ledger: Ledger, tally: Tally
) -> None:
    who = {"reviewer": reviewer.name}
    choice = store.open_choice(engine, item.item_id, reviewer.name)
    if choice is None:
        started = time.monotonic()
        chosen, answered = _call(
            model,
            reviewer,
            ledger,
            item,
            system=CHOICE_INSTRUCTION,
            content=screen(item),
            output_format=Chosen,
        )
        elapsed = time.monotonic() - started
        opened = {
            **who,
            "time_to_decide_s": elapsed,
            "reviewer_role": reviewer.role,
            "reviewer_model": reviewer.model,
            "answered_by": answered or None,
        }
        if chosen.choice == ISSUE:
            if not chosen.comment.strip():
                raise _StepFailed("an issue with no text")
            store.record_issue(engine, item.item_id, issue=chosen.comment, **opened)
            tally.issues += 1
            return
        # Through the page's own rule (`first_step_from`), so a person's "A" and a model's "A"
        # are recorded against the same arrangement, and a model that chose a text but read no
        # value is refused exactly as a person is.
        try:
            first = review.first_step_from(item, chosen.choice, chosen.value_read)
        except review.Incomplete as incomplete:
            raise _StepFailed(incomplete.message) from incomplete
        store.record_choice(
            engine,
            item.item_id,
            chosen_supporting=first.chosen_supporting,
            value_read=first.value_read,
            **opened,
        )
        # Read back rather than built here: the store computed the agreement.
        choice = store.open_choice(engine, item.item_id, reviewer.name)
        if choice is None:  # pragma: no cover - the write above succeeded or raised
            raise _StepFailed("the choice did not stay written")
        if item.second_kind is SecondTextKind.DISTRACTOR:
            tally.distractors += 1
            tally.distractors_caught += choice.chosen_supporting
        if choice.chosen_supporting and choice.value_agreement == readings.Agreement.MATCHES:
            tally.values_agreed += 1

    started = time.monotonic()
    judged, answered = _call(
        model,
        reviewer,
        ledger,
        item,
        system=VERDICT_INSTRUCTION,
        content=reveal(item, choice),
        output_format=Judged,
    )
    closing = {
        **who,
        "time_to_decide_s": time.monotonic() - started,
        "answered_by": answered or None,
    }
    if judged.verdict == ISSUE:
        if not judged.comment.strip():
            raise _StepFailed("an issue with no text")
        store.record_issue(engine, item.item_id, issue=judged.comment, **closing)
        tally.issues += 1
        return
    approved = judged.verdict == "APPROVE"
    store.record_verdict(engine, item.item_id, approved=approved, comment=judged.comment, **closing)
    if approved:
        tally.approved += 1
    else:
        tally.disapproved += 1
