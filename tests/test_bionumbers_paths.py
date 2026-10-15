"""The two output locations are ones git will not track.

Asked of git itself rather than read from `.gitignore`, because the ignore file's semantics are
what a person guesses at and git's answer is what actually protects the repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bionumbers.paths import EUROPEPMC_DIR, RUNS_DIR

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("location", [EUROPEPMC_DIR, RUNS_DIR], ids=["europepmc", "runs"])
def test_output_location_is_ignored_by_git(location):
    probe = ROOT / location / "probe-file"
    ignored = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "-q", str(probe)],
        capture_output=True,
        timeout=10,
    )
    assert ignored.returncode == 0, f"git would track {probe}"


def test_a_tracked_location_is_told_apart():
    """The check can fail: the tests directory itself is tracked."""
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "-q", str(ROOT / "tests" / "probe-file")],
        capture_output=True,
        timeout=10,
    )
    assert tracked.returncode != 0
