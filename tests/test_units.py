"""What kind of quantity a unit measures.

The one machine-checkable guard against presenting a mass and a count as two
estimates of one quantity. The interface is three-valued on purpose: the reference
corpus holds 2,305 distinct unit strings whose 45 commonest cover 64 per cent of
entries, so "unrecognised" is a permanent state rather than a gap to be closed.
"""

from __future__ import annotations

import pytest

from scinumbers_ask.units import comparable, dimension, dimensions_of


@pytest.mark.parametrize(
    ("units", "expected"),
    [
        ("μm", "length"),
        ("nm", "length"),
        ("μm^3", "volume"),
        ("mL", "volume"),
        ("μg", "mass"),
        ("kDa", "mass"),
        ("molecules/cell", "count"),
        ("bp", "count"),
        ("Hours", "time"),
        ("min", "time"),
        ("Unitless", "dimensionless"),
        ("%", "dimensionless"),
        ("mM", "concentration"),
    ],
)
def test_a_recognised_unit_names_what_it_measures(units, expected):
    assert dimension(units) == expected


@pytest.mark.parametrize("units", ["N/A", "", "1/min", "sec^-1", "μm^2/sec", "kJ/mol", "mV"])
def test_an_unrecognised_unit_is_not_guessed_at(units):
    """None is not "dimensionless". Filing what nobody classified under a shared
    bucket would make two unrelated entries look like they share a dimension."""
    assert dimension(units) is None


def test_case_tells_millimolar_from_millimetres():
    """The corpus distinguishes them by case alone, so case cannot be folded away."""
    assert dimension("mM") == "concentration"
    assert dimension("mm") == "length"
    assert dimension("M") == "concentration"
    assert dimension("m") == "length"


def test_a_capital_s_is_not_a_second():
    """Lowercasing files siemens and Svedbergs under time. The corpus holds one
    sedimentation coefficient in "S" and two neuron conductances in "nS"; read as
    seconds, each becomes comparable with a duration."""
    assert dimension("S") is None
    assert dimension("nS") is None
    assert dimension("s") == "time"
    assert dimension("ns") == "time"


def test_a_mass_and_a_count_are_not_comparable():
    """The pair the requirement names. Presented as a range they read as an
    estimate spanning four orders of magnitude, and no arithmetic on them means
    anything."""
    assert comparable("μg", "molecules/cell") is False
    assert comparable("μg", "unitless") is False


def test_two_scales_of_one_quantity_are_comparable():
    assert comparable("μm", "nm") is True
    assert comparable("kDa", "μg") is True


def test_comparability_is_unknown_when_either_unit_is():
    """Not comparable, not incomparable. Claiming either would be a guess, and the
    one that matters is the false claim of compatibility."""
    assert comparable("μm", "1/min") is None
    assert comparable("N/A", "N/A") is None


def test_a_shared_dimension_is_a_floor_and_not_a_proof():
    """A percentage and a fold-change are both dimensionless and are still not each
    other's alternative. Documented here so nobody reads comparable() as more than
    it is."""
    assert comparable("%", "Fold") is True


def test_unrecognised_units_contribute_no_dimension():
    assert dimensions_of(["μg", "unitless", "nm", "N/A", "1/min"]) == (
        "dimensionless",
        "length",
        "mass",
    )
    assert dimensions_of(["N/A", "kJ/mol"]) == ()


def test_a_spelled_out_dalton_is_a_mass_like_its_symbol():
    """`kda` was in the table and `kDalton` was not, so the corpus's seven
    `kDalton` entries classified as nothing at all. Both spellings of one unit
    must not disagree."""
    for spelling in ("kDa", "kDalton", "Kdalton", "kilodalton", "Daltons", "megadalton"):
        assert dimension(spelling) == "mass", spelling


def test_a_mass_is_incompatible_with_a_length_rather_than_unknown():
    """The case found on the reviewer page of 2026-09-04: an answer offered
    2,700 kDa as the top of a range of nanometres, and this returned None -- so
    the one check that should have refused the comparison said nothing."""
    assert comparable("nm", "kDalton") is False
    assert comparable("kDalton", "nm^3") is False


def test_a_per_cell_count_matches_the_other_spellings_of_itself():
    """`Copies/cell` classified and `ribosomes/cell` did not, so two entries
    counting the same kind of thing per cell were not comparable."""
    assert dimension("ribosomes/cell") == "count"
    assert dimension("Ribosomes/cell") == "count"
    assert dimension("atoms per cell") == "count"
    assert comparable("ribosomes/cell", "Copies/cell") is True


def test_an_amount_per_cell_is_not_promoted_to_a_count():
    """The other direction, and the reason `<X>/cell` is enumerated rather than
    matched by a rule. Under a blanket per-cell rule these become counts, and a
    mass per cell then compares compatible with a ribosome count -- 38 entries
    in the reference corpus. Unrecognised is the correct answer for them."""
    for unit in ("pg/cell", "fg/cell", "g/cell", "μL/cell"):
        assert dimension(unit) is None, unit
    assert comparable("pg/cell", "ribosomes/cell") is None


def test_a_rate_or_a_density_per_cell_is_not_a_count():
    """`ribosomes/cell` is a count; `Ribosomes/μm^3` is a number density and
    `ATP/cell/sec` is a rate. Adding the first must not drag in the others."""
    for unit in ("Ribosomes/μm^3", "ATP/cell/sec", "mol/cell/sec", "molecules/cell/sec"):
        assert dimension(unit) is None, unit
