"""The keepalive script's one coupling to the app: the phrase it waits for."""

import importlib.util
import sys
import types
from pathlib import Path

from scinumbers_ask import messages

SCRIPT = Path(__file__).parent.parent / "bin" / "keepalive.py"


def _load_keepalive():
    # The script imports playwright at module level, and playwright is not a
    # project dependency -- the workflow installs it. A stub is enough to read
    # the constant without it.
    stub = types.ModuleType("playwright.sync_api")
    stub.Page = object
    stub.sync_playwright = None
    pkg = types.ModuleType("playwright")
    sys.modules.setdefault("playwright", pkg)
    sys.modules.setdefault("playwright.sync_api", stub)
    spec = importlib.util.spec_from_file_location("keepalive", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_door_text_is_still_what_the_door_says():
    # If the wording moves and the script's phrase does not, the scheduled check
    # fails every hour on a healthy app -- or, worse, someone loosens it to pass.
    assert _load_keepalive().DOOR_TEXT in messages.SIGN_IN_NEEDED
