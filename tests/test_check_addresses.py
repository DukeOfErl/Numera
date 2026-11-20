"""`bin/check_addresses.py`: no email address committed outside placeholders and named exceptions.

Real-looking addresses are assembled at run time ("someone" + AT + domain) so this file does not
itself hold one the hook would refuse.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AT = "@"


def _checker():
    spec = importlib.util.spec_from_file_location(
        "check_addresses", ROOT / "bin" / "check_addresses.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = _checker()
PERSONAL = "someone" + AT + "gmail.com"


def test_a_personal_address_is_refused_and_a_placeholder_with_the_same_user_is_not():
    """The dimension the rule reads is the domain: same user, a reserved domain, passes."""
    assert check.offending("src/numera_ask/x.py", f'OWNER = "{PERSONAL}"\n') == [(1, PERSONAL)]
    for placeholder in ("someone@example.org", "someone@example.com", "a@ep.invalid", "b@c.test"):
        assert check.offending("src/numera_ask/x.py", f'OWNER = "{placeholder}"\n') == []


def test_a_domain_that_only_ends_like_a_placeholder_is_refused():
    """The reserved name has to be a whole label: `notexample.org` is a domain someone can own."""
    for owned in ("notexample.org", "myexample.com", "uninvalid.de"):
        address = "someone" + AT + owned
        assert check.offending("src/numera_ask/x.py", f'OWNER = "{address}"\n') == [(1, address)]


def test_the_user_part_of_a_url_is_not_an_address():
    for url in (
        "postgresql://neondb_owner:PASSWORD@ep-x-pooler.eu-central-1.aws.neon.tech/db",
        "postgresql://p@ep-x-pooler.eu-central-1.aws.neon.tech/db",
    ):
        assert check.offending("README.md", url + "\n") == []


def test_a_paper_fixture_may_carry_its_author_s_address_and_no_other_path_may():
    line = "<email>author" + AT + "uni.edu</email>\n"
    assert check.offending("tests/fixtures/europepmc/fulltext_PMC1.xml", line) == []
    assert check.offending("tests/fixtures/other.xml", line) == [(1, "author" + AT + "uni.edu")]


def test_the_privacy_contact_is_allowed_on_its_own_line_of_its_own_module_only():
    allowed = f'PRIVACY_CONTACT = "{PERSONAL}"\n'
    assert check.offending("src/numera_ask/messages.py", allowed) == []
    # The same address elsewhere in the same module, and the same line in another module.
    assert check.offending("src/numera_ask/messages.py", f'OTHER = "{PERSONAL}"\n') == [
        (1, PERSONAL)
    ]
    assert check.offending("src/numera_ask/web.py", allowed) == [(1, PERSONAL)]


def test_the_hook_fails_and_names_the_file_and_line(tmp_path, capsys):
    clean, dirty = tmp_path / "clean.py", tmp_path / "dirty.py"
    clean.write_text('ADMIN = "admin@example.org"\n')
    dirty.write_text(f'\nADMIN = "{PERSONAL}"\n')

    assert check.main([str(clean)]) == 0
    assert check.main([str(clean), str(dirty)]) == 1
    assert f"{dirty}:2:" in capsys.readouterr().err
