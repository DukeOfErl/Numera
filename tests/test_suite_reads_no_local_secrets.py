"""The suite never reads a secrets file from the machine it runs on.

Replacing `st.secrets` is not enough. An `AppTest` run parses secrets itself, from the
files the `secrets.files` option lists, and Streamlit copies every top-level key into
`os.environ` as it does. A developer's `.streamlit/secrets.toml` keeps the tracing
switch, the Langfuse keys and the trail database's URL at its top level, so one page
test that ran a question switched hosted tracing on with real keys and tried to reach
the real trail database. The sandbox refused both connections, which is how it was
found (2026-11-19); in a terminal they would have gone through.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_streamlit_is_pointed_at_no_secrets_file_on_this_machine():
    from streamlit import config

    files = [Path(f) for f in config.get_option("secrets.files")]
    for real in (Path.home() / ".streamlit" / "secrets.toml", ROOT / ".streamlit" / "secrets.toml"):
        assert real not in files, f"the suite would read {real}"
    assert files, "an empty list lets nothing in, but would also hide a later default"
    assert all(f.read_text() == "" for f in files)
