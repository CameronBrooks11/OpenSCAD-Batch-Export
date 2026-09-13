import logging
import os

import pytest

from openscad_export import BatchResult, ExportResult, batch_export

SCAD = "model.scad"


@pytest.fixture
def params_csv(tmp_path):
    p = tmp_path / "params.csv"
    p.write_text("exported_filename,size,fail\nfirst,5,false\nsecond,7,true\nthird,9,false\n")
    return str(p)


@pytest.mark.parametrize("sequential", [True, False])
def test_returns_results_in_input_order_with_failure_isolated(
    fake_openscad, params_csv, tmp_path, sequential
):
    out = tmp_path / "out"

    result = batch_export(SCAD, params_csv, str(out), fake_openscad, "binstl", None, sequential)

    assert isinstance(result, BatchResult)
    assert [r.name for r in result.results] == ["first", "second", "third"]
    assert [r.ok for r in result.results] == [True, False, True]
    assert [r.name for r in result.failures] == ["second"]
    assert (out / "first.stl").exists() and (out / "third.stl").exists()
    assert not (out / "second.stl").exists()
    assert result.total_duration >= 0
    assert all(r.duration >= 0 for r in result.results)


def test_failure_carries_returncode_and_stderr(fake_openscad, params_csv, tmp_path):
    result = batch_export(
        SCAD, params_csv, str(tmp_path / "o"), fake_openscad, "binstl", None, True
    )

    failed = result.failures[0]
    assert isinstance(failed, ExportResult)
    assert failed.returncode == 1
    assert "boom" in failed.stderr
    assert result.successes[0].stderr == ""
    assert result.successes[0].returncode == 0


def test_parameters_reach_the_command_line(fake_openscad, params_csv, tmp_path):
    out = tmp_path / "o"
    batch_export(SCAD, params_csv, str(out), fake_openscad, "binstl", None, True)

    assert (out / "first.stl").read_text().splitlines() == ["-Dsize=5", "-Dfail=false"]


def test_selection_is_applied(fake_openscad, params_csv, tmp_path):
    result = batch_export(
        SCAD, params_csv, str(tmp_path / "o"), fake_openscad, "binstl", "0,2", True
    )

    assert [r.name for r in result.results] == ["first", "third"]
    assert result.failures == []


def test_summary_reports_counts_and_paths(fake_openscad, params_csv, tmp_path):
    result = batch_export(
        SCAD, params_csv, str(tmp_path / "o"), fake_openscad, "binstl", None, True
    )

    text = result.summary()
    assert "Total exports attempted: 3" in text
    assert "Successful exports: 2" in text
    assert "Failed exports: 1" in text
    assert "second.stl: boom" in text


def test_progress_is_logged_not_printed(fake_openscad, params_csv, tmp_path, caplog, capsys):
    with caplog.at_level(logging.INFO, logger="openscad_export"):
        batch_export(SCAD, params_csv, str(tmp_path / "o"), fake_openscad, "binstl", None, True)

    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("Exported: ") and m.endswith("seconds.") for m in messages)
    assert any(m.startswith("Error exporting ") and "boom" in m for m in messages)
    assert capsys.readouterr().out == ""


def test_unsupported_parameter_file_raises(fake_openscad, tmp_path):
    bad = tmp_path / "params.yaml"
    bad.write_text("x: 1")

    with pytest.raises(ValueError, match=r"Unsupported parameter file format: \.yaml"):
        batch_export(SCAD, str(bad), str(tmp_path / "o"), fake_openscad, "binstl", None, True)


def test_invalid_selection_raises(fake_openscad, params_csv, tmp_path):
    with pytest.raises(ValueError, match="out of range"):
        batch_export(SCAD, params_csv, str(tmp_path / "o"), fake_openscad, "binstl", "0-9", True)


def test_bad_parameter_is_a_per_case_failure_and_batch_continues(fake_openscad, tmp_path):
    csv = tmp_path / "p.csv"
    csv.write_text('exported_filename,pts\ngood,"[1,2,3]"\nbad,"[1,2"\nalso_good,"[4]"\n')
    out = tmp_path / "o"

    result = batch_export(SCAD, str(csv), str(out), fake_openscad, "binstl", None, True)

    assert [r.ok for r in result.results] == [True, False, True]
    bad = result.failures[0]
    assert bad.returncode is None
    assert "Parameter 'pts'" in bad.stderr and "missing ']'" in bad.stderr
    assert (out / "also_good.stl").exists()


def test_missing_openscad_fails_before_any_case_runs(params_csv, tmp_path):
    from openscad_export import OpenSCADNotFound

    out = tmp_path / "never-created"
    with pytest.raises(OpenSCADNotFound):
        batch_export(SCAD, params_csv, str(out), "/nope/openscad", "binstl", None, True)
    assert not out.exists()


def test_engine_detection_is_logged(fake_openscad, params_csv, tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="openscad_export"):
        batch_export(SCAD, params_csv, str(tmp_path / "o"), fake_openscad, "binstl", None, True)

    assert f"Using OpenSCAD version 2021.01 at {fake_openscad}" in caplog.text


@pytest.fixture
def params_json(tmp_path):
    p = tmp_path / "params.json"
    p.write_text(
        '{"fileFormatVersion": "1", "parameterSets": {'
        '"first": {"size": "5", "fail": "false"}, '
        '"second": {"size": "7", "fail": "true"}, '
        '"Third Größe": {"size": "9"}}}'
    )
    return str(p)


def test_customizer_json_is_passed_natively_with_p_and_P(
    fake_openscad, params_json, tmp_path, caplog
):
    out = tmp_path / "o"
    with caplog.at_level(logging.INFO, logger="openscad_export"):
        result = batch_export(SCAD, params_json, str(out), fake_openscad, "binstl", None, True)

    assert "Passing parameter sets natively with -p/-P." in caplog.text
    assert [r.ok for r in result.results] == [True, False, True]
    assert (out / "first.stl").read_text().splitlines() == ["-p", params_json, "-P", "first"]
    # the set name must reach -P untouched: a wrong name makes OpenSCAD export defaults, exit 0
    assert (out / "Third Größe.stl").read_text().splitlines() == [
        "-p",
        params_json,
        "-P",
        "Third Größe",
    ]
    assert "boom" in result.failures[0].stderr


def test_csv_is_passed_as_d_flags_never_p(fake_openscad, params_csv, tmp_path, caplog):
    out = tmp_path / "o"
    with caplog.at_level(logging.INFO, logger="openscad_export"):
        batch_export(SCAD, params_csv, str(out), fake_openscad, "binstl", None, True)

    assert "Passing parameters as -D flags." in caplog.text
    lines = (out / "first.stl").read_text().splitlines()
    assert lines == ["-Dsize=5", "-Dfail=false"]
    assert "-p" not in lines


def test_json_falls_back_to_d_flags_on_an_engine_without_parameter_sets(
    fake_openscad, params_json, tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv("FAKE_OPENSCAD_VERSION", "2015.03")
    out = tmp_path / "o"
    with caplog.at_level(logging.INFO, logger="openscad_export"):
        result = batch_export(SCAD, params_json, str(out), fake_openscad, "binstl", None, True)

    assert "Passing parameters as -D flags." in caplog.text
    assert (out / "first.stl").read_text().splitlines() == ["-Dsize=5", "-Dfail=false"]
    assert [r.ok for r in result.results] == [True, False, True]


def test_parameter_file_may_be_a_path_object(fake_openscad, params_json, tmp_path):
    from pathlib import Path

    result = batch_export(
        SCAD, Path(params_json), str(tmp_path / "o"), fake_openscad, "binstl", None, True
    )

    assert [r.ok for r in result.results] == [True, False, True]


def test_a_case_never_gets_both_p_and_d(fake_openscad, params_json, params_csv, tmp_path):
    for source in (params_json, params_csv):
        out = tmp_path / ("out_" + os.path.basename(source))
        batch_export(SCAD, source, str(out), fake_openscad, "binstl", None, True)
        lines = (out / "first.stl").read_text().splitlines()
        assert ("-p" in lines) != any(line.startswith("-D") for line in lines)
