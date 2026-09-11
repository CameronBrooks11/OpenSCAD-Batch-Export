import pytest

from openscad_export.params import parse_selection


@pytest.mark.parametrize(
    ("selection", "total", "expected"),
    [
        ("0-5", 6, [0, 1, 2, 3, 4, 5]),
        ("1-3,7,10-12", 13, [1, 2, 3, 7, 10, 11, 12]),
        ("2,4", 5, [2, 4]),
        ("every:2 in 0-10", 11, [0, 2, 4, 6, 8, 10]),
        ("every:3 in 1-8", 9, [1, 4, 7]),
        ("from:5", 8, [5, 6, 7]),
        ("up_to:4", 10, [0, 1, 2, 3, 4]),
        ("from:6,up_to:1", 8, [0, 1, 6, 7]),
    ],
)
def test_documented_forms(selection, total, expected):
    assert parse_selection(selection, total) == expected


def test_result_is_sorted_and_deduplicated():
    assert parse_selection("3,1-2,2,3", 5) == [1, 2, 3]


def test_whitespace_and_empty_parts_are_ignored():
    assert parse_selection(" 1 , ,2 ", 5) == [1, 2]


@pytest.mark.parametrize(
    "selection",
    [
        "5",  # index == total
        "0-5",  # range end == total
        "from:5",
        "up_to:5",
        "every:5 in 0-5",
    ],
)
def test_index_equal_to_total_is_out_of_range(selection):
    with pytest.raises(ValueError):
        parse_selection(selection, 5)


@pytest.mark.parametrize("selection", ["5-2", "every:1 in 4-1"])
def test_reversed_range_is_rejected(selection):
    with pytest.raises(ValueError, match="start > end"):
        parse_selection(selection, 10)


@pytest.mark.parametrize("selection", ["abc", "1-x", "every:2", "every:a in 0-4", "-1"])
def test_malformed_selection_is_rejected(selection):
    with pytest.raises(ValueError):
        parse_selection(selection, 10)
