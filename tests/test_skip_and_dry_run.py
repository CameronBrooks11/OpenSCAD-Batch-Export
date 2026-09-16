import logging
import os

import pytest

from openscad_export import batch_export
from openscad_export.cli import main

SCAD = "model.scad"


@pytest.fixture
def params_csv(tmp_path):
    p = tmp_path / "params.csv"
    p.write_text("exported_filename,size\nfirst,5\nsecond,7\n")
    return str(p)


def run(fake_openscad, params_csv, out, **kwargs):
    return batch_export(SCAD, params_csv, str(out), fake_openscad, "binstl", None, True, **kwargs)


def test_default_overwrites_an_existing_output(fake_openscad, params_csv, tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    stale = out / "first.stl"
    stale.write_text("stale")

    result = run(fake_openscad, params_csv, out)

    assert stale.read_text() != "stale"  # re-rendered
    assert result.skipped == [] and len(result.successes) == 2


def test_skip_existing_leaves_present_outputs_alone(fake_openscad, params_csv, tmp_path, caplog):
    out = tmp_path / "o"
    out.mkdir()
    stale = out / "first.stl"
    stale.write_text("stale")

    with caplog.at_level(logging.INFO, logger="openscad_export"):
        result = run(fake_openscad, params_csv, out, skip_existing=True)

    assert stale.read_text() == "stale"  # untouched
    assert (out / "second.stl").exists()  # the missing one was rendered
    assert [(r.name, r.skipped, r.ok) for r in result.results] == [
        ("first", True, True),
        ("second", False, True),
    ]
    assert result.skipped[0].returncode is None and result.skipped[0].command is None
    assert [r.name for r in result.successes] == ["second"]
    assert f"Skipped (already present): {stale}" in caplog.text
    assert "Total exports attempted: 1" in result.summary()
    assert "Skipped (already present): 1" in result.summary()


def test_skip_existing_is_per_format(fake_openscad, params_csv, tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    (out / "first.stl").write_text("stale")

    result = run(fake_openscad, params_csv, out, skip_existing=True, formats=["stl", "png"])

    assert [(r.name, r.format, r.skipped) for r in result.results] == [
        ("first", "stl", True),
        ("first", "png", False),
        ("second", "stl", False),
        ("second", "png", False),
    ]


def test_skip_existing_does_not_start_openscad_for_skipped_cases(
    fake_openscad, params_csv, tmp_path, monkeypatch
):
    out = tmp_path / "o"
    out.mkdir()
    (out / "first.stl").write_text("stale")
    (out / "second.stl").write_text("stale")
    probe = tmp_path / "probe.log"
    monkeypatch.setenv("FAKE_OPENSCAD_LOG", str(probe))

    run(fake_openscad, params_csv, out, skip_existing=True)

    assert list(tmp_path.glob("probe.log.*")) == []  # the fake never ran


def test_dry_run_runs_nothing_and_creates_nothing(
    fake_openscad, params_csv, tmp_path, monkeypatch, caplog
):
    out = tmp_path / "never"
    probe = tmp_path / "probe.log"
    monkeypatch.setenv("FAKE_OPENSCAD_LOG", str(probe))

    with caplog.at_level(logging.INFO, logger="openscad_export"):
        result = run(fake_openscad, params_csv, out, dry_run=True)

    assert not out.exists()
    assert list(tmp_path.glob("probe.log.*")) == []
    assert result.dry_run is True
    assert [r.ok for r in result.results] == [True, True]
    first = result.results[0]
    assert first.command == [
        fake_openscad,
        "-o",
        str(out / "first.stl"),
        "--export-format=binstl",
        "-Dsize=5",
        SCAD,
    ]
    assert f"Would run: {' '.join(first.command)}" in caplog.text
    assert result.summary().startswith("Dry run: 2 export(s) would run.")
    assert str(out / "second.stl") in result.summary()


def test_dry_run_still_reports_a_bad_parameter(fake_openscad, tmp_path):
    csv = tmp_path / "p.csv"
    csv.write_text('exported_filename,pts\ngood,"[1,2]"\nbad,"[1,2"\n')

    result = run(fake_openscad, str(csv), tmp_path / "o", dry_run=True)

    assert [r.ok for r in result.results] == [True, False]
    assert "Would fail before running: 1" in result.summary()
    assert "Parameter 'pts'" in result.failures[0].stderr


def test_dry_run_with_skip_existing_reports_both(fake_openscad, params_csv, tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    (out / "first.stl").write_text("stale")

    result = run(fake_openscad, params_csv, out, dry_run=True, skip_existing=True)

    assert [(r.name, r.skipped) for r in result.results] == [("first", True), ("second", False)]
    assert "Dry run: 1 export(s) would run." in result.summary()
    assert "Skipped (already present): 1" in result.summary()


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


def test_cli_skip_existing(fake_openscad, params_csv, tmp_path, capsys):
    out = tmp_path / "out"
    out.mkdir()
    (out / "first.stl").write_text("stale")

    code = main(cli_args(params_csv, tmp_path, fake_openscad, "--skip-existing"))

    assert code == 0
    assert (out / "first.stl").read_text() == "stale"
    assert "Skipped (already present): 1" in capsys.readouterr().out


def test_cli_overwrite_is_the_default_and_explicit(fake_openscad, params_csv, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "first.stl").write_text("stale")

    main(cli_args(params_csv, tmp_path, fake_openscad, "--overwrite"))
    assert (out / "first.stl").read_text() != "stale"

    (out / "first.stl").write_text("stale")
    main(cli_args(params_csv, tmp_path, fake_openscad))
    assert (out / "first.stl").read_text() != "stale"


def test_cli_overwrite_and_skip_existing_are_mutually_exclusive(
    fake_openscad, params_csv, tmp_path
):
    with pytest.raises(SystemExit) as info:
        main(cli_args(params_csv, tmp_path, fake_openscad, "--overwrite", "--skip-existing"))
    assert info.value.code == 2


@pytest.mark.parametrize("flag", ["--dry-run", "-n"])
def test_cli_dry_run_prints_commands_and_exits_0(fake_openscad, params_csv, tmp_path, capsys, flag):
    code = main(cli_args(params_csv, tmp_path, fake_openscad, flag))

    out = capsys.readouterr().out
    assert code == 0
    assert not (tmp_path / "out").exists()
    assert out.count("Would run: ") == 2
    assert (
        f"-o {os.path.join(tmp_path, 'out', 'second.stl')} --export-format=binstl -Dsize=7 {SCAD}"
        in out
    )
    assert "Dry run: 2 export(s) would run." in out
