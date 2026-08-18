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
import uuid
from dataclasses import dataclass
from typing import Any

LOGGER_NAME = "bionumbers_ask"


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
    """Records for one question. Every record carries the same identifier."""

    question_id: str

    def record(self, event: str, **fields: Any) -> None:
        logging.getLogger(LOGGER_NAME).info(
            event, extra={"question_id": self.question_id, "fields": fields}
        )

    def run_config(self, name: str) -> dict[str, Any]:
        """Config for a framework call, so its own traces are readable too.

        Names and tags cost nothing now and cannot be retrofitted onto traces
        already recorded; a trace of runs all called the same thing is unusable.
        """
        return {
            "run_name": f"{name}:{self.question_id}",
            "tags": ["bionumbers-ask", name],
            "metadata": {"question_id": self.question_id},
        }


def start_question() -> QuestionTrace:
    return QuestionTrace(question_id=uuid.uuid4().hex[:12])
