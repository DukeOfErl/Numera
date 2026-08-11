"""End-to-end checks of the installed entry point: load a corpus, or explain why not."""

import subprocess
import sys
from pathlib import Path

import pytest

from bionumbers.cli import main
from conftest import record_json

CONSOLE_SCRIPT = Path(sys.executable).parent / "bionumbers"


def run_cli(*args, cwd):
    """Run the CLI the way a user would, in a directory with no corpus lying around."""
    return subprocess.run(
        [sys.executable, "-m", "bionumbers", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def corpus(write_corpus):
    return write_corpus(
        [
            record_json(id="100001", value_low=25.0, units="nm"),
            record_json(id="100002", value_low=0.44, value_high=1.79, units="µm"),
            record_json(id="100003", quotation="the spindle is 10 µm long"),
        ]
    )


class TestTypicalWorkflow:
    def test_loads_a_supplied_corpus(self, corpus, tmp_path):
        result = run_cli("--corpus", str(corpus), cwd=tmp_path)

        assert result.returncode == 0, result.stderr
        assert "Loaded 3 entries" in result.stdout
        assert result.stderr == ""

    def test_console_script_entry_point_is_installed(self, corpus, tmp_path):
        if not CONSOLE_SCRIPT.exists():
            pytest.skip(f"console script not installed at {CONSOLE_SCRIPT}")

        result = subprocess.run(
            [str(CONSOLE_SCRIPT), "--corpus", str(corpus)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert "Loaded 3 entries" in result.stdout

    def test_help_is_available(self, tmp_path):
        result = run_cli("--help", cwd=tmp_path)

        assert result.returncode == 0
        assert "--corpus" in result.stdout


class TestFailures:
    def test_no_corpus_supplied_explains_and_fails(self, tmp_path):
        result = run_cli(cwd=tmp_path)

        assert result.returncode == 2
        assert "no bundled corpus" in result.stderr.lower()
        assert result.stdout == ""

    def test_no_corpus_is_not_silently_read_from_the_working_directory(
        self, corpus, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(corpus.parent)

        result = run_cli(cwd=corpus.parent)

        assert result.returncode == 2
        assert "Loaded" not in result.stdout

    def test_missing_corpus_file_names_the_path(self, tmp_path):
        missing = tmp_path / "nowhere.jsonl"

        result = run_cli("--corpus", str(missing), cwd=tmp_path)

        assert result.returncode == 2
        assert str(missing) in result.stderr

    def test_malformed_corpus_names_the_line(self, write_corpus, tmp_path):
        broken = write_corpus([record_json(id="1"), "{not json"])

        result = run_cli("--corpus", str(broken), cwd=tmp_path)

        assert result.returncode == 2
        assert "line 2" in result.stderr
        assert result.stdout == ""

    def test_unknown_option_is_rejected(self, tmp_path):
        result = run_cli("--nonsense", cwd=tmp_path)

        assert result.returncode == 2


class TestInProcess:
    def test_returns_zero_on_success(self, corpus, capsys):
        assert main(["--corpus", str(corpus)]) == 0
        assert "Loaded 3 entries" in capsys.readouterr().out

    def test_returns_two_when_no_corpus_is_supplied(self, capsys):
        assert main([]) == 2

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "JSONL" in captured.err
