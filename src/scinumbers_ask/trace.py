"""Structured records for the deterministic layer, keyed per question.

Several failures in this system are silent rather than loud: an alias resolving
to the wrong stored value, a truncated search treated as complete, spend
accumulated from a response that reported no cost. A non-deterministic agent
reproduces those only sometimes, so the trail has to be there before anyone
knows to look for it.

Model calls are not logged here. Tracing tools cover those; this covers the
deterministic layer, which is where this project's own bugs will be.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER_NAME = "scinumbers_ask"

# Inside the repository but gitignored: the trail is this project's own output, not
# corpus data, and the records carry search terms, identifiers and token counts --
# no entry text, so nothing of the corpus's licensing travels with them.
DEFAULT_FILE = "logs/trace.jsonl"

# Set at import, not only in configure(). An unconfigured logger inherits the
# root's WARNING level, so every INFO record would be discarded without error --
# the trail vanishing precisely when nobody knows to look for it, which is the
# failure this module exists to prevent.
logging.getLogger(LOGGER_NAME).setLevel(logging.INFO)


class JsonLines(logging.Formatter):
    """One JSON object per record, so a trail can be filtered by question."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "event": record.getMessage(),
            "level": record.levelname.lower(),
        }
        question_id = getattr(record, "question_id", None)
        if question_id is not None:
            payload["question_id"] = question_id
        # Omitted when absent rather than written as null: a trail read by a
        # person should not carry a column that is empty on every line from the
        # terminal driver, which has a session but no reason to name it twice.
        session_id = getattr(record, "session_id", None)
        if session_id:
            payload["session_id"] = session_id
        run_label = getattr(record, "run_label", None)
        if run_label is not None:
            payload["run"] = run_label
        payload.update(getattr(record, "fields", {}) or {})
        return json.dumps(payload, default=str)


def configure(stream: Any = None, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLines())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


@dataclass(frozen=True)
class QuestionTrace:
    """Records for one question. Every record carries the same identifier.

    And the same run label, so a trail covering an evaluation run and a
    hand-driven session can be told apart when the spend figures are added up.
    """

    question_id: str
    run_label: str = "dev"
    # The session the question was asked in. The question identifier locates one
    # question; without this, a sequence of questions asked by one person cannot
    # be reassembled, and one person asking ten is indistinguishable from ten
    # people asking one.
    #
    # Defaulted rather than required, because a caller that has no session is a
    # real case -- a test, a direct `QuestionTrace` -- and forcing a placeholder
    # would put a fabricated identifier in the record instead of nothing.
    session_id: str = ""

    def record(self, event: str, **fields: Any) -> None:
        logging.getLogger(LOGGER_NAME).info(
            event,
            extra={
                "question_id": self.question_id,
                "session_id": self.session_id,
                "run_label": self.run_label,
                "fields": fields,
            },
        )

    def run_config(self, name: str) -> dict[str, Any]:
        """Config for a framework call, so its own traces are readable too.

        Names and tags cost nothing now and cannot be retrofitted onto traces
        already recorded; a trace of runs all called the same thing is unusable.
        """
        metadata = {"question_id": self.question_id, "run": self.run_label}
        # Only when there is one. A tracing tool treats metadata keys as facets,
        # and a facet that is the empty string on some runs and an identifier on
        # others is worse than one that is simply absent.
        if self.session_id:
            metadata["session_id"] = self.session_id
        return {
            "run_name": f"{name}:{self.question_id}",
            "tags": ["scinumbers-ask", name, f"run:{self.run_label}"],
            "metadata": metadata,
        }


def start_question(run_label: str = "dev", session_id: str = "") -> QuestionTrace:
    return QuestionTrace(
        question_id=uuid.uuid4().hex[:12], run_label=run_label, session_id=session_id
    )


def to_file(spec: str) -> None:
    """Point the structured trail somewhere a real run can be read from.

    Nothing called this outside the tests, so every search, alias resolution,
    truncation decision and spend increment was discarded in every real run: the
    logger is at INFO with no handler, and the handler-less root drops the records
    at WARNING without error. The trail vanished precisely where nobody would think
    to look for it, which is the failure this module exists to prevent.

    Never stdout: the rendered answer goes there, and interleaving JSON with it
    would corrupt both.
    """
    if not spec:
        return
    if spec == "-":
        configure(sys.stderr)
        return
    path = Path(spec)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Appended and left open for the life of the process: a run is a sequence of
    # questions, and each carries its own identifier for filtering afterwards.
    configure(path.open("a", encoding="utf-8"))
