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
