"""Re-record the Europe PMC fixtures used by the retrieval tests.

The test suite runs offline against these recordings. Run this only to refresh them:

    uv run python tests/fixtures/capture_europepmc.py

Each recording is a real response, trimmed of nothing, so the tests exercise the shapes the API
actually returns rather than shapes we imagined.
"""

import json
from pathlib import Path

import httpx

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
HERE = Path(__file__).parent / "europepmc"

SEARCHES = {
    # Open-access article with full text in PMC.
    "search_open_access.json": "EXT_ID:9722616 AND SRC:MED",
    # Indexed, but not open access and no PMC record.
    "search_paywalled.json": "EXT_ID:6771086 AND SRC:MED",
    # Identifier that Europe PMC does not index at all.
    "search_not_indexed.json": "EXT_ID:99999999 AND SRC:MED",
    # A bioRxiv preprint, found by title the way preprint fallback finds one.
    # Note the Greek alpha: transliterating it to ASCII returns zero hits, and the source title
    # additionally carries <i> markup that has to be stripped before it is used as a query.
    "search_preprint_by_title.json": (
        "SRC:PPR AND TITLE:"
        '"Gαi2 coordinates neuronal microtubule and neurofilament networks '
        'to regulate axon initiation in vivo"'
    ),
    # A preprint whose record exists but which serves no JATS XML (see fulltext_missing below).
    "search_preprint_without_xml.json": "SRC:PPR AND EXT_ID:PPR1090496",
}

FULL_TEXTS = {
    "fulltext_PMC2132865.xml": "PMC2132865",
    "fulltext_PPR1218639.xml": "PPR1218639",
    # The two papers the 2026-09-18 research inspected, both CC BY 4.0: a brief report with no
    # `<back>` element, no methods section and a bare XML declaration; and a research article
    # with XHTML tables that carry both micro-sign code points (U+00B5 and U+03BC).
    "fulltext_PMC13340094.xml": "PMC13340094",
    "fulltext_PMC13248727.xml": "PMC13248727",
}

# Europe PMC flags this preprint as having full text, yet serves no XML for it. The body *is*
# recorded now: the client decides "no XML" from the body rather than the status, because the
# status moved from 404 to 500 between recordings, and the test that proves the body is what
# gets read needs the real one.
FULL_TEXT_MISSING = "PPR1090496"
FULL_TEXT_MISSING_FIXTURE = "fulltext_missing_PPR1090496.json"

USER_AGENT = "BioNumbers-validator/0.1 (research prototype; fixtures)"


def main() -> None:
    HERE.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60.0, headers={"User-Agent": USER_AGENT}) as client:
        for name, query in SEARCHES.items():
            response = client.get(
                f"{BASE}/search",
                params={"query": query, "resultType": "core", "format": "json"},
            )
            response.raise_for_status()
            (HERE / name).write_text(
                json.dumps(response.json(), indent=1, ensure_ascii=False), encoding="utf-8"
            )
            print(f"{name}: {len(response.text)} bytes")

        for name, article_id in FULL_TEXTS.items():
            response = client.get(f"{BASE}/{article_id}/fullTextXML")
            print(f"{name}: HTTP {response.status_code}, {len(response.text)} bytes")
            response.raise_for_status()
            (HERE / name).write_text(response.text, encoding="utf-8")

        missing = client.get(f"{BASE}/{FULL_TEXT_MISSING}/fullTextXML")
        print(f"{FULL_TEXT_MISSING} (expected to have no XML): HTTP {missing.status_code}")
        if missing.is_success:
            print("  WARNING: this preprint now serves XML; pick another for the no-XML test")
        else:
            (HERE / FULL_TEXT_MISSING_FIXTURE).write_text(missing.text, encoding="utf-8")
            if missing.status_code != 500:
                print(
                    "  NOTE: the status moved again; the client reads the body, so nothing breaks"
                )


if __name__ == "__main__":
    main()
