"""A reviewer's typed value against the stored one: every way a person writes a number.

The cases are written from the requirement -- what a reader could type and what the stored
entry holds -- not from running the parser; a wrong expectation here fails the test rather
than the reviewer.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from bionumbers import readings
from bionumbers.readings import Agreement, compare, parse

M, U, D, X = (
    Agreement.MATCHES,
    Agreement.SAME_NUMBER_DIFFERENT_UNIT,
    Agreement.DIFFERS,
    Agreement.UNREADABLE,
)


# --- parsing -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "numbers", "unit", "uncertainty", "approximate"),
    [
        ("39", ["39"], "", None, False),
        ("39 min", ["39"], "min", None, False),
        ("39 ± 1 min", ["39"], "min", "1", False),
        ("39 +/- 1 min", ["39"], "min", "1", False),
        ("39+-1", ["39"], "", "1", False),
        ("~13,000", ["13000"], "", None, True),
        ("about 13,000 cells", ["13000"], "cells", None, True),
        ("≈ 0.7 μM", ["0.7"], "μM", None, True),
        ("60.3 million", ["60300000"], "", None, False),
        (
            "60.3 million protein molecules/cell",
            ["60300000"],
            "protein molecules/cell",
            None,
            False,
        ),
        ("187,000 ± 56,000", ["187000"], "", "56000", False),
        ("5 × 10⁻¹ m", ["0.5"], "m", None, False),
        ("5 x 10^-1 m", ["0.5"], "m", None, False),
        ("5e-1 m", ["0.5"], "m", None, False),
        ("1.2E+09 bp", ["1200000000"], "bp", None, False),
        ("20–40 s", ["20", "40"], "s", None, False),
        ("20 to 40 s", ["20", "40"], "s", None, False),
        ("2.3-2.5 μm", ["2.3", "2.5"], "μm", None, False),
        ("thirty-nine min", ["39"], "min", None, False),
        ("twelve", ["12"], "", None, False),
        ("about twelve", ["12"], "", None, True),
        ("~ thirty-nine min", ["39"], "min", None, True),
        ("two hundred", ["200"], "", None, False),
        ("half", ["0.5"], "", None, False),
        ("0.61 ± 0.28 actin patches µm⁻²", ["0.61"], "actin patches μm^-2", "0.28", False),
        ("39 um", ["39"], "μm", None, False),
        ("0.7 uM", ["0.7"], "μM", None, False),
        ("lower than 20 nM", ["20"], "nM", None, False),
        ("increased from 70 to 150 dyn/cm²", ["70", "150"], "dyn/cm^2", None, False),
        ("0.16 ± 0.10 μM ([ref 14]) and 0.17 μM", ["0.16"], "μM", "0.10", False),
        ("103 filaments per µm (sdm = 17; 20 measurements)", ["103"], "filaments/μm", None, False),
        ("570 ^+/− 260 s", ["570"], "s", "260", False),
        ("~10-min", ["10"], "min", None, True),
        ("95-µm–sized", ["95"], "μm-sized", None, False),
        ("10⁻³ M", ["0.001"], "M", None, False),
        ("10^6 cells", ["1000000"], "cells", None, False),
        ("39 min (n = 3-5)", ["39"], "min", None, False),
        ("39 (30–45) min", ["39"], "", None, False),
        ("(94 ± 7) °C", ["94"], "°C", "7", False),
        ("T = (170 ± 2) K", ["170"], "K", "2", False),
        ("∼(5 × 10²) nm²/s", ["500"], "nm^2/s", None, True),
    ],
)
def test_a_value_as_a_person_writes_it_is_read(text, numbers, unit, uncertainty, approximate):
    reading = parse(text)
    assert reading is not None
    assert list(reading.numbers) == [Decimal(n) for n in numbers]
    assert reading.unit == unit
    assert reading.uncertainty == (None if uncertainty is None else Decimal(uncertainty))
    assert reading.approximate is approximate


@pytest.mark.parametrize("text", ["", "   ", "no value given", "min", "μM"])
def test_text_with_no_number_is_not_a_reading(text):
    assert parse(text) is None


@pytest.mark.parametrize(
    ("text", "precision"),
    [("39", 2), ("39.0", 3), ("0.045", 2), ("187000", 6), ("1", 1), ("1.2e9", 2), ("5 × 10⁵", 1)],
)
def test_precision_is_the_digits_written(text, precision):
    assert parse(text).precision == precision


# --- comparing -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("read", "value", "unit", "expected"),
    [
        # The same number, written differently.
        ("39", "39", "min", M),
        ("39 min", "39", "min", M),
        ("39 ± 1 min", "39 ± 1", "min", M),
        ("39", "39 ± 1", "min", M),
        ("thirty-nine", "39", "min", M),
        ("~13,000", "13,000", "", M),
        ("13000", "~13,000", "", M),
        ("60.3 million", "60.3 million", "protein molecules/cell", M),
        ("60,300,000", "60.3 million", "protein molecules/cell", M),
        ("60.3 million protein molecules per cell", "60.3 million", "protein molecules/cell", M),
        ("5e-1", "5 × 10⁻¹", "m", M),
        ("0.5 m", "5 × 10⁻¹", "m", M),
        ("1.2 x 10^9", "1.23 × 10⁹", "bp", M),
        ("5 × 10⁵", "4.8 × 10⁵", "cells", M),
        ("0.001", "10⁻³", "M", M),
        ("1e-6 M", "10⁻⁶", "M", M),
        ("39", "39 (30–45)", "min", M),
        ("39 min (n = 3-5)", "39", "min", M),
        ("(94 ± 7) °C", "94 ± 7", "°C", M),
        (
            "about 53 million proteins, with 90% confidence limits of 30–80 million",
            "53 million (30–80 million)",
            "proteins per cell",
            M,
        ),
        ("3.72 pg per cell", "3.72 (1.9–5.6)", "pg per cell", M),
        ("20–40", "20-40", "s", M),
        ("20 to 40 s", "20–40", "s", M),
        ("increased from 70 to 150 dyn/cm²", "70 to 150", "dyn/cm²", M),
        ("0.16 ± 0.10 μM ([ref 14]) and 0.17 μM ([ref 15])", "0.16 ± 0.10", "μM", M),
        (
            "103 filaments per µm (sdm = 17; 20 measurements in 5 cells)",
            "103",
            "filaments per µm",
            M,
        ),
        ("570 +/− 260 s", "570 ^+/− 260", "s", M),
        # The unit and some of the sentence with it.
        ("35–40 nm wide", "35–40", "nm", M),
        ("6 molecularly distinct segments", "6", "segments", M),
        ("∼10-min", "∼10", "min", M),
        ("95-µm–sized", "95", "µm", M),
        ("0.38 of a normalized cell length", "0.38", "normalized cell length", M),
        ("39 nm/s", "39", "nm", U),
        # The reader's precision, or the paper's, whichever is coarser.
        ("39", "39.2", "min", M),
        ("39.2", "39", "min", M),
        ("840,173,815", "840,173,815", "bp", M),
        ("0.6", "0.61 ± 0.16", "μm", M),
        # A convertible unit is the same unit.
        ("0.65 h", "39", "min", M),
        ("2340 s", "39", "min", M),
        ("39 um", "39", "μm", M),
        ("0.7 uM", "0.7", "μM", M),
        ("700 nM", "0.7", "μM", M),
        # The digits agree and the unit does not.
        ("39 um", "39", "nm", U),
        ("39 h", "39", "min", U),
        ("0.7 mM", "0.7", "μM", U),
        ("39 widgets", "39", "min", U),
        # A different number.
        ("21", "39", "min", D),
        ("21 min", "39", "min", D),
        ("0.45 ± 0.11 μm", "0.6", "μm", D),
        ("30", "20–40", "s", D),
        ("20–40", "30", "s", D),
        ("819,865,861", "840,173,815", "bp", D),
        ("1.43", "2.3–2.5", "μm", D),
        ("1.1 x 10^9", "1.23 × 10⁹", "bp", D),
        ("~1 μM", "0.02 ± 0.01", "μM", D),
        # Nothing to compare.
        ("", "39", "min", X),
        ("the first one", "39", "min", X),
    ],
)
def test_how_a_reading_stands_to_the_stored_value(read, value, unit, expected):
    assert compare(read, value, unit) is expected


def test_every_agreement_has_a_line_and_none_has_a_verdict_in_it():
    for agreement in Agreement:
        line = readings.line_for(agreement)
        assert line.startswith("Your reading")
        assert "approve" not in line.lower()
    assert readings.line_for(None) == ""
    assert readings.line_for("MATCHES") == readings.AGREEMENT_LINES[Agreement.MATCHES]
