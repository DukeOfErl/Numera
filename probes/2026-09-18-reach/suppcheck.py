"""Does the supplementary material contain what the article text did not?

This is the recipe gap in miniature, on the two entries where the answer is
known: BNID 108345/108346 are the curator's arithmetic over Tables S1-S8, so the
files are reachable and the number is not in them -- unless it is, which is the
thing to find out rather than assume.
"""

import glob
import os
import sys

from extract import read_any
from numfind import find

ROOT = "/tmp/claude-1000/suppprobe"

TARGETS = [
    ("108345 average protein MW", 46429.8, "g/mole", f"{ROOT}/x3159969/tables"),
    ("108346 molar protein conc", 2.305, "mM", f"{ROOT}/x3159969/tables"),
    # the paper's own stated inputs, as a positive control: if the reader works,
    # the 413-protein count and a known abundance must turn up.
    ("CONTROL 413 proteins", 413.0, "proteins", f"{ROOT}/x3159969/tables"),
    ("115327 carbon density peak", 1000.0, "fg C/um^3", f"{ROOT}/x5005352"),
    ("CONTROL depth 9.57 mbsf", 9.57, "mbsf", f"{ROOT}/x5005352"),
]


def main() -> int:
    for label, value, units, d in TARGETS:
        files = sorted(glob.glob(f"{d}/*"))
        read, skipped, total_chars = [], [], 0
        allhits = []
        for f in files:
            if os.path.isdir(f):
                continue
            try:
                text, how = read_any(f)
            except Exception as e:  # noqa: BLE001 - want the reason, per file
                skipped.append((os.path.basename(f), str(e)[:45]))
                continue
            read.append((os.path.basename(f), how, len(text)))
            total_chars += len(text)
            for h in find(value, text, units):
                allhits.append((os.path.basename(f), h))
        print(f"=== {label}  (value {value}, units {units!r}) ===")
        print(f"    read {len(read)} files, {total_chars:,} chars; skipped {len(skipped)}")
        for n, why in skipped:
            print(f"      UNREAD  {n}  ({why})")
        if allhits:
            print(f"    FOUND in supplementary: {len(allhits)} hit(s)")
            for fn, h in allhits[:3]:
                print(f"      {fn}: {h['form']!r} ({h['why']})")
                print(f"        ...{h['context'][:120]}...")
        else:
            print("    NOT FOUND in any readable supplementary file")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
