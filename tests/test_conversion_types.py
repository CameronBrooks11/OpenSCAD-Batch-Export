"""CSV <-> JSON conversion must use the same value interpretation as the exporter."""

import csv
import json
import logging

import pytest

from openscad_export.params import coerce_cell, construct_d_flags, csv_to_json, json_to_csv


def convert(tmp_path, cells):
    """Write one CSV row, convert it to JSON, and return the parameter set."""
    src = tmp_path / "p.csv"
    with open(src, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["exported_filename", *cells])
        writer.writeheader()
        writer.writerow({"exported_filename": "row", **cells})
    out = tmp_path / "p.json"
    csv_to_json(src, out)
    return json.loads(out.read_text())["parameterSets"]["row"]


@pytest.mark.parametrize(
    ("cell", "stored"),
    [
        ("12", 12),
        ("-2.5", -2.5),
        (".5", 0.5),
        ("1e3", 1000.0),
        ("true", True),
        ("FALSE", False),
        ("hello", "hello"),
        ('"007"', "007"),  # the quote hatch keeps it a string
        ("undef", "undef"),  # written as the OpenSCAD literal
        ("[1, 2, 3]", "[1, 2, 3]"),  # a vector, as a literal in a string
        ("[[0,0],[1,1]]", "[[0, 0], [1, 1]]"),
        ("1_000", "1_000"),  # not a number in OpenSCAD's grammar, so a string
        ("1.2.3", "1.2.3"),
        ("inf", "inf"),
    ],
)
def test_csv_to_json_stores_what_the_exporter_would_read(tmp_path, cell, stored):
    assert convert(tmp_path, {"v": cell})["v"] == stored


def test_underscore_number_means_the_same_either_way(tmp_path):
    """CSV -> export and CSV -> JSON -> export must agree; Python's int() accepts
    underscores and OpenSCAD's grammar does not."""
    direct = construct_d_flags({"a": "1_000"})
    via_json = construct_d_flags({"a": convert(tmp_path, {"a": "1_000"})["a"]})

    assert direct == ['-Da="1_000"']
    assert via_json == direct


def test_vectors_are_stored_as_strings_not_json_arrays(tmp_path):
    """OpenSCAD's -p ignores a JSON array and keeps the model default, so the literal
    has to reach it as text."""
    stored = convert(tmp_path, {"pts": "[1, 2]"})["pts"]

    assert isinstance(stored, str)
    assert coerce_cell(stored) == [1, 2]


@pytest.mark.parametrize(
    "cell",
    ["[[1, 2]]", "[0:2:10]", "undef", '["a", "b"]', "[true, false]"],
    ids=["nested", "range", "undef", "string-vector", "bool-vector"],
)
def test_value_kinds_openscad_ignores_in_a_parameter_set_are_warned_about(tmp_path, cell, caplog):
    """Only a flat numeric vector survives the literal-in-a-string encoding; for the rest
    OpenSCAD silently keeps the model's default, so the conversion must say so."""
    with caplog.at_level(logging.WARNING, logger="openscad_export"):
        stored = convert(tmp_path, {"v": cell})["v"]

    assert isinstance(stored, str)
    assert "OpenSCAD ignores" in caplog.text and "'v'" in caplog.text
    assert "keep the model's default" in caplog.text


@pytest.mark.parametrize("cell", ["[1, 2]", "[3]", "[1.5, -2, 0]"])
def test_flat_numeric_vectors_are_not_warned_about(tmp_path, cell, caplog):
    with caplog.at_level(logging.WARNING, logger="openscad_export"):
        convert(tmp_path, {"v": cell})

    assert "OpenSCAD ignores" not in caplog.text


def test_a_cell_that_cannot_be_read_names_the_row_and_column(tmp_path):
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,label\nfirst,ok\nsecond,[draft]\n")

    with pytest.raises(ValueError, match=r"Row 1, column 'label': Invalid vector"):
        csv_to_json(src, tmp_path / "p.json")


def test_duplicate_row_names_are_refused_instead_of_dropping_a_row(tmp_path):
    """A parameter-set file holds one set per name, so two rows called the same thing
    would silently become one; the exporter refuses them too."""
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,d\nsame,10\nsame,20\nother,30\n")

    with pytest.raises(ValueError, match=r"Duplicate parameter set name 'same'"):
        csv_to_json(src, tmp_path / "p.json")


def test_blank_names_fall_back_to_the_index_like_the_exporter(tmp_path):
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,d\n,1\n,2\n")
    out = tmp_path / "p.json"

    csv_to_json(src, out)

    assert list(json.loads(out.read_text())["parameterSets"]) == ["model_0", "model_1"]


def test_json_to_csv_writes_cells_the_exporter_can_read_back(tmp_path):
    src = tmp_path / "p.json"
    src.write_text(
        json.dumps(
            {
                "parameterSets": {
                    "row": {
                        "n": 12,
                        "x": 2.5,
                        "flag": True,
                        "off": False,
                        "label": "hello",
                        "pts": ["a", "b"],
                        "nested": [1, [2, 3]],
                        "nothing": None,
                    }
                }
            }
        )
    )
    out = tmp_path / "p.csv"

    json_to_csv(src, out)

    with open(out, newline="") as f:
        (row,) = list(csv.DictReader(f))
    assert row["n"] == "12" and row["x"] == "2.5"
    assert row["flag"] == "true" and row["off"] == "false"
    assert row["label"] == "hello"
    assert row["pts"] == '["a", "b"]'  # not Python's ['a', 'b']
    assert row["nested"] == "[1, [2, 3]]"
    assert row["nothing"] == "undef"
    # every cell round-trips through the exporter's own reader
    assert coerce_cell(row["pts"]) == ["a", "b"]
    assert coerce_cell(row["nested"]) == [1, [2, 3]]
    assert coerce_cell(row["nothing"]) is None
    assert construct_d_flags(row)  # no ValueError from a malformed cell


def test_list_values_round_trip_csv_to_json_to_csv(tmp_path):
    src = tmp_path / "a.csv"
    src.write_text('exported_filename,pts\nrow,"[1, 2, 3]"\n')
    mid, back = tmp_path / "b.json", tmp_path / "c.csv"

    csv_to_json(src, mid)
    json_to_csv(mid, back)

    with open(back, newline="") as f:
        (row,) = list(csv.DictReader(f))
    assert row["pts"] == "[1, 2, 3]"
    assert coerce_cell(row["pts"]) == [1, 2, 3]


def test_unnamed_rows_get_the_index_the_exporter_uses(tmp_path):
    """Without an exported_filename column the exporter names cases model_<index>,
    zero-based; the converter used to number from 1 and to resolve the index by
    equality, so identical rows collapsed onto the first one."""
    src = tmp_path / "p.csv"
    src.write_text("d\n5\n5\n7\n")
    out = tmp_path / "p.json"

    csv_to_json(src, out)

    assert list(json.loads(out.read_text())["parameterSets"]) == ["model_0", "model_1", "model_2"]


def test_cli_reports_a_bad_cell_without_a_traceback(tmp_path, capsys):
    from openscad_export.cli import main

    src = tmp_path / "p.csv"
    src.write_text("exported_filename,label\nrow,[draft]\n")

    code = main(["csv2json", str(src), str(tmp_path / "p.json")])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error: Row 0, column 'label'")
    assert "Traceback" not in captured.err


def test_cli_reports_an_unserialisable_json_value_without_a_traceback(tmp_path, capsys):
    from openscad_export.cli import main

    src = tmp_path / "p.json"
    src.write_text('{"parameterSets": {"row": {"nested": {"a": 1}}}}')

    code = main(["json2csv", str(src), str(tmp_path / "p.csv")])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error: Cannot serialize dict")
    assert "Traceback" not in captured.err
