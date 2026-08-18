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
}

# Europe PMC flags these as having full text, yet serves no XML for them. Recorded as a status
# code rather than a body, because the body is an error page we never parse.
FULL_TEXT_MISSING = "PPR1090496"


def main() -> None:
    HERE.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60.0) as client:
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
        if missing.status_code != 404:
            print("  WARNING: this preprint now serves XML; pick another for the no-XML test")


if __name__ == "__main__":
    main()
