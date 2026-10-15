"""A read-only repository over the corpus (the Repository pattern).

Nothing else reaches the corpus, and nothing here mutates it. Retrieval is two
tier: search returns compact rows plus the total that matched, and full entries
are fetched one at a time. A single-word property search matches up to 1,656 of
the corpus's 14,294 entries, and a full entry averages roughly eight times a
compact row, so returning matches in full would be a six-figure token result for
one tool call -- and would bury the few relevant entries among the rest.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .bionumbers import cross_references
from .corpus import Entry, EntryId, entry_key
from .trace import QuestionTrace

DEFAULT_LIMIT = 50
# The model chooses `limit`, and a large value defeats the two-tier design
# entirely -- asking for 20,000 rows would return the whole corpus in one tool
# message, which is the context and spend blow-up this module exists to prevent.
MAX_LIMIT = 200


@dataclass(frozen=True)
class CompactRow:
    """What search returns: enough to choose, not enough to answer from."""

    entry_id: EntryId
    property: str
    organism: str
    value: str
    units: str


@dataclass(frozen=True)
class SearchResult:
    rows: tuple[CompactRow, ...]
    total_matched: int

    @property
    def truncated(self) -> bool:
        return self.total_matched > len(self.rows)


@dataclass(frozen=True)
class FullEntry:
    entry: Entry
    cited_ids: tuple[int, ...]


def _compact(entry: Entry) -> CompactRow:
    return CompactRow(
        entry_id=entry.entry_id,
        property=entry.property,
        organism=entry.organism,
        value=entry.value_display,
        units=entry.units,
    )


def _unpunctuated(term: str) -> str:
    """One key for the punctuation a reader may or may not type.

    "E. coli", "E.coli" and "E coli" are the same request. Only the first resolved,
    and the other two returned no entries at all rather than a near miss -- which
    reads as "the corpus does not cover this", the one answer that must be true.
    The period becomes a space rather than being dropped, or "E.coli" would key on
    "ecoli" and reach nothing.
    """
    return " ".join(term.replace(".", " ").lower().split())


def _abbreviated_binomials(organism: str) -> set[str]:
    """Abbreviations a reader would type: "E. coli" for "Escherichia coli".

    This is the one variant plain substring matching cannot reach -- "e. coli" is
    not a substring of "Bacteria Escherichia coli" -- which is why an index exists
    at all. Everything else a user is likely to type (a genus, a common name, a
    group) is already a substring of the stored value, and needs no mapping.
    """
    tokens = organism.split()
    out = set()
    # strict=False is the point, not an oversight: the two sequences are meant to
    # differ in length by one -- that is what makes the pairs adjacent -- so strict=True
    # would raise on every organism with more than one word.
    for index, (first, second) in enumerate(zip(tokens, tokens[1:], strict=False)):
        if not (
            first[:1].isupper()
            and first.isalpha()
            and len(first) > 2
            and second.islower()
            and second.isalpha()
            and len(second) > 2
        ):
            continue
        # A species epithet ends the name, give or take an authority or strain
        # marker ("Arachis hypogaea L."). If another lowercase word follows, the
        # pair is a common-name phrase -- "African clawed frog" would otherwise
        # yield "a. clawed". Requiring the pair to be final instead would lose
        # real binomials, since 79 stored names carry a suffix after them.
        following = tokens[index + 2 : index + 3]
        if following and following[0].islower() and following[0].isalpha():
            continue
        out.add(f"{first[0].lower()}. {second.lower()}")
    return out


class CorpusRepository:
    def __init__(self, entries: tuple[Entry, ...]) -> None:
        self._entries = entries
        self._by_id = {e.entry_id: e for e in entries}
        if len(self._by_id) != len(entries):
            # Otherwise search would show two rows for one identifier while get()
            # returned only the last, so the agent would cite one entry and read
            # another's data.
            seen: set[EntryId] = set()
            repeated = sorted(
                {e.entry_id for e in entries if e.entry_id in seen or seen.add(e.entry_id)},
                key=str,
            )
            raise ValueError(f"corpus contains repeated identifiers: {repeated[:5]}")
        self._organisms = Counter(e.organism for e in entries if e.organism)
        self._properties = Counter(e.property for e in entries if e.property)
        aliases: dict[str, set[str]] = defaultdict(set)
        for organism in self._organisms:
            for alias in _abbreviated_binomials(organism):
                aliases[alias].add(organism)
        self._aliases = {k: frozenset(v) for k, v in aliases.items()}
        # The same index keyed without punctuation, so "E.coli" and "E coli" reach
        # what "E. coli" reaches. The readable form stays the one `aliases()`
        # exposes, because that index is meant to be read and corrected by a person.
        self._alias_keys = {_unpunctuated(k): k for k in self._aliases}

    # -- inspection -------------------------------------------------------

    def aliases(self) -> dict[str, frozenset[str]]:
        """The index, readable and correctable. Deliberately not learned."""
        return dict(self._aliases)

    def __len__(self) -> int:
        return len(self._entries)

    def saved_ids(self, entry_ids: Iterable[EntryId]) -> dict[str, str]:
        """For each harvested entry among `entry_ids`, its label and the store's id for it.

        What a record writes beside the labels it lists, so the record can be resolved later by the
        id that never moves (ADR-1610). Empty for a corpus-file entry, whose BNID is both, so a
        corpus-file run's records are exactly what they were.
        """
        out: dict[str, str] = {}
        for entry_id in entry_ids:
            entry = self._by_id.get(entry_key(entry_id))
            if entry is not None and entry.harvest is not None:
                out[str(entry.entry_id)] = entry.harvest.item_id
        return out

    # -- search -----------------------------------------------------------

    def search(
        self,
        *,
        property: str | None = None,
        organism: str | None = None,
        keyword: str | None = None,
        limit: int = DEFAULT_LIMIT,
        trace: QuestionTrace | None = None,
    ) -> SearchResult:
        # limit arrives from the model as a tool argument. Negative values slice
        # from the end -- silently dropping the last match while reporting
        # truncation -- and zero returns nothing against a non-zero total.
        limit = max(1, min(int(limit), MAX_LIMIT))
        resolved = self.resolve_organism(organism) if organism else None
        matched = [
            e
            for e in self._entries
            if (property is None or property.lower() in e.property.lower())
            and (resolved is None or e.organism in resolved)
            and (
                keyword is None
                or any(keyword.lower() in k.lower() for k in e.keywords)
                or keyword.lower() in e.property.lower()
            )
        ]
        rows = tuple(_compact(e) for e in matched[:limit])
        result = SearchResult(rows=rows, total_matched=len(matched))
        if trace is not None:
            saved = self.saved_ids(row.entry_id for row in rows)
            trace.record(
                "search",
                property=property,
                organism=organism,
                keyword=keyword,
                matched=result.total_matched,
                returned=len(rows),
                entry_ids=[row.entry_id for row in rows],
                truncated=result.truncated,
                organism_resolved_to=sorted(resolved) if resolved else None,
                **({"saved_ids": saved} if saved else {}),
            )
        return result

    def resolve_organism(self, term: str) -> frozenset[str]:
        """Stored organism values a term refers to: aliases first, then substrings.

        Public because the evaluation has to judge "did the agent search for the
        asked organism" with the same resolution `search` uses. A harness that
        compared the strings would score a search for "E. coli" as not being a
        search for "Escherichia coli", and report the resolution's success as the
        agent's failure.
        """
        key = " ".join(term.lower().split())
        canonical = self._alias_keys.get(_unpunctuated(term))
        stored = set(self._aliases.get(canonical or key, ()))
        stored.update(o for o in self._organisms if key in o.lower())
        return frozenset(stored)

    def resolve_property(self, term: str) -> frozenset[str]:
        """Stored property values a term selects, the way `search` selects them.

        Search matches a property by case-insensitive substring, and this is that
        rule read through the corpus rather than applied to two free-text strings:
        "volume" and "Cell volume" both select the stored value `Cell volume`, so
        they agree, while comparing the strings directly would not.

        No alias index. Organisms have abbreviated binomials, which are a closed
        and enumerable pattern; property names have no equivalent, and inventing
        one here would be a heuristic reasoned from the shape of the input rather
        than measured against the corpus.
        """
        key = " ".join(term.lower().split())
        return frozenset(p for p in self._properties if key in p.lower())

    # -- vocabulary -------------------------------------------------------

    def vocabulary(
        self,
        field: str,
        term: str = "",
        limit: int = 20,
        *,
        trace: QuestionTrace | None = None,
    ) -> tuple[tuple[str, int], ...]:
        """Stored values matching a partial term, so nothing has to be guessed.

        A search that returns nothing is otherwise indistinguishable from a topic
        the corpus does not cover.
        """
        fields = {"organism": self._organisms, "property": self._properties}
        if field not in fields:
            # The agent reaches for this when a search came back empty; a KeyError
            # is not something it can act on.
            raise ValueError(f"unknown field {field!r}; choose one of {sorted(fields)}")
        counts = fields[field]
        key = term.lower()
        hits = [(value, n) for value, n in counts.items() if key in value.lower()]
        hits.sort(key=lambda pair: (-pair[1], pair[0]))
        found = tuple(hits[:limit])
        if trace is not None:
            trace.record("vocabulary", field=field, term=term, found=len(found))
        return found

    # -- retrieval --------------------------------------------------------

    def get(self, entry_id: EntryId, *, trace: QuestionTrace | None = None) -> FullEntry | None:
        entry_id = entry_key(entry_id)
        entry = self._by_id.get(entry_id)
        if entry is None:
            if trace is not None:
                trace.record("entry.missing", entry_id=entry_id)
            return None
        # The source's own notation, read by the one implementation of it. Entry text
        # cites other entries as "See BNID 102065, 104333"; the answer path reads the
        # same function (ADR-0410), because two parsers for one notation drifted once
        # already -- this one read the run and the answer parser did not. An earlier
        # version also hardcoded identifiers as six digits beginning with 1, which is
        # a fact about this corpus rather than about a citation.
        cited = tuple(sorted(set(cross_references(entry.quotation_text))))
        if trace is not None:
            saved = {"saved_id": entry.harvest.item_id} if entry.harvest is not None else {}
            trace.record("entry.retrieved", entry_id=entry_id, cited_ids=list(cited), **saved)
        return FullEntry(entry=entry, cited_ids=cited)
