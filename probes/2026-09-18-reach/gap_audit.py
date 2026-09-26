"""Audit the run: is `not_found` real, or is the finder missing things?

A count of not_found is only as good as the finder's false-negative rate, and
calibration was seven cases. This lists what needs a human eye and quantifies
the two known confounds:

  unread material   the value may be in a binary .xls, a PDF or a figure image,
                    none of which the text path reads. Counted separately,
                    because "we could not read it" is not "it is not there".
  thin article      an article whose XML came back short may have yielded no
                    real text, making not_found meaningless for that entry.
"""

import json
import sys
from collections import Counter

PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-1000/suppprobe/gap_results.jsonl"
recs = [json.loads(line) for line in open(PATH)]

cls = Counter(r["class"] for r in recs)
print("=== classes ===")
for k, v in cls.most_common():
    print(f"  {k:16} {v:4}")

nf = [r for r in recs if r["class"] == "not_found"]
print(f"\n=== not_found: {len(nf)} entries ===")
unread = [r for r in nf if r.get("supp_files_unread", 0) not in (0, None)]
toobig = [r for r in nf if r.get("supp_files_unread") == -1]
nosupp = [r for r in nf if not r.get("supp_files_read")]
thin = [r for r in nf if r.get("article_chars", 0) < 8000]
print(f"  had UNREAD supplementary files (binary xls / pdf / images): {len(unread)}")
print(f"  supplementary bundle skipped as too large               : {len(toobig)}")
print(f"  no readable supplementary at all                        : {len(nosupp)}")
print(f"  article text under 8k chars (suspiciously thin)          : {len(thin)}")

print("\n=== not_found sample for manual check ===")
for r in nf[:12]:
    t = r["targets"][0]
    print(
        f"  BNID {r['bnid']:>7} {r['pmcid']:<12} {t['which']}={t['value']!r} units={r['units']!r}"
        f"  art={r.get('article_chars', 0):>7} supp_read={r.get('supp_files_read', 0)}"
        f" unread={r.get('supp_files_unread', 0)}"
    )

ia = [r for r in recs if r["class"] == "in_article"]
print(f"\n=== in_article: how was the match made? ({len(ia)}) ===")
why = Counter(m["why"] for r in ia for m in r.get("matched", []))
for k, v in why.most_common():
    print(f"  {v:3}  {k}")
weak = [r for r in ia for m in r.get("matched", []) if "unit-confirmed" in m["why"]]
print(
    f"\n  matches resting on the weak unit-confirmed path: {len(weak)}"
    f"  ({len(weak) / max(1, len(ia)) * 100:.0f}% of in_article)"
)
print("  -- these are the ones a false positive would hide in; sample:")
for r in weak[:6]:
    m = r["matched"][0]
    print(f"    BNID {r['bnid']:>7} {m['form']!r} :: ...{m['context'][:110]}...")
