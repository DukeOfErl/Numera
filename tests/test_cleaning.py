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


@pytest.mark.parametrize(
    "range_text,low,high",
    [
        ("'1-2×10^9", 1.0, 2e9),  # E. coli saturation: means 1e9 .. 2e9
        ("'0.25-2.5e30", 0.25, 2.5e30),
        ("'1-5e-7", 5e-7, 1.0),
    ],
)
def test_a_shared_exponent_is_flagged_and_the_bounds_left_alone(range_text, low, high):
    # The exponent is written once and applies to both bounds, but which reading is
    # right cannot be settled from the cell — `1-5e-7` is either "1 to 5e-7" or
    # "1e-7 to 5e-7", and only knowing an epithelial cell is not a square
    # centimetre decides it. So: flagged, never corrected.
    r = clean_row({"bion_id": "1", "Range": range_text})
    assert r.range_low == pytest.approx(low)
    assert r.range_high == pytest.approx(high)
    assert "range_shared_exponent" in r.parse_flags
    assert r.range_fused is True


@pytest.mark.parametrize(
    "range_text",
    [
        "'5e-9 to 8e-9",  # both bounds carry their own exponent
        "'1.2E-8 - 1.7E-8",
        "'10^-6-10^-9",
        "'1 to 10^6",  # a bare power of ten is a number, not a shared exponent
        "'0.44-1.79",
    ],
)
def test_a_range_with_no_shared_exponent_is_not_flagged_for_one(range_text):
    r = clean_row({"bion_id": "1", "Range": range_text})
    assert "range_shared_exponent" not in r.parse_flags


def test_a_shared_exponent_that_changes_nothing_is_not_flagged():
    # `0 - 1.3×10^6` reads the same either way, so there is no ambiguity to
    # report, and marking a correct record teaches a reader to ignore the mark.
    r = clean_row({"bion_id": "1", "Range": "'0 - 1.3×10^6"})
    assert r.range_low == pytest.approx(0.0)
    assert r.range_high == pytest.approx(1.3e6)
    assert "range_shared_exponent" not in r.parse_flags
    assert r.range_fused is False


# --- ranges the source did not state as a closed interval ---------------------


@pytest.mark.parametrize(
    "range_text,flag",
    [
        ("'<0.001", "range_one_sided"),
        ("'>100", "range_one_sided"),
        ("'≤ 5", "range_one_sided"),
        ("'≥ 10", "range_one_sided"),
        ("'up to 30", "range_one_sided"),
        ("'at least 2", "range_one_sided"),
        ("'~5", "range_approximate"),
        ("'≈ 5", "range_approximate"),
        ("'about 12", "range_approximate"),
    ],
)
def test_a_hedged_range_is_flagged_and_marked_not_exact(range_text, flag):
    # 2,233 records of the export carry such a marker. `<0.001` stored as the
    # closed interval [0.001, 0.001] asserts an exact equality where the source
    # said *less than* — the project's own unfalsifiable-error class.
    r = clean_row({"bion_id": "1", "Range": range_text})
    assert flag in r.parse_flags
    assert r.range_qualified is True


@pytest.mark.parametrize("range_text", ["'0.44-1.79", "'1.94 to 2.72", "'-90 to -60"])
def test_a_plainly_stated_range_is_not_marked_hedged(range_text):
    r = clean_row({"bion_id": "1", "Range": range_text})
    assert r.range_qualified is False
    assert "range_one_sided" not in r.parse_flags
    assert "range_approximate" not in r.parse_flags


def test_hedging_is_a_separate_predicate_from_fusion():
    # They mean different things and must not be conflated: `range_fused` says the
    # bounds may come from two quantities; `range_qualified` says the source never
    # claimed a closed interval. Widening range_fused would have redefined a
    # contract add-ask-agent already reads.
    hedged = clean_row({"bion_id": "1", "Range": "'<0.001"})
    assert hedged.range_qualified is True and hedged.range_fused is False
    fused = clean_row({"bion_id": "1", "Range": "'2 4 9"})
    assert fused.range_fused is True and fused.range_qualified is False


def test_an_incoherent_shared_exponent_reading_is_not_flagged():
    # `1000-2e5` would invert under the shared reading (1000e5 above 2e5), so the
    # literal 1000..200000 is the only possible reading and the range is correct.
    r = clean_row({"bion_id": "1", "Range": "'1000-2e5"})
    assert "range_shared_exponent" not in r.parse_flags
    assert r.range_fused is False


@pytest.mark.parametrize(
    "range_text,low,high",
    [
        ("'7.4±0.3 μm", 7.1, 7.7),  # a trailing unit no longer costs both bounds
        ("'0.5±0.1 SD", 0.4, 0.6),
        ("'-3.26±0.41 kcal/mol", -3.67, -2.85),
    ],
)
def test_a_mean_and_deviation_with_a_trailing_unit_keeps_its_bounds(range_text, low, high):
    r = clean_row({"bion_id": "1", "Value": "", "Range": range_text})
    assert r.range_low == pytest.approx(low)
    assert r.range_high == pytest.approx(high)
    assert "range_mean_sd_embedded" in r.parse_flags


@pytest.mark.parametrize(
    "range_text",
    [
        "'1.3±0.2x10^6",  # the exponent applies to BOTH mean and deviation
        "'15.6±0.5х10^3",
        "'± 300 to 400",  # a range OF the deviation
        "'0.5±0.1 (n=12)",  # a sample size, indistinguishable from a second number
    ],
)
def test_trailing_text_containing_a_number_yields_no_bounds_and_is_flagged(range_text):
    # Deliberately conservative. 21 cells of the export are shaped this way, and
    # most are `mean±sd × 10^n` — reading the mean and deviation while dropping
    # the exponent would be wrong by a factor of a million, silently. So no
    # bounds and a flag, rather than a plausible number.
    r = clean_row({"bion_id": "1", "Value": "", "Range": range_text})
    assert r.range_low is None and r.range_high is None
    assert "range_plus_minus" in r.parse_flags


def test_an_uppercase_X_multiplier_is_read_like_the_others():
    r = clean_row({"bion_id": "1", "Range": "'2X10^5 to 4X10^5"})
    assert r.range_low == pytest.approx(2e5)
    assert r.range_high == pytest.approx(4e5)
    assert "range_multi_number" not in r.parse_flags


def test_a_unit_exponent_between_the_bounds_does_not_stop_the_scan():
    """Holds `A unit's exponent is not a measurement` in measurement-cleaning.

    Skipping the exponent must not abandon the numbers after it. Found by mutation
    testing: turning the skip's `continue` into a `break` survived the whole
    suite, and 258 range cells carry a caret exponent ahead of a later number, so
    the difference is between bounds of 1..5 and bounds of 1..1.
    """
    r = clean_row({"bion_id": "1", "Range": "'1 " + GREEK_MU + "m^3 to 5"})
    assert r.range_low == pytest.approx(1.0)
    assert r.range_high == pytest.approx(5.0)


def test_two_mutation_survivors_are_knowingly_left_alive():
    """Two mutants survive this suite deliberately; neither is a contract.

    1. `re.IGNORECASE` on the `to` separator. The export uses lowercase `to` 845
       times and uppercase `TO` zero times, so case-insensitivity is tuning. A
       test asserting `1 TO 5` parses would pin a behaviour nothing requires.
    2. The `j >= 0` boundary in the sign-versus-separator scan. It differs from
       `j > 0` only for a cell beginning with whitespace then a signed number, of
       which the export has none.

    Both are recorded here rather than killed, because a survivor nobody triaged
    is an oversight while one nobody killed on purpose is a decision. What the
    suite does assert is the requirement itself — that a hyphen after a digit
    separates and a leading sign is a sign — which the cases below cover.
    """
    assert clean_row({"bion_id": "1", "Range": "'1-1.1"}).range_low == pytest.approx(1.0)
    assert clean_row({"bion_id": "1", "Range": "'-70"}).range_low == pytest.approx(-70.0)


COLUMN_TO_FIELD = {
    "Properties": "property",
    "Organism": "organism",
    "Units": "units",
    "Reference": "reference",
    "Reference PubMed ID": "reference_pubmed_id",
    "Primary Source": "primary_source",
    "Primary Source PubMed ID": "primary_source_pubmed_id",
    "Measurement Method": "measurement_method",
    "Comments": "comments",
    "Entered By": "entered_by",
}


@pytest.mark.parametrize("column,field", sorted(COLUMN_TO_FIELD.items()))
def test_each_column_reaches_its_own_field(column, field):
    """Holds `Each key carries the value of its own column` in corpus-ingestion.

    Found by mutation testing, and it is the gap the contract test structurally
    could not catch: `null` is an accepted type for ten of the twelve keys, so
    blanking eight pass-through fields left all 205 tests passing. The corpus
    would have loaded cleanly and answered with no organism, no reference and no
    measurement method.
    """
    raw = {"bion_id": "900001"}
    raw.update({c: f"value-of-{f}" for c, f in COLUMN_TO_FIELD.items()})
    record = clean_row(raw)
    assert getattr(record, field) == f"value-of-{field}"


def test_the_numeric_columns_reach_their_own_fields():
    r = clean_row({"bion_id": "900002", "Value": "1.5", "Range": "'2-3"})
    assert r.bnid == 900002
    assert r.value == pytest.approx(1.5)
    assert r.range_low == pytest.approx(2.0)
    assert r.range_high == pytest.approx(3.0)


def test_the_keyword_column_reaches_the_keyword_field():
    r = clean_row({"bion_id": "1", "Keywords": "alpha, beta, gamma"})
    assert r.keywords == ["alpha", "beta", "gamma"]


@pytest.mark.parametrize("phrase", ["Table link", "Table Link", "table link"])
def test_the_table_link_phrase_is_matched_however_it_is_cased(phrase):
    # All three spellings occur in the export; matching one exactly left the
    # other two sitting in the text the bounds are read from.
    r = clean_row({"bion_id": "1", "Range": f"'0.44-1.79 {phrase} - http://x.invalid/a.pdf"})
    assert r.range_low == pytest.approx(0.44)
    assert r.range_high == pytest.approx(1.79)
    assert r.table_link == "http://x.invalid/a.pdf"
    assert "range_is_link" in r.parse_flags
    assert "link" not in (r.range_raw or "").lower().split("http")[0].replace(phrase.lower(), "")


# --- final review findings, all latent in today's export ----------------------


@pytest.mark.parametrize(
    "range_text,low,high",
    [
        ("'2×10^+5 to 4×10^+5", 2e5, 4e5),
        ("'10^+8", 1e8, 1e8),
        ("'10^-8", 1e-8, 1e-8),  # the minus forms must still work
        ("'10^–8", 1e-8, 1e-8),
    ],
)
def test_an_explicitly_positive_exponent_is_not_negated(range_text, low, high):
    # A `+` in the caret-sign class rewrote `10^+5` as `10^-5`: a number ten orders
    # of magnitude out that parsed without complaint and raised no flag.
    r = clean_row({"bion_id": "1", "Range": range_text})
    assert r.range_low == pytest.approx(low)
    assert r.range_high == pytest.approx(high)


def test_a_positive_exponent_shared_across_bounds_is_flagged_not_corrected():
    """`1-2×10^+9` is the shared-exponent shape, and the fix must not "correct" it.

    The first draft of this test asserted bounds of 1e9..2e9 — the reading a human
    would take — which is exactly the unsourced correction ADR-0230 forbids. What
    the fix has to deliver is that the exponent is read as POSITIVE (so the high
    bound is 2e9 rather than 2e-09) while the ambiguity between the two readings is
    reported rather than resolved.
    """
    r = clean_row({"bion_id": "1", "Range": "'1-2×10^+9"})
    assert r.range_low == pytest.approx(1.0)
    assert r.range_high == pytest.approx(2e9)
    assert "range_shared_exponent" in r.parse_flags
    assert r.range_fused is True


def test_a_positive_exponent_in_the_value_column_is_not_negated():
    r = clean_row({"bion_id": "1", "Value": "2×10^+5"})
    assert r.value == pytest.approx(2e5)


def test_a_scheme_less_link_does_not_turn_a_filename_into_bounds():
    # `table%2012.pdf` gave a range of 2012 to 2012 — a measurement invented from
    # a filename's percent-escapes.
    r = clean_row({"bion_id": "1", "Range": "'Table link - www.example.org/files/table%2012.pdf"})
    assert r.range_low is None and r.range_high is None
    assert "range_is_link" in r.parse_flags
    assert "range_link_unparsed" in r.parse_flags


@pytest.mark.parametrize(
    "value_text,flag",
    [("&lt;2", "value_one_sided"), ("&gt;100", "value_one_sided"), ("~5", "value_approximate")],
)
def test_a_hedged_value_reaches_the_contract_not_just_the_flags(value_text, flag):
    # Reporting a hedge in the range column and hiding it in the value column
    # means `<2` arrives at a consumer as an exact 2, and the only signal was a
    # flag the model docstring tells consumers never to read.
    r = clean_row({"bion_id": "1", "Value": value_text})
    assert flag in r.parse_flags
    assert r.range_qualified is True


@pytest.mark.parametrize(
    "row",
    [{"Value": "abc 1e400"}, {"Value": "1e400"}, {"Range": "'1-1e400"}, {"Range": "'1e400"}],
)
def test_an_overflowing_literal_is_not_a_measurement(row):
    # float("1e400") returns inf rather than raising, and pydantic writes inf as
    # JSON null — so it would become an absent number on a record the report
    # counted as having one, and corpus and manifest would disagree.
    import math

    r = clean_row({"bion_id": "1", **row})
    for number in (r.value, r.range_low, r.range_high):
        assert number is None or math.isfinite(number)
    assert (r.range_low is None) == (r.range_high is None)  # both or neither
    assert r.parse_flags, "an unusable number must say so"


def test_a_range_cell_holding_only_the_text_marker_is_empty_not_unreadable():
    # The export writes an empty Range as a bare apostrophe. Reporting it as
    # unparseable inflates the one count the report presents as a claim about what
    # could not be read.
    assert "range_unparsed" not in clean_row({"bion_id": "1", "Range": "'"}).parse_flags
    assert "range_unparsed" not in clean_row({"bion_id": "1", "Range": ""}).parse_flags
