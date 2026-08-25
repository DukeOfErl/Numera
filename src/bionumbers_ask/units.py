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
    "mass": "g, kg, mg, ug, ng, pg, fg, da, kda, mda, amu, dalton",
    "time": (
        "s, sec, secs, second, seconds, ms, us, ns, min, mins, minute, minutes, "
        "h, hr, hrs, hour, hours, day, days, week, weeks, month, months, "
        "year, years, mya"
    ),
    "concentration": "m, mm, um, nm, pm, molar, mol/l, mmol/l, umol/l",
    "count": (
        "copies/cell, copies per cell, molecules/cell, molecules per cell, "
        "molecules, copies, cells, genes, proteins, atoms, ribosomes, "
        "nucleotides, nucleotide, bp, kb, mb, gb, base pairs, amino acids"
    ),
    "dimensionless": "unitless, %, percent, fold, ratio, fraction, dimensionless",
}

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
