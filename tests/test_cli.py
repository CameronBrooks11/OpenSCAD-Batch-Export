import pytest

from openscad_export.cli import main


@pytest.fixture
def params_csv(tmp_path):
    p = tmp_path / "params.csv"
    p.write_text("exported_filename,size,fail\nok,5,false\nbad,7,true\n")
    return str(p)


def export_args(params_csv, tmp_path, fake_openscad, *extra):
    return [
        "export",
        "m.scad",
        params_csv,
        str(tmp_path / "out"),
        "--openscad_path",
        fake_openscad,
        *extra,
    ]


def test_exit_1_when_any_case_fails(fake_openscad, params_csv, tmp_path, capsys):
    code = main(export_args(params_csv, tmp_path, fake_openscad))

    out = capsys.readouterr().out
    assert code == 1
    assert "Failed exports: 1" in out
    assert "Exported: " in out  # progress lines still reach stdout


def test_exit_0_when_every_case_succeeds(fake_openscad, params_csv, tmp_path):
    code = main(export_args(params_csv, tmp_path, fake_openscad, "--select", "0"))

    assert code == 0


def test_invalid_selection_is_reported_on_stderr(fake_openscad, params_csv, tmp_path, capsys):
    code = main(export_args(params_csv, tmp_path, fake_openscad, "--select", "5"))

    captured = capsys.readouterr()
    assert code == 1
    assert "Error: " in captured.err and "out of range" in captured.err


def test_conversion_logs_to_stdout_and_exits_0(tmp_path, params_csv, capsys):
    out = tmp_path / "p.json"

    code = main(["csv2json", params_csv, str(out)])

    assert code == 0
    assert out.exists()
    assert "Converted" in capsys.readouterr().out


def test_verbose_shows_the_openscad_command_line(fake_openscad, params_csv, tmp_path, capsys):
    main(["-v", *export_args(params_csv, tmp_path, fake_openscad, "--select", "0")])
    verbose_out = capsys.readouterr().out
    main(export_args(params_csv, tmp_path, fake_openscad, "--select", "0"))
    quiet_out = capsys.readouterr().out

    assert "Running command: " in verbose_out and "-Dsize=5" in verbose_out
    assert "Running command: " not in quiet_out
