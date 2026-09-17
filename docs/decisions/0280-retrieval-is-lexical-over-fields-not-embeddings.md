# ADR-0280: Retrieval matches fields lexically; there is no vector store

- **Status:** accepted
- **Date:** 2026-09-14
- **Pull request:** _pending — `docs/adr-no-vector-store`_

> **Written retroactively**, against this project's own rule that an ADR is written
> with the change that makes the decision. The decision was made silently inside
> `add-ask-agent` by building the alias index and never considering an alternative
> out loud, which is exactly how the rejected options come to be lost. What follows
> reconstructs the reasoning and adds the evidence that has since accumulated
> against it; treat the "options on the table" as reconstructed rather than recorded.

## Context

The corpus is 14,294 **structured records**, not documents: each carries a property,
an organism, a value, units, a measurement method and free-text comments. A question
is almost always a lookup over two of those columns — *number of ribosomes* in
*Escherichia coli*.

The conventional answer for retrieval-augmented generation, and the one the capstone
brief names in Cases 1 and 3, is to embed the corpus and put it in a vector store
(ChromaDB, Pinecone). That option was never argued down in writing. What was built
instead is lexical: a deterministic alias index over property and organism
([ADR-0130](0130-deterministic-alias-index.md)), searched in two tiers — capped
summaries with an honest total, then whole entries by identifier
([ADR-0150](0150-two-tier-retrieval.md)).

Three forces make the default a worse fit here than usual:

- **What retrieval returned has to be auditable.** Every citation in an answer is
  checked against the entries tool calls actually returned, and one that was not is
  flagged as unsupported. That check only means something if the retrieved set is
  reproducible for the same question.
- **The match is on fields, not on prose.** Similarity over concatenated entry text
  puts ribosome *mass fraction* next to ribosome *count*. They are different
  properties, and an answer that conflates them is wrong in the way this project
  exists to prevent.
- **The deployment is one Streamlit container** with a corpus fetched at start-up. A
  vector index is a second artefact to build, version against the corpus digest, and
  ship.

## Decision

Retrieval is lexical over the structured fields. No embeddings, no vector database,
no similarity ranking anywhere in the retrieval path.

**Hybrid retrieval — keyword for precision on the field, vector similarity for the
spelling variants the alias index misses, the two fused — is deferred, not rejected.**
It is the intended successor, and the section below is the argument for it.

## Trade-off accepted

Recall rests entirely on the alias index catching how a property is spelt, and **the
first evaluation baseline has now measured the ceiling that puts on us**: `property`
is free text rather than a controlled vocabulary. Ten entries record the ribosome
count under four spellings — `Number of ribosomes/cell`, `Number of ribosomes in ...`,
`No. of ribosomes per ...`, `Mean number of ribosomes ...` — and **no (property,
organism) pair in the corpus holds five or more entries with a usable value**, which
is why the outlier check in `scoring.py` cannot fire on real data at all.

That is the strongest evidence against this decision, and it is recorded here rather
than in a footnote. It does not overturn the auditability argument — approximate
nearest-neighbour ranking shifts with the embedding model, its version and the index
parameters, so an evaluation measured across a retrieval set that can move silently
measures two things at once. It does say that lexical-only is a floor we have now hit,
and that the successor above should be scheduled rather than left as an aspiration.

Also given up: nothing here can answer a question phrased in terms the corpus does not
use. A reader asking about "protein synthesis machinery" gets nothing, where a
semantic index would have found ribosomes.
