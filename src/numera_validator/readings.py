"""What a reviewer typed as the value they read, compared with the value stored (ADR-0970).

The reading is free text written by a person at the first step, before the stored value is shown,
and people write the same number many ways: `39`, `39 min`, `39 ± 1 min`, `~39`, `about 39`,
`thirty-nine`, `60.3 million`, `60,300,000`, `5 x 10^-1`, `5e-1`, `um` for `µm`. A comparison that
read any of these as a disagreement would be a comparison of spelling. So both sides are reduced
to a number (or a range), an uncertainty, a unit and an approximation mark, through the same fold
the quote checker uses (`quotes.fold`) and the same unit registry the distractor uses, and then
compared loosely in the one direction that matters: a reading that names the stored quantity at
the reader's precision agrees with it.

Loose on purpose, and the looseness is stated here rather than spread: a reading is as precise as
the reader made it, so `39` agrees with a stored `39.2` and `39.2` with a stored `39`; `±` is
dropped on both sides; `~` and "about" are noted and otherwise ignored; a unit the reader left out
is not a disagreement; a unit that converts to the stored one is the same unit. What does not
agree: a different number, a range against a single value, or a unit of another dimension.

This is a tally and a hint to the reviewer, never a verdict: the verdict is theirs, given with both
values in front of them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from numera_validator.quotes import fold


class Agreement(StrEnum):
    """How the reading stands to the stored value. Closed, like every state here (ADR-1530)."""

    MATCHES = "MATCHES"
    """The same number at the reader's precision; the unit the same, convertible, or not given."""
    SAME_NUMBER_DIFFERENT_UNIT = "SAME_NUMBER_DIFFERENT_UNIT"
    """The digits agree and the units do not: `39 um` against `39 nm`, or `39 min` against
    `39 h`. The likeliest slip of a reader, and the one worth naming to them."""
    DIFFERS = "DIFFERS"
    UNREADABLE = "UNREADABLE"
    """No number could be read from the text."""


#: What each state says to the reviewer at the reveal. One line, no verdict in it.
AGREEMENT_LINES: dict[Agreement, str] = {
    Agreement.MATCHES: "Your reading matches the stored value.",
    Agreement.SAME_NUMBER_DIFFERENT_UNIT: (
        "Your reading has the stored number but a different unit."
    ),
    Agreement.DIFFERS: "Your reading differs from the stored value.",
    Agreement.UNREADABLE: "Your reading could not be read as a number.",
}

#: Under the box the reviewer types into. Says what is read, not what is required: anything with
#: a number in it is accepted, and the comparison does the rest.
HOW_TO_WRITE = (
    "The number as the text writes it, with ± and the unit if given — 39 ± 1 min, ~13,000, "
    "60.3 million, 5 × 10⁻¹ or 5e-1. A unit left out is not held against you."
)


@dataclass(frozen=True)
class Reading:
    """A value as parsed: one number, or the two ends of a range."""

    numbers: tuple[Decimal, ...]
    unit: str = ""
    """As written, folded, with a keyboard `u` for micro normalised to `μ`; empty when none."""
    uncertainty: Decimal | None = None
    approximate: bool = False
    """A `~`, `≈`, "about", "approximately", "circa" or "roughly" was written."""
    precision: int = 1
    """Significant digits of the least precise number written, read off the digits."""


_APPROX = re.compile(
    r"^\s*(?:~|∼|≈|about|approximately|approx\.?|circa|ca\.|roughly|around|some)\s*", re.I
)
#: The optional caret is the fold's: a paper's superscript `+/-` comes back as `^+/-`.
_UNCERTAINTY = re.compile(r"\s*\^?\s*(?:±|\+/-|\+-)\s*")
#: `5 x 10^-1`, `5e-1`, and a bare `10^-3` (a mantissa of one). The fold has already turned `×`
#: into `x` and a superscript into `^`.
_SCIENTIFIC = re.compile(
    r"(?:(?P<mantissa>[+-]?\d+(?:\.\d+)?)\s*(?:x\s*10\s*\^?\s*|e)|\b10\s*\^\s*)"
    r"(?P<exponent>[+-]?\d+)",
    re.I,
)
_DIGITS = r"[+-]?\d+(?:\.\d+)?(?:E[+-]?\d+)?"
_RANGE = re.compile(rf"(?P<low>{_DIGITS})\s*(?:-|to)\s*(?P<high>{_DIGITS})")
#: Where a unit ends: a parenthesis, a bracket, a semicolon, or an "and" joining a second value.
_UNIT_END = re.compile(r"\s*(?:\(|\[|;|\band\b).*$", re.S)
_NUMBER = re.compile(_DIGITS)
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")

_SMALL: dict[str, Decimal] = {
    word: Decimal(n)
    for word, n in {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
        "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
        "seventy": 70, "eighty": 80, "ninety": 90,
    }.items()
}  # fmt: skip
_SMALL["half"] = Decimal("0.5")
_SMALL["quarter"] = Decimal("0.25")
_MAGNITUDE: dict[str, int] = {
    "hundred": 100, "thousand": 10**3, "million": 10**6, "billion": 10**9, "trillion": 10**12,
}  # fmt: skip
_WORDS = re.compile(
    r"^\s*((?:(?:" + "|".join(sorted(_SMALL, key=len, reverse=True)) + r")(?:[\s-]+|\b))+)", re.I
)
_SCALE = re.compile(r"^\s*(" + "|".join(_MAGNITUDE) + r")\b\s*", re.I)
#: `u` typed for micro, before a unit letter: `um`, `uM`, `ug`, `uL`, `us`. Not `u` alone.
_KEYBOARD_MICRO = re.compile(r"\bu(?=[mMgGlLsS]\b)")


def parse(text: str) -> Reading | None:
    """Read a value a person or a paper wrote. None when no number is in it."""
    rest = fold(text).strip()
    approximate = bool(_APPROX.match(rest))
    rest = _APPROX.sub("", rest, count=1)
    rest = _words_to_digits(rest)
    rest = _THOUSANDS.sub("", rest)
    rest = _SCIENTIFIC.sub(_plain, rest)
    first = _NUMBER.search(rest)
    if not first:
        return None

    uncertainty: Decimal | None = None
    tail = ""
    halves = _UNCERTAINTY.split(rest, maxsplit=1)
    if len(halves) == 2:
        rest, after = halves
        found = _NUMBER.search(after)
        if found:
            uncertainty = _decimal(found.group(0))
            tail = after[found.end() :]
        else:
            tail = after

    # A range starts at the first number: `increased from 70 to 150` is one, and a later
    # `30–80` in the sentence after the value is not.
    span = _RANGE.match(rest, first.start())
    if span:
        numbers = [_decimal(span["low"]), _decimal(span["high"])]
        remainder = rest[span.end() :]
    else:
        numbers = [_decimal(first.group(0))]
        remainder = rest[first.end() :]
    precision = min(_digits(n) for n in numbers)

    remainder = f"{remainder} {tail}"
    scale = _SCALE.match(remainder)
    if scale:
        factor = Decimal(_MAGNITUDE[scale.group(1).lower()])
        numbers = [n * factor for n in numbers]
        if uncertainty is not None:
            uncertainty *= factor
        remainder = remainder[scale.end() :]
    return Reading(tuple(numbers), _unit(remainder), uncertainty, approximate, precision)


def compare(read: str, value: str, unit: str = "") -> Agreement:
    """How a reviewer's reading stands to the stored value and unit."""
    reading = parse(read)
    if reading is None:
        return Agreement.UNREADABLE
    # The stored value and unit are two fields; put together they parse as a reading would.
    stored = parse(f"{value} {unit}".strip())
    if stored is None or len(reading.numbers) != len(stored.numbers):
        return Agreement.DIFFERS

    precision = min(reading.precision, stored.precision)
    pairs = list(zip(reading.numbers, stored.numbers, strict=True))
    same_digits = all(_close(a, b, precision) for a, b in pairs)
    if not reading.unit or not stored.unit or _same_unit(reading.unit, stored.unit):
        return Agreement.MATCHES if same_digits else Agreement.DIFFERS

    factor = _conversion(reading.unit, stored.unit)
    if factor is not None:
        if all(_close(a * factor, b, precision) for a, b in pairs):
            return Agreement.MATCHES
    # Another dimension, a unit the registry does not know, or a convertible unit that does
    # not land on the stored number: the digits decide, and the unit is named as the difference.
    return Agreement.SAME_NUMBER_DIFFERENT_UNIT if same_digits else Agreement.DIFFERS


def line_for(agreement: Agreement | str | None) -> str:
    """The sentence the page shows for a recorded agreement; empty where none was recorded."""
    return "" if agreement is None else AGREEMENT_LINES[Agreement(agreement)]


def _plain(match: re.Match) -> str:
    """`5 x 10^-1` as `5E-1`, `10^-3` as `1E-3`: the form `_NUMBER` reads and `Decimal` keeps
    the written digits of, so `1.2e9` stays two digits of precision and not ten."""
    return f"{match['mantissa'] or '1'}E{match['exponent']}"


def _words_to_digits(text: str) -> str:
    """`thirty-nine min` -> `39 min`; `two hundred` -> `200` (the scale is read later). Only a
    leading run of number words is read: a unit or a quantity name is never one of them."""
    match = _WORDS.match(text)
    if not match:
        return text
    total = sum(
        (_SMALL[word.lower()] for word in re.split(r"[\s-]+", match.group(1).strip()) if word),
        Decimal(0),
    )
    return f"{total} {text[match.end() :]}"


def _decimal(text: str) -> Decimal:
    try:
        return Decimal(text)
    except InvalidOperation:  # a sign with no digits, which the regexes do not admit
        return Decimal(0)


def _digits(number: Decimal) -> int:
    """Significant digits as written: `39` is 2, `39.0` is 3, `0.045` is 2, `187000` is 6,
    `1.2E9` is 2."""
    return max(len(number.as_tuple().digits), 1)


def _close(a: Decimal, b: Decimal, precision: int) -> bool:
    """Equal when rounded to `precision` significant digits -- the reader's precision, since a
    reader who wrote `39` for a stored `39.2` read it correctly."""
    if a == b:
        return True
    if a == 0 or b == 0:
        return False
    step = Decimal(1).scaleb(max(abs(a), abs(b)).adjusted() - precision + 1)
    return abs(a - b) <= step / 2


def _unit(text: str) -> str:
    """The unit as written: folded, trimmed of punctuation, `per` as `/`, a keyboard `u` for
    micro as `μ`."""
    # `10-min`, `95-µm-sized`: a hyphen between the number and its unit is a space.
    unit = _UNIT_END.sub("", text.strip().lstrip("-").strip())
    unit = re.sub(r"\s+", " ", unit.strip(",;:.()[]").strip())
    unit = re.sub(r"\s+per\s+", "/", unit)
    return _KEYBOARD_MICRO.sub("μ", unit)


def _same_unit(read: str, stored: str) -> bool:
    """The stored unit, or the stored unit inside what was read: `nm wide` and
    `molecularly distinct segments` carry the unit and some of the sentence with it."""
    if read == stored:
        return True
    return re.search(rf"(?<![\w/]){re.escape(stored)}(?![\w/])", read) is not None


def _conversion(from_unit: str, to_unit: str) -> Decimal | None:
    """How many `to_unit` one `from_unit` is, or None when pint cannot say."""
    from numera_validator.distractor import _registry  # the one registry, built on first use

    try:
        quantity = _registry().Quantity(1.0, from_unit.replace("μ", "µ"))
        return Decimal(str(quantity.to(to_unit.replace("μ", "µ")).magnitude))
    except Exception:  # pint raises several unrelated types for a unit it does not know
        return None
