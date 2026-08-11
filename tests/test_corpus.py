import pytest

from bionumbers.corpus import (
    CorpusEntry,
    CorpusError,
    CorpusNotSuppliedError,
    MalformedCorpusError,
    load_corpus,
)
from conftest import record_json

MICRO_SIGN = "µm"  # U+00B5 MICRO SIGN
GREEK_MU = "μm"  # U+03BC GREEK SMALL LETTER MU


class TestFieldMapping:
    def test_every_field_is_read(self, write_corpus):
        path = write_corpus(
            [
                record_json(
                    id="100001",
                    property="Diameter of microtubule",
                    organism="Generic",
                    value_low=25.0,
                    units="nm",
                    source_id="PMID:9843947",
                    quotation="microtubules have an outer diameter of 25 nm",
                    quotation_location="p.1719 left column 2nd paragraph",
                    keywords=["cytoskeleton", "microtubule"],
                )
            ]
        )

        (entry,) = load_corpus(path)

        assert entry == CorpusEntry(
            id="100001",
            property="Diameter of microtubule",
            organism="Generic",
            value_low=25.0,
            value_high=None,
            units="nm",
            source_id="PMID:9843947",
            quotation="microtubules have an outer diameter of 25 nm",
            quotation_location="p.1719 left column 2nd paragraph",
            keywords=("cytoskeleton", "microtubule"),
        )

    def test_optional_fields_default_to_none(self, write_corpus):
        path = write_corpus([record_json()])

        (entry,) = load_corpus(path)

        assert (entry.organism, entry.value_low, entry.value_high, entry.units) == (
            None,
            None,
            None,
            None,
        )
        assert (entry.source_id, entry.quotation, entry.quotation_location) == (None, None, None)
        assert entry.keywords == ()

    def test_point_value_has_no_upper_bound(self, write_corpus):
        path = write_corpus([record_json(value_low=1.5)])

        (entry,) = load_corpus(path)

        assert (entry.value_low, entry.value_high) == (1.5, None)

    def test_range_carries_both_bounds(self, write_corpus):
        path = write_corpus([record_json(value_low=0.44, value_high=1.79)])

        (entry,) = load_corpus(path)

        assert (entry.value_low, entry.value_high) == (0.44, 1.79)

    def test_integer_values_become_floats(self, write_corpus):
        path = write_corpus([record_json(value_low=25)])

        (entry,) = load_corpus(path)

        assert entry.value_low == 25.0
        assert isinstance(entry.value_low, float)

    def test_negative_value_is_preserved(self, write_corpus):
        path = write_corpus([record_json(value_low=-3.2)])

        (entry,) = load_corpus(path)

        assert entry.value_low == -3.2

    @pytest.mark.parametrize("units", [MICRO_SIGN, GREEK_MU])
    def test_both_micro_sign_encodings_survive_loading(self, write_corpus, units):
        path = write_corpus([record_json(units=units)])

        (entry,) = load_corpus(path)

        assert entry.units == units

    def test_unknown_fields_are_ignored(self, write_corpus):
        path = write_corpus([record_json(some_curator_column="whatever")])

        (entry,) = load_corpus(path)

        assert entry.id == "100001"

    def test_whitespace_is_stripped_and_blank_text_becomes_none(self, write_corpus):
        path = write_corpus([record_json(organism="  Homo sapiens  ", units="   ")])

        (entry,) = load_corpus(path)

        assert entry.organism == "Homo sapiens"
        assert entry.units is None

    def test_entries_are_immutable(self, write_corpus):
        path = write_corpus([record_json()])

        (entry,) = load_corpus(path)

        with pytest.raises(AttributeError):
            entry.id = "changed"


class TestFileHandling:
    def test_entries_keep_file_order(self, write_corpus):
        path = write_corpus([record_json(id=str(n)) for n in range(5)])

        entries = load_corpus(path)

        assert [entry.id for entry in entries] == ["0", "1", "2", "3", "4"]

    def test_blank_lines_are_skipped(self, write_corpus):
        path = write_corpus(["", record_json(id="1"), "   ", record_json(id="2"), ""])

        assert len(load_corpus(path)) == 2

    def test_missing_trailing_newline_is_fine(self, write_corpus):
        path = write_corpus([record_json(id="1")])
        path.write_text(path.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")

        assert len(load_corpus(path)) == 1

    def test_empty_file_yields_no_entries(self, write_corpus):
        path = write_corpus([])

        assert load_corpus(path) == []

    def test_path_may_be_a_string(self, write_corpus):
        path = write_corpus([record_json()])

        assert len(load_corpus(str(path))) == 1

    def test_missing_file_names_the_path(self, tmp_path):
        missing = tmp_path / "nowhere.jsonl"

        with pytest.raises(CorpusError, match=str(missing)):
            load_corpus(missing)

    def test_directory_instead_of_file_is_reported(self, tmp_path):
        with pytest.raises(CorpusError, match="directory"):
            load_corpus(tmp_path)

    def test_non_utf8_file_is_reported(self, tmp_path):
        path = tmp_path / "corpus.jsonl"
        path.write_bytes(b'{"id": "1", "property": "\xff\xfe"}\n')

        with pytest.raises(MalformedCorpusError, match="UTF-8"):
            load_corpus(path)


class TestNoCorpusSupplied:
    def test_none_path_is_refused(self):
        with pytest.raises(CorpusNotSuppliedError):
            load_corpus(None)

    def test_refusal_explains_what_to_supply(self):
        with pytest.raises(CorpusNotSuppliedError) as caught:
            load_corpus(None)

        message = str(caught.value)
        assert "JSONL" in message
        assert "no bundled corpus" in message.lower()

    def test_refusal_is_a_corpus_error(self):
        assert issubclass(CorpusNotSuppliedError, CorpusError)


class TestMalformedRecords:
    def test_invalid_json_names_the_line(self, write_corpus):
        path = write_corpus([record_json(id="1"), "{not json", record_json(id="3")])

        with pytest.raises(MalformedCorpusError, match="line 2"):
            load_corpus(path)

    def test_json_that_is_not_an_object_is_rejected(self, write_corpus):
        path = write_corpus(["[1, 2, 3]"])

        with pytest.raises(MalformedCorpusError, match="expected a JSON object"):
            load_corpus(path)

    @pytest.mark.parametrize("missing", ["id", "property"])
    def test_required_field_missing(self, write_corpus, missing):
        path = write_corpus([record_json(**{missing: ...})])

        with pytest.raises(MalformedCorpusError, match=f"missing required field '{missing}'"):
            load_corpus(path)

    @pytest.mark.parametrize("empty", ["id", "property"])
    def test_required_field_blank(self, write_corpus, empty):
        path = write_corpus([record_json(**{empty: "   "})])

        with pytest.raises(MalformedCorpusError, match="is empty"):
            load_corpus(path)

    def test_required_field_of_wrong_type(self, write_corpus):
        path = write_corpus([record_json(id=100001)])

        with pytest.raises(MalformedCorpusError, match="must be a string"):
            load_corpus(path)

    @pytest.mark.parametrize("bad_value", ["1.5", True, [1.5], {"value": 1.5}])
    def test_non_numeric_value_is_rejected(self, write_corpus, bad_value):
        path = write_corpus([record_json(value_low=bad_value)])

        with pytest.raises(MalformedCorpusError, match="'value_low' must be a number"):
            load_corpus(path)

    def test_upper_bound_without_lower_bound_is_rejected(self, write_corpus):
        path = write_corpus([record_json(value_high=1.79)])

        with pytest.raises(MalformedCorpusError, match="value_high given without value_low"):
            load_corpus(path)

    @pytest.mark.parametrize("bad_keywords", ["actin", [1, 2], [None]])
    def test_keywords_must_be_a_list_of_strings(self, write_corpus, bad_keywords):
        path = write_corpus([record_json(keywords=bad_keywords)])

        with pytest.raises(MalformedCorpusError, match="'keywords' must be a list of strings"):
            load_corpus(path)

    def test_blank_keywords_are_dropped(self, write_corpus):
        path = write_corpus([record_json(keywords=["actin", "  ", " tubulin "])])

        (entry,) = load_corpus(path)

        assert entry.keywords == ("actin", "tubulin")

    def test_duplicate_identifiers_are_rejected(self, write_corpus):
        path = write_corpus([record_json(id="1"), record_json(id="2"), record_json(id="1")])

        with pytest.raises(MalformedCorpusError, match="duplicate entry id '1'.*line 1"):
            load_corpus(path)
