"""The command, end to end over the fixture."""

import json

import pytest

from bionumbers_ingest.cli import main


def test_the_command_writes_a_corpus_a_manifest_and_a_report(tmp_path, sample_html, capsys):
    out = tmp_path / "corpus.jsonl"
    assert main([str(sample_html), "-o", str(out)]) == 0

    assert out.exists()
    assert (tmp_path / "corpus.jsonl.manifest.json").exists()
    assert len(out.read_text(encoding="utf-8").splitlines()) == 6

    printed = capsys.readouterr().out
    assert "rows read:              7" in printed
    assert "records written:        6" in printed
    assert "rows skipped non-data:  1" in printed
    assert "parse flags:" in printed


def test_the_whole_file_is_the_default_and_a_limit_must_be_asked_for(tmp_path, sample_html, capsys):
    out = tmp_path / "all.jsonl"
    main([str(sample_html), "-o", str(out)])
    assert len(out.read_text(encoding="utf-8").splitlines()) == 6
    assert "ROW LIMIT APPLIED" not in capsys.readouterr().out

    limited = tmp_path / "some.jsonl"
    main([str(sample_html), "-o", str(limited), "--limit", "3"])
    assert "ROW LIMIT APPLIED" in capsys.readouterr().out
    assert len(limited.read_text(encoding="utf-8").splitlines()) == 3


def test_a_missing_source_fails_with_the_path_and_writes_nothing(tmp_path, capsys):
    out = tmp_path / "corpus.jsonl"
    missing = tmp_path / "absent.xls"
    assert main([str(missing), "-o", str(out)]) == 2
    assert str(missing) in capsys.readouterr().err
    assert not out.exists()


def test_a_truncated_source_fails_and_writes_nothing(tmp_path, capsys):
    bad = tmp_path / "cut.html"
    bad.write_text("<table><tr><td>bion_id</td></tr><tr><td>1", encoding="utf-8")
    out = tmp_path / "corpus.jsonl"
    assert main([str(bad), "-o", str(out)]) == 1
    assert "cannot be ingested" in capsys.readouterr().err
    assert not out.exists()


def test_a_renamed_column_fails_and_writes_nothing(tmp_path, capsys):
    bad = tmp_path / "renamed.html"
    bad.write_text(
        "<table><tr><td>id</td><td>Value</td></tr><tr><td>1</td><td>2</td></tr></table>",
        encoding="utf-8",
    )
    out = tmp_path / "corpus.jsonl"
    assert main([str(bad), "-o", str(out)]) == 1
    assert "not the ones expected" in capsys.readouterr().err
    assert not out.exists()


def test_the_report_states_its_zeroes_rather_than_omitting_them(tmp_path, capsys):
    clean = tmp_path / "clean.html"
    header = "".join(
        f"<td>{h}</td>"
        for h in (
            "bion_id,Properties,Organism,Value,Range,Units,Reference,"
            "Reference PubMed ID,Primary Source,Primary Source PubMed ID,"
            "Measurement Method,Comments,Entered By,Keywords"
        ).split(",")
    )
    row = "<td>900001</td>" + "<td>x</td>" * 2 + "<td>1.5</td>" + "<td></td>" * 10
    clean.write_text(f"<table><tr>{header}</tr><tr>{row}</tr></table>", encoding="utf-8")
    assert main([str(clean), "-o", str(tmp_path / "c.jsonl")]) == 0
    printed = capsys.readouterr().out
    assert "duplicate identifiers:  0" in printed
    assert "range_fused): 0" in printed


def test_duplicate_identifiers_are_reported_and_both_records_kept(tmp_path, capsys):
    dup = tmp_path / "dup.html"
    header = "".join(
        f"<td>{h}</td>"
        for h in (
            "bion_id,Properties,Organism,Value,Range,Units,Reference,"
            "Reference PubMed ID,Primary Source,Primary Source PubMed ID,"
            "Measurement Method,Comments,Entered By,Keywords"
        ).split(",")
    )
    row = "<td>900001</td>" + "<td>x</td>" * 2 + "<td>1.5</td>" + "<td></td>" * 10
    dup.write_text(
        f"<table><tr>{header}</tr><tr>{row}</tr><tr>{row}</tr></table>", encoding="utf-8"
    )
    out = tmp_path / "dup.jsonl"
    assert main([str(dup), "-o", str(out)]) == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 2  # both kept
    assert "duplicate identifiers:  1" in capsys.readouterr().out
    manifest = json.loads((tmp_path / "dup.jsonl.manifest.json").read_text())
    assert manifest["duplicate_bnids"] == [900001]


@pytest.mark.parametrize("argv", [["--version"], ["--help"]])
def test_version_and_help_exit_cleanly(argv):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 0


def test_the_report_counts_each_flag_that_was_raised(tmp_path, sample_html, capsys):
    # "parse flags:" appearing says nothing; the counts under it are the report.
    assert main([str(sample_html), "-o", str(tmp_path / "c.jsonl")]) == 0
    printed = capsys.readouterr().out
    assert "injected_html_removed: 2" in printed
    assert "range_is_link: 1" in printed
    manifest = json.loads((tmp_path / "c.jsonl.manifest.json").read_text())
    assert manifest["flag_counts"]["injected_html_removed"] == 2
    assert manifest["flag_counts"]["range_is_link"] == 1


def test_a_run_that_raised_no_flags_says_so_rather_than_printing_nothing(tmp_path, capsys):
    clean = tmp_path / "clean.html"
    header = "".join(
        f"<td>{h}</td>"
        for h in (
            "bion_id,Properties,Organism,Value,Range,Units,Reference,"
            "Reference PubMed ID,Primary Source,Primary Source PubMed ID,"
            "Measurement Method,Comments,Entered By,Keywords"
        ).split(",")
    )
    row = "<td>900001</td>" + "<td>x</td>" * 2 + "<td>1.5</td>" + "<td></td>" * 10
    clean.write_text(f"<table><tr>{header}</tr><tr>{row}</tr></table>", encoding="utf-8")
    assert main([str(clean), "-o", str(tmp_path / "c.jsonl")]) == 0
    assert "(none raised)" in capsys.readouterr().out
