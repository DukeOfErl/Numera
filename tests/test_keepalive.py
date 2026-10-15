"""The keepalive script: its one coupling to the app, and its handling of a page
that changes under it."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

from scinumbers_ask import messages

SCRIPT = Path(__file__).parent.parent / "bin" / "keepalive.py"


class FakeError(Exception):
    """Stands in for `playwright.sync_api.Error`."""


@pytest.fixture
def keepalive(monkeypatch):
    # The script imports playwright at module level, and playwright is not a
    # project dependency -- the workflow installs it. Stubs stand in, and
    # `monkeypatch` removes them afterwards so they cannot leak into a test that
    # imports the real thing.
    stub = types.ModuleType("playwright.sync_api")
    stub.Page = object
    stub.Error = FakeError
    stub.sync_playwright = None
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", stub)
    spec = importlib.util.spec_from_file_location("keepalive", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Locator:
    def __init__(self, count, on_click=None):
        self._count = count
        self._on_click = on_click

    def count(self):
        if isinstance(self._count, Exception):
            raise self._count
        return self._count

    @property
    def first(self):
        return self

    def click(self):
        self._on_click()


class Frame:
    def __init__(self, showing):
        self._showing = showing

    def get_by_text(self, text):
        return Locator(1 if self._showing else 0)


class Page:
    """Enough of a page for `look`: a wake button and some frames."""

    def __init__(self, *, wake=0, frames=(), wake_error=None):
        self.clicked = False
        self._wake = wake_error or wake
        self.frames = list(frames)

    def get_by_role(self, role, name):
        return Locator(self._wake, on_click=lambda: setattr(self, "clicked", True))


def test_door_text_is_still_what_the_door_says(keepalive):
    # If the wording moves and the script's phrase does not, the scheduled check
    # fails every hour on a healthy app -- or, worse, someone loosens it to pass.
    assert keepalive.DOOR_TEXT in messages.SIGN_IN_NEEDED


def test_look_finds_the_door_inside_an_iframe(keepalive):
    page = Page(frames=[Frame(False), Frame(True)])
    assert keepalive.look(page, keepalive.DOOR_TEXT) is True


def test_look_does_not_see_a_door_that_is_not_there(keepalive):
    page = Page(frames=[Frame(False)])
    assert keepalive.look(page, keepalive.DOOR_TEXT) is False


def test_look_clicks_the_wake_button_when_it_is_showing(keepalive):
    page = Page(wake=1, frames=[Frame(False)])
    keepalive.look(page, keepalive.DOOR_TEXT)
    assert page.clicked


def test_a_page_changing_under_the_look_is_not_yet_rather_than_a_crash(keepalive):
    # A wake reloads the page and replaces the iframe; a look that lands
    # mid-navigation raises. That must read as "not yet" so the loop looks again.
    page = Page(wake_error=FakeError("Execution context was destroyed"))
    assert keepalive.look(page, keepalive.DOOR_TEXT) is False


def test_an_error_that_is_not_playwrights_still_propagates(keepalive):
    # Only the page's own errors are swallowed; a bug in the script must not be.
    page = Page(wake_error=ValueError("a bug"))
    with pytest.raises(ValueError):
        keepalive.look(page, keepalive.DOOR_TEXT)
