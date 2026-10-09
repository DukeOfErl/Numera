# `bionumbers` — the validator prototype

Loaded when a file in this package is read. The root `CLAUDE.md` has the one-paragraph version.

A **fixed pipeline, not an agent** (ADR-1520): discovery → fetch → JATS reader → one structured
extraction call → mechanical quote check → one retry → one second-text call → JSONL under
`data/runs/<run-id>/` → Postgres → a review page. No module here builds a graph or hands the model a
tool; if the extractor seems to need to search the paper, give it the whole paper.

| Module | Holds |
|---|---|
| `records.py` | Every shape the steps exchange, as frozen pydantic models; the closed state sets (ADR-1530). Also the extraction call's output schema |
| `europepmc.py` | The client: identifier retrieval (ported), `search_open_access`, `fetch`, `licence_of`, the project `User-Agent`. "No XML" is read from the body, not the status |
| `cache.py` / `retrieval.py` | The disk cache and the typed retrieval outcomes, ported from the feasibility branch |
| `jats.py` | `read_jats` → passages with ids; table cells carry their headers; `[ref N]` tokens for bibliographic markers; `render_for_model` |
| `quotes.py` | The fold table from the retrieval probe, byte for byte, plus the micro sign; `verify` names the passage first and the paper second |
| `spend.py` | Prices for the configured model, projection through the provider's token count, `Ledger` with the $2 per-paper ceiling and the run budget |
| `extraction.py` | The instruction (no unit, no expected value), the one call, the verification pass, the states, the fingerprint, the JSONL writer behind the ingester's guard |
| `distractor.py` | The second text: candidates of five types, mechanical exclusion of the value in every form, preference order, second-occurrence fallback (ADR-1540) |
| `store.py` | `review_paper`, `review_item`, `review_decision`, `review_skip`, `curated_entry` in SQLAlchemy Core; a decision in two writes on one row, `record_choice` then `record_verdict`, or `record_issue` at either step; a person's `Preference` (domain, topic, skips) that the serving query takes and the runner never passes (ADR-0980); every writer **fails closed** (ADR-0930, ADR-0970). DDL in `sql/review.sql` |
| `review.py` | Presentation: the two texts in an uninformative order and as the paper wrote them, the whole table a cell sits in (ADR-0940), the condition rows, each step's completeness rule |
| `harvest.py` | Harvest mode (ADR-0950): the classes of number wanted and not wanted, the instruction built from extraction's, the three model-written labels, the twenty-claim bound, one scope per domain (ADR-1500), `organismal` among them |
| `curated.py` | The curated tier (ADR-1510): which BioNumbers entries in the slice nothing marks doubtful, and why each other one is left out |
| `cli.py` | `bionumbers discover \| harvest \| extract \| load \| curate \| status \| simulate-review \| upgrade-store` |
| `paths.py` | `data/europepmc/`, `data/runs/`; a test asks git that both stay ignored |
| `readings.py` | A reviewer's typed value against the stored one: both parsed through `quotes.fold` and pint (±, ~, number words, thousands, exponents, `u` for µ), compared at the reader's precision; four closed states, a hint and no verdict. `store.record_choice` computes it |
| `simulated_review.py` | Models standing in for reviewers (ADR-0960): the two screens as text, built from `review.py`'s own functions; each role's subset by hash; two calls per decision under a ledger; rows that say a model wrote them and which model answered. A second **driver** over the review task, not a pipeline step |

**The dependency direction holds here too.** Core modules import no Streamlit and nothing from
`scinumbers_ask`; only `review.py` and the root `review_app.py` may, and
`tests/test_bionumbers_dependency_direction.py` asserts it over the source the way
`test_driver_independence.py` does for the ask package. The review page imports the ask app's
door (`web.admit` with `check_key=None`) rather than copying it, so a deployment installs both
extras.

**What the model is never shown**: a decision, a choice or a comment. Decisions measure the
extractor and cannot also be its input; the messages are built from the paper and the question only.
A simulated reviewer is a different model call with the mirror rule: it sees one item's screen and
nothing else -- not the paper, not the second text's kind, not another reviewer's row.

**A row with `reviewer_model` set and a role other than `AI` is simulated**, and anything that
counts or draws decisions has to say so. A row with `approved` null and `issue` empty is *open*: a
choice awaiting its verdict, still the reviewer's to finish. The store's writers are the only way
in, one per step and shape; there is no check constraint behind them.

**The value is withheld until the text is chosen** (ADR-0970), on the page and in the simulated
review alike. Nothing on the first screen may name the stored value, the paper's own term for the
quantity, or a condition: `tests/test_review_app.py` and `test_bionumbers_simulated_review.py`
both read the first screen for them. `value_read` is written before the reveal and is the one
figure the extractor's answer cannot have steered.

**Every OpenRouter price is a price at one provider.** `spend.Prices.provider` is the slug the
row was read from and `cli._model` pins the request to it with no fallback; a row without a pin
is a projection against whatever OpenRouter picks. The Jev router is the one unpinned row, priced
as an upper bound.

**Ported code is unreviewed code.** `europepmc.py`, `cache.py` and `retrieval.py` came from
`feat/grounding-validator-cytoskeleton` with two corrections made in the port itself; the commit
that brought them across lists what a review found.

