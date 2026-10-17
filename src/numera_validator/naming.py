"""A harvested entry's property: the measure, of what, as one name (ADR-1700).

"Average length" says what was measured and not of what; "cytokinetic actin rings" says of what
and not what. Neither is an entry a reader can use, and the first live harvest produced both.
So the model writes the two parts, and the application joins them: the name is one field in the
store, BioNumbers style ("Average length of F-actin filaments in non-contracting rings"), and the
check that both parts are there is a string test rather than a judgement.

The check is a classifier, so it moves names in both directions. The expensive direction is a
vague name that passes, since it looks like an entry and is not one; the cheap direction is a
good name refused, which costs one entry and is recorded. The rule therefore over-refuses: a part
that repeats the other (`measure="length"`, `object="actin filament length"`) is refused too,
because joining them would say the measure twice.

`backfill` names the entries of a store loaded before the parts were asked for, one call per
entry, without re-reading the paper: the entry's own quote, value, unit and labels are what the
model needs, and the paper would cost a hundred times the tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bionumbers import spend, store
from bionumbers.records import Frozen, ReviewItem
from bionumbers.spend import Ceiling, CeilingReached, Ledger

#: Two of the labels the harvest instruction asks for, as the instruction and the backfill word
#: them. One text so the model that extracts and the model that backfills read the same rule.
MEASURE_RULE = (
    "measure: what was measured, as a database heading without the value, the unit or the "
    'organism -- "Doubling time", "Diameter", "Average length", "Dissociation constant".'
)
OBJECT_RULE = (
    "measured_object: what the measure is a measure of -- the structure, molecule, cell, "
    "organism, material or system, with the qualifier that tells this value apart from the "
    "article's other values of the same measure. Where the article reports the quantity "
    "under more than one condition, every value but the control ends with its condition, "
    "named as a scientist would name it -- the growth state, genotype or construct, genome "
    'assembly ("haplotype 1 assembly"), tissue, developmental stage, or position ("third '
    'hyphal compartment from the tip", not "3rd cell"); outside biology, the sample or state '
    "-- and never as a table's row or column label, nor left to a heading that spans several "
    "columns. The value the article marks as its control or wild type carries no condition. "
    "Do not repeat the measure here."
)

BACKFILL_INSTRUCTION = f"""You name one quantitative entry harvested from a scientific article.

You are given the entry: the article's title, the value with its unit, the sentence or table
cell it was quoted from, the article's own term for the quantity, the conditions recorded with
it, and the label an earlier pass gave it. Write two labels, nothing quoted:
- {MEASURE_RULE}
- {OBJECT_RULE}
The two will be joined as "<measure> of <measured_object>", so write each to read well there."""

#: Two short labels need a few dozen tokens; 600 because a provider may count the model's own
#: reasoning against the bound, and 14 of 452 demo entries came back empty at 200 for that reason
#: (finish_reason "length" with no output), the long-object papers first.
MAX_OUTPUT_TOKENS = 600


class PropertyOutput(Frozen):
    """What the backfill asks the model for: the two parts, and nothing else."""

    measure: str
    measured_object: str


def property_name(measure: str, measured_object: str) -> str:
    """The one name, or empty where the parts do not make one.

    Empty when either part is missing or when one part repeats the other, compared without
    case or surrounding space: a name that says the measure twice is a name nobody wrote.
    """
    measure, measured_object = measure.strip(), measured_object.strip()
    if not measure or not measured_object:
        return ""
    folded_measure, folded_object = measure.casefold(), measured_object.casefold()
    if folded_measure in folded_object or folded_object in folded_measure:
        return ""
    return f"{measure[0].upper()}{measure[1:]} of {measured_object}"


@dataclass(frozen=True, slots=True)
class Refusal:
    """An entry the backfill could not name, with the two parts the model wrote, so the
    classifier's expensive direction can be read off the run rather than assumed."""

    item_id: str
    measure: str
    measured_object: str


@dataclass(slots=True)
class Backfill:
    named: int = 0
    refused: list[Refusal] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    """Item ids whose call raised; the next item is still named."""
    spend_usd: float = 0.0
    stopped: str = ""
    """Why the run ended before the last item, if it did: the run budget."""


def backfill(engine: Any, model: Any, model_id: str, *, ceiling: Ceiling | None = None) -> Backfill:
    """Name every item in the store that has no property yet.

    Resumable: what is named has a non-empty `property`, so a stopped run is continued by
    running it again. The run budget ends the run; any other failure costs one item its name
    and is listed. Nothing is written for a refused name, so a later run with a better model
    asks about it again.
    """
    ledger = Ledger(ceiling or Ceiling())
    done = Backfill()

    def name_for(item: ReviewItem) -> str:
        if done.stopped:
            return ""
        try:
            parts, _ = spend.call(
                model,
                system=BACKFILL_INSTRUCTION,
                messages=[{"role": "user", "content": describe(item)}],
                output_format=PropertyOutput,
                max_tokens=MAX_OUTPUT_TOKENS,
                ledger=ledger,
                entry=item.paper.pmcid,
                model_id=model_id,
            )
        except CeilingReached as reached:
            if reached.scope == "run":
                done.stopped = str(reached)
            else:
                done.failed.append(item.item_id)
            return ""
        except Exception as failure:  # noqa: BLE001 -- one item's failure, listed, not the run's
            done.failed.append(f"{item.item_id}: {type(failure).__name__}: {failure}")
            return ""
        named = property_name(parts.measure, parts.measured_object)
        if named:
            done.named += 1
        else:
            done.refused.append(Refusal(item.item_id, parts.measure, parts.measured_object))
        return named

    store.fill_properties(engine, name_for)
    done.spend_usd = ledger.run.usd
    return done


def describe(item: ReviewItem) -> str:
    """The entry as the backfill shows it: what the extractor had, minus the paper."""
    claim = item.claim
    conditions = "; ".join(
        f"{condition.name}: {condition.quote}" for condition in claim.conditions if condition.quote
    )
    lines = [
        f"Article: {item.paper.title}",
        f"Value: {claim.value} {claim.unit}".rstrip(),
        f"Quoted from: {claim.quote.text}",
        f"The article's term: {claim.property_in_paper}",
        f"Conditions: {conditions or 'none recorded'}",
        f"Earlier label: {claim.property_asked}",
    ]
    if claim.organism_name:
        lines.append(f"Organism: {claim.organism_name}")
    return "\n".join(lines)
