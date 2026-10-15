# Europe PMC API surface — verified 2026-09-18

All claims below were checked with real requests on 2026-09-18 unless marked **unverified**. Raw
responses are in `data/` beside this file (`searches.out`, `fields_compare.out`, `inventory.out`,
`openapi.json`, `fields.json`, two full-text XMLs, annotation JSON). Nothing was written into the
repository.

**Documentation reachability.** `https://europepmc.org/RestfulWebService`, `/Help`,
`/Copyright`, `/AnnotationsApi` and the Reference Guide PDF all sit behind a Cloudflare
JavaScript challenge and answered `403` / "Just a moment" to both curl and WebFetch from this
sandbox. The machine-readable OpenAPI description is on the EBI host and *is* reachable; it is the
primary documentary citation used here:

```sh
curl -sS https://www.ebi.ac.uk/europepmc/webservices/rest/v3/api-docs -o openapi.json
curl -sS "https://www.ebi.ac.uk/europepmc/webservices/rest/fields?format=json"   # 150 search fields
```

## 0. What already exists on `feat/grounding-validator-cytoskeleton` — reuse it

```
src/bionumbers/europepmc.py          EuropePMC(client, cache=, allow_preprint_fallback=)
src/bionumbers/retrieval.py          SourceIdentifier, RetrievedDocument, Unavailable, UnavailabilityReason
src/bionumbers/cache.py              DocumentCache: write-then-rename on-disk cache
tests/europepmc_double.py            FakeEuropePMC over httpx.MockTransport serving recorded fixtures
tests/fixtures/capture_europepmc.py  re-records the fixtures from the live service
tests/fixtures/europepmc/            5 search JSONs, 2 full-text XMLs (PMC2132865, PPR1218639)
tests/test_europepmc.py, tests/test_europepmc_live.py (marker `network`)
```

`EuropePMC.retrieve(identifier)` resolves a PMID / PMCID / DOI via `search?resultType=core`,
fetches `{pmcid}/fullTextXML` when `isOpenAccess == "Y"`, and falls back to an open-access
preprint found by exact title under `SRC:PPR`. It already handles the two things a new client
would get wrong first: `<i>` markup in titles, and query-syntax punctuation in titles.

**One drift to fix before reuse.** The double and a comment in `_fetch_full_text` say Europe PMC
answers **404** when no XML exists. Today it answers **500** for every such case (see §5), and
`_fetch_full_text` only returns `None` on 404, then calls `raise_for_status()`, so a paywalled
PMCID or an XML-less preprint now raises `httpx.HTTPStatusError` instead of yielding
`Unavailable`. The live tests do not catch it because `retrieve` never reaches the fetch for a
non-OA record. Treat "no XML" as `status in (404, 500)` *and* body not starting with `<article`,
and re-record `fulltext_missing` as a 500.

What is missing for this prototype: a **topic search** (the existing client searches only by
identifier), and a **JATS reader** (it returns the XML string).

## 1. Search endpoint

`GET https://www.ebi.ac.uk/europepmc/webservices/rest/search` with `query`, `resultType`
(`idlist|lite|core`), `format` (`json|xml|dc`), `pageSize` (default 25, max 1000), `cursorMark`,
`sort`, `synonym`, `email` — per the OpenAPI spec. Fielded syntax is `FIELD:value`, phrases in
double quotes, `AND`/`OR`/`NOT`, ranges `[a TO b]`. Field names come from `/fields`.

### Hit counts for three property-style questions

```sh
q='"Escherichia coli" AND "doubling time"'
curl -sS "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$q AND OPEN_ACCESS:Y")&resultType=idlist&pageSize=1&format=json"
```

| Restriction appended | E. coli doubling time | ribosome "copy number" yeast | HeLa "cell volume" |
|---|---|---|---|
| none | 11,356 | 7,400 | 4,074 |
| `AND OPEN_ACCESS:Y` | 4,558 | 4,221 | 2,354 |
| `AND HAS_FT:Y` | 11,214 | 7,372 | 3,985 |
| `AND IN_EPMC:Y` | 11,214 | 7,372 | 3,985 |
| `AND HAS_PDF:Y` | 11,162 | 7,301 | 3,875 |
| `AND SRC:MED` | 11,123 | 7,083 | 3,791 |
| `AND SRC:PMC` | 154 | 247 | 247 |
| `AND SRC:PPR` | 76 | 69 | 36 |
| `AND OPEN_ACCESS:Y AND NOT PUB_TYPE:review` | 4,131 | 3,304 | 1,832 |
| `AND OPEN_ACCESS:Y AND PUB_YEAR:[2015 TO 2026]` | 3,620 | 3,353 | 1,771 |
| `AND OPEN_ACCESS:Y AND HAS_SUPPL:Y` | 3,258 | 2,782 | 1,240 |
| `AND OPEN_ACCESS:Y AND LICENSE:"cc by"` | 3,389 | 3,046 | 1,534 |

Readings:

- **An unfielded query already searches full text.** 11,214 of 11,356 E. coli hits are `HAS_FT:Y`;
  the phrase is matched in the body, not the abstract. `TITLE_ABS:"Escherichia coli" AND
  TITLE_ABS:"doubling time"` gives 44; `BODY:... AND BODY:...` gives 3,910 (OA). Section fields
  exist and work: `METHODS:` 1,263, `RESULTS:` 2,583, `TABLE:` 412, `FIG:` 724, `SUPPL:` 119 (all
  with `"Escherichia coli" AND OPEN_ACCESS:Y`). `TABLE:` and `RESULTS:` are the useful ones for
  a value question; `TITLE_ABS:` is far too narrow.
- **`HAS_FT:Y` and `IN_EPMC:Y` are the same set** (12,354,901 records each, database-wide) and
  are *not* the open-access filter: 4,088,313 records have full text in Europe PMC but
  `OPEN_ACCESS:N`. **`OPEN_ACCESS:Y` is the filter that predicts `fullTextXML`** (8,267,080
  records; only 492 of them lack `HAS_FT`, all preprints). This confirms COVERAGE.md.
- **`SRC:MED` vs `SRC:PMC`.** `SRC:PMC` (987,151 records) is the *residual* of PMC articles with
  no PubMed record (`id` is the PMCID, `pmid` null). Every article with a PMID is `SRC:MED` even
  when it has a PMCID, so `SRC:PMC` does not mean "in PMC": use `OPEN_ACCESS:Y` and read `pmcid`
  from the record. `(SRC:MED OR SRC:PMC)` excludes preprints (`PPR`), patents, theses.
- **`PUB_TYPE`** is case-insensitive (`review` = `"Review"`, 4,131 both ways). Observed values:
  `research-article`, `Journal Article`, `review-article`, `Review`, `brief-report`, `Preprint`,
  `Case Reports`. `NOT PUB_TYPE:review` removes both `Review` and `review-article` (957,544 vs
  749,474 OA database-wide, so `review` is the wider term).
- **Dates.** `PUB_YEAR:[2015 TO 2026]` and `FIRST_PDATE:[2015-01-01 TO 2026-12-31]` both work;
  `sort=CITED desc` and `sort=P_PDATE_D desc` work.

### `lite` vs `core` fields

`lite` (verified on a real hit) returns `id, source, pmid, pmcid, doi, title, authorString,
journalTitle, pubYear, pubType, isOpenAccess, inEPMC, inPMC, hasPDF, hasSuppl, hasReferences,
hasTextMinedTerms, citedByCount, firstPublicationDate, fullTextIdList` and a few more (full list
in `data/fields_compare.out`). `pubType` in lite is one semicolon-joined lowercase string.

`core` adds `abstractText, license, pubTypeList, authorList, keywordList, meshHeadingList,
journalInfo, fullTextUrlList, authMan, epmcAuthMan, nihAuthMan, publicationStatus, hasData` and
dates. **`license` is core-only** (0 of 50 lite records carried it); `hasSuppl`, `isOpenAccess`,
`pmcid`, `pubType` are in lite. Search with `lite`; use `core` or the JATS `<license>` element
(§3) when the licence must be recorded.

## 2. Full text: `GET /{PMCID}/fullTextXML`

```sh
curl -sS https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13340094/fullTextXML -o PMC13340094.xml   # 41,825 B, brief-report, mSpectrum
curl -sS https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13248727/fullTextXML -o PMC13248727.xml   # 121,627 B, research-article, IAI
python3 data/inventory.py data/PMC13340094.xml data/PMC13248727.xml   # full element inventory in data/inventory.out
```

The id must be the `PMC`-prefixed PMCID (a bare PMID gives 500) or a `PPR` id for preprints.
Both papers are JATS (`article-type` on `<article>`; the second declares `dtd-version="1.4"`,
older PMC2680341 declares JATS 1.4 with MathML3 in its DOCTYPE).

**Structure actually returned (PMC13248727, the fuller one):**

- Top level: `processing-meta, front, body, back`. `front/article-meta` holds `article-id`
  elements with `pub-id-type` = `pmcid, pmcid-ver, pmcaid, pmid, doi, publisher-id`, plus
  `permissions/license`.
- `body`: 4 `sec` with `sec-type` `intro|results|discussion|materials\|methods`, nested `sec` with
  `title`, 52 `p`. Section titles: INTRODUCTION, RESULTS (3 subsections), DISCUSSION, MATERIALS
  AND METHODS (4 subsections).
- **Tables: XHTML table model inside `table-wrap`.** `table-wrap` → `label` ("TABLE 1"),
  `caption`, `table` → `colgroup/col`, `thead/tr/th`, `tbody/tr/td` with `align/valign/colspan/
  rowspan` attributes. 3 tables, 36 rows, 198 `td`. Header cell raw: `Volume (µm<sup>3</sup>)`.
  The 2009 PMC2680341 has 5 table-wraps of the same form. No image-only tables in these two
  (older PLOS-style `<alternatives><graphic>` tables exist elsewhere and would need checking).
- **Figures**: `fig` → `label, caption, graphic[@xlink:href]` (6 figs); the brief report wraps the
  graphic in `alternatives` with `alt-text`. Only the caption text is recoverable.
- **Supplementary material**: `supplementary-material[@id, @position="float",
  @content-type="local-data"]` → `object-id?, label, caption, media[@xlink:href, @mimetype,
  @mime-subtype]`. Labels: `Fig. S1`, `File S1`, `Movie S1`, `Supplemental material`. Captions
  start with the filename (`iai.00007-26-s0001.docx…`). Body references are
  `xref[@ref-type="supplementary-material"]` (6 and 8 occurrences) and prose phrasing `Fig. S1`,
  `Supplemental Material`, `Supplemental data file`. mSpectrum duplicates each item in an
  `associated-data` `sec` (8 elements for 3 files). Search-side signal: `hasSuppl` (lite) and
  `HAS_SUPPL:Y`; 168 of 200 OA E. coli hits have `hasSuppl=Y`.
- **Bibliography**: `back/ref-list/ref` → `label, mixed-citation[@publication-type]` with
  `person-group, article-title, source, year, volume, fpage, lpage, pub-id`. Inline citations are
  `xref[@ref-type="bibr"]` (57). **The brief report has no `<back>`:** its references and
  supplementary section live as `sec` inside `body` (`sec-type` `ref-list`, `associated-data`).
  A reader must not assume `back` exists.
- `xref` ref-types seen: `bibr, fig, table, supplementary-material, aff, corresp, author-notes`.

**Markup that breaks naive verbatim matching** (this is what the probe's `check_quote.py` fold
table exists for):

| Issue | Evidence |
|---|---|
| Inline `<sup>/<sub>/<italic>/<bold>/<xref>` split a sentence's text nodes | 11 `sup`, 109 `italic` in PMC13248727; `µm<sup>3</sup>` in a table header |
| Two different "micro" code points in one paper | U+03BC (Greek mu) ×20 and U+00B5 (micro sign) ×14 in PMC13248727 |
| Dashes | en-dash U+2013 ×37 in one paper; minus U+2212 present in the corpus |
| Degree/percent spacing | `37°C`, `10%` — no space; `5 µm` — space |
| MathML | 0 `inline-formula` in both picks; PMC2680341's DOCTYPE includes MathML3, so `mml:math` must be expected in physics-heavy papers |
| `named-content[@content-type="citation-string"]` wrapping references (mSpectrum) | 18 in PMC13340094 |
| Entities | only `&amp; &lt; &gt;` seen; no numeric entities, no NBSP/thin space in these two |

Recommendation: emit per-`p`/per-`td` text with inline elements flattened (`itertext()`), keep a
sentence → (section path, element id) map, and normalise both sides with the probe's 15-entry
fold table — never widened without re-running the canaries in
`probes/2026-09-09-retrieval/README.md`.

**Supplementary files** are downloadable as one zip:
`GET /{PMCID}/supplementaryFiles` → `application/zip`, 2.7 MB for PMC13340094 containing the
xlsx, the PDF supplement, a reviewer-comments PDF and the figure files. OpenAPI: "all
supplementary files can be retrieved with the exception of non-Open Access images." The xlsx
inside is exactly the kind of table COVERAGE.md found missing from XML — a later probe.

## 3. Licensing

- **Where:** `license` in `resultType=core` search results, and in the XML at
  `front/article-meta/permissions/license`, with `ali:license_ref[@specific-use="textmining"]`
  carrying the CC URL (`https://creativecommons.org/licenses/by/4.0/`,
  `.../publicdomain/zero/1.0/` for CC0) and `license-p` the sentence. Older XML (PMC2680341) puts
  the URL on `license/@xlink:href`; the newer puts it only in `ali:license_ref`. Read both.
- **Values seen** (500 recent OA hits): `cc by` 342, `cc by-nc-nd` 97, `cc by-nc` 59,
  `cc by-nc-sa` 1, `null` 1. In the 200 E. coli OA hits: `cc by` 146, `cc by-nc-nd` 40,
  `cc by-nc` 13, `null` 1. Filterable: `LICENSE:"cc by"`.
- **Terms.** Europe PMC's own copyright/terms page is `https://europepmc.org/Copyright`
  (**unverified** from here: 403). The EBI terms of use
  (`https://www.ebi.ac.uk/about/terms-of-use`, fetched) say EMBL-EBI "places no additional
  restrictions on the use or redistribution of the data available via its Data Resources and
  Tools other than those provided by the original data owners" and that specific resource terms
  prevail. So the operative licence is the **per-article CC licence**, and the requirement for
  storing verbatim sentences plus PMC ids in a private database shown to reviewers is:
  attribution (all CC variants) — store `pmcid`, `pmid`, `doi`, `license`, and the licence URL
  with every sentence; **NC** variants forbid commercial use, **ND** forbids distributing
  *adaptations* (a verbatim sentence with citation is quotation, not adaptation, but any
  paraphrase or altered table is). For a private review tool this is comfortably within scope;
  for anything sold or public, keep `cc by` / `cc by-sa` / CC0 only and record the licence
  per record rather than per run. The empty-`license` record (`null`) should be treated as
  "unknown, do not store text".

## 4. Rate limits, etiquette, pagination

- **No rate limit is documented in the OpenAPI spec** (grep for rate/throttle/limit: nothing), and
  **no rate-limit headers** are returned (only `strict-transport-security`). The human pages that
  would state a policy are `https://europepmc.org/RestfulWebService` and the Reference Guide PDF
  (**unverified**: 403). ~200 requests at ~0.3 s spacing during this session drew no 429.
- **`email` parameter**: optional on `/search`, `/profile`, `/article`, "registers the user's
  email address with EBI. The user can then be contacted about Web Service related news"
  (OpenAPI). Accepted live. Not a rate-limit key. Set a descriptive `User-Agent` anyway.
- **Pagination**: `cursorMark=*` first, then `nextCursorMark` from the response; `nextPageUrl` is
  also returned ready-made. Verified: two pages of 1,000 ids. The old `page=` parameter still
  answers but the spec documents only `cursorMark`. Max `pageSize` 1000.
- **Bulk**: for thousands of papers, Europe PMC's OA subset FTP
  (`https://europepmc.org/downloads/openaccess`, **unverified**: 403) is the intended route, not
  the API.
- The branch's `DocumentCache` docstring already states the etiquette: cache, because
  "re-fetching the same few hundred documents each time is slow and impolite to a free service."

## 5. Pitfalls

1. **Three ids.** `id` is the Europe PMC record id: the PMID for `SRC:MED`, the PMCID for
   `SRC:PMC`, `PPRnnnn` for preprints. `PMCID:PMC13340094`, `EXT_ID:42138383` and
   `DOI:"10.1128/spectrum.03512-25"` all resolve to the same MED record; `EXT_ID:PMC13340094`
   gives **0** hits. `/article/PMC/PMC13340094` works, `/article/PMC/13340094` does not.
2. **PMCID without XML → HTTP 500, not 404 and not empty.** Verified 3× on PMC13394429 and on 8
   other non-OA PMCIDs, on a nonexistent `PMC99999999`, on a bare PMID, and on preprint
   `PPR1090496` (the branch's "no XML" fixture, recorded as 404). 6,638 hits for the E. coli
   query are `OPEN_ACCESS:N AND PMCID:PMC*` — full text is *in* Europe PMC (`inEPMC=Y`,
   `hasPDF=Y`) but not in the OA subset, so no XML is served. `/supplementaryFiles` on such a
   record returns 200 with a 297-byte stub.
3. **Author manuscripts.** `authMan=Y` records (1,131,869; 84,272 OA) have a PMCID and
   `fullTextUrlList` entries with `availabilityCode="F"` (free) at `site="Europe_PMC"`, yet
   `isOpenAccess=N` and no XML (verified on PMC6284397, PMC4812601, PMC5065786). "Free to read"
   ≠ "open access XML".
4. **`isOpenAccess` vs `inEPMC` vs `hasPDF`.** `inEPMC ⊇ isOpenAccess` (4.09 M in EPMC but not
   OA; 492 OA not in EPMC, all preprints). `hasPDF` is nearly independent: 3.99 M `hasPDF=Y`
   non-OA, 154,702 OA without PDF. Only `isOpenAccess` predicts XML.
5. **`embargoDate`** was `null` on every record seen, and `EMBARGO_DATE:[2026-09-19 TO
   2028-12-31]` gave 0 hits for the E. coli query — embargoed items appear to be indexed without
   that field populated, so embargo cannot be distinguished from "non-OA" via the API.
6. **`SRC:PPR` full text** is served for some preprints (PPR1218639: 144 kB) and 500 for others
   although `HAS_FT` is set; the branch's docstring records this.
7. Recent papers may be **annotated only at abstract level** (see §6).

## 6. Annotations API

```sh
curl -sS "https://www.ebi.ac.uk/europepmc/annotations_api/annotationsByArticleIds?articleIds=PMC:PMC13248727&type=Organisms&section=Results&format=JSON"
```

Verified: `articleIds` takes 1–8 `SRC:id` values (9 → 400 "must contain between 1 and 8
values"); `type` (`Organisms`, `Chemicals`, `Gene Ontology`, `Experimental Methods`, …),
`section` (`Results`, …), `format=JSON`. Response per article: `source, extId, pmcid,
fullTextIdList, annotations[]` with `prefix, exact, postfix, tags[{name, uri}], type, section,
provider, id`. `annotationsByEntity` and `annotationsBySectionAndOrType` also work, paged by
`cursorMark`. Docs page `https://europepmc.org/AnnotationsApi` (**unverified**: 403).

Observed: PMC13248727 → 61 organism annotations across Results (21), Introduction (18),
Abstract, Discussion, Methods and Supplementary material. PMC13340094 (published 2026-08) → 28
annotations, **all in Title/Abstract**: full-text mining had not run yet.

**Verdict: does not help this prototype.** Reasons, all from the data:

- There is **no character offset** (`position` absent). Location is `prefix` (2–4 words) +
  `exact` + `postfix`, and the three do **not** concatenate to a substring of the article: 0 of 89
  `prefix+exact+postfix` strings were found in the stripped XML, versus 89 of 89 `exact` strings.
  Prefix/postfix also carry residual `<i>` / `&lt;i&gt;` markup. Locating the sentence therefore
  reduces to a string search for `exact` — which is what one would do without the API.
- The entity types are chemicals, organisms, genes, GO terms, methods. **There is no quantity or
  measurement type**, so it cannot point at "the sentence with the number".
- Coverage lags publication (abstract-only for a 2026-08 paper).

The one cheap use, `type=Organisms&section=Results` as a post-filter on candidates (8 papers per
call), is marginal. Skip it for the prototype.

## 7. Recommended minimal client

Extend the branch's `europepmc.py` rather than writing a second one; keep `httpx.Client`
injection and `DocumentCache`. Four functions:

1. `search_open_access(question_terms: str, *, since_year: int, exclude_reviews=True,
   page_size=100, sections=("RESULTS","TABLE")) -> list[Candidate]` — builds
   `(<terms>) AND OPEN_ACCESS:Y AND (SRC:MED OR SRC:PMC) AND NOT PUB_TYPE:review AND
   PUB_YEAR:[since TO now]`, optionally section-scoped (`RESULTS:(…) OR TABLE:(…)`), `resultType=
   lite`, iterates `cursorMark`. `Candidate` = `id, source, pmid, pmcid, title, pub_year,
   has_suppl, cited_by`. Only records with a `pmcid` are candidates.
2. `fetch_full_text(pmcid) -> str | NoXml` — the existing `_fetch_full_text` with the 500 fix;
   `NoXml` carries the status code.
3. `read_jats(xml: str) -> Document` — `Document(pmcid, pmid, doi, license_url, license_text,
   passages: list[Passage])`; `Passage(text, kind ∈ {p, td, th, caption, title},
   section_path, element_id, supplementary_refs)`; plus `supplementary: list[(label, href,
   mimetype, caption)]`. Text via `itertext()` on each `p`/`td`/`caption`; `back` optional.
4. `record_licence(core_record | Document) -> Licence(spdx_like: str, url: str)` — from `core`
   `license` or the XML `ali:license_ref`, refusing `None`.

**Test against the live service** (marker `network`, two cases only): (a) a known non-OA PMCID
returns a non-XML body with status 500 (this is the case that drifted, and it will drift again);
(b) `OPEN_ACCESS:Y` for the identifier query implies a `<article` body for its `pmcid` — the
exact-predictor claim from COVERAGE.md, one fresh record per run. **Everything else on
fixtures**: JATS reading (both `back`-present and `back`-absent papers, XHTML table, `sup`
inside `th`, mixed µ/μ), query construction (punctuation escaping, `NOT PUB_TYPE:review`),
`cursorMark` iteration, licence extraction from both licence layouts, and lite-vs-core field
presence. Re-record with `capture_europepmc.py` extended by the two PMCIDs used here.
