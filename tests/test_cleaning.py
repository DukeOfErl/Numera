import re

import pytest

from bionumbers_ingest.cleaning import clean_row, is_data_row
from bionumbers_ingest.parsing import iter_rows

GREEK_MU = "μ"
MICRO_SIGN = "µ"
ESCAPED_IMG = '&lt;IMG SRC="/WF_SQL_XSRF.html"&gt;'
LITERAL_IMG = '<IMG SRC="/WF_SQL_XSRF.html">'

# The export's 14 columns, for tests that need to inject into each in turn.
COLUMNS = [
    "bion_id",
    "Properties",
    "Organism",
    "Value",
    "Range",
    "Units",
    "Reference",
    "Reference PubMed ID",
    "Primary Source",
    "Primary Source PubMed ID",
    "Measurement Method",
    "Comments",
    "Entered By",
    "Keywords",
]


# --- ranges: notation, sign versus separator ---------------------------------


@pytest.mark.parametrize(
    "range_text,expected_low,expected_high",
    [
        ("'1.94 to 2.72", 1.94, 2.72),
        ("'1-1.1", 1.0, 1.1),  # hyphen after digit = separator, both positive
        ("'0.44-1.79", 0.44, 1.79),
        ("'-70", -70.0, -70.0),  # negative single value (e.g. membrane potential)
        ("'-90 to -60", -90.0, -60.0),  # negatives with word separator
        ("'-90--60", -90.0, -60.0),  # negatives with hyphen separator
        ("'−5 to −1", -5.0, -1.0),  # unicode minus sign
        ("'1–2", 1.0, 2.0),  # en-dash separator
        ("'1.5e-3 to 4e-2", 0.0015, 0.04),  # exponent sign not mistaken for separator
    ],
)
def test_signed_range_parsing(range_text, expected_low, expected_high):
    r = clean_row({"bion_id": "1", "Range": range_text})
    assert r.range_low == pytest.approx(expected_low)
    assert r.range_high == pytest.approx(expected_high)


def test_the_apostrophe_is_stripped_but_the_cell_text_is_kept():
    r = clean_row({"bion_id": "1", "Range": "'1.94 to 2.72"})
    assert r.range_raw == "1.94 to 2.72"


# --- plus-or-minus is uncertainty, not a bound -------------------------------


@pytest.mark.parametrize("range_text", ["'+-1.15", "'±1.15", "'+/-1.15"])
def test_plus_minus_is_uncertainty_around_value(range_text):
    r = clean_row({"bion_id": "1", "Value": "7.4", "Range": range_text})
    assert r.range_low == pytest.approx(7.4 - 1.15)
    assert r.range_high == pytest.approx(7.4 + 1.15)
    assert "range_plus_minus" in r.parse_flags


def test_plus_minus_without_value_flagged():
    r = clean_row({"bion_id": "1", "Value": "", "Range": "'±2"})
    assert r.range_low is None and r.range_high is None
    assert "range_plus_minus" in r.parse_flags
    assert "range_plus_minus_no_value" in r.parse_flags
    assert r.range_raw == "±2"  # original preserved for audit


def test_embedded_mean_sd_recovered():
    # mean lives in Range, Value empty
    r = clean_row({"bion_id": "1", "Value": "", "Range": "'-3.26±0.41"})
    assert r.range_low == pytest.approx(-3.26 - 0.41)
    assert r.range_high == pytest.approx(-3.26 + 0.41)
    assert "range_mean_sd_embedded" in r.parse_flags
    assert "range_plus_minus_no_value" not in r.parse_flags


def test_multi_measurement_cell_not_collapsed():
    # two measurements in one cell must stay flagged, not mis-parsed
    r = clean_row({"bion_id": "1", "Value": "", "Range": "'7.4±0.3 one face 5.9±0.3 other face"})
    assert r.range_low is None and r.range_high is None
    assert "range_plus_minus_no_value" in r.parse_flags
    assert "range_mean_sd_embedded" not in r.parse_flags


# --- one number, in every notation the source writes them --------------------


@pytest.mark.parametrize(
    "range_text,low,high",
    [
        ("'150,000-250,000", 150_000, 250_000),  # thousands separators, not four numbers
        ("'1,234,567 to 2,000,000", 1_234_567, 2_000_000),
        ("'2\u00d710^5 to 4\u00d710^5", 2e5, 4e5),  # × mantissa form
        ("'10^-8 to 10^-6", 1e-8, 1e-6),  # bare power of ten
        ("'10^\u201311 to 10^\u20139", 1e-11, 1e-9),  # en dash as the exponent's sign
        ("'1.4\u00d710^-6 to 3\u00d710^-6", 1.4e-6, 3e-6),
    ],
)
def test_scientific_and_grouped_numbers_are_one_number_each(range_text, low, high):
    r = clean_row({"bion_id": "1", "Range": range_text})
    assert r.range_low == pytest.approx(low)
    assert r.range_high == pytest.approx(high)
    # and therefore not mistaken for a cell holding more than two numbers
    assert "range_multi_number" not in r.parse_flags
    assert r.range_fused is False


def test_a_unit_exponent_does_not_become_a_bound():
    # `μm^3` trails the range; the 3 is the unit's exponent, not a measurement.
    r = clean_row({"bion_id": "1", "Range": "'1-2 " + GREEK_MU + "m^3"})
    assert r.range_low == pytest.approx(1.0)
    assert r.range_high == pytest.approx(2.0)
    assert r.range_fused is False


def test_a_comma_that_is_not_a_thousands_separator_still_separates():
    # only 3-digit groups are a separator, so a list stays a list
    r = clean_row({"bion_id": "1", "Range": "'1,2"})
    assert r.range_low == pytest.approx(1.0)
    assert r.range_high == pytest.approx(2.0)


# --- the fused-range predicate ----------------------------------------------


def test_more_than_two_numbers_is_flagged_and_bounds_unchanged():
    r = clean_row({"bion_id": "1", "Range": "'2 4 9"})
    assert r.range_low == 2.0 and r.range_high == 9.0  # computed, not corrected
    assert "range_multi_number" in r.parse_flags
    assert r.range_fused is True


def test_prose_between_the_bounds_is_flagged():
    r = clean_row({"bion_id": "1", "Range": "'7.4 in one strain 5.9 in another"})
    assert "range_prose_between_bounds" in r.parse_flags
    assert r.range_fused is True


def test_the_prose_check_spans_the_bounds_not_the_outermost_numbers():
    # `3 1-2`: the bounds are 1 and 2, which sit side by side with only a
    # separator between them, so no prose stands between the bounds. Comparing
    # the first and last number instead spans " 1-", which is not separators
    # only, and would raise the flag on a cell that does not earn it. Found by
    # fault seeding; only the flag list distinguishes the two, because
    # range_multi_number already covers the record either way.
    r = clean_row({"bion_id": "1", "Range": "'3 1-2"})
    assert r.range_low == pytest.approx(1.0)
    assert r.range_high == pytest.approx(3.0)
    assert "range_prose_between_bounds" not in r.parse_flags


def test_an_ordinary_two_number_range_raises_neither_flag():
    r = clean_row({"bion_id": "1", "Range": "'0.44-1.79"})
    assert "range_multi_number" not in r.parse_flags
    assert "range_prose_between_bounds" not in r.parse_flags
    assert r.range_fused is False


def test_a_trailing_unit_is_not_prose_between_bounds():
    # the unit stands after the high bound, not between the two
    r = clean_row({"bion_id": "1", "Range": "'1.94 to 2.72 " + GREEK_MU + "m"})
    assert "range_prose_between_bounds" not in r.parse_flags
    assert r.range_fused is False


@pytest.mark.parametrize(
    "row,why",
    [
        ({"Value": "7.4", "Range": "'±1.15"}, "a successful plus-or-minus parse"),
        ({"Value": "", "Range": "'-3.26±0.41"}, "a recovered mean and deviation"),
        (
            {"Range": "'Table link - http://example.invalid/f%2012.pdf"},
            "a link-only row",
        ),
        ({"Range": "'see comments"}, "a cell no number could be read from"),
        ({"Value": "", "Range": ""}, "a row with no scalar at all"),
    ],
)
def test_range_fused_is_false_for_flags_that_do_not_concern_fusion(row, why):
    # THE point of `range_fused` being a field. Every one of these carries a
    # non-empty parse_flags whose entries begin with `range_`, and none of them
    # means the bounds fuse two quantities. A rule over flag names would select
    # 5,494 records against the ~1,222 meant, and mark thousands of correctly
    # parsed entries in a user-visible marking.
    r = clean_row({"bion_id": "1", **row})
    assert r.parse_flags, f"expected {why} to raise some flag"
    assert r.range_fused is False, f"{why} is not a fused range"


# --- markup and entities: unescape before stripping --------------------------


@pytest.mark.parametrize("form,label", [(ESCAPED_IMG, "escaped"), (LITERAL_IMG, "literal")])
def test_injected_markup_is_removed_and_flagged_in_either_form(form, label):
    r = clean_row({"bion_id": "1", "Keywords": f"  Cell size{form}{form}  "})
    assert r.keywords == ["Cell size"], f"{label} markup survived into keywords"
    assert "injected_html_removed" in r.parse_flags


@pytest.mark.parametrize("column", COLUMNS[1:])
def test_escaped_markup_in_any_column_is_removed_and_flagged(column):
    # The export carries injected markup only in Keywords, but that is an absence
    # observed in one sample, which is not an absence. Any column could carry it.
    raw = {"bion_id": "1", column: f"text{ESCAPED_IMG}"}
    r = clean_row(raw)
    dumped = r.model_dump()
    for name, field in dumped.items():
        rendered = " ".join(field) if isinstance(field, list) else str(field)
        assert "<IMG" not in rendered, f"markup reached {name} from {column}"
        assert "WF_SQL_XSRF" not in rendered, f"markup reached {name} from {column}"
    assert "injected_html_removed" in r.parse_flags


def test_markup_in_the_range_column_puts_no_digit_into_a_bound():
    # The two defect classes meeting: a manufactured tag in Range would put an
    # escaped filename's digits within reach of number extraction, raising
    # range_fused indistinguishably from a genuine fusion.
    r = clean_row({"bion_id": "1", "Range": '\'1.94 to 2.72&lt;IMG SRC="/WF_12_34.html"&gt;'})
    assert r.range_low == pytest.approx(1.94)
    assert r.range_high == pytest.approx(2.72)
    assert r.range_fused is False
    assert "range_multi_number" not in r.parse_flags


TAG_RE = re.compile(r"<\s*/?\s*[A-Za-z]")


def test_no_emitted_field_ever_contains_a_tag(sample_html):
    # The record-boundary guard: a `<` followed by a tag name, in any field of
    # any record, including every element of the keyword list.
    for raw in iter_rows(sample_html):
        if not is_data_row(raw):
            continue
        for name, field in clean_row(raw).model_dump().items():
            parts = field if isinstance(field, list) else [field]
            for part in parts:
                assert not TAG_RE.search(str(part)), f"tag in {name}: {part!r}"


@pytest.mark.parametrize(
    "cell,must_survive",
    [
        # Variable notation: the export writes means and quantities in angle
        # brackets. None of these is an HTML element.
        ("the ratio &lt;Csat&gt; over &lt;Vcell&gt;", ["Csat", "Vcell"]),
        ("mean diameter &lt;D&gt; of the cell", ["D"]),
        ("&lt;Raf/cell&gt; and &lt;liter/cell&gt;", ["Raf/cell", "liter/cell"]),
        # The less-than sign in prose. A generic `<[^>]+>` eats from the `<` to
        # the next `>`, taking the whole clause with it.
        ("significant (p&lt;0.05) in body height and weight", ["0.05", "body height"]),
        ("faster (&lt;20 ms) than most diffusion limits", ["20 ms", "diffusion"]),
        ("mesotrophic=0.1&lt;Csat&lt;1 mg m&gt;", ["0.1", "Csat", "1 mg"]),
        ("doi fragment &lt;750::AID-BIT15&gt;", ["750::AID-BIT15"]),
    ],
)
def test_angle_bracket_content_is_not_treated_as_markup(cell, must_survive):
    r = clean_row({"bion_id": "1", "Comments": cell})
    for fragment in must_survive:
        assert fragment in r.comments, f"{fragment!r} was deleted from {r.comments!r}"


def test_content_in_angle_brackets_does_not_raise_the_markup_flag():
    # Otherwise the flag conflates "injected markup removed" with "the source
    # wrote a variable in angle brackets", and its count stops meaning anything.
    r = clean_row({"bion_id": "1", "Comments": "the ratio &lt;Csat&gt; over &lt;Vcell&gt;"})
    assert "injected_html_removed" not in r.parse_flags


def test_a_less_than_clause_in_the_range_column_keeps_its_numbers():
    # This is the row that moved range_multi_number from 1,222 to 1,221: a
    # generic tag pattern deleted part of the cell and the digits it contained.
    r = clean_row({"bion_id": "1", "Range": "'0.1&lt;Csat&lt;1"})
    assert r.range_low == pytest.approx(0.1)
    assert r.range_high == pytest.approx(1.0)


def test_real_html_elements_are_still_stripped():
    r = clean_row({"bion_id": "1", "Comments": "a&lt;br&gt;b&lt;sub&gt;2&lt;/sub&gt;c"})
    assert "<" not in r.comments
    assert "injected_html_removed" in r.parse_flags


def test_multiply_escaped_markup_does_not_survive_one_pass():
    r = clean_row({"bion_id": "1", "Keywords": "size&amp;lt;IMG SRC=&amp;quot;x&amp;quot;&amp;gt;"})
    assert all("<" not in kw for kw in r.keywords)
    assert "IMG" not in " ".join(r.keywords)


# --- units -------------------------------------------------------------------


def test_the_micro_sign_is_folded_into_the_greek_mu():
    r = clean_row({"bion_id": "1", "Units": MICRO_SIGN + "m"})
    assert r.units == GREEK_MU + "m"
    assert MICRO_SIGN not in r.units


def test_an_entity_encoded_micrometre_normalises_the_same_way():
    r = clean_row({"bion_id": "1", "Units": "&#181;m"})
    assert r.units == GREEK_MU + "m"


def test_a_unit_already_written_with_the_greek_mu_is_unchanged():
    r = clean_row({"bion_id": "1", "Units": "&#956;m^3"})
    assert r.units == GREEK_MU + "m^3"


# --- link-only and link-plus-range rows -------------------------------------


def test_a_link_beside_a_range_keeps_both_and_no_url_digit_becomes_a_bound():
    r = clean_row(
        {
            "bion_id": "1",
            "Range": "'0.44-1.79 Table link - http://example.invalid/E.%20coli%20vol%2012.pdf",
        }
    )
    assert r.range_low == pytest.approx(0.44)
    assert r.range_high == pytest.approx(1.79)
    assert r.table_link == "http://example.invalid/E.%20coli%20vol%2012.pdf"
    assert "range_is_link" in r.parse_flags


def test_a_link_and_nothing_else_is_kept_with_no_bounds():
    r = clean_row({"bion_id": "1", "Range": "'Table link - http://example.invalid/f%2012.pdf"})
    assert r.value is None and r.range_low is None and r.range_high is None
    assert r.table_link == "http://example.invalid/f%2012.pdf"
    assert "range_is_link" in r.parse_flags
    assert "no_scalar" in r.parse_flags


def test_the_preserved_range_text_still_contains_the_link():
    # Deliberate: the field is the source cell, not the string the bounds came
    # from. A recomputation must strip the link first.
    r = clean_row(
        {"bion_id": "1", "Range": "'0.44-1.79 Table link - http://example.invalid/f%2012.pdf"}
    )
    assert "http://example.invalid/f%2012.pdf" in r.range_raw
    assert r.range_low == pytest.approx(0.44) and r.range_high == pytest.approx(1.79)


# --- unparseable cells and non-data rows ------------------------------------


def test_an_unparseable_range_is_flagged_not_hidden():
    r = clean_row({"bion_id": "1", "Range": "'see comments"})
    assert r.range_low is None and r.range_high is None
    assert "range_unparsed" in r.parse_flags


def test_an_unparseable_value_is_flagged():
    r = clean_row({"bion_id": "1", "Value": "not a number"})
    assert r.value is None
    assert "value_unparsed" in r.parse_flags


def test_a_row_with_neither_value_nor_range_is_flagged_no_scalar():
    r = clean_row({"bion_id": "1", "Value": "", "Range": ""})
    assert "no_scalar" in r.parse_flags


@pytest.mark.parametrize(
    "bion_id,expected", [("900001", True), ("&nbsp;", False), ("", False), ("  ", False)]
)
def test_padding_rows_are_not_data_rows(bion_id, expected):
    assert is_data_row({"bion_id": bion_id}) is expected


# --- over the fixture --------------------------------------------------------


def _by_bnid(sample_html):
    return {
        r.bnid: r for r in (clean_row(raw) for raw in iter_rows(sample_html) if is_data_row(raw))
    }


def test_the_fixture_yields_six_records(sample_html):
    assert sorted(_by_bnid(sample_html)) == [900001, 900002, 900003, 900004, 900005, 900006]


def test_range_to_form_over_the_fixture(sample_html):
    r = _by_bnid(sample_html)[900001]
    assert r.range_low == pytest.approx(1.94)
    assert r.range_high == pytest.approx(2.72)
    assert r.value is None
    assert r.units == GREEK_MU + "m"
    assert r.keywords == ["Cell size"]  # the injected markup is gone
    assert "injected_html_removed" in r.parse_flags


def test_number_plus_hyphen_range_over_the_fixture(sample_html):
    r = _by_bnid(sample_html)[900002]
    assert r.value == pytest.approx(1.1)
    assert r.range_low == pytest.approx(0.44)
    assert r.range_high == pytest.approx(1.79)
    assert r.units == GREEK_MU + "m^3"
    assert r.range_fused is False


def test_link_only_row_over_the_fixture(sample_html):
    r = _by_bnid(sample_html)[900003]
    assert r.table_link == "http://example.invalid/files/synthetic%20file%2012.pdf"
    assert r.range_low is None and r.range_high is None
    assert "range_is_link" in r.parse_flags
    assert r.range_fused is False


# --- defects found by code review, each reproduced before it was fixed --------


@pytest.mark.parametrize(
    "row,low,high,flag",
    [
        # The deviation is the number AFTER the sign, not the first in the cell.
        ({"Value": "7.4", "Range": "'(n=3) ±1.15"}, 7.4 - 1.15, 7.4 + 1.15, None),
        # A whole-cell mean±sd is read that way whether or not Value is filled.
        # Gated on an empty Value, this used the mean itself as the deviation.
        ({"Value": "-3.26", "Range": "'-3.26±0.41"}, -3.67, -2.85, "range_mean_sd_embedded"),
    ],
)
def test_the_plus_minus_deviation_is_the_number_after_the_sign(row, low, high, flag):
    r = clean_row({"bion_id": "1", **row})
    assert r.range_low == pytest.approx(low)
    assert r.range_high == pytest.approx(high)
    if flag:
        assert flag in r.parse_flags


def test_more_than_one_plus_minus_is_more_than_one_measurement():
    # 138 records of the export. With a value present this used to fuse them into
    # one interval, and the fused-range flags never see this branch, so it shipped
    # unmarked as an exact measurement.
    r = clean_row({"bion_id": "1", "Value": "7.4", "Range": "'7.4±0.3 one face 5.9±0.3 other face"})
    assert r.range_low is None and r.range_high is None
    assert "range_multi_measurement" in r.parse_flags


def test_a_value_that_is_not_a_bare_number_is_flagged():
    # `<2` is a bound, not a measurement; emitting an exact 2.0 is the unsourced
    # correction ADR-0230 forbids.
    r = clean_row({"bion_id": "1", "Value": "&lt;2"})
    assert r.value == pytest.approx(2.0)
    assert "value_recovered_from_text" in r.parse_flags


@pytest.mark.parametrize("text", ["nan", "inf", "-inf"])
def test_a_non_finite_value_is_not_a_measurement(text):
    # float() accepts all three; none survives JSON or means anything here.
    r = clean_row({"bion_id": "1", "Value": text})
    assert r.value is None
    assert "value_unparsed" in r.parse_flags


def test_bounds_written_after_the_link_are_not_discarded():
    # Truncating from the URL onward dropped them with no flag. 10 real records.
    r = clean_row({"bion_id": "1", "Range": "'Table link - http://x.invalid/a.pdf 0.44-1.79"})
    assert r.range_low == pytest.approx(0.44)
    assert r.range_high == pytest.approx(1.79)
    assert "range_is_link" in r.parse_flags


def test_equal_extremes_do_not_blind_the_prose_check():
    # min() and max() by value return the SAME element here, leaving an empty span
    # to inspect and shipping two unrelated quantities as one measurement.
    r = clean_row({"bion_id": "1", "Range": "'5 in one strain 5 in another"})
    assert r.range_fused is True
    assert "range_prose_between_bounds" in r.parse_flags


def test_a_number_without_a_leading_zero_keeps_its_decimal_point():
    # `.5` tokenised as 5, giving bounds 1.5..5.0 — a bound 10x off, and swapped.
    r = clean_row({"bion_id": "1", "Range": "'.5-1.5"})
    assert r.range_low == pytest.approx(0.5)
    assert r.range_high == pytest.approx(1.5)


@pytest.mark.parametrize(
    "range_text,low,high",
    [
        ("'5%-10%", 5.0, 10.0),  # invented a low bound of -10 before the fix
        ("'5g-10g", 5.0, 10.0),
        ("'-90 to -60", -90.0, -60.0),  # a real sign must still be a sign
        ("'-70", -70.0, -70.0),
    ],
)
def test_a_hyphen_after_a_unit_is_a_separator_not_a_sign(range_text, low, high):
    r = clean_row({"bion_id": "1", "Range": range_text})
    assert r.range_low == pytest.approx(low)
    assert r.range_high == pytest.approx(high)


def test_an_identifier_that_int_would_reject_is_not_a_data_row():
    # "²".isdigit() is True but int("²") raises, and one exception mid-run costs
    # the entire corpus rather than one row.
    assert is_data_row({"bion_id": "²"}) is False
