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
    assert "(range_fused):  0" in printed
    assert "(range_qualified):        0" in printed


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


@pytest.mark.parametrize("bad", ["-5", "0"])
def test_a_limit_below_one_is_rejected_rather_than_writing_one_row(
    tmp_path, sample_html, bad, capsys
):
    out = tmp_path / "c.jsonl"
    assert main([str(sample_html), "-o", str(out), "--limit", bad]) == 2
    assert "--limit must be at least 1" in capsys.readouterr().err
    assert not out.exists()


def test_an_unwritable_destination_blames_the_destination(tmp_path, sample_html, capsys):
    readonly = tmp_path / "readonly"
    readonly.mkdir()
    readonly.chmod(0o500)
    try:
        rc = main([str(sample_html), "-o", str(readonly / "out.jsonl")])
        err = capsys.readouterr().err
        assert rc == 2
        assert "out.jsonl" in err, f"the message names the wrong file: {err}"
        assert str(sample_html) not in err
    finally:
        readonly.chmod(0o700)


def test_the_link_count_and_the_link_flag_agree(tmp_path, sample_html, capsys):
    assert main([str(sample_html), "-o", str(tmp_path / "c.jsonl")]) == 0
    printed = capsys.readouterr().out
    manifest = json.loads((tmp_path / "c.jsonl.manifest.json").read_text())
    flagged = manifest["flag_counts"].get("range_is_link", 0)
    assert f"records carrying a link:{flagged:>6}" in printed


def test_it_refuses_to_write_a_corpus_where_git_would_track_it(tmp_path, sample_html, capsys):
    # A .gitignore protects only the repositories someone remembered to edit. The
    # default output path is relative, so a run started from the wrong checkout
    # writes 19.5 MB of unlicensed data into whichever repo the caller is in —
    # and three checkouts here share one origin, one of them on main.
    import subprocess

    repo = tmp_path / "somerepo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    out = repo / "data" / "corpus.jsonl"

    assert main([str(sample_html), "-o", str(out)]) == 3
    err = capsys.readouterr().err
    assert "refusing to write" in err
    assert "unresolved licensing" in err
    assert not out.exists()


def test_it_writes_where_git_ignores_the_path(tmp_path, sample_html):
    import subprocess

    repo = tmp_path / "ignoring"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".gitignore").write_text("data/\n", encoding="utf-8")
    out = repo / "data" / "corpus.jsonl"

    assert main([str(sample_html), "-o", str(out)]) == 0
    assert out.exists()


def test_it_writes_outside_any_repository(tmp_path, sample_html):
    out = tmp_path / "plain" / "corpus.jsonl"
    assert main([str(sample_html), "-o", str(out)]) == 0
    assert out.exists()


def test_the_guard_covers_the_manifest_as_well_as_the_corpus(tmp_path, sample_html, capsys):
    # The manifest is written beside the corpus under a different name, so an
    # ignore rule can cover one and not the other.
    import subprocess

    repo = tmp_path / "partial"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".gitignore").write_text("bionumbers*.jsonl\n", encoding="utf-8")

    assert main([str(sample_html), "-o", str(repo / "bionumbers.jsonl")]) == 3
    assert "manifest" in capsys.readouterr().err
    assert not (repo / "bionumbers.jsonl.manifest.json").exists()


def test_the_guard_covers_the_partial_files_a_run_writes_through(tmp_path, sample_html, capsys):
    # The partial is unlinked on the way out of an exception, but a SIGKILL, an
    # OOM or a power cut leaves it behind — ~19.5 MB of unlicensed export data on
    # a path a suffix-matching ignore rule does not cover, which `git add .`
    # would then take.
    import subprocess

    repo = tmp_path / "finals-only"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".gitignore").write_text(
        "bionumbers.jsonl\nbionumbers.jsonl.manifest.json\n", encoding="utf-8"
    )

    assert main([str(sample_html), "-o", str(repo / "bionumbers.jsonl")]) == 3
    assert ".partial" in capsys.readouterr().err
    assert not (repo / "bionumbers.jsonl").exists()
