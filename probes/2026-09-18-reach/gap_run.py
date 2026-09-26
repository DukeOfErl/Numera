"""How often is a corpus value actually present in what we can reach?

For a random sample of entries that carry a reference PMID and a value:
resolve the paper, fetch article XML and the supplementary bundle, and ask the
calibrated finder whether the value occurs. Classifies each entry into one of:

  no_pmcid        the reference does not resolve to a PMC record
  not_open        resolves, but isOpenAccess=N -- nothing is reachable (probe 2
                  established that this gates supplementary as well as XML)
  in_article      the value occurs in the article text
  in_supplement   not in the article, but in a supplementary file
  not_found       reachable, read, and the value is not in any of it

`not_found` is the recipe gap: the material is in hand and the number is not in
it. It is NOT the same as "not derivable" -- BNID 108345 is not_found and is
nonetheless computable from Table S1 by someone who knows the recipe. Only a
human or an agent can make that second call; this run sizes the population that
needs one.

Both directions are recorded, not just the interesting one. `unread_files`
counts material that exists and could not be parsed (binary .xls, PDF, images),
because a source that yielded no text and a source that yielded text without the
number are different facts and collapsing them would inflate not_found.
"""

import io
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import read_any  # noqa: E402
from numfind import find, strip_markup  # noqa: E402

CORPUS = "/home/yoavpol/corpus/bionumbers.jsonl"
BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
SEED = 20260918
N = int(os.environ.get("GAP_N", "60"))
MAX_SUPP_MB = 40  # bundles run to 163 MB; cap and record the skip
OUT = os.environ.get("GAP_OUT", "/tmp/claude-1000/suppprobe/gap_results.jsonl")
UA = {"User-Agent": "SciNumbers-feasibility-probe/1.0 (research; contact via repo)"}


def get(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def resolve(pmid: str) -> dict:
    q = urllib.parse.urlencode(
        {"query": f"EXT_ID:{pmid}", "resultType": "lite", "format": "json", "pageSize": "1"}
    )
    try:
        d = json.loads(get(f"{BASE}/search?{q}", 45))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:60]}
    rs = d.get("resultList", {}).get("result", [])
    if not rs:
        return {}
    r = rs[0]
    return {"pmcid": r.get("pmcid"), "oa": r.get("isOpenAccess"), "pdf": r.get("hasPDF")}


def article_text(pmcid: str) -> str:
    try:
        raw = get(f"{BASE}/{pmcid}/fullTextXML")
    except Exception:  # noqa: BLE001
        return ""
    return strip_markup(raw.decode("utf8", "replace")) if len(raw) > 5000 else ""


def supplement_texts(pmcid: str, workdir: str) -> tuple[list[str], int, int]:
    """-> (texts, files_read, files_unread). Empty list if no bundle."""
    try:
        raw = get(f"{BASE}/{pmcid}/supplementaryFiles", 180)
    except Exception:  # noqa: BLE001
        return [], 0, 0
    if len(raw) < 1000:
        return [], 0, 0
    if len(raw) > MAX_SUPP_MB * 1024 * 1024:
        return [], 0, -1  # -1 marks "skipped, too large" rather than "unreadable"
    texts, read, unread = [], 0, 0
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except Exception:  # noqa: BLE001
        return [], 0, 0
    os.makedirs(workdir, exist_ok=True)
    for name in z.namelist():
        if name.endswith("/"):
            continue
        target = os.path.join(workdir, os.path.basename(name))
        try:
            with open(target, "wb") as f:
                f.write(z.read(name))
            text, _how = read_any(target)
            texts.append(text)
            read += 1
        except Exception:  # noqa: BLE001
            unread += 1
        finally:
            if os.path.exists(target):
                os.remove(target)
        # inner zips carry the real tables (Tables S1-S8 in the M. pneumoniae case)
        if name.lower().endswith(".zip"):
            try:
                inner = zipfile.ZipFile(io.BytesIO(z.read(name)))
                for iname in inner.namelist():
                    if iname.endswith("/"):
                        continue
                    itarget = os.path.join(workdir, os.path.basename(iname))
                    try:
                        with open(itarget, "wb") as f:
                            f.write(inner.read(iname))
                        text, _how = read_any(itarget)
                        texts.append(text)
                        read += 1
                    except Exception:  # noqa: BLE001
                        unread += 1
                    finally:
                        if os.path.exists(itarget):
                            os.remove(itarget)
            except Exception:  # noqa: BLE001
                pass
    return texts, read, unread


def targets(d: dict) -> list[tuple[str, float]]:
    """Which numbers of an entry to look for. Value, else range endpoints."""
    out = []
    if d.get("value") is not None:
        out.append(("value", float(d["value"])))
    else:
        for k in ("range_low", "range_high"):
            if d.get(k) is not None:
                out.append((k, float(d[k])))
    return out


def main() -> int:
    rows = []
    with open(CORPUS) as f:
        for line in f:
            d = json.loads(line)
            if d.get("reference_pubmed_id") and targets(d):
                rows.append(d)
    print(f"eligible entries (pmid + value/range): {len(rows)}", flush=True)
    random.seed(SEED)
    sample = random.sample(rows, min(N, len(rows)))
    print(f"sampling {len(sample)} with seed {SEED}\n", flush=True)

    work = "/tmp/claude-1000/suppprobe/_work"
    seen_out = open(OUT, "w")
    counts: dict[str, int] = {}
    for i, d in enumerate(sample, 1):
        bnid = str(d["bnid"])
        pmid = str(d["reference_pubmed_id"])
        units = d.get("units")
        tg = targets(d)
        rec = {
            "bnid": bnid,
            "pmid": pmid,
            "units": units,
            "targets": [{"which": w, "value": v} for w, v in tg],
        }
        info = resolve(pmid)
        rec["pmcid"] = info.get("pmcid")
        rec["oa"] = info.get("oa")
        if not info.get("pmcid"):
            rec["class"] = "no_pmcid"
        elif info.get("oa") != "Y":
            rec["class"] = "not_open"
        else:
            art = article_text(info["pmcid"])
            rec["article_chars"] = len(art)
            hits_a = {w: find(v, art, units) for w, v in tg} if art else {}
            if any(hits_a.values()):
                rec["class"] = "in_article"
                rec["matched"] = [
                    {
                        "which": w,
                        "form": h[0]["form"],
                        "why": h[0]["why"],
                        "context": h[0]["context"][:160],
                    }
                    for w, h in hits_a.items()
                    if h
                ]
            else:
                sup, nread, nunread = supplement_texts(info["pmcid"], work)
                rec["supp_files_read"] = nread
                rec["supp_files_unread"] = nunread
                hit_s = None
                for t in sup:
                    for w, v in tg:
                        hh = find(v, t, units)
                        if hh:
                            hit_s = {
                                "which": w,
                                "form": hh[0]["form"],
                                "why": hh[0]["why"],
                                "context": hh[0]["context"][:160],
                            }
                            break
                    if hit_s:
                        break
                if hit_s:
                    rec["class"] = "in_supplement"
                    rec["matched"] = [hit_s]
                else:
                    rec["class"] = "not_found"
        counts[rec["class"]] = counts.get(rec["class"], 0) + 1
        seen_out.write(json.dumps(rec) + "\n")
        seen_out.flush()
        print(f"[{i:3}/{len(sample)}] {bnid:>7} pmid={pmid:<9} -> {rec['class']}", flush=True)
        time.sleep(0.4)
    seen_out.close()

    print("\n=== CLASSIFICATION ===")
    tot = sum(counts.values())
    for k in ("no_pmcid", "not_open", "in_article", "in_supplement", "not_found"):
        c = counts.get(k, 0)
        print(f"  {k:16} {c:4}  {c / tot * 100:5.1f}%")
    reach = (
        counts.get("in_article", 0) + counts.get("in_supplement", 0) + counts.get("not_found", 0)
    )
    if reach:
        found = counts.get("in_article", 0) + counts.get("in_supplement", 0)
        print(f"\n  reachable (OA, text read): {reach}")
        print(f"  value present in it      : {found}  ({found / reach * 100:.1f}% of reachable)")
        print(
            f"  RECIPE GAP (not_found)   : {counts.get('not_found', 0)}"
            f"  ({counts.get('not_found', 0) / reach * 100:.1f}% of reachable)"
        )
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
