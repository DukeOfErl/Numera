# Design

## Context

See `proposal.md` for why. What shapes the how:

- **Two probes are in force.** ADR-0040: retrieval with a verbatim quote works and a mechanical
  checker (`probes/2026-09-09-retrieval/check_quote.py`) is the instrument every "verified" claim
  rests on. ADR-0050: article XML is the reachable surface; `isOpenAccess` is the pre-filter;
  supplementary files and figures are out.
- **Two research reports** were written for this change on 2026-09-18 and are summarised in the
  decisions below: one on how life-science papers place values, conditions and methods (six papers
  inspected as JATS), one on the Europe PMC API (every claim verified by a live call). They live in
  the session's scratchpad, not the repository; what matters from them is recorded here.
- **A client exists on `feat/grounding-validator-cytoskeleton`**: `src/bionumbers/europepmc.py`,
  `cache.py`, `retrieval.py`, a fixture-backed double and `network`-marked live tests. That branch
  is 338 commits behind `dev` and its change is entry-driven; only these modules are wanted.
- **`pyproject.toml` on `dev` already declares** the `validator` extra (`anthropic`, `httpx`,
  `lxml`, `pint`) and the `bionumbers` script, with no package behind them.
- **The ask app supplies**: a sign-in door (`web.admit`, fails closed), `st.connection` to Neon,
  an append-only trail store that fails open, and Streamlit conventions tested through `AppTest`.
- **The default model on `dev` is Opus 4.7**, priced $5 / $25 per million tokens, with a 2,048-token
  prompt-caching minimum and a tokenizer that yields up to about a third more tokens than earlier
  Opus models. A paper's XML is 40 to 150 kB.

## Goals / Non-Goals

**Goals**

- A fixed pipeline whose every step is listable, so the brief's rule applies: no agent loop.
- Every artefact a reviewer sees traceable to a verbatim, mechanically checked quote.
- A review record designed for the rebuild: enough columns that reviewer agreement, distractor
  difficulty and extractor error can all be computed later without re-asking anyone.
- Reuse over rewrite where the reused thing is tested: the Europe PMC client, the quote checker's
  fold table, the sign-in door, the Neon connection pattern.

**Non-Goals**

- Coverage. Discovery keeps what is open access and stops; ADR-0050 says why.
- Cheapness. Opus, one call per paper, no routing. The ceiling exists to stop runaways, not to
  optimise.
- Generality. One property question at a time, biological quantities, Europe PMC only.
- An agent. If the extractor needs to search the paper, it is because the paper was not given to it
  whole; the fix is to give it whole, not to add tools.

## Decisions

### D1. A fixed pipeline with one extraction call per paper, not an agent loop (ADR-0900)

Discovery → fetch → read → **one** structured extraction call → mechanical check → **one** bounded
retry → second-text selection → store. The paper sits in the system block with `cache_control`, so
the retry and the second-text call read it at the cached rate. The extractor never has tools.

*Why not a tool-using agent over the paper:* the ask agent's shape. Rejected because every step here
is known in advance, because the LitXBench finding (frontier models beat multi-turn extraction
pipelines by up to 0.37 F1) argues against loops for extraction, and because a paper fits in one
context. The five failure modes of the loop-engineering brief (no exit, context rot, thrashing,
reward hacking, fake success) mostly cannot occur in a pipeline with a fixed step count; the two that
can — reward hacking of the quote check and fake success — are addressed by D4 and D6.

*Why one call and not a chunked map-reduce:* chunking is what loses the Methods-to-Results link the
scientist report says is the whole difficulty (conditions live in Methods, values in Results tables,
pages apart). The paper goes in whole.

### D2. Named terminal states, not confidence (ADR-0910)

Per paper: `CLAIMS_FOUND`, `NOTHING_TO_EXTRACT`, `NOT_A_RESEARCH_ARTICLE`, `UNREADABLE`,
`CEILING_REACHED`, `FAILED`. Per condition field: `BESIDE_VALUE`, `FROM_METHODS`, `BY_REFERENCE`,
`SUPPLEMENTARY_ONLY`, `NOT_STATED`. Per candidate value: `MEASURED`, `DERIVED` (claims) and
`CITED`, `PARAMETER`, `COMPILED` (rejected, kept for the distractor pool).

*Why these and not a confidence score:* the brief and ADR-0040 both say self-scoring is the least
reliable exit; the probe's blind arm was confidently wrong on the most famous number. The states
come from observed paper structure: `BY_REFERENCE` exists because one of six sample papers offloads
its culture conditions to a citation; `NOTHING_TO_EXTRACT` because a 2026 paper ranked highly for
"doubling time of *E. coli*" states that number only as figure curves; `COMPILED` because a
perspective essay's Table 1 is other papers' values with BNIDs.

*Measured versus cited:* the decisive cue is a `<xref ref-type="bibr">` inside the clause holding the
number, so the JATS reader keeps citation markers as tokens (`[ref 27]`) in passage text rather than
stripping them. Verbs are secondary. This is also why the review page shows the markers.

### D3. The JATS reader produces passages, and passages are the unit everywhere

`read_jats` yields `Passage(text, kind ∈ {p, td, caption, title}, section_path, element_id,
row_headers, column_headers)` plus the licence and the list of supplementary-material references.
Table cells are passages with their headers attached, because the scientist report's clearest
finding is that the authoritative statement is the cell and the prose paraphrases it. `back` is
optional (one sample paper had none). Text is `itertext()` with inline markup flattened; two
micro-sign code points, superscripts in table headers and en-dashes are normal, not edge cases.

The model is given the passages with their ids and asked to quote *and* to name the id it quoted
from. The checker verifies the quote against that passage first and the whole paper second, so a
right quote with a wrong id is caught as a location error rather than passed.

### D4. The checker is ported, not rewritten, and its canary is a test

`quotes.py` carries `check_quote.py`'s fold table byte for byte (as `\u` escapes, ASCII-only, for
the reason its header gives) plus the micro-sign fold the Europe PMC report found necessary (U+00B5
→ U+03BC). Widening the table is a decision recorded in the code with the paper that forced it. The
canary — a one-digit change to a real quote must fail, plain and tag-bearing — becomes a pytest
case over a fixture, so it runs on every commit rather than being asserted in a README.

*Reward hacking of the check:* the cheap way to pass is a sentence that mentions the number without
asserting the measurement. The check cannot see that; the reviewer can, and that is what the second
text is for. The rejected-candidate categories (D2) also give the model a legitimate place to put
such sentences, which removes the incentive to dress them as claims.

### D5. The second text: always two, kind recorded, admissibility mechanical (ADR-0920)

A second call, on the cached paper, asks for candidate second texts of each type from the paper's
passages, given the claim. Selection is then mechanical: reject any candidate whose folded text
contains the claim's value, its rounding to fewer significant figures, or its conversion to the
common units of the property (the `pint` dependency already in the extra); reject any candidate the
extraction pass returned as an occurrence of the same claim; among survivors prefer, in order,
adjacent-condition, cited, different-quantity, parameter, derivation-half; if none survives and the
claim has a second verified occurrence, use that as a second-occurrence item; otherwise no item.

*Why a separate call and not part of extraction:* the extraction output is already large, and the
distractor should be chosen knowing the final verified claim, not a candidate that may be dropped.
The paper is cached, so the second call is cheap.

*Why record the kind and never show it:* uniform experience was the user's decision; the stored kind
is what lets the rebuild measure attention (distractor items) separately from ambiguity
(second-occurrence items).

### D6. Spend: projected before, reported after, discarded on ceiling

Projection uses the provider's token-counting endpoint on the exact request, priced from a table the
module owns (input, cached input, output at the model's rates), with output assumed at the request's
`max_tokens`. The ceiling is checked before each of the up-to-three calls per paper. Actual spend is
taken from the response's usage block including cache-read tokens. A paper that would cross $2 ends
`CEILING_REACHED` with nothing kept: half a paper's claims with no second texts would enter the
record looking complete.

*Why not the ask app's `SpendGate`:* it is a LangChain `wrap_model_call` middleware and this
pipeline has no LangChain. The projection-then-report shape is the same by design (ADR-0180); only
the enforcement point differs.

### D7. Prior knowledge suppressed in the instruction, and tested

The instruction names the property and organism and nothing else about the value: no unit, no
expected magnitude, no canonical figure (the probe's confound, corrected here per its own protocol
notes). It states that `NOTHING_TO_EXTRACT` is correct when true. The suppression is tested with the
one case the probe found: the paper that states 65 min for *E. coli* replication where the textbook
says 40; the fixture-backed test asserts no claim carrying 40 is produced, because no passage
contains it — which the checker enforces regardless of what the model wants to say.

### D8. The store fails closed, and is its own tables (ADR-0930)

Three tables in the existing Neon project, on the `dev` branch database for development:
`review_paper` (identifiers, title, year, licence, state, spend, run), `review_item` (the claim,
both texts with locations, kind and type, the condition block as JSON, the fingerprint) and
`review_decision` (item, reviewer account or null, chosen text, was-supporting, verdict, comment,
time). SQLAlchemy Core, `st.connection` in the page for the engine cache, a plain engine in the
CLI.

*Why not rows in the `trail` table:* the trail is an append-only event log with a `detail` JSON
column and a fail-open writer. The decision is a first-class record with a foreign key to an item,
and its writer must fail closed. Both differences are the point; putting them in one table would
mean one of them loses.

*Why fail closed here when the trail fails open (ADR-0700):* the trail's row is telemetry beside a
product; here the row *is* the product. The page tells the reviewer the decision was not saved and
keeps the item open.

### D9. The review page is a second script, and reuses the door

`review_app.py` at the repository root, beside `streamlit_app.py`, run as its own Streamlit app.
It imports `scinumbers_ask.web.admit`, `effective_session` and `draw_closed_door` for the door, and
`draw_identity` for the sidebar row, with `check_key=None` because a reviewer needs no model
credential. Identity is keyed exactly as the ask app keys it (ADR-0830). With no `[auth]`
configured the door is open and decisions record no account, which `user-identity` already requires.

Everything that is not a screen element lives in `bionumbers.review` and is tested without a
browser; the order and lifetime of elements is tested through `AppTest`, per
`.claude/rules/streamlit-driver.md`.

*Dependency direction:* `bionumbers` core modules (`europepmc`, `jats`, `quotes`, `extraction`,
`distractor`, `spend`, `store`) import no Streamlit and nothing from `scinumbers_ask`. Only
`review_app.py` and `bionumbers.review` (presentation) may. A source-parsing test asserts it, the
way `test_driver_independence.py` does for the ask package.

### D10. The port is unreviewed code, with its correction in the port task

`europepmc.py`, `cache.py`, `retrieval.py` (types only — `resolve_identifier` and `corpus.py` are
the entry-driven half and are not taken), the fixture double and the offline tests come across. The
task that copies `_fetch_full_text` also changes it: "no XML" is *an error status with a non-article
body*, not 404, because the live service answers 500 today and answered 404 when the fixture was
recorded. The `fulltext_missing` fixture is re-recorded as a 500. The two live tests are the two
things that drift: a known non-open-access PMCID yields a non-XML error, and `OPEN_ACCESS:Y` on an
identifier query implies an `<article` body.

*Not taken:* the preprint fallback stays in the code but is switched off by construction (`SRC:PPR`
is excluded at search), because discovery here starts from the version of record and a preprint's
values may differ from it.

### D11. Where the outputs live, and the guard

Fetched XML and search JSON go under `data/europepmc/`, which `.gitignore` covers. Extraction
outputs — claims, rejected candidates, spend — are written as JSONL under `data/runs/<run-id>/`
before anything reaches Postgres, so a run can be inspected and re-loaded. Both paths pass through
`bionumbers_ingest.guard`, imported rather than reimplemented, exactly as `evaluation.py` does: a
run file carries paper text, and although that text is openly licensed, the refusal costs nothing
and a committed 100 kB of someone else's article is a mistake we have already spent a guard on.

## Risks / Trade-offs

- **[The model quotes a sentence that mentions the value without asserting it]** → the checker
  passes it; the reviewer is the check, and the item's `verdict` plus `chosen_text` record it. The
  rebuild measures this rate from the decisions.
- **[Distractors are too easy, so the choice measures nothing]** → the five types are ranked hardest
  first and the type is stored; after the first fifty items, the distribution of wrong choices by
  type says which types to keep.
- **[Distractors are unfair — a second legitimate support slips through]** → the mechanical
  exclusion catches value restatements; "same value, same conditions, other method" it cannot. The
  comment box and the disapproval verdict are the reviewer's route, and such items are found by
  reading disapprovals.
- **[Opus 4.7's tokenizer inflates the paper]** → projection uses the provider's count, not an
  estimate; a 150 kB paper is about 50–65k tokens, well inside the $2 ceiling even three times over.
- **[Prompt caching silently not applied]** → the usage block reports cache-read tokens; the run
  summary prints the cached fraction, and a run with zero cache reads is a bug, not a cost.
- **[A perspective essay gets through with a section titled "Methods"]** → the state
  `NOT_A_RESEARCH_ARTICLE` is a coarse filter; the `COMPILED` candidate category and the
  citation-marker rule catch its values downstream.
- **[`web.admit` changes under the review page]** → the door is imported, not copied, so it moves
  with the ask app; the review page's `AppTest` cases cover open, closed and unconfigured doors.
- **[The Neon `dev` branch fills with test decisions]** → the same convention as the roadmap
  describes: `dev` for development, `test` for live tests, a fresh branch when there are real
  reviewers.

## Migration Plan

No existing behaviour changes. Deployment is additive: install `--extra ask --extra validator`,
create the three tables from `sql/review.sql`, point `[connections.usage]` at the intended Neon
branch, run `bionumbers discover` and `bionumbers extract` for one question, then start
`review_app.py`. Rollback is to stop the second app; the tables can stay.

## Open Questions

- **Which property questions seed the first run.** Deferrable: it changes no code. The scientist
  report's six papers give three obvious ones (doubling time, cell volume, protein copy number, all
  *E. coli* or yeast) with known answers to sanity-check against.
- **Whether `review_decision` should hold a per-item time-to-decide.** Cheap to add, useful for the
  rebuild's attention analysis, not required by any scenario. Add if it costs one column.
