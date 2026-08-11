import json

import pytest

MINIMAL_RECORD = {
    "id": "100001",
    "property": "Diameter of microtubule",
}


def record_json(**overrides) -> str:
    """A JSON line for one corpus entry; overrides are merged over a minimal valid record."""
    record = {**MINIMAL_RECORD, **overrides}
    return json.dumps({k: v for k, v in record.items() if v is not ...}, ensure_ascii=False)


@pytest.fixture
def write_corpus(tmp_path):
    """Write lines to a corpus file and return its path."""

    def _write(lines, name="corpus.jsonl"):
        path = tmp_path / name
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    return _write
