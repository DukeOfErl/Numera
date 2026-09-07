## Why

A reader who wants to run the ask agent now does three things: download the export, run
`bionumbers-ingest`, then start the app. The middle step exists only because nobody has told the app
that the raw file beside its missing corpus is one it could use. Two of the three are unavoidable —
the download, because the data may not be redistributed (ADR-0200), and the run — so the ingest is
the only one that can be removed, and removing it is the difference between a reviewer who gets an
answer and one who reads an error and stops.

The failure today is `CorpusUnavailable: No corpus file at <path>`, which is accurate and unhelpful:
the export may be sitting in that same directory.

## What changes

`bionumbers_ingest` gains a **resolver**: given the configured corpus path, it reports whether a
corpus is already there, whether an export beside it could produce one, and where that corpus would
be written. Building is a separate call, so the caller can say what is about to happen before a
27 MB read begins.

`bionumbers_ask`'s two drivers call it. **That side is owned by `add-ask-agent`** and is not in this
change: this change ships the resolver and the build, and the drivers decide the policy and the
wording. The dependency runs ask → ingest and never back, which is the direction
`test_driver_independence` already enforces.

## What does not change

**A corpus that exists is never rebuilt.** Not when it is older than the export, not when its
manifest names a different digest. A corpus someone produced deliberately being silently replaced is
a worse surprise than a stale one, and "the file changed under me" is the hardest class of bug to see
from the answer side. Staleness detection, if it is ever wanted, is a report and not an action.

**The refusal still fires.** The resolver builds through `ingest()`, which refuses before reading
anything if git would track the output. That guard moved out of the command into the operation
precisely so that this caller would inherit it.

**The ask extra does not grow.** A reviewer installing `--extra ask` wants to run the agent, not to
carry the ingester's dependencies for a convenience that may never fire. The import is guarded on the
consumer's side and the feature degrades to a better error message than today's.
