"""What formats does the unreadable material actually consist of?

91% of reachable papers in the sample carried files the text path could not read,
which is what makes the recipe gap unmeasurable with a text-only reader. This
counts the formats, so the next capability to build is chosen from data rather
than from the two papers that happened to be inspected by hand.

Counts bytes as well as files: 280 thumbnail GIFs and one 19-page PDF of tables
are the same "1 file unread" to the audit and very different to a reader.
"""

import io
import json
import os
import sys
import time
import urllib.request
import zipfile
from collections import Counter

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
IN = "/tmp/claude-1000/suppprobe/gap_results_backfilled.jsonl"
UA = {"User-Agent": "Numera-feasibility-probe/1.0 (research; contact via repo)"}
READABLE = {".xml", ".nxml", ".xlsx", ".docx", ".dotx"}


def main() -> int:
    recs = [json.loads(line) for line in open(IN)]
    reach = [
        r
        for r in recs
        if r["class"] in ("in_article", "in_supplement", "not_found")
        and r.get("article_chars", 0) > 5000
    ]
    print(f"bundles to census: {len(reach)}\n", flush=True)
    files = Counter()
    byts = Counter()
    papers_with = Counter()
    nobundle = 0
    for i, r in enumerate(reach, 1):
        try:
            req = urllib.request.Request(f"{BASE}/{r['pmcid']}/supplementaryFiles", headers=UA)
            with urllib.request.urlopen(req, timeout=180) as h:
                raw = h.read()
        except Exception:  # noqa: BLE001
            nobundle += 1
            continue
        if len(raw) < 1000:
            nobundle += 1
            continue
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
        except Exception:  # noqa: BLE001
            nobundle += 1
            continue
        here = set()
        for info in z.infolist():
            if info.filename.endswith("/"):
                continue
            ext = os.path.splitext(info.filename)[1].lower() or "(none)"
            files[ext] += 1
            byts[ext] += info.file_size
            here.add(ext)
        for e in here:
            papers_with[e] += 1
        print(f"[{i:3}/{len(reach)}] {r['pmcid']:<12} {len(z.infolist()):4} files", flush=True)
        time.sleep(0.3)

    print(f"\nno bundle at all: {nobundle} of {len(reach)} papers\n")
    print(f"{'ext':10} {'files':>7} {'MB':>9} {'papers':>7}  readable?")
    for ext, n in files.most_common(18):
        mark = "yes" if ext in READABLE else "NO"
        print(f"{ext:10} {n:7} {byts[ext] / 1e6:9.1f} {papers_with[ext]:7}  {mark}")

    unread_files = sum(n for e, n in files.items() if e not in READABLE)
    unread_bytes = sum(b for e, b in byts.items() if e not in READABLE)
    tot_f, tot_b = sum(files.values()), sum(byts.values())
    print(
        f"\nunreadable: {unread_files}/{tot_f} files ({unread_files / tot_f * 100:.0f}%), "
        f"{unread_bytes / 1e6:.0f}/{tot_b / 1e6:.0f} MB ({unread_bytes / tot_b * 100:.0f}%)"
    )
    print("\npapers that would be unlocked by ONE more reader:")
    for ext in (".pdf", ".xls", ".doc", ".csv", ".txt"):
        if papers_with.get(ext):
            print(f"  {ext:6} -> {papers_with[ext]:3} of {len(reach)} papers")
    img = sum(papers_with.get(e, 0) for e in (".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff"))
    print(f"  images -> present in up to {img} paper-format pairs (figure reading)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
