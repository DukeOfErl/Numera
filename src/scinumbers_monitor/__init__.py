"""The operator's view of the alpha: a reader of the trail, not an adapter over the agent.

It reads the trail and changes nothing (ADR-1300, ADR-1310). From `scinumbers_ask`
it may take only `neon` (a branch by name), `hosted_trace` (a question's trace id),
`pending` (the door rule, so there is one copy of it) and `trail_store` (its
timeouts). Nothing in `scinumbers_ask` imports it, and within
this package only `app` imports Streamlit. `tests/test_monitor_boundaries.py`
holds all three.

Langfuse is linked from here and never queried (ADR-1320).
"""
