# ADR-1300: The monitor is a reader of the trail, not an adapter over the agent

- **Status:** accepted
- **Date:** 2026-10-02
- **Pull request:** _pending — `feat/monitor-dashboard`_

## Context

The operator needed one place to see the alpha's use, cost, endings, ratings, the
sign-in queue and whether recording works. Until now, that meant pasting queries
from `sql/feedback.sql` and `sql/signin.sql` into Neon's console. The view is a
Streamlit page, which raised the question of where it lives.

Three options were on the table:

- **A module in `scinumbers_ask`.** `test_driver_independence.py` allows exactly
  one module there to import Streamlit (`web`). Making room would mean exempting a
  second importer from that test, or listing the view as a driver. It is not a
  driver: it never puts a question to the agent.
- **A separate repository.** That copies the event names and the table's shape
  into a place where nothing notices when they change. A renamed event would show
  as zero, and a zero looks like data.
- **A package of its own in this repository, `scinumbers_monitor`.**

## Decision

`src/scinumbers_monitor/` is its own package and a reader of the trail. The
dependency direction is plain: it may import from `scinumbers_ask`, and nothing
there imports it. From `scinumbers_ask` it may take exactly four modules:

- `neon`, to resolve a branch by name;
- `hosted_trace`, for `trace_id_for`, so the trace id has one derivation;
- `pending`, so the door row applies the daily check's rule rather than a copy;
- `trail_store`, for its timeouts.

Within the package only `app` imports Streamlit. `tests/test_monitor_boundaries.py`
asserts all three rules.

The figures are pure functions over rows (`figures.py`). The reads are a single
`select` per period (`queries.py`). The page only draws. Endings are classified
from a declared map of event names (`ENDING_EVENTS`). A question the map cannot
place is shown as *unidentified*, never as answered. Two tests keep the map
complete against `EndReason` and against the source.

No new dependency extra: `ask` already carries everything the page needs.

## Trade-off accepted

The ending map is a second statement of which events end a question, maintained by
hand and kept honest by tests. Recording one `question.ended` row in `ask` would
make it exact for new rows, but it changes what the application records, and the
map is needed for the history anyway. That is left for its own change.

The view and the app now share a repository, so a branch that changes the trail's
events is the branch that must keep the view's map green.
