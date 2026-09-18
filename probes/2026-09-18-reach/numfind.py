"""Does a corpus value appear in a body of source text?

ADR-0040 discarded string-level pre-classification as a *pre-filter deciding what
to probe*, on two named false negatives: "19,042" (thousands comma) and
"46.4298 kDa" (unit-prefix form). This module is the same idea used for a
different job -- a population-level count with its error measured -- so both of
those forms are generated explicitly.

It answers "do these digits occur", never "is this the same quantity". A match is
a candidate for a human or an agent to judge, which is why `find` returns the
surface form and its context rather than a bare boolean.

**A short form has no discriminating power, and that is the governing
constraint.** The first version of this module generated rescaled, 2-significant-
figure forms, so 19043 produced "19" and 87654321 produced "88" -- both of which
occur in any paper. The canaries in calibrate.py caught it. The rule that
replaced it: a form of fewer than MIN_DIGITS digit characters is only a hit when
a unit token sits beside it. Values like 65 minutes and 40% cannot be found on
their digits alone by anything, and pretending otherwise is how a count of
"present" becomes a count of coincidences.

Which direction is cheap: a missed occurrence understates how often a value is
stated in its source, which understates how reachable the corpus is. A spurious
occurrence overstates it, and would make the validator look feasible where it is
not. So the uncertainty is pushed into false negatives deliberately, and the
measured false-negative rate is reported with any figure derived from this.
"""

import re
import unicodedata

MIN_DIGITS = 3  # below this, a form needs a unit beside it to count
FLOOR_DIGITS = 2  # below this a form is dropped outright: one digit is never evidence
UNIT_WINDOW = 30  # chars either side within which a unit token must appear

_FOLD = {
    "−": "-",  # MINUS SIGN
    "–": "-",  # EN DASH
    "—": "-",  # EM DASH
    "×": "x",  # MULTIPLICATION SIGN
    " ": " ",  # NO-BREAK SPACE
    " ": " ",  # THIN SPACE
    " ": " ",  # NARROW NO-BREAK SPACE
    "µ": "u",  # MICRO SIGN
    "μ": "u",  # GREEK SMALL LETTER MU
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = "".join(_FOLD.get(c, c) for c in s)
    return re.sub(r"\s+", " ", s)


def strip_markup(s: str) -> str:
    """XML/HTML out. Superscripts become ^n so 10<sup>9</sup> stays readable."""
    s = re.sub(r"<sup>\s*([-\d.]+)\s*</sup>", r"^\1", s)
    s = re.sub(r"<[^>]+>", " ", s)
    for ent, ch in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        s = s.replace(ent, ch)
    return norm(s)


def _fmt(x: float) -> str:
    s = f"{x:.10f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _digits(form: str) -> int:
    """Discriminating power: how many digit characters the form carries."""
    return len(re.sub(r"\D", "", form).lstrip("0"))


def surface_forms(v: float) -> dict[str, str]:
    """Plausible ways `v` could be written. form -> why it is generated.

    Deliberately NOT generated: a rescaling combined with a rounding. Each
    transformation may drop digits; applying two drops enough that the result
    matches unrelated text (see the module docstring).
    """
    out: dict[str, str] = {}

    def add(s: str, why: str) -> None:
        if s and s not in out:
            out[s] = why

    add(_fmt(v), "exact")

    if abs(v) >= 1000:
        ip = int(abs(v))
        add(f"{ip:,}", "thousands comma")
        if v != ip:
            frac = _fmt(abs(v) - ip).lstrip("0")
            add(f"{ip:,}{frac}", "thousands comma + decimal")

    # Rounding alone: papers round, curators do not. Safe at 2 sig figs
    # because rounding pads zeros rather than shortening (19043 -> 19000, still
    # five digits); it is only rounding *combined with* rescaling that produced
    # the promiscuous "19". Short results are caught by the MIN_DIGITS rule.
    for sig in (2, 3, 4):
        try:
            r = float(f"%.{sig}g" % v)
        except (ValueError, OverflowError):
            continue
        add(_fmt(r), f"{sig} sig figs")
        if abs(r) >= 1000:
            add(f"{int(abs(r)):,}", f"{sig} sig figs, comma")

    # Rescaling alone: a decimal-point shift keeping every digit (Da -> kDa).
    for factor, label in (
        (1e3, "kilo"),
        (1e-3, "milli"),
        (1e6, "mega"),
        (1e-6, "micro"),
        (1e9, "giga"),
    ):
        r = v / factor
        if 0.001 <= abs(r) < 1e6:
            add(_fmt(r), f"rescaled {label}")

    # Scientific notation, as papers print it. Mantissa keeps >=2 digits.
    if v != 0:
        exp = len(str(int(abs(v)))) - 1 if abs(v) >= 1 else 0
        mant = v / (10**exp)
        if abs(v) >= 1000 or abs(v) < 0.01:
            for sig in (3, 4):
                m = _fmt(float(f"%.{sig}g" % mant))
                add(f"{m} x 10^{exp}", f"scientific, {sig} sig figs")
                add(f"{m}x10^{exp}", f"scientific compact, {sig} sig figs")

    return out


def _unit_tokens(units: str | None) -> list[str]:
    """Searchable fragments of a unit string. 'fg C/um^3' -> ['fg','c','um']."""
    if not units or units.strip().lower() in {"unitless", "dimensionless", "none", ""}:
        return []
    u = norm(units).lower()
    stop = {"of", "per", "the", "and", "in", "at"}
    toks = [t for t in re.split(r"[^a-z]+", u) if len(t) >= 2 and t not in stop]
    # Three characters, because the *paper* usually writes the shorter form: a
    # corpus "minutes" has to match a paper's "min", so a 4-char "minu" prefix
    # matches nothing. Calibration case 109252 is exactly this and caught it.
    return [t[:3] for t in toks][:6]


def find(value: float, text: str, units: str | None = None, window: int = 70) -> list[dict]:
    """Every surface form of `value` occurring in `text`, with context.

    A form must stand alone as a number: not preceded or followed by a digit, so
    "65" does not match inside "1650". A form carrying fewer than MIN_DIGITS
    digits additionally requires a unit token within UNIT_WINDOW characters --
    without that it is not evidence of anything.
    """
    hits = []
    toks = _unit_tokens(units)
    low = text.lower()
    for form, why in surface_forms(value).items():
        if _digits(form) < FLOOR_DIGITS:
            # "1000" rescaled to "1" is the rounding-plus-rescaling failure in
            # another guise: a single digit sits beside a unit on every page.
            continue
        weak = _digits(form) < MIN_DIGITS
        if weak and not toks:
            continue  # unitless and too short to discriminate: unfindable, say so
        pat = re.compile(r"(?<![\d.,])" + re.escape(form) + r"(?![\d])")
        for m in pat.finditer(text):
            if weak:
                near = low[max(0, m.start() - UNIT_WINDOW) : m.end() + UNIT_WINDOW]
                if not any(t in near for t in toks):
                    continue
            hits.append(
                {
                    "form": form,
                    "why": why + (" [unit-confirmed]" if weak else ""),
                    "weak": weak,
                    "at": m.start(),
                    "context": text[max(0, m.start() - window) : m.end() + window],
                }
            )
    return hits


def present(value: float, text: str, units: str | None = None) -> bool:
    return bool(find(value, text, units))
