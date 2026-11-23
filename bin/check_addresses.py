#!/usr/bin/env python3
"""Refuse a commit that adds an email address, unless it is a placeholder or named below.

    bin/check_addresses.py FILE...     pre-commit: exit 1 and name each address found

A personal address committed once is in the history for good: removing it later means
rewriting every branch and changing every later commit's ID. On 2026-11-20 that was weighed for
an address that sat in a docstring as an example, and declined -- the history's commit IDs were
worth more than the address. So the check runs before the commit, when refusing costs nothing.

**Allowed without asking:** the domains reserved for examples (RFC 2606/6761: `example.com`,
`.org`, `.net`, and anything under `.example`, `.invalid`, `.test`, `localhost`), and the
user part of a URL (`postgresql://user:password@host`), which is not an address.
**Allowed by name:** the paths and lines in `ALLOWED`, each with its reason. Anything else
is refused; the cheap direction is a placeholder the author has to type, the expensive one
is an address nobody can take back.

Stdlib only, so the hook runs in a checkout with no environment, as `testloop.py` does.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ADDRESS = re.compile(
    r"(?<![\w.%+:/-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"
)
PLACEHOLDER_DOMAINS = re.compile(
    r"(?i)(?:^|\.)(?:example\.(?:com|org|net)|example|invalid|test|localhost)$"
)

#: Path prefix, and a pattern the line must match (empty: any line), with the reason.
ALLOWED = (
    (
        "tests/fixtures/europepmc/",
        "",
        "open-access papers as published; a corresponding author's address is part of the text",
    ),
    (
        "src/numera_ask/messages.py",
        r'^PRIVACY_CONTACT = "',
        "the privacy policy's contact, shown on purpose on the deployed app (kept 2026-11-20)",
    ),
)


def offending(path: str, text: str) -> list[tuple[int, str]]:
    """Each (line number, address) in `text` that no rule above allows."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if any(path.startswith(p) and re.search(rule, line) for p, rule, _ in ALLOWED):
            continue
        for match in ADDRESS.finditer(line):
            if not PLACEHOLDER_DOMAINS.search(match.group(0).rsplit("@", 1)[1]):
                found.append((number, match.group(0)))
    return found


def main(argv: list[str]) -> int:
    status = 0
    for name in argv:
        path = Path(name)
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, address in offending(path.as_posix(), text):
            print(
                f"{name}:{number}: an email address, {address!r}. Use a placeholder "
                "(someone@example.org) or, if it must stay, name it in bin/check_addresses.py.",
                file=sys.stderr,
            )
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
