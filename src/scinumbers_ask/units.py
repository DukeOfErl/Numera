"""What kind of quantity a unit measures, so far as it can be told.

Presenting a mass and a count as two estimates of one quantity is an arithmetic
error dressed as a range, and the units are the only machine-checkable signal the
corpus carries for it. This module reads them and nothing more.

Deliberately a table rather than inference. The reference corpus holds 2,305
distinct unit strings and its 45 commonest cover only 64 per cent of entries, so a
complete classification is not available at any price -- which makes the honest
interface a three-valued one. `dimension` returns None for a unit it does not
recognise, and `comparable` returns None when either side is unrecognised: not
comparable, not incomparable, unknown. Claiming compatibility for a unit nobody
classified would be the unsourced guess this project exists to avoid.

What it cannot do, and does not pretend to: two dimensionless figures may be a
percentage and a fold-change, which share a dimension and are still not each
other's alternative. Dimension is a floor on comparability, never a proof of it.
"""

from __future__ import annotations

# One entry per unit as the corpus writes it, lowercased with the micro sign folded
# to "u". Grouped by what the unit measures. Written as comma-separated strings
# rather than tuples so the table stays one line per dimension: this will grow, and
# a table of a few hundred units is read by scanning a dimension's row, not by
# scrolling a column of one token per line.
_BY_DIMENSION: dict[str, str] = {
    "length": "m, cm, mm, um, nm, pm, km, angstrom, å",
    "area": "m^2, cm^2, mm^2, um^2, nm^2",
    "volume": "m^3, cm^3, mm^3, um^3, nm^3, l, ml, ul, nl, pl, fl, liter",
    "mass": (
        "g, kg, mg, ug, ng, pg, fg, da, kda, mda, amu, dalton, daltons, "
        # The spelled-out forms of the four symbols above. `kda` was in the table
        # and `kDalton` was not, so a molecular mass compared against a length
        # returned unknown instead of incompatible -- found on the reviewer page
        # of 2026-09-04, where an answer presented 2,700 kDa as the top of a range
        # of nanometres and nothing could say so.
        "kdalton, mdalton, kilodalton, megadalton"
    ),
    "time": (
        "s, sec, secs, second, seconds, ms, us, ns, min, mins, minute, minutes, "
        "h, hr, hrs, hour, hours, day, days, week, weeks, month, months, "
        "year, years, mya"
    ),
    "concentration": "m, mm, um, nm, pm, molar, mol/l, mmol/l, umol/l",
    "count": (
        "copies/cell, copies per cell, molecules/cell, molecules per cell, "
        "molecules, copies, cells, genes, proteins, atoms, ribosomes, "
        "nucleotides, nucleotide, bp, kb, mb, gb, base pairs, amino acids, "
        # Per-cell counts of a thing this row already classifies. Enumerated, not
        # matched by a rule -- see the note below on why.
        "ribosomes/cell, proteins/cell, atoms/cell, atoms per cell, amino acids/cell"
    ),
    "dimensionless": "unitless, %, percent, fold, ratio, fraction, dimensionless",
}

# **`<X>/cell` is enumerated and deliberately not a rule.** A rule reading "anything
# per cell is a count" is the obvious generalisation and it is wrong. Measured over
# the reference corpus, the 103 distinct `<X>/cell` strings whose `X` this table does
# not classify are mostly countable (`mRNAs/cell`, `virions/cell`), but 38 entries
# across `pg/cell`, `fg/cell` and `g/cell` are a *mass* per cell, and one is a volume
# per cell. Under such a rule a mass per cell would compare compatible with a ribosome
# count -- an arithmetic error dressed as a range, which is the one thing this module
# exists to catch. The 62 entries whose `X` is already a known count are listed above;
# the rest stay unrecognised, which is the honest answer and the safe direction, since
# an unrecognised unit yields no comparison rather than a wrong one.
#
# The same reasoning rules out a rate: `ATP/cell/sec` and `mol/cell/sec` are per-cell
# per-second, and nothing here should file them beside a count.

# "mM" is millimolar and "mm" is millimetres; "M" is molar and "m" is metres. The
# corpus distinguishes them only by case, so case cannot be folded away for these.
# Resolved before lowercasing, and the rest of the table is case-insensitive.
_BY_CASE: dict[str, str] = {
    "concentration": "M mM nM pM μM µM uM fM",
    "length": "m mm nm pm μm µm um",
}
_CASE_SENSITIVE = {
    symbol: dimension for dimension, symbols in _BY_CASE.items() for symbol in symbols.split()
}

# Capital S after a metric prefix is siemens, and bare "S" is a Svedberg; neither
# is a second. Lowercasing would file all three under time, and the corpus holds
# one sedimentation coefficient and two neuron conductances that it would file
# wrongly. Named here rather than guessed at: unrecognised is the right answer.
_AMBIGUOUS = frozenset("S nS mS uS μS µS pS kS".split())

# Ambiguous between dimensions in the table above; the case-sensitive map decides.
_DECIDED_BY_CASE = frozenset("m mm nm pm um".split())

_LOOKUP = {
    unit.strip(): dimension
    for dimension, units in _BY_DIMENSION.items()
    for unit in units.split(",")
    if unit.strip() not in _DECIDED_BY_CASE
}


def _normalised(units: str) -> str:
    return " ".join(units.replace("μ", "u").replace("µ", "u").lower().split())


def dimension(units: str) -> str | None:
    """What the unit measures, or None when it is not recognised.

    None is not "dimensionless". An unrecognised unit is one nobody classified, and
    treating it as compatible with anything is exactly the guess to avoid.
    """
    raw = (units or "").strip()
    # The first two clauses are redundant and kept deliberately. Neither "" nor
    # "N/A" is in the lookup, so both would miss and return None anyway -- mutation
    # testing found this, by breaking each of them in turn without any test
    # noticing. They stay because 2,594 of the corpus's entries carry "N/A", and
    # naming that here says the corpus recorded no unit, which a silent lookup miss
    # does not. The third clause is load-bearing: without it "nS" resolves to time.
    if not raw or raw.upper() == "N/A" or raw in _AMBIGUOUS:
        return None
    if raw in _CASE_SENSITIVE:
        return _CASE_SENSITIVE[raw]
    return _LOOKUP.get(_normalised(raw))


def comparable(left: str, right: str) -> bool | None:
    """Whether two units could describe the same quantity. None when unknown."""
    a, b = dimension(left), dimension(right)
    if a is None or b is None:
        return None
    return a == b


def dimensions_of(units: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """The distinct recognised dimensions among these units, in a stable order.

    Unrecognised units contribute nothing rather than a shared "unknown" bucket,
    which would otherwise read as a dimension two entries have in common.
    """
    found = {d for d in (dimension(u) for u in units) if d is not None}
    return tuple(sorted(found))
