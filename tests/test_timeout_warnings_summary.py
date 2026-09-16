import json
import logging
import time

import pytest

from openscad_export import batch_export
from openscad_export.cli import main

SCAD = "model.scad"


@pytest.fixture
def params_csv(tmp_path):
    p = tmp_path / "params.csv"
    p.write_text("exported_filename,size,fail\nfirst,5,false\nsecond,7,true\n")
    return str(p)


def run(fake_openscad, params_csv, out, **kwargs):
    return batch_export(SCAD, params_csv, str(out), fake_openscad, "binstl", None, True, **kwargs)


def cli_args(params_csv, tmp_path, fake_openscad, *extra):
    return [
        "export",
        SCAD,
        params_csv,
        str(tmp_path / "out"),
        "--openscad-path",
        fake_openscad,
        *extra,
    ]


# --- timeout -------------------------------------------------------------------------


def test_timed_out_case_is_a_failure_and_the_batch_continues(fake_openscad, tmp_path, monkeypatch):
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,size\nslow,1\nquick,2\n")
    monkeypatch.setenv("FAKE_OPENSCAD_SLEEP", "5")
    monkeypatch.setenv("FAKE_OPENSCAD_PARTIAL", "1")
    started = time.monotonic()

    result = batch_export(
        SCAD, str(csv), str(tmp_path / "o"), fake_openscad, "binstl", "0", True, timeout=0.5
    )

    assert time.monotonic() - started < 4, "the timeout did not kill the process"
    (slow,) = result.results
    assert slow.timed_out is True and slow.ok is False and slow.status == "timeout"
    assert slow.stderr == "Timed out after 0.5 s"
    assert slow.returncode not in (None, 0)  # the process was killed
    assert list((tmp_path / "o").iterdir()) == []  # no partial output left behind
    assert result.failures == [slow]


def test_timeout_leaves_fast_cases_alone(fake_openscad, params_csv, tmp_path):
    result = run(fake_openscad, params_csv, tmp_path / "o", timeout=30)

    assert [r.status for r in result.results] == ["ok", "failed"]
    assert not any(r.timed_out for r in result.results)


@pytest.mark.parametrize("timeout", [0, -1, "5", True])
def test_invalid_timeout_is_rejected_before_anything_runs(
    fake_openscad, params_csv, tmp_path, timeout
):
    with pytest.raises(ValueError, match="timeout must be a positive number"):
        run(fake_openscad, params_csv, tmp_path / "o", timeout=timeout)
    assert not (tmp_path / "o").exists()


def test_timed_out_case_is_reported_in_the_summary_text(fake_openscad, tmp_path, monkeypatch):
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,size\nslow,1\n")
    monkeypatch.setenv("FAKE_OPENSCAD_SLEEP", "5")

    result = batch_export(
        SCAD, str(csv), str(tmp_path / "o"), fake_openscad, "binstl", None, True, timeout=0.3
    )

    assert "slow.stl: Timed out after 0.3 s" in result.summary()


# --- warnings ------------------------------------------------------------------------


def test_diagnostic_lines_are_captured_on_success(fake_openscad, params_csv, tmp_path, monkeypatch):
    monkeypatch.setenv(
        "FAKE_OPENSCAD_STDERR",
        "Compiling design (CSG Tree generation)...|ECHO: size = 5|WARNING: variable x is unused"
        "|DEPRECATED: old thing|Geometries in cache: 1",
    )

    result = run(fake_openscad, params_csv, tmp_path / "o")

    first = result.results[0]
    assert first.ok and first.stderr == ""  # success still blanks raw stderr
    assert first.warnings == [
        "ECHO: size = 5",
        "WARNING: variable x is unused",
        "DEPRECATED: old thing",
    ]
    assert "OpenSCAD warnings/echo output from 2 case(s):" in result.summary()
    assert "      WARNING: variable x is unused" in result.summary()


def test_no_warnings_means_no_warnings_section(fake_openscad, params_csv, tmp_path):
    result = run(fake_openscad, params_csv, tmp_path / "o")

    assert all(r.warnings == [] for r in result.results)
    assert "OpenSCAD warnings" not in result.summary()


def test_warnings_are_captured_on_failure_too(fake_openscad, params_csv, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_OPENSCAD_STDERR", "WARNING: about to fail")

    result = run(fake_openscad, params_csv, tmp_path / "o")

    # the fake writes its diagnostics before checking fail=true, so the failing case has both
    failed = result.failures[0]
    assert failed.warnings == ["WARNING: about to fail"]
    assert "boom" in failed.stderr


# --- JSON summary --------------------------------------------------------------------


def test_to_dict_records_engine_inputs_and_every_case(
    fake_openscad, params_csv, tmp_path, monkeypatch
):
    monkeypatch.setenv("FAKE_OPENSCAD_STDERR", "ECHO: hi")
    out = tmp_path / "o"
    out.mkdir()
    (out / "first.png").write_text("present")

    result = run(
        fake_openscad, params_csv, out, formats=["stl", "png"], skip_existing=True, timeout=30
    )
    doc = result.to_dict()

    assert doc["openscad"] == {"path": fake_openscad, "version": "2021.01"}
    assert doc["inputs"]["scad_file"] == SCAD
    assert doc["inputs"]["parameter_file"] == params_csv
    assert doc["inputs"]["formats"] == ["stl", "png"]
    assert doc["inputs"]["jobs"] == 1 and doc["inputs"]["timeout"] == 30
    assert doc["inputs"]["skip_existing"] is True
    assert doc["dry_run"] is False
    assert doc["counts"] == {"ok": 1, "failed": 2, "skipped": 1}
    statuses = [(r["name"], r["format"], r["status"]) for r in doc["results"]]
    assert statuses == [
        ("first", "stl", "ok"),
        ("first", "png", "skipped"),
        ("second", "stl", "failed"),
        ("second", "png", "failed"),
    ]
    ok = doc["results"][0]
    assert ok["returncode"] == 0 and ok["warnings"] == ["ECHO: hi"] and ok["stderr"] == ""
    assert ok["command"][0] == fake_openscad and ok["command"][-1] == SCAD
    assert isinstance(ok["duration"], float)
    skipped = doc["results"][1]
    assert skipped["returncode"] is None and skipped["command"] is None
    failed = doc["results"][2]
    assert failed["returncode"] == 1 and "boom" in failed["stderr"]
    json.dumps(doc)  # serialisable


def test_write_summary_round_trips_through_json(fake_openscad, params_csv, tmp_path):
    result = run(fake_openscad, params_csv, tmp_path / "o")
    path = tmp_path / "summary.json"

    result.write_summary(path)

    assert json.loads(path.read_text(encoding="utf-8")) == result.to_dict()
    assert path.read_text().endswith("}\n")


def test_dry_run_summary_marks_cases_as_dry_run(fake_openscad, params_csv, tmp_path):
    result = run(fake_openscad, params_csv, tmp_path / "o", dry_run=True)
    doc = result.to_dict()

    assert doc["dry_run"] is True
    assert [r["status"] for r in doc["results"]] == ["dry-run", "dry-run"]
    assert all(r["command"] for r in doc["results"])


# --- CLI -----------------------------------------------------------------------------


def test_cli_timeout_flag(fake_openscad, tmp_path, monkeypatch, capsys):
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,size\nslow,1\n")
    monkeypatch.setenv("FAKE_OPENSCAD_SLEEP", "5")

    code = main(cli_args(str(csv), tmp_path, fake_openscad, "--timeout", "0.3"))

    assert code == 1
    assert "Timed out after 0.3 s" in capsys.readouterr().out


def test_cli_summary_flag_writes_the_json_record(fake_openscad, params_csv, tmp_path, capsys):
    summary = tmp_path / "run.json"

    code = main(cli_args(params_csv, tmp_path, fake_openscad, "--summary", str(summary)))

    assert code == 1  # one case fails; the summary is still written
    doc = json.loads(summary.read_text())
    assert doc["counts"] == {"ok": 1, "failed": 1, "skipped": 0}
    assert doc["openscad"]["version"] == "2021.01"
    assert f"Summary written to {summary}" in capsys.readouterr().out


def test_cli_summary_is_written_for_a_dry_run_too(fake_openscad, params_csv, tmp_path):
    summary = tmp_path / "run.json"

    main(cli_args(params_csv, tmp_path, fake_openscad, "--dry-run", "--summary", str(summary)))

    doc = json.loads(summary.read_text())
    assert doc["dry_run"] is True and doc["counts"]["ok"] == 2


def test_warnings_are_logged_per_case(fake_openscad, params_csv, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("FAKE_OPENSCAD_STDERR", "WARNING: careful")

    with caplog.at_level(logging.WARNING, logger="openscad_export"):
        run(fake_openscad, params_csv, tmp_path / "o")

    assert "first.stl: WARNING: careful" in caplog.text
