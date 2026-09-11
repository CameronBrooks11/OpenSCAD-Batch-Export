import logging

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
