"""Is a reported QUOTE a literal substring of the source XML?

Normalisation is deliberately minimal and one-directional: collapse whitespace,
fold the unicode dashes/quotes/spaces that XML and a model's copy-paste differ on,
and strip XML tags from the source so an inline <italic> inside a sentence does not
count against the quote. Anything beyond that would start excusing paraphrase,
which is the thing being tested.
"""

import re
import sys
import unicodedata

# Written as \u escapes rather than literal characters: this table is the whole
# looseness budget of the check, and a character that is mangled in transit
# (through a message, a clipboard, an editor's normalisation) silently widens or
# narrows it with nothing to show. Five dashes, four quotes, four spaces, the
# multiplication sign and the minus sign.
FOLD = {
    "\u2010": "-",  # HYPHEN
    "\u2011": "-",  # NON-BREAKING HYPHEN
    "\u2012": "-",  # FIGURE DASH
    "\u2013": "-",  # EN DASH
    "\u2014": "-",  # EM DASH
    "\u2018": "'",  # LEFT SINGLE QUOTATION MARK
    "\u2019": "'",  # RIGHT SINGLE QUOTATION MARK
    "\u201c": '"',  # LEFT DOUBLE QUOTATION MARK
    "\u201d": '"',  # RIGHT DOUBLE QUOTATION MARK
    "\u00a0": " ",  # NO-BREAK SPACE
    "\u2007": " ",  # FIGURE SPACE
    "\u2009": " ",  # THIN SPACE
    "\u202f": " ",  # NARROW NO-BREAK SPACE
    "\u00d7": "x",  # MULTIPLICATION SIGN
    "\u2212": "-",  # MINUS SIGN
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = "".join(FOLD.get(c, c) for c in s)
    return re.sub(r"\s+", " ", s).strip()


def source_text(path: str) -> str:
    raw = open(path, encoding="utf8", errors="replace").read()
    stripped = re.sub(r"<[^>]+>", " ", raw)
    for ent, ch in (
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#x2013;", "-"),
    ):
        stripped = stripped.replace(ent, ch)
    return norm(stripped)


if __name__ == "__main__":
    xml, quote = sys.argv[1], sys.stdin.read()
    # strip tags from the QUOTE too: an agent that pasted raw JATS is being more
    # literal, not less, and the source side is already tag-stripped.
    quote = re.sub(r"<[^>]+>", " ", quote)
    for ent, ch in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        quote = quote.replace(ent, ch)
    q, src = norm(quote), source_text(xml)
    if not q:
        print("EMPTY_QUOTE")
        sys.exit(0)
    if q in src:
        print("VERBATIM_OK")
        sys.exit(0)
    lo, hi = 0, len(q)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if q[:mid] in src:
            lo = mid
        else:
            hi = mid - 1
    print(f"NOT_VERBATIM (longest matching prefix: {lo}/{len(q)} chars)")
    print(f"  diverges at: ...{q[max(0, lo - 40) : lo + 60]!r}")
