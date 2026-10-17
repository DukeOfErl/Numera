# source-discovery Specification

## Purpose
From a property question to the open-access research articles that might answer it, each with its
full text in hand or a typed reason it is not, and its licence recorded. Discovery decides what the
extractor is allowed to read; it never decides what a paper says.
## Requirements
### Requirement: A question is answered from open-access research articles only

Given a property question, discovery SHALL search the literature index for candidate articles and
SHALL keep only candidates that are open access, carry a PubMed Central identifier, and are research
articles by the index's publication type. Reviews, meta-analyses, editorials, comments and preprints
SHALL be excluded by metadata before any full text is fetched. The number of candidates kept per
question SHALL be bounded by a configurable limit, and the search terms actually sent SHALL be
recorded with the run.

Open access is the one attribute known to predict that machine-readable full text exists
(ADR-0040, ADR-0050). A candidate excluded here is *out of scope*, never *unconfirmed*: nothing was
read, so nothing can be said about what it states.

#### Scenario: A candidate is not open access
- **WHEN** the index returns an article for the question that is not marked open access
- **THEN** it is excluded before any fetch, and the exclusion is recorded with its reason

#### Scenario: A candidate is a review
- **WHEN** the index returns an article whose publication type names a review or meta-analysis
- **THEN** it is excluded before any fetch, and the exclusion is recorded with its reason

#### Scenario: A candidate has no PubMed Central identifier
- **WHEN** the index returns an open-access record with no PubMed Central identifier
- **THEN** it is excluded, because no full text can be addressed for it

#### Scenario: The candidate limit is reached
- **WHEN** the index returns more qualifying candidates than the configured limit
- **THEN** exactly the limit is kept, in the index's ranking order, and the run records that more existed

### Requirement: Full text is fetched or its absence is typed

For every kept candidate, discovery SHALL obtain the article's full text as structured XML, or
SHALL record a typed reason it could not: the service served no XML for the identifier, the response
was not an article, or the service could not be reached. An absence SHALL never be reported as an
error that stops the run, and SHALL never be reported as the article stating nothing.

The service answers a request for an article without XML with a server error status rather than a
not-found status, and has changed which one it uses before. Discovery SHALL therefore decide
"no XML" from the body of the response — whether it is an article — and not from the status code
alone.

#### Scenario: The service serves XML
- **WHEN** a kept candidate's full text is requested and the response is an article document
- **THEN** the document is kept for extraction, and the URL it came from is recorded

#### Scenario: The service serves an error for an article without XML
- **WHEN** a kept candidate's full text is requested and the response is an error status with a non-article body
- **THEN** the candidate is recorded as having no readable full text, with the status observed
- **AND** the run continues with the next candidate

#### Scenario: A fetched document is served again
- **WHEN** the same article's full text is requested a second time in any later run
- **THEN** it is served from the local cache without contacting the service

### Requirement: An article that is not a research article is set aside after reading its structure

An article whose metadata calls it a research article but whose structure has no methods section
SHALL be set aside as not a research article, before any value is extracted from it, and the reason
SHALL be recorded. Perspective and essay pieces reach the open-access research-article set under
research-article metadata, and every number in them is a citation of other work.

#### Scenario: A perspective piece tagged as a research article
- **WHEN** a fetched document has no section whose title names methods or materials
- **THEN** it is set aside with the reason recorded, and no extraction is attempted on it

#### Scenario: A research article with methods
- **WHEN** a fetched document has a section whose title names methods or materials
- **THEN** it proceeds to extraction

### Requirement: The licence travels with the paper

For every fetched document, discovery SHALL record the article's licence as the index or the
document states it, together with the identifiers needed to cite it: the PubMed Central identifier,
the PubMed identifier and the DOI where present, the title, and the year. A document whose licence
cannot be determined SHALL be recorded as such, and its text SHALL NOT be stored beyond the local
cache.

Every quote later shown to a reviewer or written to the record is a quotation from this document,
and attribution is the one obligation every open licence shares.

#### Scenario: A licensed document
- **WHEN** a document is fetched and its licence is stated in the index record or in the document
- **THEN** the licence and the identifiers are recorded with the document

#### Scenario: A document with no determinable licence
- **WHEN** a document is fetched and neither the index record nor the document states a licence
- **THEN** the document is recorded as unlicensed, and no text from it is written to the record

### Requirement: Discovery is polite to a free service

Requests to the index SHALL be cached on disk so a repeated run makes no repeated request for the
same search or the same document, and SHALL identify this project in the request's user agent.
Discovery SHALL page through results using the service's cursor rather than by page number.

#### Scenario: A run is repeated
- **WHEN** discovery for the same question, with the same terms and limit, runs a second time
- **THEN** the search and every previously fetched document are served from the cache

### Requirement: The bibliographic record travels with the paper

For every fetched document, the system SHALL read from its front matter the bibliographic record
needed to cite it -- its authors in the paper's order, the journal, the volume, the issue, the
pages or article number, the publication date and its identifiers -- and SHALL keep it with the
paper as one CSL-JSON item. Only what the front matter states SHALL be recorded. Editors and
reviewers SHALL NOT be recorded as authors. The citation shown to a reader SHALL be formatted from
this record by the application, never written by a model.

A record kept before this requirement existed SHALL be filled from the cached full text on
request, without re-extracting anything.

#### Scenario: The authors, and only the authors
- **WHEN** a document names its authors on each contributor or on the contributor group, and
  names an editor or a reviewer in another group
- **THEN** the record lists the authors in the paper's order and nobody else

#### Scenario: A collaboration
- **WHEN** an author is a named collaboration rather than a person
- **THEN** the record carries it as one literal author

#### Scenario: Pages or an article number
- **WHEN** a document states a first and last page, a first page alone, or an article number
- **THEN** the record carries the range, the page, or the article number respectively

#### Scenario: The article's own date
- **WHEN** a document states a volume's collection date and the article's own publication date
- **THEN** the record's date is the article's own, and the paper's year agrees with it

#### Scenario: A store loaded earlier
- **WHEN** a store holds papers from before the record was kept and the full text is in the cache
- **THEN** each such paper's record is filled from its front matter, and a paper already holding
  one is left as it is

