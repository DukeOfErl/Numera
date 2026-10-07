# ADR-1540: The reviewer always sees two texts; the second's kind is recorded and never shown

- **Status:** accepted
- **Date:** 2026-09-18
- **Pull request:** not yet opened — branch `feat/validator-prototype`

## Context

The mechanical quote check passes any sentence that contains the number, including one that merely
mentions it, cites it, or uses it as an assumption. A person can tell those apart; a substring check
cannot. The brief asked for the reviewer to see the supporting text beside a second text of similar
content and choose — so that approving means having read.

Options:

1. Show the supporting text alone; ask approve/disapprove.
2. Show two texts only when a plausible distractor exists; otherwise one.
3. Always two texts. The second is a distractor when one is admissible, else a second legitimate
   occurrence of the same value, else no item. Record which it was; never show it.

## Decision

Option 3, Yoav's decision of 2026-09-18 ("a uniform experience where the user always has to
choose"). `distractor.py` asks the model, on the cached paper, for candidates of five types in
preference order — adjacent condition, cited, different quantity, parameter, derivation half — and
then decides *mechanically*: a candidate is refused if its folded text contains the claim's value,
any rounding of it to fewer significant figures, or any unit conversion of it (`pint`), or if it is a
recorded occurrence of the claim. The two texts are shown in an order derived from the item id, so
the order is stable and carries no information. The kind and type are columns on the item.

## Trade-off accepted

*Given up:* items. A claim whose paper offers no admissible distractor and no second occurrence
gets no item, and the claim is recorded as not reviewable with the reason. Also given up: a fair
fight in one case the exclusion cannot see — "same value, same conditions, other method" is a
legitimate second support that passes as a distractor. The comment box and disapproval are the
reviewer's route; such items are found by reading disapprovals.

*Bought:* a choice that is made every time, so the presence of a choice says nothing about the item;
and a stored kind that lets the rebuild measure attention (distractor items) apart from ambiguity
(second-occurrence items), and distractor difficulty by type from the first fifty decisions.
