from pathlib import Path

import pytest


@pytest.fixture
def sample_html() -> Path:
    """A synthetic export in the published file's exact shape.

    The identifiers are deliberately outside the real corpus's range (`9xxxxx`)
    and the content is invented, so no BioNumbers data enters this repository —
    see ADR-0200. What the fixture reproduces faithfully is the *structure* and
    the quirks: `<td>` header cells, the text-marker apostrophe, HTML-escaped
    injected markup, entity-encoded micrometre glyphs, a link-only range, and a
    trailing padding row. Behaviour against the real file is verified separately
    against a locally-fetched export, never from a committed copy of it.
    """
    return Path(__file__).parent / "fixtures" / "sample_table.html"
