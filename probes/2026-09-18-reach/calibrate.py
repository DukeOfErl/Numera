"""Does the number-finder actually work? Calibrate it before counting anything.

The six entries from the 2026-09-09 probe are the only place in this project
where ground truth is known, so they are the calibration set. Each case names
the expectation and WHERE it comes from -- the source text, not the finder's own
output, because an expectation read off the tool under test is a photograph of
current behaviour promoted to a contract.

The harness aborts unless the canaries fail. A finder that reports everything
present, or nothing present, would otherwise produce a clean-looking table.
"""

import sys

from extract import from_xml
from numfind import find

XMLDIR = "/home/yoavpol/AI Engineering/Numera-feasibility/probes/2026-09-09-retrieval/data"

# (label, pmcid, value, units, expected_present, why the expectation holds)
CASES = [
    (
        "105447 protein-coding genes",
        "PMC2680341",
        19042.0,
        "Unitless",
        True,
        "GROUND-TRUTH.md: stated 3x; occurs as '19,042' -- the comma false negative",
    ),
    (
        "109252 S phase, upper end",
        "PMC2288635",
        65.0,
        "minutes",
        True,
        "GROUND-TRUTH.md: paper states 65 min",
    ),
    (
        "115327 carbon density peak",
        "PMC5005352",
        1000.0,
        "fg C/\u03bcm^3",
        True,
        "GROUND-TRUTH.md: 'peaking at 1000 fg C um^-3'",
    ),
    (
        "114567 carbohydrate upper",
        "PMC5720811",
        40.4,
        "% of dry weight",
        True,
        "GROUND-TRUTH.md: paper states 'up to c. 40% of dry weight' -- needs sig-fig rounding",
    ),
    (
        "114567 carbohydrate central",
        "PMC5720811",
        28.4,
        "% of dry weight",
        False,
        "GROUND-TRUTH.md: curator-computed, string absent from the paper",
    ),
    (
        "108345 average protein MW",
        "PMC3159969",
        46429.8,
        "g/mole",
        False,
        "GROUND-TRUTH.md: curator arithmetic, not stated in the paper",
    ),
    (
        "108346 molar protein conc",
        "PMC3159969",
        2.305,
        "mM",
        False,
        "GROUND-TRUTH.md: curator arithmetic, not stated in the paper",
    ),
]

# Must NOT be found. A finder that cannot fail proves nothing.
CANARIES = [
    (
        "one digit off 19042",
        "PMC2680341",
        19043.0,
        "Unitless",
        "19,043 does not occur; 19,042 does -- so a hit here means the matcher is fuzzy",
    ),
    ("absurd value", "PMC2680341", 87654321.0, "Unitless", "nothing like it in the paper"),
    (
        "one digit off 65 min",
        "PMC2288635",
        66.0,
        "minutes",
        "the paper states 65 min, not 66 -- the unit-confirmed path must discriminate too",
    ),
    (
        "plausible but absent %DW",
        "PMC5720811",
        33.7,
        "% of dry weight",
        "a percentage the paper does not state, in a paper full of percentages",
    ),
]


def main() -> int:
    texts = {}
    for pmcid in {c[1] for c in CASES} | {c[1] for c in CANARIES}:
        texts[pmcid] = from_xml(f"{XMLDIR}/{pmcid}.xml")

    print("=== CANARIES (must all be ABSENT) ===")
    canary_ok = True
    for label, pmcid, val, units, why in CANARIES:
        hits = find(val, texts[pmcid], units)
        ok = not hits
        canary_ok &= ok
        print(f"  [{'ok' if ok else 'FAIL'}] {label:24} {val:<12g} hits={len(hits)}")
        if hits:
            print(f"        why this matters: {why}")
            for h in hits[:3]:
                print(f"        matched {h['form']!r} ({h['why']}): ...{h['context'][:110]}...")
    if not canary_ok:
        print(
            "\nABORT: the finder matched something that is not there. "
            "Any count it produces is meaningless."
        )
        return 1

    print("\n=== CALIBRATION CASES ===")
    wrong = []
    for label, pmcid, val, units, expect, why in CASES:
        hits = find(val, texts[pmcid], units)
        got = bool(hits)
        ok = got == expect
        mark = "ok" if ok else "MISMATCH"
        exp_s = "present" if expect else "absent"
        got_s = "present" if got else "absent"
        print(f"  [{mark}] {label:30} value={val:<10g} expected={exp_s:7} got={got_s}")
        if hits:
            forms = sorted({(h["form"], h["why"]) for h in hits})
            for f, w in forms[:3]:
                print(f"           via {f!r} ({w})")
        if not ok:
            wrong.append((label, expect, got, why, hits[:2]))

    agree = len(CASES) - len(wrong)
    print(f"\n=== RESULT: {agree}/{len(CASES)} calibration cases agree with ground truth ===")
    for label, expect, got, why, hits in wrong:
        direction = "FALSE POSITIVE" if got else "FALSE NEGATIVE"
        print(f"\n  {direction}: {label}")
        print(f"    ground truth: {'present' if expect else 'absent'} -- {why}")
        for h in hits:
            print(f"    matched {h['form']!r} ({h['why']}): ...{h['context'][:130]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
