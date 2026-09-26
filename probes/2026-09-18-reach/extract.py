"""Reachable source material -> plain text.

Handles what Europe PMC's supplementaryFiles bundle actually contains: JATS XML,
xlsx, xls-as-xml, docx, and (as a named gap) PDF. Anything it cannot read is
reported as unread rather than silently contributing an empty string -- a source
that yielded no text and a source that yielded text without the number are
different facts, and collapsing them would inflate the "not present" count.
"""

import re
import zipfile
from xml.etree import ElementTree as ET

from numfind import norm, strip_markup

XL = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def from_xml(path: str) -> str:
    with open(path, encoding="utf8", errors="replace") as f:
        return strip_markup(f.read())


def from_xlsx(path: str) -> str:
    out = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(f"{XL}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{XL}t")))
        sheets = sorted(
            (n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
            key=lambda n: int(re.search(r"(\d+)", n.split("/")[-1]).group(1)),
        )
        for sn in sheets:
            root = ET.fromstring(z.read(sn))
            for row in root.iter(f"{XL}row"):
                cells = []
                for c in row.findall(f"{XL}c"):
                    v = c.find(f"{XL}v")
                    t = c.get("t")
                    if t == "inlineStr":
                        cells.append("".join(x.text or "" for x in c.iter(f"{XL}t")))
                    elif v is None:
                        continue
                    elif t == "s":
                        cells.append(shared[int(v.text)])
                    else:
                        cells.append(v.text or "")
                if cells:
                    out.append(" ".join(cells))
    return norm(" \n ".join(out))


def from_docx(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        parts = [
            n for n in z.namelist() if re.match(r"word/(document|header\d*|footer\d*)\.xml$", n)
        ]
        chunks = []
        for p in parts:
            root = ET.fromstring(z.read(p))
            chunks.append(" ".join(t.text or "" for t in root.iter(f"{W}t")))
        return norm(" ".join(chunks))


def from_xls_xml(path: str) -> str:
    """Some 'xls' files are SpreadsheetML or plain XML."""
    with open(path, "rb") as f:
        head = f.read(8)
    if head[:2] == b"\xd0\xcf":  # OLE2 -- real binary .xls, not readable here
        raise ValueError("binary xls (OLE2) unsupported")
    with open(path, encoding="utf8", errors="replace") as f:
        return strip_markup(f.read())


def read_any(path: str) -> tuple[str, str]:
    """-> (text, how). Raises on anything unreadable, so callers can count gaps."""
    low = path.lower()
    if low.endswith((".xml", ".nxml")):
        return from_xml(path), "xml"
    if low.endswith(".xlsx"):
        return from_xlsx(path), "xlsx"
    if low.endswith((".docx", ".dotx")):
        return from_docx(path), "docx"
    if low.endswith(".xls"):
        return from_xls_xml(path), "xls-as-xml"
    if low.endswith(
        (".doc", ".pdf", ".jpg", ".jpeg", ".gif", ".png", ".tif", ".tiff", ".zip", ".eps")
    ):
        raise ValueError(f"unsupported format: {low.rsplit('.', 1)[-1]}")
    raise ValueError(f"unknown format: {path}")
