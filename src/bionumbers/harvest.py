"""Harvest mode: one paper, no question -- the reusable numbers it establishes (ADR-0950).

The question-first pipeline found the right papers 4 times in 32 (2026-09-23): a full-text search
for a property and an organism returns papers that mention both and measure neither. This mode
turns the problem round. Papers are harvested ahead of any question, each is asked once for the
values a scientist outside the study would look up, and the question is answered later from the
store. Finding a paper stops being a precision problem at question time and becomes a coverage
problem at harvest time, which is the cheaper one.

Everything downstream is the extraction pipeline's, unchanged: the same passages, the same
verbatim-quote rule and checker, the same one retry, the same claim-or-rejected categories, the
same second text. What differs is the first paragraph of the instruction, three labels the model
writes for each claim, and a bound on how many claims one paper may yield.

The scope -- which classes of number are wanted and which are not -- is data in this module and
travels in the user turn, so the cached paper prefix is the same whatever the scope becomes.
The classes are read off the BioNumbers entries for yeast and for the cytoskeleton that are
measured, carry a method and cite a paper (492 entries, counted 2026-10-03), which is the nearest
thing to a definition of "useful number" this project has.
"""

from __future__ import annotations

from bionumbers.extraction import INSTRUCTION
from bionumbers.records import Claim

#: At most this many claims from one paper. A bound on cost before it is one on content: every
#: claim buys a second-text call, and a paper's output has to fit the extraction call's cap.
MAX_CLAIMS = 10

#: The classes of value wanted, each with what it covers. In words only: a unit or a magnitude
#: here would be prior knowledge handed to the model, which the instruction forbids it to use.
PROPERTY_CLASSES: tuple[tuple[str, str], ...] = (
    (
        "SIZE",
        "lengths, diameters, thicknesses, areas and volumes of cells, organelles, cellular "
        "structures, filaments and molecules",
    ),
    (
        "COPY_NUMBER",
        "how many molecules, complexes, organelles or structures there are per cell, per "
        "nucleus or per named structure",
    ),
    (
        "CONCENTRATION",
        "concentrations and densities of molecules, cells or mass, including critical "
        "concentrations",
    ),
    (
        "RATE",
        "speeds and rates of biological processes: growth, polymerisation and "
        "depolymerisation, motor movement, replication, transcription, translation, transport, "
        "and the frequencies of events such as catastrophe and rescue",
    ),
    (
        "TIME",
        "durations and characteristic times: doubling and generation times, half-lives, "
        "lifetimes, the length of a phase or a process",
    ),
    (
        "FRACTION",
        "fractions, proportions and ratios describing composition or allocation, such as the "
        "share of a pool in one state or the ratio of two volumes",
    ),
    (
        "PHYSICAL_CONSTANT",
        "physical and biochemical constants of biological material: diffusion coefficients, "
        "binding and dissociation constants, forces, step sizes, stiffness and persistence "
        "length",
    ),
)

#: What is never wanted, however prominent in the paper. These are the numbers a store of
#: "every number" fills with.
EXCLUDED: tuple[str, ...] = (
    "statistics about the study rather than the biology: p-values, sample sizes, correlation "
    "coefficients, fold changes, scores, percentages of a sample responding",
    "experimental settings: amounts added, incubation times, temperatures set, instrument "
    "and imaging parameters, software thresholds",
    "values for single genes, single proteins or single samples out of a genome-wide or "
    "large-scale dataset, where the summary value is the reusable one",
    "counts of items in a database, a library or a dataset",
)

_HEAD = (
    "You are given one research article, passage by passage, each passage with an id. There "
    "is no single question. Report the quantitative values this article itself establishes "
    "that a scientist outside this study would look up and reuse. The user turn lists the "
    "classes of value wanted and what is not wanted. Use only the passages you were given."
)

_SELECTION = f"""AT MOST {MAX_CLAIMS} CLAIMS, THE MOST REUSABLE FIRST. Prefer the baseline: wild
type, control, untreated, the standard condition. Prefer a summary value -- a mean, a median, a
total -- over rows for single genes, samples or replicates. A value that exists only under
a perturbation particular to this study (its drug, its mutant, its construct) is not wanted,
unless the article presents it as a property of that named system. An article with no value
of the wanted classes is NOTHING_TO_EXTRACT.

THE REJECTED LIST IS SHORT HERE. List at most five rejected candidates: numbers of the
wanted classes that read like this article's own values and are not (CITED, PARAMETER,
COMPILED). Leave every other number in the article out.

THREE LABELS ARE YOURS TO WRITE. They are labels, not quotes; everything else stays quoted.
- property_name: a short general name for the quantity, worded as a database heading,
  without the value, the organism or this study's condition.
- property_class: one of the class names in the user turn.
- organism_name: the species the value belongs to, in full, as the article names it; for
  purified material or an in vitro system, the species the material came from."""

#: The extraction instruction with its first paragraph replaced and the harvest rules added.
#: Built from `extraction.INSTRUCTION` rather than restated, so the quoting rule, the claim
#: categories, the citation-marker rule and the conditions cannot drift between the two modes.
HARVEST_INSTRUCTION = "\n\n".join((_HEAD, INSTRUCTION.split("\n\n", 1)[1], _SELECTION))


def user_turn() -> dict:
    """The scope: the wanted classes and the unwanted kinds. Nothing about any paper."""
    wanted = "\n".join(f"- {name}: {covers}" for name, covers in PROPERTY_CLASSES)
    unwanted = "\n".join(f"- {kind}" for kind in EXCLUDED)
    return {"role": "user", "content": f"Wanted classes:\n{wanted}\n\nNot wanted:\n{unwanted}"}


def question_of(claim: Claim) -> str:
    """The claim as a question a reviewer and the second-text step can read.

    A harvested claim answers no question anyone asked, so its own labels stand in for one: the
    review screen and the distractor rules both need a property to judge a text against.
    """
    return (
        f"{claim.property_asked} ({claim.organism_name})"
        if claim.organism_name
        else claim.property_asked
    )
