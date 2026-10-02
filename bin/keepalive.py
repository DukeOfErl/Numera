# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright==1.63.0"]
# ///
"""Visit the deployed app in a real browser, waking it if it is asleep.

Streamlit Community Cloud hibernates an app after 12 hours without traffic, and
only a visitor's browser counts as traffic -- a plain HTTP request, a commit and an
uptime pinger do not wake a sleeping app. So this loads the page, clicks the
sleep screen's button if it is showing, and then insists on seeing the door.

**Exit status is the report.** 0 means a reader would have been served; anything
else means the app is asleep and would not wake, or is up but not drawing the door.
Nothing is printed to a person: it is a check, and a check that succeeds has
nothing to say. The notice is not mail per failed run -- `keepalive-digest.yml`
reads the runs and writes one issue a day.

    uv run bin/keepalive.py --install-browser
    uv run bin/keepalive.py https://scinumbers.streamlit.app

**The browser is installed by this script, from its own environment.** Playwright
looks for the browser build matching its own version, so installing it from a
different resolution (`uvx playwright install`) can leave the check failing with
"Executable doesn't exist" for reasons unrelated to the app. The version is pinned
above for the same reason: a release landing between two steps cannot split them.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

#: What the sleep screen's button says. Streamlit's wording, not ours -- if they
#: change it this fails loudly (the door never appears) rather than passing.
WAKE_BUTTON = re.compile(r"get this app back up", re.IGNORECASE)

#: A phrase only the door draws (`messages.SIGN_IN_NEEDED`). Seeing it proves the
#: script ran, the session started and the page rendered -- stronger than "the URL
#: answered 200", which the sleep screen does too.
#: `tests/test_keepalive.py` fails if the wording moves and this does not.
DOOR_TEXT = "by invitation only"

#: A cold start installs the environment, which takes minutes, not seconds.
DEADLINE_SECONDS = 300


def door_is_showing(page: Page, text: str) -> bool:
    """The text may sit in the page or in the iframe Community Cloud wraps it in."""
    return any(frame.get_by_text(text).count() for frame in page.frames)


def look(page: Page, text: str) -> bool:
    """One look at the page: click the wake button if it is there, then the door.

    A wake reloads the page and replaces the app's iframe, so a look that lands
    mid-navigation raises ("Execution context was destroyed", "Frame was
    detached"). That is the page changing under us, not the app failing, so it
    counts as "not yet" and the loop looks again -- the deadline is what decides
    a real failure. Without this, the path the script exists for would report a
    failure for an app that woke correctly.
    """
    try:
        wake = page.get_by_role("button", name=WAKE_BUTTON)
        if wake.count():
            wake.first.click()
        return door_is_showing(page, text)
    except PlaywrightError:
        return False


def keep_alive(url: str, text: str = DOOR_TEXT, deadline: float = DEADLINE_SECONDS) -> bool:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            stop = time.monotonic() + deadline
            while time.monotonic() < stop:
                if look(page, text):
                    return True
                page.wait_for_timeout(2000)
            return False
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", nargs="?")
    parser.add_argument(
        "--install-browser",
        action="store_true",
        help="install the browser build matching this script's Playwright, then stop",
    )
    parser.add_argument("--expect", default=DOOR_TEXT, help="text the door must show")
    parser.add_argument("--deadline", type=float, default=DEADLINE_SECONDS)
    args = parser.parse_args()
    if args.install_browser:
        # `--with-deps` also installs the system libraries; the hosted runner has
        # passwordless sudo for it.
        return subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"]
        ).returncode
    if not args.url:
        parser.error("a url is needed unless --install-browser is given")
    if keep_alive(args.url, args.expect, args.deadline):
        return 0
    print(
        f"{args.url}: no door within {args.deadline:g}s -- asleep and not woken, "
        f"or up and not showing {args.expect!r}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
