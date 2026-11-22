"""The validator's environment reads, each refusing a name this project has retired.

The ask package keeps the same refusal in `numera_ask.config`, but the validator's core may not
import the ask package (`tests/test_bionumbers_dependency_direction.py`), so it holds its own
short map. The refusal sits in the read itself rather than in the command that happens to call
it: a guard in one caller protects only that caller (ADR-0250, ADR-1900).
"""

import os

#: Every retired name the validator reads, each mapped to its current replacement.
RENAMED = {
    "BIONUMBERS_REVIEW_DB_URL": "NUMERA_REVIEW_DB_URL",
    "BIONUMBERS_OPENROUTER_API_KEY": "NUMERA_OPENROUTER_API_KEY",
    "SCINUMBERS_CORPUS": "NUMERA_CORPUS",
    # Retired by the rename before that (ADR-0400); the ask package refuses it too, and a name
    # refused by one package and ignored by the other is the inconsistency this map prevents.
    "BIONUMBERS_ASK_CORPUS": "NUMERA_CORPUS",
}


class RetiredSetting(ValueError):
    """A retired environment name is set. The message says what to set instead."""


def read(name: str, default: str = "") -> str:
    """`os.environ.get`, refusing first if any retired name is present.

    Any retired name, not only the one being read: a stale key exported beside a current
    database URL is still a configuration nobody meant, and it is cheapest to hear about it once.
    """
    for old, new in RENAMED.items():
        if old in os.environ:
            raise RetiredSetting(f"{old} is now {new}. Rename it and try again.")
    return os.environ.get(name, default)
