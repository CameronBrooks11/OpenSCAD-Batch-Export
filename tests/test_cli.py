import os

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


def test_missing_openscad_is_a_clean_error(params_csv, tmp_path, capsys):
    code = main(export_args(params_csv, tmp_path, "/nope/openscad"))

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error: OpenSCAD executable not found")
    assert "Traceback" not in captured.err


def test_hyphenated_openscad_path_flag(fake_openscad, params_csv, tmp_path):
    code = main(
        ["export", "m.scad", params_csv, str(tmp_path / "o"), "--openscad-path", fake_openscad]
    )

    assert code == 1  # one deliberately failing case in params_csv; the flag itself parsed
    assert (tmp_path / "o" / "ok.stl").exists()


def test_format_flag_repeats_and_defaults_to_stl(fake_openscad, params_csv, tmp_path):
    main(
        export_args(
            params_csv,
            tmp_path,
            fake_openscad,
            "--select",
            "0",
            "--format",
            "png",
            "--format",
            "off",
        )
    )
    main(
        [
            "export",
            "m.scad",
            params_csv,
            str(tmp_path / "default"),
            "--openscad-path",
            fake_openscad,
            "--select",
            "0",
        ]
    )

    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["ok.off", "ok.png"]
    assert [p.name for p in (tmp_path / "default").iterdir()] == ["ok.stl"]


def test_unlisted_format_warns_and_fails_per_case(fake_openscad, params_csv, tmp_path, capsys):
    code = main(
        export_args(params_csv, tmp_path, fake_openscad, "--select", "0", "--format", "xyz")
    )

    out = capsys.readouterr().out
    assert code == 1
    assert "xyz not listed by OpenSCAD 2021.01" in out
    assert "Failed exports: 1" in out


def test_image_flags_reach_openscad(fake_openscad, params_csv, tmp_path):
    main(
        export_args(
            params_csv,
            tmp_path,
            fake_openscad,
            "--select",
            "0",
            "--format",
            "png",
            "--imgsize",
            "320,240",
            "--camera",
            "0,0,0,55,0,25,140",
            "--colorscheme",
            "Tomorrow",
        )
    )

    lines = (tmp_path / "out" / "ok.png").read_text().splitlines()
    assert "--imgsize=320,240" in lines
    assert "--camera=0,0,0,55,0,25,140" in lines
    assert "--colorscheme=Tomorrow" in lines


def test_jobs_flag_is_passed_through(fake_openscad, params_csv, tmp_path, capsys):
    main(export_args(params_csv, tmp_path, fake_openscad, "-j", "2"))

    assert "Running exports with up to 2 parallel jobs." in capsys.readouterr().out


def test_sequential_is_a_deprecated_alias_for_one_job(fake_openscad, params_csv, tmp_path, capsys):
    main(export_args(params_csv, tmp_path, fake_openscad, "--sequential"))

    captured = capsys.readouterr()
    assert "Running exports sequentially." in captured.out
    assert "--sequential is deprecated; use --jobs 1" in captured.err


def test_zero_jobs_is_a_clean_error(fake_openscad, params_csv, tmp_path, capsys):
    code = main(export_args(params_csv, tmp_path, fake_openscad, "--jobs", "0"))

    assert code == 1
    assert "--jobs must be at least 1" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


@pytest.mark.skipif(os.name == "nt", reason="SIGINT delivery to self is POSIX-specific")
def test_interrupt_exits_130(fake_openscad, params_csv, tmp_path, monkeypatch, capsys):
    import signal
    import threading

    monkeypatch.setenv("FAKE_OPENSCAD_SLEEP", "10")
    threading.Timer(0.5, os.kill, args=(os.getpid(), signal.SIGINT)).start()

    code = main(export_args(params_csv, tmp_path, fake_openscad, "-j", "2"))

    assert code == 130
    assert "Interrupted." in capsys.readouterr().err
