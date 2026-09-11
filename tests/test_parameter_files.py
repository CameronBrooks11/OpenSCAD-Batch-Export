import csv
import json
from pathlib import Path

import pytest

from openscad_export.params import csv_to_json, json_to_csv, read_json

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
EXAMPLE_NAMES = sorted(p.name for p in EXAMPLES.iterdir() if (p / f"{p.name}.csv").exists())


def rows_by_name(csv_path):
    with open(csv_path, newline="") as f:
        return {row["exported_filename"]: row for row in csv.DictReader(f)}


def test_read_json_names_each_set_from_its_key(tmp_path):
    src = tmp_path / "p.json"
    src.write_text(
        json.dumps(
            {
                "fileFormatVersion": "1",
                "parameterSets": {"lid": {"d": 10, "open": True}, "base": {"d": 12}},
            }
        )
    )
    sets = read_json(src)
    assert [s["exported_filename"] for s in sets] == ["lid", "base"]
    assert sets[0] == {"d": 10, "open": True, "exported_filename": "lid"}


def test_csv_to_json_types_values_and_writes_customizer_format(tmp_path):
    src = tmp_path / "p.csv"
    src.write_text(
        "exported_filename,n,x,flag,label\nsmall,3,2.5,true,ab c\nbig,10,4.0,FALSE,7up\n"
    )
    out = tmp_path / "p.json"

    csv_to_json(src, out)
    data = json.loads(out.read_text())

    assert data["fileFormatVersion"] == "1"
    assert data["parameterSets"] == {
        "small": {"n": 3, "x": 2.5, "flag": True, "label": "ab c"},
        "big": {"n": 10, "x": 4.0, "flag": False, "label": "7up"},
    }


def test_json_to_csv_puts_name_first_and_lowercases_booleans(tmp_path):
    src = tmp_path / "p.json"
    src.write_text(
        json.dumps(
            {"parameterSets": {"a": {"bore": 1, "flag": True}, "b": {"bore": 2, "flag": False}}}
        )
    )
    out = tmp_path / "p.csv"

    json_to_csv(src, out)

    with open(out, newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["exported_filename", "bore", "flag"]
        rows = list(reader)
    assert rows == [
        {"exported_filename": "a", "bore": "1", "flag": "true"},
        {"exported_filename": "b", "bore": "2", "flag": "false"},
    ]


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_example_csv_survives_round_trip(name, tmp_path):
    src = EXAMPLES / name / f"{name}.csv"
    mid = tmp_path / "mid.json"
    back = tmp_path / "back.csv"

    csv_to_json(src, mid)
    json_to_csv(mid, back)

    original = rows_by_name(src)
    restored = rows_by_name(back)
    assert restored.keys() == original.keys()
    for key in original:
        assert set(restored[key]) == set(original[key])
        for column, value in original[key].items():
            # Booleans are normalised to lowercase; everything else must survive verbatim.
            expected = value.lower() if value.lower() in ("true", "false") else value
            assert restored[key][column] == expected, (key, column)
