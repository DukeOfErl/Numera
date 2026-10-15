"""The harvest store as the agent's corpus (`add-ask-over-store`).

Test data here is invented. The real store holds passages from papers some of which are licensed
NC or ND, and none of that text may enter the repository; the fixture builds a store with the real
schema and made-up words.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _loaded_after(statements: str) -> set[str]:
    """Which `bionumbers` modules a fresh interpreter holds after running `statements`.

    A fresh interpreter because this process has imported everything the suite touches, so asking
    `sys.modules` here would report what some other test loaded.
    """
    probe = (
        f"{statements}\n"
        "import sys\n"
        "print(','.join(sorted(m for m in sys.modules "
        "if m == 'bionumbers' or m.startswith('bionumbers.'))))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    return {name for name in result.stdout.strip().split(",") if name}


def test_a_corpus_file_run_never_imports_the_validator_package():
    """ADR-1600: only the store's loader imports `bionumbers`, so a corpus-file run never does."""
    loaded = _loaded_after(
        "from scinumbers_ask import agent, cli, corpus, entries_table, messages\n"
        "from scinumbers_ask import repository, tools\n"
        f"repository.CorpusRepository(corpus.load({str(FIXTURES / 'corpus_sample.jsonl')!r}))\n"
    )
    assert loaded == set()


def test_a_corpus_file_entry_carries_no_harvest_and_no_tier():
    """D2: both parts are None for a corpus-file entry, which is how a surface tells "never
    reviewed" from "reviewed, and no one approved"."""
    from scinumbers_ask import corpus

    entries = corpus.load(FIXTURES / "corpus_sample.jsonl")
    assert entries
    assert all(e.harvest is None and e.trust is None for e in entries)
    assert all(e.record_id == e.entry_id for e in entries)
