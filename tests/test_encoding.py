"""Parameter files are UTF-8, not whatever the machine's locale happens to be."""

import csv
import json

import pytest

from openscad_export import batch_export
from openscad_export.cli import main
from openscad_export.params import csv_to_json, json_to_csv, read_parameters

SCAD = "model.scad"
ACCENTED = "Größe_日本_café"


def test_utf8_names_and_values_survive_a_csv(tmp_path):
    src = tmp_path / "p.csv"
    src.write_bytes(f"exported_filename,label\n{ACCENTED},{ACCENTED}\n".encode())

    (row,) = read_parameters(src)

    assert row["exported_filename"] == ACCENTED
    assert row["label"] == ACCENTED


def test_utf8_names_and_values_survive_a_json_parameter_set(tmp_path):
    src = tmp_path / "p.json"
    src.write_bytes(json.dumps({"parameterSets": {ACCENTED: {"label": ACCENTED}}}).encode())

    (row,) = read_parameters(src)

    assert row["exported_filename"] == ACCENTED and row["label"] == ACCENTED


@pytest.mark.parametrize("suffix", [".csv", ".json"])
def test_a_byte_order_mark_is_not_read_as_part_of_the_first_name(tmp_path, suffix):
    """Excel writes UTF-8 with a BOM; read as plain utf-8 it becomes a \\ufeff on the
    first column name, which then matches no column at all."""
    src = tmp_path / f"p{suffix}"
    if suffix == ".csv":
        src.write_bytes(b"\xef\xbb\xbf" + b"exported_filename,d\nlid,10\n")
    else:
        src.write_bytes(b"\xef\xbb\xbf" + b'{"parameterSets": {"lid": {"d": "10"}}}')

    (row,) = read_parameters(src)

    assert row["exported_filename"] == "lid"
    assert row["d"] == "10"
    assert all(not key.startswith("﻿") for key in row)


def test_the_locale_encoding_is_not_used(tmp_path, monkeypatch):
    """A cp1252 locale must not change how a UTF-8 file is read."""
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("LANG", "C")
    src = tmp_path / "p.csv"
    src.write_bytes(f"exported_filename,label\nrow,{ACCENTED}\n".encode())

    (row,) = read_parameters(src)

    assert row["label"] == ACCENTED


def test_a_file_in_another_encoding_says_what_to_do(tmp_path):
    src = tmp_path / "p.csv"
    src.write_bytes("exported_filename,label\nrow,café\n".encode("cp1252"))

    with pytest.raises(ValueError, match=r"not valid utf-8-sig text .*Re-save it as UTF-8"):
        read_parameters(src)


def test_an_explicit_encoding_reads_that_file(tmp_path):
    src = tmp_path / "p.csv"
    src.write_bytes("exported_filename,label\nrow,café\n".encode("cp1252"))

    (row,) = read_parameters(src, "cp1252")

    assert row["label"] == "café"


def test_conversions_read_the_given_encoding_and_write_utf8(tmp_path):
    name = "Größe"  # cp1252 has no CJK, so this test stays within that encoding
    src = tmp_path / "p.csv"
    src.write_bytes(f"exported_filename,label\n{name},café\n".encode("cp1252"))
    out = tmp_path / "p.json"

    csv_to_json(src, out, "cp1252")

    assert json.loads(out.read_bytes().decode("utf-8")) == {
        "parameterSets": {name: {"label": "café"}},
        "fileFormatVersion": "1",
    }

    back = tmp_path / "back.csv"
    json_to_csv(out, back)

    with open(back, newline="", encoding="utf-8") as f:
        (row,) = list(csv.DictReader(f))
    assert row["exported_filename"] == name and row["label"] == "café"


def test_written_files_carry_no_byte_order_mark(tmp_path):
    src = tmp_path / "p.csv"
    src.write_bytes(b"\xef\xbb\xbfexported_filename,d\nlid,10\n")
    out = tmp_path / "p.json"

    csv_to_json(src, out)

    assert not out.read_bytes().startswith(b"\xef\xbb\xbf")


def test_batch_export_reads_utf8_and_records_the_encoding(fake_openscad, tmp_path):
    src = tmp_path / "p.csv"
    src.write_bytes(f"exported_filename,label\n{ACCENTED},café\n".encode())
    out = tmp_path / "o"

    result = batch_export(SCAD, str(src), str(out), fake_openscad, "binstl", None, True)

    assert [r.set_name for r in result.results] == [ACCENTED]
    assert (out / f"{ACCENTED}.stl").read_text(encoding="utf-8").splitlines()[-1] == (
        '-Dlabel="café"'
    )
    assert result.inputs["encoding"] == "utf-8-sig"


def test_cli_encoding_flag(fake_openscad, tmp_path, capsys):
    src = tmp_path / "p.csv"
    src.write_bytes("exported_filename,label\nrow,café\n".encode("cp1252"))
    out = tmp_path / "out"

    failed = main(["export", SCAD, str(src), str(out), "--openscad-path", fake_openscad])
    assert failed == 1
    assert "not valid utf-8-sig text" in capsys.readouterr().err

    ok = main(
        [
            "export",
            SCAD,
            str(src),
            str(out),
            "--openscad-path",
            fake_openscad,
            "--encoding",
            "cp1252",
        ]
    )
    assert ok == 0
    assert (out / "row.stl").read_text(encoding="utf-8").splitlines()[-1] == '-Dlabel="café"'


def test_cli_conversion_encoding_flag(tmp_path, capsys):
    src = tmp_path / "p.csv"
    src.write_bytes("exported_filename,label\nrow,café\n".encode("cp1252"))
    out = tmp_path / "p.json"

    assert main(["csv2json", str(src), str(out)]) == 1
    assert "not valid utf-8-sig text" in capsys.readouterr().err

    assert main(["csv2json", str(src), str(out), "--encoding", "cp1252"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["parameterSets"]["row"]["label"] == "café"


# The locale is an ambient input to open(), so a test that only runs in a UTF-8 locale
# cannot tell an explicit encoding from a lucky default. These two run the conversion in a
# subprocess whose locale cannot encode the text at all.
ASCII_ONLY_ENV = {
    "PYTHONUTF8": "0",
    "PYTHONCOERCECLOCALE": "0",
    "LC_ALL": "C",
    "LANG": "C",
}


def run_in_ascii_locale(code, tmp_path):
    import os
    import subprocess
    import sys

    env = {**os.environ, **ASCII_ONLY_ENV}
    env.pop("PYTHONIOENCODING", None)
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=tmp_path, env=env
    )


def test_json_is_written_as_utf8_whatever_the_locale(tmp_path):
    src = tmp_path / "p.csv"
    src.write_bytes("exported_filename,label\nrow,café\n".encode())
    out = tmp_path / "p.json"
    code = (
        "import locale, sys; assert locale.getpreferredencoding(False).lower() != 'utf-8', "
        "locale.getpreferredencoding(False)\n"
        "from openscad_export.params import csv_to_json\n"
        f"csv_to_json({str(src)!r}, {str(out)!r})\n"
    )

    result = run_in_ascii_locale(code, tmp_path)

    assert result.returncode == 0, result.stderr
    raw = out.read_bytes()
    assert "café".encode() in raw  # real UTF-8 bytes, not \uXXXX escapes
    assert json.loads(raw.decode("utf-8"))["parameterSets"]["row"]["label"] == "café"


def test_csv_is_written_as_utf8_whatever_the_locale(tmp_path):
    src = tmp_path / "p.json"
    src.write_bytes(json.dumps({"parameterSets": {"row": {"label": "café"}}}).encode())
    out = tmp_path / "p.csv"
    code = (
        "import locale; assert locale.getpreferredencoding(False).lower() != 'utf-8'\n"
        "from openscad_export.params import json_to_csv\n"
        f"json_to_csv({str(src)!r}, {str(out)!r})\n"
    )

    result = run_in_ascii_locale(code, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "café" in out.read_bytes().decode("utf-8")


# --- the native -p/-P path: OpenSCAD reads the file, so we cannot decode it for it -------


def test_a_non_utf8_parameter_set_file_is_refused_rather_than_exported_wrong(
    fake_openscad, tmp_path
):
    """OpenSCAD opens the file itself for -p/-P, always as UTF-8: it would reject the whole
    set, keep the model's defaults and still exit 0, so every case would look fine and
    carry the wrong geometry."""
    src = tmp_path / "p.json"
    src.write_bytes(
        json.dumps({"parameterSets": {"Größe": {"d": "22"}}}, ensure_ascii=False).encode("cp1252")
    )
    out = tmp_path / "o"

    with pytest.raises(ValueError, match=r"reads a parameter-set file as UTF-8 itself"):
        batch_export(
            SCAD, str(src), str(out), fake_openscad, "binstl", None, True, encoding="cp1252"
        )

    assert not out.exists()


def test_the_same_file_is_allowed_when_the_engine_cannot_take_parameter_sets(
    fake_openscad, tmp_path, monkeypatch
):
    """Before 2019.05 the values go out as -D flags, which we encode ourselves, so the
    guard must not fire."""
    monkeypatch.setenv("FAKE_OPENSCAD_VERSION", "2015.03")
    src = tmp_path / "p.json"
    src.write_bytes(
        json.dumps({"parameterSets": {"Größe": {"d": "22"}}}, ensure_ascii=False).encode("cp1252")
    )
    out = tmp_path / "o"

    result = batch_export(
        SCAD, str(src), str(out), fake_openscad, "binstl", None, True, encoding="cp1252"
    )

    assert [r.set_name for r in result.results] == ["Größe"]
    assert (out / "Größe.stl").read_text(encoding="utf-8").splitlines()[-1] == "-Dd=22"


def test_a_utf8_parameter_set_file_is_not_refused(fake_openscad, tmp_path):
    src = tmp_path / "p.json"
    src.write_bytes(
        json.dumps({"parameterSets": {ACCENTED: {"d": "22"}}}, ensure_ascii=False).encode()
    )

    for encoding in (None, "utf-8", "utf8", "utf-8-sig"):
        result = batch_export(
            SCAD,
            str(src),
            str(tmp_path / str(encoding)),
            fake_openscad,
            "binstl",
            None,
            True,
            encoding=encoding,
        )
        assert [r.set_name for r in result.results] == [ACCENTED]


@pytest.mark.parametrize(
    "argv",
    [
        ["export", SCAD, "P", "OUT", "--encoding", "bogus-8"],
        ["csv2json", "P", "OUT", "--encoding", "bogus-8"],
        ["json2csv", "P", "OUT", "--encoding", "bogus-8"],
    ],
    ids=["export", "csv2json", "json2csv"],
)
def test_an_unknown_encoding_name_is_an_error_not_a_traceback(
    fake_openscad, tmp_path, capsys, argv
):
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,d\nrow,1\n", encoding="utf-8")
    argv = [str(src) if a == "P" else str(tmp_path / "out.json") if a == "OUT" else a for a in argv]
    if argv[0] == "export":
        argv = [*argv, "--openscad-path", fake_openscad]

    code = main(argv)

    captured = capsys.readouterr()
    assert code == 1
    assert "Unknown encoding 'bogus-8'" in captured.err
    assert "Traceback" not in captured.err
