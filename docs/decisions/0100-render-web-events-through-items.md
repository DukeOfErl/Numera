# ADR-0100: The web driver decides in items and draws from them

- **Status:** accepted
- **Date:** 2026-08-26
- **Pull request:** _pending — `feat/ask-agent`_

## Context

The agent emits a stream of events per question, and each driver renders them.
The terminal driver renders as it reads: one line per event, printed and gone.
The obvious equivalent for the web driver is to render into the page as the
events arrive — a status line or a placeholder updated in place, which is what a
live progress indicator wants to be.

Streamlit forecloses that. `ForwardMsgQueue.enqueue` composes a delta into any
message already queued for the same `delta_path`, because the browser only needs
the latest state of a given screen location. Streamlit's own test harness,
`AppTest`, parses its element tree from that same queue. Anything written to one
location and then overwritten is therefore unobservable after the fact — not only
to a reader scrolling back, but to any test.

Measured against Streamlit 1.61.1, three progress events rendered two ways:

```
st.empty() overwritten 3x  → ['progress: answer: 42']              # two events gone
st.caption appended 3x     → ['step: searching', 'step: found 3', 'step: answer: 42']
st.status                  → [('done', 'complete')]                # 'running' never visible
```

Three options were on the table. Render in place and accept that retrieval
progress cannot be asserted. Append one element per event, which is observable
but constrains the layout to whatever appends cleanly. Or separate the decision
from the drawing.

## Decision

Events become `Item(kind, text)` values in `bionumbers_ask.web`, and the page
draws from the items. `item_for` and `items_for` are pure functions over the
event stream; `show` is the only function in the module that touches the screen.

The sequence — which events produce items, in what order, carrying what text —
is asserted as ordinary Python, with no `AppTest` involved. `AppTest` is left
covering the thinner claim that the page drew something and kept the session
identifier.

This puts the seam in the same place `events.py` already puts it: the port is
what the agent emits, and a driver's job is to decide what that means before
deciding what it looks like.

## Trade-off accepted

The page gains a layer the terminal driver does not have. `cli.render` goes
straight from an event to a string, and `web.item_for` goes from an event to an
item that something else turns into a widget — so the two drivers, which render
the same events, do not share a shape. That is a standing invitation to drift,
and the warning text is already duplicated in prospect (task 8.3).

In exchange, how the page *looks* stops being load-bearing. `st.status` and an
in-place progress line remain available, because correctness no longer lives in
the widget choice; and a rendering change cannot silently drop an event, because
what is dropped is decided in a function a test can call.
