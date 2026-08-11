"""The corpus is an external input: nothing is bundled, and nothing can be committed."""

import inspect
import subprocess
from pathlib import Path

import pytest

import bionumbers
from bionumbers.corpus import CorpusNotSuppliedError, load_corpus

PACKAGE_ROOT = Path(bionumbers.__file__).parent
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_SUFFIXES = {".jsonl", ".json", ".csv", ".tsv", ".xls", ".xlsx", ".parquet"}


def test_package_ships_no_data_files():
    bundled = [p for p in PACKAGE_ROOT.rglob("*") if p.suffix.lower() in DATA_SUFFIXES]

    assert bundled == [], f"data files bundled with the package: {bundled}"


def test_loader_has_no_default_corpus():
    default = inspect.signature(load_corpus).parameters["path"].default

    assert default is inspect.Parameter.empty


def test_loading_without_a_path_raises_rather_than_falling_back():
    with pytest.raises(CorpusNotSuppliedError):
        load_corpus(None)


@pytest.mark.parametrize(
    "candidate",
    ["corpus/bionumbers.jsonl", "corpus/nested/anything.jsonl", "corpus/README.md"],
)
def test_corpus_directory_is_git_ignored(candidate):
    result = subprocess.run(
        ["git", "check-ignore", "-q", candidate],
        cwd=REPO_ROOT,
        capture_output=True,
    )

    assert result.returncode == 0, f"{candidate} is not ignored by .gitignore"
