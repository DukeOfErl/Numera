# Research behind this change (2026-09-18)

Two reports written by research agents before the proposal, kept because `design.md` summarises
them and the rebuild will want the evidence.

| File | What it establishes |
|---|---|
| `how-papers-report-numbers.md` | Where values, conditions and methods sit in six open-access life-science papers read as JATS; measured vs cited vs derived vs parameter cues; the five distractor types and the exclusion rule; paper types that break the task |
| `europepmc-api-surface.md` | The search fields that actually predict full text, the JATS structure returned, licence layouts, the HTTP 500 for articles without XML, why the Annotations API does not help, the minimal client |

Every claim in the second was verified by a live call on 2026-09-18. The fetched XML and raw
responses the reports cite under `data/` were **not** kept: article text stays out of the repository
(ADR-0170's rule, applied to papers), and both are re-fetchable from the identifiers named.
