"""Fetch supplementary for the entries that matched in the article.

gap_run.py only fetched a supplementary bundle when the article match failed, so
`supp_files_unread` was absent for every in_article entry and any partition on
"fully read" separated found from not-found by construction. This backfills the
missing side so the partition means something.

It changes no classification -- a value found in the article is still in_article.
It only records how much of that paper's material was unreadable, which is the
covariate the audit needs.
"""

import io
import json
import os
import sys
import time
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import read_any  # noqa: E402

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
IN = "/tmp/claude-1000/suppprobe/gap_results.jsonl"
OUT = "/tmp/claude-1000/suppprobe/gap_results_backfilled.jsonl"
MAX_SUPP_MB = 40
UA = {"User-Agent": "SciNumbers-feasibility-probe/1.0 (research; contact via repo)"}
WORK = "/tmp/claude-1000/suppprobe/_bwork"


def supp_stats(pmcid: str) -> tuple[int, int]:
    """-> (files_read, files_unread). (0, -1) if the bundle was too large."""
    try:
        req = urllib.request.Request(f"{BASE}/{pmcid}/supplementaryFiles", headers=UA)
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read()
    except Exception:  # noqa: BLE001
        return 0, 0
    if len(raw) < 1000:
        return 0, 0
    if len(raw) > MAX_SUPP_MB * 1024 * 1024:
        return 0, -1
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except Exception:  # noqa: BLE001
        return 0, 0
    os.makedirs(WORK, exist_ok=True)
    read = unread = 0
    for name in z.namelist():
        if name.endswith("/"):
            continue
        target = os.path.join(WORK, os.path.basename(name))
        try:
            with open(target, "wb") as f:
                f.write(z.read(name))
            read_any(target)
            read += 1
        except Exception:  # noqa: BLE001
            unread += 1
        finally:
            if os.path.exists(target):
                os.remove(target)
        if name.lower().endswith(".zip"):
            try:
                inner = zipfile.ZipFile(io.BytesIO(z.read(name)))
                for iname in inner.namelist():
                    if iname.endswith("/"):
                        continue
                    it = os.path.join(WORK, os.path.basename(iname))
                    try:
                        with open(it, "wb") as f:
                            f.write(inner.read(iname))
                        read_any(it)
                        read += 1
                    except Exception:  # noqa: BLE001
                        unread += 1
                    finally:
                        if os.path.exists(it):
                            os.remove(it)
            except Exception:  # noqa: BLE001
                pass
    return read, unread


def main() -> int:
    recs = [json.loads(line) for line in open(IN)]
    todo = [r for r in recs if r["class"] == "in_article"]
    print(f"backfilling supplementary stats for {len(todo)} in_article entries", flush=True)
    for i, r in enumerate(todo, 1):
        read, unread = supp_stats(r["pmcid"])
        r["supp_files_read"] = read
        r["supp_files_unread"] = unread
        print(
            f"[{i:3}/{len(todo)}] {r['bnid']:>7} {r['pmcid']:<12} read={read} unread={unread}",
            flush=True,
        )
        time.sleep(0.4)
    with open(OUT, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
