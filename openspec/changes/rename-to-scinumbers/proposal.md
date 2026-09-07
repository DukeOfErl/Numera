## Why

The app calls itself **SciNumbers** everywhere a human can see it — `README.md`, `CHANGELOG.md`, the
Streamlit page title — and `bionumbers_ask` everywhere a developer can. The rename went as far as the
user-facing surface and stopped at the package and script names.

That is not only untidy. BioNumbers is the first corpus this project tests its idea against, not the
only one; a purpose-built database is planned. The name `bionumbers_ask` asserts a coupling the code
has largely already shed — all five `add-ask-agent` capability specs are written source-agnostically,
and several user-facing strings already say "identifier" rather than "BNID".

The one place the coupling is real is the citation notation. `BNID 100002` is what the model is told
to write, and it is also what BioNumbers writes in its own entry prose (`"Range for E. coli B. See
BNID 102065, 104333"`). Those are two different texts with two different authors, and one parser has
been serving both.

## What changes

**The package is renamed** to `scinumbers_ask`, with the console script `scinumbers-ask` and the
environment prefix `SCINUMBERS_*`. The retired environment names are refused by name, following the
precedent already set for `BIONUMBERS_ASK_WARN_USD`.

**`BNID` survives in exactly one module**, `scinumbers_ask/bionumbers.py`, which carries today's
regex verbatim and is used only to read and render what BioNumbers wrote. The model is asked for a
delimited form, `[[100002]]`, and BioNumbers' notation is rewritten into it **when an entry is
rendered to the model** — never in the corpus, which keeps the source's own words so that a
displayed entry remains an attribution and a raw-entry view stays possible.

**The answer parser accepts either form.** Not because the model mimics what it reads — the rewrite
removes that — but because a user who knows BioNumbers types `BNID 100002` in a question, and
sessions are checkpointed, so that notation persists for the rest of the conversation.

**The identifier field becomes `entry_id`**, still an integer. The corpus key changes with it, so a
corpus built by an older ingester is refused by name rather than by `KeyError`.

## What does not change

`bionumbers_ingest` keeps its name — it genuinely is the BioNumbers adapter, and that is correct
naming rather than coupling. `src/bionumbers/` and the `bionumbers` console script are untouched;
they belong to the unmerged `feat/grounding-validator-cytoskeleton`.

**No source abstraction is introduced.** An earlier draft added a `Source` descriptor read from the
corpus manifest so a second database could be plugged in without touching the agent. That is
speculative while BioNumbers is the only corpus, and it was dropped. `organism`, `property` and the
binomial alias index stay exactly as they are. When a second source arrives, that is when it gets
designed.
