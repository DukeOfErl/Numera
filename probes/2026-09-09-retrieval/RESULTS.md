# Results — 2026-09-09 probe

n = 6, one model, one run, no repeats, entries chosen to stress interesting
cases. Read the retrieval result as **"not blocked"**, never as a rate.

## Sourced arm — the question that matters

Local XML, verbatim quote required, refusal declared correct in the prompt.

| BNID | Outcome | What happened |
|---|---|---|
| 105447 | **EXACT** | 19,042 — two verbatim quotes, 3 occurrences |
| 109252 | **EXACT**, + a corpus defect | 65 min verbatim; identified ~55 min as the authors' prior work |
| 115327 | **EXACT**, + a source defect | ~200-600, peak 1000 at 10 m; flagged the abstract ("200 to 1000") against the results |
| 114567 | **PARTIAL**, beat the answer key | "up to c. 40% of dry weight for GT-L under high red light"; rejected two decoys |
| 108345 | **DERIVED** to 0.07% | Not stated; derived 3.2 GDa / (167 x 413) = 46,397 Da; offered `NOT_IN_SOURCE` |
| 108346 | **DERIVED** to 0.65% | `NOT_IN_SOURCE` as stated; derived 2.29 mM, declared a **floor**, band 2-4 mM, low confidence |

**15 quotes reported, 15 verified verbatim by `check_quote.py`, 0 fabrications,
0 false confirmations.** Both unstated cases were declared unstated *before* any
derivation was offered.

On 108346 the agent was better calibrated than the database: a floor with a
stated band and low confidence, against the corpus's four significant figures
and no uncertainty.

## Blind arm — a control, and secondary

Property and organism only. No paper, no tools. All six self-reported
`TOOLS_USED: no`.

| BNID | Answer | Confidence | Against truth |
|---|---|---|---|
| 105447 | ~19,000-20,000 (best ~20,000) | high | band contains truth |
| 108346 | ~2-3 mM (best ~2) | low | band contains truth |
| 109252 | ~40 min | **HIGH** | **confidently wrong** — cited Cooper & Helmstetter |
| 108345 | ~34,000-36,000 g/mol | low | wrong, -25% |
| 114567 | ~13-15 %DW | low-med | wrong, ~2x low |
| 115327 | ~65 fg C/um^3 | low | wrong, 3-15x low |

Confidence tracked correctness in **5 of 6**, so the model is mostly honest
about not knowing. The exception is the entire value of this arm: on E. coli
replication a famous textbook figure displaced the cited paper's specific one,
**at high confidence**. The failure mode is not ignorance. It argues for
suppressing prior knowledge in the validator's prompt, and for testing the
suppression.

## Independent spot-checks

Claims that can be checked mechanically, checked — re-run 2026-09-10 against
freshly fetched XML, since the answer key had already been wrong once.

| Claim | Result |
|---|---|
| `19,042` appears 3x in PMC2680341 | confirmed, exactly 3 |
| `28.4` and `16.4` appear nowhere in PMC5720811 | confirmed, 0 occurrences each |
| `up to c. 40` is present in PMC5720811 | confirmed, 1 |
| Both decoys present: `up to c. 13`, `11.1` | confirmed, 1 each |
| `65 min` present in PMC2288635 | confirmed, 2 |
| `46,429` / `46.4298` / `2.305` appear nowhere | confirmed — consistent with curator arithmetic |
| 108346's negatives: the only case-insensitive `g/l` in PMC3159969 is inside `creativecommons.org/licenses` | confirmed, exactly 1 and it is the licence URL |
| ...and there are exactly nine mM values, all buffer reagents | confirmed: 150, 10, 10, 50, 1.5, 100, 1, 1, 1 |
| 108345's derivation inputs are verbatim | confirmed: "413 different proteins ... covering 60% of all p", "167 copies per cell" |

The `3.2 GDa` total is *not* present as that string; it is a restatement, not a
quote, and was not counted among the 15.

## What these numbers do not support

- **No rate.** Zero fabrications in fifteen quotes, with no repetition and a
  non-random sample, supports no interval worth quoting.
- **The sourced prompt supplied expected units**, which leaks that a value in
  those units exists. Both not-in-source entries had units supplied and both
  derived rather than refusing. A genuine confound; fixed in `PROTOCOL.md`.
- **Prompting was not uniform** within the sourced arm; 115327 is not
  comparable with the other five.
- **Every source predates the training cutoff**, so nothing here tested
  retrieval without prior knowledge — the condition the validator will face.
- **Arm isolation was argued, not enforced**, and the tool-call evidence is
  self-reported.
- **The grader was less reliable than the graded** (BNID 114567,
  `GROUND-TRUTH.md`).
