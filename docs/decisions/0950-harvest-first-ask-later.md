# ADR-0950: Harvest papers for their reusable numbers first; answer questions from the store

- **Status:** accepted
- **Date:** 2026-10-03
- **Pull request:** not yet opened — branch `feat/harvest-prototype`, off `feat/validator-prototype`

## Context

The validator prototype starts from a question, searches Europe PMC for papers, and extracts the
asked value from each. Three trial questions (2026-09-18 to 2026-09-23) read 32 papers and found 4
on target. The extractor was right every time, including each "nothing to extract"; the search was
the weak link. A full-text query for a property and an organism returns papers that mention both
and measure neither: "cell volume" matched the unit cell of ZnO crystals, and *E. coli* appeared
as a pathogen in feed trials. Every miss cost $0.13 to $0.52 to confirm.

Options: sharpen the query (ranking, synonyms, taxon ids), which treats precision at question
time and still pays per question for every wrong paper; keep the question but triage papers with
a cheap model first; or drop the question from extraction altogether, harvest papers ahead of
time for the numbers worth keeping, and answer questions from the resulting store, as the ask
agent already does from BioNumbers.

"Every number in the paper" was considered and rejected as a scope: papers are full of p-values,
sample sizes and reagent amounts. The scope has to say what a useful number is.

## Decision

Extraction gains a harvest mode. A run is started from a list of articles
(`bionumbers harvest`), and each is asked once for the quantitative values a scientist outside
the study would look up and reuse. The scope is seven classes — size, copy number, concentration,
rate, time, fraction, physical constant — read off the 492 BioNumbers entries for yeast and for
the cytoskeleton that are measured, carry a method and cite a paper; plus a list of what is never
wanted. It is data in `bionumbers.harvest` and travels in the user turn.

The instruction is the extraction instruction with its opening replaced and three rules added:
at most twenty claims per paper (ten until the first seed of 2026-10-04) with baseline and summary values first; a short rejected list; and
three labels the model writes for each claim (property name, class, species), which are the only
unquoted fields. The quote checker, the retry, the claim categories, the conditions and the second
text are unchanged. A claim is named by its label and its review item asks about that.

Review moves away from retrieval: each entry carries a trust tier derived from the decisions it
has collected, and the review pipeline (a separate change) fills those in over time.

**Amended 2026-10-04.** A third claimable category, `DERIVED_FROM_PUBLISHED`, for a value an
article computes itself from other publications' data. On the first model comparison one paper
(PMC2590609, yeast translation figures estimated from published genome-wide datasets) was taken as
ten derived claims by three models and refused outright by three others, each reading "derived
from its own measurements" its own way. BioNumbers lists four entries from that paper. Keeping
such values under their own category records what they are instead of forcing a choice between
mislabelling and losing them. The alternative, leaving the rule strict, would drop the papers that
are most often the cited source of a number.

## Trade-off accepted

Cost now scales with papers harvested rather than with questions asked, and is paid before anyone
asks anything. The property name, class and species are model-written labels that nothing checks
mechanically, where every other field is a verified quote; a vocabulary that maps them to
canonical properties is still to be built, and until then two papers may name one quantity two
ways. The claim bound drops real values from rich papers: at ten, the first seed recovered 15 of
BioNumbers' 34 values for its ten papers, which is why it is twenty. The question-first path stays
in the code and is no longer the direction.
