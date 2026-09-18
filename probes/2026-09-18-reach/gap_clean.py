"""Separate "the number is not there" from "we could not read the file".

The first pass conflated them and produced a 43.8% recipe gap that mostly
measured unreadable formats. This recomputes on the subset where the claim is
actually supportable: article text was read, and nothing in the supplementary
bundle was left unread.
"""

import json
import sys
from collections import Counter

PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-1000/suppprobe/gap_results.jsonl"
recs = [json.loads(line) for line in open(PATH)]


def fully_read(r: dict) -> bool:
    """Everything this paper offered was parsed into text."""
    return r.get("article_chars", 0) > 5000 and not r.get("supp_files_unread")


reach = [r for r in recs if r["class"] in ("in_article", "in_supplement", "not_found")]
noart = [r for r in reach if r.get("article_chars", 0) <= 5000]
print(f"reachable (as first classified) : {len(reach)}")
print(f"  of which NO article text read : {len(noart)}")
print("    ^ misclassified: the article fetch returned nothing, which is not evidence of absence")
for r in noart:
    print(f"      BNID {r['bnid']} {r['pmcid']} class={r['class']} chars={r.get('article_chars')}")

real = [r for r in reach if r.get("article_chars", 0) > 5000]
print(f"\nreachable with real article text: {len(real)}")
print("  classes:", dict(Counter(r["class"] for r in real)))

clean = [r for r in real if fully_read(r)]
dirty = [r for r in real if not fully_read(r)]
print(f"\n=== fully read (article + every supplementary file parsed): {len(clean)} ===")
cc = Counter(r["class"] for r in clean)
for k in ("in_article", "in_supplement", "not_found"):
    print(f"  {k:16} {cc.get(k, 0):3}")
if clean:
    found = cc.get("in_article", 0) + cc.get("in_supplement", 0)
    print(f"\n  value present : {found}/{len(clean)}  ({found / len(clean) * 100:.0f}%)")
    print(
        f"  RECIPE GAP    : {cc.get('not_found', 0)}/{len(clean)}"
        f"  ({cc.get('not_found', 0) / len(clean) * 100:.0f}%)"
    )

print(f"\n=== had unread material, so not_found is unsupportable: {len(dirty)} ===")
dc = Counter(r["class"] for r in dirty)
for k in ("in_article", "in_supplement", "not_found"):
    print(f"  {k:16} {dc.get(k, 0):3}")
un = [r.get("supp_files_unread", 0) for r in dirty if r.get("supp_files_unread")]
if un:
    print(
        f"  unread files per paper: min={min(un)} median={sorted(un)[len(un) // 2]} max={max(un)}"
    )

print("\n=== the clean not_found entries, for a human to judge ===")
for r in clean:
    if r["class"] == "not_found":
        t = r["targets"][0]
        print(
            f"  BNID {r['bnid']:>7} {r['pmcid']:<12} {t['which']}={t['value']!r:<10} "
            f"units={str(r['units'])[:22]:<22} art={r.get('article_chars'):>7}"
        )
