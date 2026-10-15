"""The on-disk document cache."""

import pytest

from bionumbers.cache import DocumentCache


@pytest.fixture
def cache(tmp_path):
    return DocumentCache(tmp_path / "cache")


class TestRoundTrip:
    def test_stores_and_returns_content(self, cache):
        cache.put("PMC1", "version of record", "<article>text</article>")

        assert cache.get("PMC1", "version of record") == "<article>text</article>"

    def test_missing_entry_returns_none(self, cache):
        assert cache.get("PMC1", "version of record") is None

    def test_creates_its_directory_on_first_write(self, tmp_path):
        directory = tmp_path / "not-yet" / "cache"
        DocumentCache(directory).put("PMC1", "v", "x")

        assert directory.is_dir()

    def test_a_second_cache_object_reads_the_same_files(self, tmp_path):
        DocumentCache(tmp_path / "c").put("PMC1", "v", "content")

        assert DocumentCache(tmp_path / "c").get("PMC1", "v") == "content"

    def test_overwriting_replaces_the_content(self, cache):
        cache.put("PMC1", "v", "old")
        cache.put("PMC1", "v", "new")

        assert cache.get("PMC1", "v") == "new"


class TestKeying:
    def test_version_is_part_of_the_key(self, cache):
        cache.put("PPR1", "bioRxiv 2020-01-01", "first")
        cache.put("PPR1", "bioRxiv 2021-06-06", "second")

        assert cache.get("PPR1", "bioRxiv 2020-01-01") == "first"
        assert cache.get("PPR1", "bioRxiv 2021-06-06") == "second"

    def test_identifier_is_part_of_the_key(self, cache):
        cache.put("PMC1", "v", "one")
        cache.put("PMC2", "v", "two")

        assert cache.get("PMC1", "v") == "one"

    def test_suffix_separates_searches_from_documents(self, cache):
        cache.put("PMID:1", "search", '{"hitCount": 0}', suffix=".json")
        cache.put("PMID:1", "search", "<article/>")

        assert cache.get("PMID:1", "search", suffix=".json") == '{"hitCount": 0}'
        assert cache.get("PMID:1", "search") == "<article/>"

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("10.1083/jcb.142", "10.1083_jcb.142"),
            ("PMID:1", "PMID_1"),
            ("a/b", "a b"),
        ],
    )
    def test_keys_differing_only_in_unsafe_characters_stay_apart(self, cache, left, right):
        """Sanitising the filename must not collapse two distinct identifiers into one entry."""
        cache.put(left, "v", "left content")
        cache.put(right, "v", "right content")

        assert cache.get(left, "v") == "left content"
        assert cache.get(right, "v") == "right content"

    def test_very_long_keys_stay_apart(self, cache):
        left = "PPR" + "x" * 300 + "1"
        right = "PPR" + "x" * 300 + "2"

        cache.put(left, "v", "left")
        cache.put(right, "v", "right")

        assert cache.get(left, "v") == "left"
        assert cache.get(right, "v") == "right"

    def test_filenames_stay_within_filesystem_limits(self, cache, tmp_path):
        cache.put("PPR" + "x" * 500, "v" * 500, "content")

        written = list((tmp_path / "cache").iterdir())
        assert all(len(path.name) < 255 for path in written)


class TestRobustness:
    def test_unicode_content_round_trips(self, cache):
        content = "<article>diameter 25 µm, Gαi2, 1.5 × 10⁶</article>"
        cache.put("PMC1", "v", content)

        assert cache.get("PMC1", "v") == content

    def test_no_partial_file_is_left_behind_after_a_successful_write(self, cache, tmp_path):
        cache.put("PMC1", "v", "content")

        assert not list((tmp_path / "cache").glob("*.partial"))

    def test_a_stray_partial_file_is_not_served_as_content(self, cache, tmp_path):
        """An interrupted write must not be read back as a complete document."""
        cache.put("PMC1", "v", "complete")
        directory = tmp_path / "cache"
        (real,) = list(directory.glob("*.xml"))
        (directory / (real.name + ".partial")).write_text("truncated", encoding="utf-8")

        assert cache.get("PMC1", "v") == "complete"
