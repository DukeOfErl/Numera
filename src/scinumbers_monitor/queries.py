"""The view's reads: the trail, a period at a time, and one question's whole record.

Every statement is a `select` on `trail`; the door row's reads are `pending`'s own
(`pending.waiting`), not restated here. One wide read per period rather than one
query per figure: `figures.py` computes every row of the view from the same rows,
so the figures cannot disagree with each other about what the period held, and the
database is woken once per refresh rather than once per card.
"""

from __future__ import annotations

from datetime import datetime

from .figures import Row

_COLUMNS = (
    "id, at, event, question_id, session_id, run_label, user_email, user_role, detail, "
    "prev_write_ms"
)

#: Ordered by id because `figures` reads write order from it; `at` is the
#: transaction's time and two rows can share one.
STATEMENTS = {
    "period": f"select {_COLUMNS} from trail where at >= :since and at < :until order by id",
    "question": f"select {_COLUMNS} from trail where question_id = :question_id order by id",
    "last_row": "select max(at) from trail",
}


def _rows(result) -> list[Row]:
    return [
        Row(
            id=r.id,
            at=r.at,
            event=r.event,
            question_id=r.question_id,
            session_id=r.session_id,
            run_label=r.run_label,
            user_email=r.user_email,
            user_role=r.user_role,
            detail=r.detail or {},
            prev_write_ms=r.prev_write_ms,
        )
        for r in result
    ]


def period_rows(engine, since: datetime, until: datetime) -> list[Row]:
    from sqlalchemy import text

    with engine.connect() as conn:
        return _rows(conn.execute(text(STATEMENTS["period"]), {"since": since, "until": until}))


def question_rows(engine, question_id: str) -> list[Row]:
    from sqlalchemy import text

    with engine.connect() as conn:
        return _rows(conn.execute(text(STATEMENTS["question"]), {"question_id": question_id}))


def last_row_at(engine) -> datetime | None:
    """Over the whole table, not the period: "nothing recorded since Tuesday" is the
    signal, and a period filter would hide it behind "nothing in this period"."""
    from sqlalchemy import text

    with engine.connect() as conn:
        return conn.execute(text(STATEMENTS["last_row"])).scalar()
