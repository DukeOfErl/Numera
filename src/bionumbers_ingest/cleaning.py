"""Turn one raw parsed row (``{header: raw_html}``) into one canonical record.

Every quirk handled here is one the published export actually contains: markup
injected into cells, HTML entities, the Excel text-marker apostrophe on
``Range``, "Table link" URLs standing in for a scalar, six range notations, and
the two micrometre glyphs.

Two rules govern the whole module, and both exist because the alternative fails
silently:

**Unescape before stripping, at one boundary.** The injected markup arrives
HTML-escaped, so stripping tags first matches nothing and the unescape then
*manufactures* a live tag that nothing strips again. Everything textual goes
through :func:`_clean_text`; no field does its own.

**Flag and count, never correct.** A cell we cannot read, or can read only
ambiguously, produces a record with the fields we could resolve and a flag
naming what we could not. Nothing is dropped and nothing is guessed. ADR-0230.
"""

from __future__ import annotations

import html
import re

from bionumbers_ingest.model import BioNumberRecord

# Angle brackets in this source are usually NOT markup. The export contains
# exactly one HTML element — <IMG SRC="/WF_SQL_XSRF.html">, 20,411 times — while
# 85 other angle-bracket tokens across 49 records are content: variable notation
# (<D>, <Csat>, <Chla>, <Raf/cell>) and the less-than sign in prose. A generic
# `<[^>]+>` eats from a `<` to the next `>`, which deletes whole clauses — a
# p-value, a rate comparison, a DOI fragment — out of `Comments`, a field the
# consumer sends to the model. So a tag is recognised only by a real HTML element
# name; anything else between angle brackets is text and survives.
_TAG_RE = re.compile(r"</?\s*([A-Za-z][A-Za-z0-9]*)\b[^>]*>")
_HTML_ELEMENTS = frozenset(
    """a abbr address area article aside audio b base bdi bdo big blockquote body br
    button canvas caption center cite code col colgroup data datalist dd del details
    dfn dialog div dl dt em embed fieldset figcaption figure font footer form h1 h2 h3
    h4 h5 h6 head header hgroup hr html i iframe img input ins kbd label legend li link
    main map mark menu meta meter nav noscript object ol optgroup option output p
    param picture pre progress q rp rt ruby s samp script section select slot small
    source span strike strong style sub summary sup svg table tbody td template
    textarea tfoot th thead time title tr track tt u ul var video wbr""".split()
)


def _is_html_tag(match: re.Match[str]) -> bool:
    return match.group(1).lower() in _HTML_ELEMENTS


def _strip_html_tags(text: str) -> tuple[str, bool]:
    """Remove real HTML tags; leave every other angle-bracket token in place."""
    found = False

    def drop(m: re.Match[str]) -> str:
        nonlocal found
        if _is_html_tag(m):
            found = True
            return ""
        return m.group()

    return _TAG_RE.sub(drop, text), found


_WS_RE = re.compile(r"\s+")
_MICRO_SIGN = "µ"  # µ MICRO SIGN
_GREEK_MU = "μ"  # μ GREEK SMALL LETTER MU
# signed mantissa with an optional signed exponent; sign disambiguated in _extract_numbers
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_URL_RE = re.compile(r"https?://\S+")
_PM_RE = re.compile(r"±|\+/-|\+-")  # plus/minus: ±X means value ± X
_NUM = r"\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
# a single "mean±sd" expression filling the whole cell (e.g. "-3.26±0.41"); the
# full-string anchor keeps multi-measurement cells from matching
_MEAN_SD_RE = re.compile(rf"^([-+]?{_NUM})\s*(?:±|\+/-|\+-)\s*({_NUM})$")
# what may stand between two bounds without being a second quantity: the
# separators _extract_numbers normalises to, and whitespace
_SEPARATORS_ONLY_RE = re.compile(r"^[\s;,\-–—±+/]*$")

#: `parse_flags` entries that mean the stored bounds may fuse two quantities.
#: The `range_fused` field is derived from exactly these; no other flag implies
#: it, and consumers read the field rather than this set.
FUSED_RANGE_FLAGS = frozenset({"range_multi_number", "range_prose_between_bounds"})


def _clean_text(raw: str) -> tuple[str, bool]:
    """Return (clean text, had_markup): unescape entities, strip tags, collapse space.

    Unescaping comes **first**, and the pair repeats until the text stops
    changing. In the published export the injected markup appears only as
    ``&lt;IMG SRC="/WF_SQL_XSRF.html"&gt;`` — 20,411 occurrences, not one literal
    ``<IMG`` — so stripping first matches nothing and the unescape then produces
    a live tag. `had_markup` is likewise determined from the unescaped text; read
    from the raw cell it would report zero on a corpus that is 71% contaminated.

    A tag is recognised only by a real HTML element name. Angle brackets in this
    source are mostly not markup, and a generic pattern deletes scientific
    content — see the comment on `_TAG_RE`.

    The loop terminates without needing a pass limit: neither unescaping nor
    stripping can lengthen the string, and a pass that changes nothing is the
    exit condition, so length strictly decreases until it stabilises.
    """
    text = raw
    had_markup = False
    while True:
        unescaped = html.unescape(text)
        stripped, found = _strip_html_tags(unescaped)
        had_markup = had_markup or found
        if stripped == text:
            break
        text = stripped
    return _WS_RE.sub(" ", text).strip(), had_markup


def _text_or_none(raw: str | None) -> str | None:
    if raw is None:
        return None
    text, _ = _clean_text(raw)
    return text or None


def _normalize_units(text: str | None) -> str | None:
    """Fold the micro sign into the Greek mu.

    The direction matters and is asserted in the tests: the consumer's own corpus
    uses the Greek letter, so normalising the other way would make every unit
    comparison miss while the strings looked identical on screen.
    """
    if text is None:
        return None
    return text.replace(_MICRO_SIGN, _GREEK_MU)


def _numbers_with_spans(text: str) -> tuple[str, list[tuple[float, int, int]]]:
    """Return (normalised text, [(value, start, end)]) for every number in it.

    Spans are offsets into the *returned* text, not the argument, because the
    separator normalisation below shifts positions. Callers that reason about
    what stands between two numbers must use both halves of this result.

    A hyphen is a range separator only where it directly follows a digit, so
    ``1-1.1`` yields two numbers while ``-70`` yields one negative one and
    ``-90 to -60`` yields two negatives. Exponents are captured whole, so the
    sign in ``1e-3`` is never mistaken for a separator.
    """
    # unicode minus -> ASCII minus (a sign); en/em dashes -> ';' (a separator
    # that, unlike a space, hides the preceding digit from the sign test)
    text = text.replace("−", "-").replace("–", ";").replace("—", ";")
    text = re.sub(r"\bto\b", ";", text, flags=re.IGNORECASE)

    found: list[tuple[float, int, int]] = []
    for m in _NUM_RE.finditer(text):
        tok = m.group()
        if tok[0] in "+-":
            j = m.start() - 1
            while j >= 0 and text[j] == " ":
                j -= 1
            if j >= 0 and text[j].isdigit():  # sign is really a separator
                tok = tok[1:]
        found.append((float(tok), m.start(), m.end()))
    return text, found


def _extract_numbers(text: str) -> list[float]:
    """Every number in the cell, signs and separators disambiguated."""
    return [value for value, _, _ in _numbers_with_spans(text)[1]]


def _prose_stands_between_bounds(text: str, found: list[tuple[float, int, int]]) -> bool:
    """Does anything but a separator stand between the two numbers used as bounds?

    A second quantity named mid-cell ("7.4 one face 5.9 other face") is the case
    this catches. A trailing unit is not between the bounds and does not count,
    which is why the check is positional rather than a search of the whole cell.
    """
    if len(found) < 2:
        return False
    low = min(found, key=lambda t: t[0])
    high = max(found, key=lambda t: t[0])
    first, second = sorted((low, high), key=lambda t: t[1])
    return not _SEPARATORS_ONLY_RE.match(text[first[2] : second[1]])


def _parse_value(raw: str, flags: list[str]) -> float | None:
    text, _ = _clean_text(raw)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        nums = _extract_numbers(text)
        if nums:
            return nums[0]
        flags.append("value_unparsed")
        return None


def _parse_range(
    raw: str, value: float | None, flags: list[str]
) -> tuple[str | None, float | None, float | None, str | None]:
    """Return (range_raw, range_low, range_high, table_link).

    ``range_raw`` is the source cell with the apostrophe removed, captured
    *before* the link URL is taken out — see the field's own docstring on
    :class:`~bionumbers_ingest.model.BioNumberRecord` for why it stays that way.

    ``±Δ`` in this column is an uncertainty around ``value``, not a bound.
    """
    text, _ = _clean_text(raw)
    if not text:
        return None, None, None, None

    text = text.lstrip("'").strip()  # drop Excel text-marker
    range_raw = text or None

    table_link = None
    if "Table link" in text or _URL_RE.search(text):
        m = _URL_RE.search(text)
        if m:
            table_link = m.group()
            text = text[: m.start()]  # strip URL so its digits don't parse as numbers
        flags.append("range_is_link")
        text = re.sub(r"Table link\s*-?\s*", "", text).strip()

    if _PM_RE.search(text):
        flags.append("range_plus_minus")
        if value is not None:
            deltas = _extract_numbers(_PM_RE.sub(" ", text))
            if deltas:
                delta = abs(deltas[0])
                return range_raw, value - delta, value + delta, table_link
            return range_raw, None, None, table_link
        # no value column: recover a single embedded "mean±sd" cell if that's all it is
        m = _MEAN_SD_RE.match(text.strip())
        if m:
            mean, delta = float(m.group(1)), abs(float(m.group(2)))
            flags.append("range_mean_sd_embedded")
            return range_raw, mean - delta, mean + delta, table_link
        flags.append("range_plus_minus_no_value")
        return range_raw, None, None, table_link

    normalised, found = _numbers_with_spans(text)
    if found:
        # Bounds are the lowest and highest number in the cell, so a cell naming a
        # second quantity contributes a bound to the first. Flag it; never correct
        # it — the bounds below are unchanged.
        if len(found) > 2:
            flags.append("range_multi_number")
        if _prose_stands_between_bounds(normalised, found):
            flags.append("range_prose_between_bounds")
        values = [v for v, _, _ in found]
        return range_raw, min(values), max(values), table_link
    if table_link is None:
        flags.append("range_unparsed")
    return range_raw, None, None, table_link


def _split_keywords(raw: str | None) -> list[str]:
    text = _text_or_none(raw)
    if not text:
        return []
    return [kw.strip() for kw in text.split(",") if kw.strip()]


def is_data_row(raw: dict[str, str]) -> bool:
    """A real record has a numeric identifier.

    The export ends with HTML padding rows whose identifier cell is a
    non-breaking space and whose other cells are empty.
    """
    text, _ = _clean_text(raw.get("bion_id", ""))
    return text.isdigit()


def clean_row(raw: dict[str, str]) -> BioNumberRecord:
    """Clean one raw parsed row into a canonical record."""
    flags: list[str] = []

    # Markup anywhere in the row, judged from the unescaped text. Computed here
    # rather than per field so one row yields one flag.
    if any(_clean_text(v)[1] for v in raw.values()):
        flags.append("injected_html_removed")

    bnid_text, _ = _clean_text(raw.get("bion_id", ""))
    bnid = int(bnid_text)

    value = _parse_value(raw.get("Value", ""), flags)
    range_raw, range_low, range_high, table_link = _parse_range(raw.get("Range", ""), value, flags)

    if value is None and range_low is None and range_high is None:
        flags.append("no_scalar")

    return BioNumberRecord(
        bnid=bnid,
        property=_text_or_none(raw.get("Properties")),
        organism=_text_or_none(raw.get("Organism")),
        value=value,
        range_raw=range_raw,
        range_low=range_low,
        range_high=range_high,
        table_link=table_link,
        units=_normalize_units(_text_or_none(raw.get("Units"))),
        reference=_text_or_none(raw.get("Reference")),
        reference_pubmed_id=_text_or_none(raw.get("Reference PubMed ID")),
        primary_source=_text_or_none(raw.get("Primary Source")),
        primary_source_pubmed_id=_text_or_none(raw.get("Primary Source PubMed ID")),
        measurement_method=_text_or_none(raw.get("Measurement Method")),
        comments=_text_or_none(raw.get("Comments")),
        entered_by=_text_or_none(raw.get("Entered By")),
        keywords=_split_keywords(raw.get("Keywords")),
        parse_flags=flags,
        range_fused=bool(FUSED_RANGE_FLAGS.intersection(flags)),
    )
