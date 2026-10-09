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

from dataclasses import dataclass

from bionumbers.extraction import INSTRUCTION
from bionumbers.records import Claim

#: At most this many claims from one paper. A bound on cost before it is one on content: every
#: claim buys a second-text call, and a paper's output has to fit the extraction call's cap.
#: Ten until the first seed (2026-10-04), which recovered 15 of BioNumbers' 34 values for its ten
#: papers: one paper filled the bound with three of those values left out.
MAX_CLAIMS = 20

#: The extraction call's output bound in this mode. Ten claims ran to about ten thousand tokens
#: in that seed, so twenty do not fit `extraction.MAX_TOKENS`; an answer cut off mid-JSON is a
#: FAILED paper. Priced into the projection like the bound it replaces.
MAX_TOKENS = 32000

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
        "binding and dissociation constants, the kinetic constants of an enzyme, forces, step "
        "sizes, stiffness and persistence length",
    ),
)

_STATISTICS = (
    "statistics about the study rather than the subject: p-values, sample sizes, correlation "
    "coefficients, fold changes, fit qualities, scores, percentages of a sample responding"
)
_SETTINGS = (
    "experimental settings: amounts added, incubation times, temperatures set, heating and "
    "cooling rates set, instrument and imaging parameters, software thresholds"
)
_COUNTS = "counts of items in a database, a library or a dataset"

#: What is never wanted, however prominent in the paper. These are the numbers a store of
#: "every number" fills with.
EXCLUDED: tuple[str, ...] = (
    _STATISTICS,
    _SETTINGS,
    "values for single genes, single proteins or single samples out of a genome-wide or "
    "large-scale dataset, where the summary value is the reusable one",
    _COUNTS,
    "properties of this study's own preparations rather than of the organism or the molecule: "
    "the concentration of a suspension or an extract it made, the activity of a crude extract, "
    "the size of particles it synthesised",
)


@dataclass(frozen=True)
class Scope:
    """One domain's wanted classes and unwanted kinds of value.

    A domain is a scope and nothing more: the instruction, the quoting rule and everything after
    the call are the same whatever the domain, and the scope travels in the user turn so the
    cached paper prefix is too. Its name is recorded on every claim's fingerprint, because two
    scopes asked of one paper are two different questions of it.
    """

    classes: tuple[tuple[str, str], ...]
    excluded: tuple[str, ...]


_MECHANICAL = (
    "MECHANICAL",
    "mechanical and rheological properties of filaments, networks, cytoplasm, cells and "
    "tissues: elastic, storage and loss moduli, viscosities, bending stiffness, persistence "
    "length, and the forces they bear or produce",
)

#: Biophysics: the biology classes with the mechanics of the material named on its own. A
#: reconstituted network is the object measured there, not a preparation to set aside, so the
#: biology scope's last exclusion is replaced rather than kept.
BIOPHYSICS = Scope(
    classes=(
        *(cls for cls in PROPERTY_CLASSES if cls[0] != "PHYSICAL_CONSTANT"),
        _MECHANICAL,
        (
            "PHYSICAL_CONSTANT",
            "other physical and biochemical constants of biological material: diffusion "
            "coefficients, binding and dissociation constants, step sizes",
        ),
    ),
    excluded=(
        *EXCLUDED[:-1],
        "the amounts used to assemble a reconstituted network or to coat a probe: they are the "
        "conditions of a value, recorded with it, not values of their own",
        "properties of probe particles, beads and calibration samples",
    ),
)

CHEMISTRY = Scope(
    classes=(
        (
            "BINDING",
            "affinities of molecules for their targets: dissociation, association and "
            "inhibition constants, and the half-maximal inhibitory or effective concentration "
            "of a named compound in a named assay",
        ),
        (
            "RATE",
            "rate constants and rates of reactions, of binding and of assembly or disassembly, "
            "including enzyme turnover numbers and Michaelis constants",
        ),
        (
            "THERMODYNAMIC",
            "free energies, enthalpies, entropies and activation energies of binding, folding, "
            "assembly or reaction; acid dissociation constants; redox potentials",
        ),
        (
            "SPECTROSCOPIC",
            "absorption and emission maxima, extinction coefficients, quantum yields and "
            "fluorescence lifetimes of named molecules",
        ),
        ("SIZE", "molecular dimensions, distances and areas determined by structure or experiment"),
        ("CONCENTRATION", "critical concentrations and solubilities"),
    ),
    excluded=(
        _STATISTICS,
        _SETTINGS,
        "computed scores without a physical unit: docking scores, predicted drug-likeness, "
        "predicted toxicity",
        "characterisation of newly made compounds: synthetic yields, spectral peak positions "
        "listed to identify them, elemental analysis",
        "rows of a screening table, where the article's lead compound or its summary is the "
        "reusable value",
        _COUNTS,
    ),
)

PHYSICS = Scope(
    classes=(
        (
            "TEMPERATURE",
            "characteristic temperatures of a material: glass transition, melting, "
            "crystallisation, and crossover or onset temperatures",
        ),
        (
            "TIME",
            "relaxation, correlation and characteristic times, with the temperature or state "
            "they belong to",
        ),
        (
            "PHYSICAL_CONSTANT",
            "material constants: fragility, activation energies, heat capacity steps, moduli, "
            "viscosities, diffusion coefficients, and the exponents of scaling laws",
        ),
        (
            "SIZE",
            "characteristic length scales: correlation lengths, sizes of cooperatively "
            "rearranging regions, interparticle distances",
        ),
        (
            "FRACTION",
            "packing and volume fractions at which a transition occurs, and ratios between "
            "characteristic temperatures or times",
        ),
    ),
    excluded=(
        _STATISTICS,
        _SETTINGS,
        "parameters of a simulation chosen by its authors: system size, time step, interaction "
        "parameters, number of runs",
        "values for single samples out of a long series, where the trend or the summary value "
        "is the reusable one",
        _COUNTS,
    ),
)

#: Organism-level biology: anatomy, physiology, life history, genomes, evolution. Written after the
#: biology scope -- read off yeast and the cytoskeleton -- returned nothing from eight of ten
#: zoology and physiology papers (2026-10-09), the model saying each time that the paper's numbers
#: were about bodies, fossils or tissues rather than cells.
ORGANISMAL = Scope(
    classes=(
        (
            "SIZE",
            "sizes, lengths, areas and volumes of whole organisms, body parts, tissues, "
            "extracellular particles and fossils",
        ),
        (
            "COUNT",
            "numbers of segments, body parts, cells of a kind, chromosomes or genes in an "
            "organism, and of species in a named group",
        ),
        ("GENOME", "genome sizes, base composition, and the gene and repeat content of genomes"),
        (
            "TIME",
            "durations of life-history and developmental events -- regeneration, development, "
            "generation time, lifespan -- and the ages of fossils and lineages",
        ),
        (
            "RATE",
            "rates of growth, regeneration, reproduction and locomotion, and physiological rates "
            "such as heart rate",
        ),
        (
            "PHYSIOLOGICAL",
            "physiological quantities of organisms and tissues: concentrations in blood or tissue, "
            "densities of vessels or cells per area, pressures, body temperatures",
        ),
        (
            "FRACTION",
            "proportions within an organism or a population: survival, sex ratios, the share of a "
            "tissue or a cell type",
        ),
    ),
    excluded=(
        _STATISTICS,
        _SETTINGS,
        "phylogenetic support values, branch lengths and alignment lengths",
        "numbers of specimens, animals or samples examined",
        "values for single genes or single samples out of a genome-wide or large-scale dataset, "
        "where the summary value is the reusable one",
        _COUNTS,
    ),
)

#: Every domain harvest can be asked in, by the name a run records. `biology` is the scope the
#: classes above were read for and the one an unnamed run used before scopes existed.
SCOPES: dict[str, Scope] = {
    "biology": Scope(classes=PROPERTY_CLASSES, excluded=EXCLUDED),
    "biophysics": BIOPHYSICS,
    "organismal": ORGANISMAL,
    "chemistry": CHEMISTRY,
    "physics": PHYSICS,
}
DEFAULT_SCOPE = "biology"

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
unless the article presents it as a property of that named system. An article that
establishes many reusable values -- a quantitative survey, a model built on measured numbers --
is wanted in full up to the bound: do not stop at the few most prominent. An article with no
value of the wanted classes is NOTHING_TO_EXTRACT.

THE VALUE FIELD HOLDS NO UNIT. The unit, a percent sign included, goes in the unit field and
nowhere else; the value keeps the number as the article writes it, with its stated error or
range.

THE REJECTED LIST IS SHORT HERE. List at most five rejected candidates: numbers of the
wanted classes that read like this article's own values and are not (CITED, PARAMETER,
COMPILED). Leave every other number in the article out.

THREE LABELS ARE YOURS TO WRITE. They are labels, not quotes; everything else stays quoted.
- property_name: a short general name for the quantity, worded as a database heading,
  without the value or the organism. Where the article reports the quantity under more
  than one condition, the name of every value but the control ends with its condition,
  named as a scientist would name it -- the growth state, genotype or construct, tissue,
  developmental stage, or position ("third hyphal compartment from the tip", not "3rd
  cell"); outside biology, the sample or state -- and never as a table's row or column
  label. The value the article marks as its control or wild type carries no condition in
  its name.
- property_class: one of the class names in the user turn.
- organism_name: the species the value belongs to, as the Latin binomial the article gives
  for it anywhere in its text -- the common name ("yeast", "mouse") only where the article
  never gives one; for purified material or an in vitro system, the species the material
  came from. A value that belongs to no organism -- a material, a compound, a model system --
  is labelled with that material or system, named as the article names it."""

#: The extraction instruction with its first paragraph replaced and the harvest rules added.
#: Built from `extraction.INSTRUCTION` rather than restated, so the quoting rule, the claim
#: categories, the citation-marker rule and the conditions cannot drift between the two modes.
HARVEST_INSTRUCTION = "\n\n".join((_HEAD, INSTRUCTION.split("\n\n", 1)[1], _SELECTION))


def class_names(scope: str = DEFAULT_SCOPE) -> frozenset[str]:
    """The class names a claim harvested in `scope` may carry."""
    return frozenset(name for name, _ in SCOPES[scope].classes)


def user_turn(scope: str = DEFAULT_SCOPE) -> dict:
    """The scope: the wanted classes and the unwanted kinds. Nothing about any paper."""
    chosen = SCOPES[scope]
    wanted = "\n".join(f"- {name}: {covers}" for name, covers in chosen.classes)
    unwanted = "\n".join(f"- {kind}" for kind in chosen.excluded)
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
