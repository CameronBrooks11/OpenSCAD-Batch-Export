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

    lines = (out / "first.stl").read_text().splitlines()
    assert lines == ["--export-format=binstl", "-Dsize=5", "-Dfail=false"]


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
    first = (out / "first.stl").read_text().splitlines()
    assert first == ["--export-format=binstl", "-p", params_json, "-P", "first"]
    # the set name must reach -P untouched: a wrong name makes OpenSCAD export defaults, exit 0
    third = (out / "Third Größe.stl").read_text().splitlines()
    assert third == ["--export-format=binstl", "-p", params_json, "-P", "Third Größe"]
    assert "boom" in result.failures[0].stderr


def test_csv_is_passed_as_d_flags_never_p(fake_openscad, params_csv, tmp_path, caplog):
    out = tmp_path / "o"
    with caplog.at_level(logging.INFO, logger="openscad_export"):
        batch_export(SCAD, params_csv, str(out), fake_openscad, "binstl", None, True)

    assert "Passing parameters as -D flags." in caplog.text
    lines = (out / "first.stl").read_text().splitlines()
    assert lines == ["--export-format=binstl", "-Dsize=5", "-Dfail=false"]
    assert "-p" not in lines


def test_json_falls_back_to_d_flags_on_an_engine_without_parameter_sets(
    fake_openscad, params_json, tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv("FAKE_OPENSCAD_VERSION", "2015.03")
    out = tmp_path / "o"
    with caplog.at_level(logging.INFO, logger="openscad_export"):
        result = batch_export(SCAD, params_json, str(out), fake_openscad, "binstl", None, True)

    assert "Passing parameters as -D flags." in caplog.text
    lines = (out / "first.stl").read_text().splitlines()
    assert lines == ["--export-format=binstl", "-Dsize=5", "-Dfail=false"]
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


@pytest.mark.parametrize("sequential", [True, False])
def test_every_case_is_exported_in_every_format_in_order(
    fake_openscad, params_csv, tmp_path, sequential
):
    out = tmp_path / "o"

    result = batch_export(
        SCAD,
        params_csv,
        str(out),
        fake_openscad,
        "binstl",
        None,
        sequential,
        formats=["stl", "png"],
    )

    assert [(r.name, r.format) for r in result.results] == [
        ("first", "stl"),
        ("first", "png"),
        ("second", "stl"),
        ("second", "png"),
        ("third", "stl"),
        ("third", "png"),
    ]
    assert (out / "first.png").exists() and (out / "third.stl").exists()
    assert [r.ok for r in result.results] == [True, True, False, False, True, True]


def test_export_format_flag_only_applies_to_stl(fake_openscad, params_csv, tmp_path):
    out = tmp_path / "o"
    batch_export(
        SCAD, params_csv, str(out), fake_openscad, "asciistl", "0", True, formats=["stl", "off"]
    )

    assert (out / "first.stl").read_text().splitlines()[0] == "--export-format=asciistl"
    assert not (out / "first.off").read_text().startswith("--export-format")


def test_unlisted_formats_are_warned_about_not_refused(fake_openscad, params_csv, tmp_path, caplog):
    out = tmp_path / "o"
    with caplog.at_level(logging.WARNING, logger="openscad_export"):
        result = batch_export(
            SCAD,
            params_csv,
            str(out),
            fake_openscad,
            "binstl",
            "0",
            True,
            formats=["xyz", "abc", "off"],
        )

    assert (
        "xyz, abc not listed by OpenSCAD 2021.01, which advertises: 3mf, csg, off, png, stl"
        in caplog.text
    )
    # the engine itself decides: the fake refuses unknown suffixes, so those cases fail
    assert [(r.format, r.ok) for r in result.results] == [
        ("xyz", False),
        ("abc", False),
        ("off", True),
    ]
    assert "Unknown suffix" in result.failures[0].stderr


def test_duplicate_formats_collapse_to_one_export(fake_openscad, params_csv, tmp_path):
    result = batch_export(
        SCAD,
        params_csv,
        str(tmp_path / "o"),
        fake_openscad,
        "binstl",
        "0",
        False,
        formats=["stl", "STL", ".stl"],
    )
    assert [r.format for r in result.results] == ["stl"]


def test_no_warning_when_the_engine_list_is_unknown(
    fake_openscad, params_csv, tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv("FAKE_OPENSCAD_FORMATS", "none")
    with caplog.at_level(logging.WARNING, logger="openscad_export"):
        result = batch_export(
            SCAD,
            params_csv,
            str(tmp_path / "o"),
            fake_openscad,
            "binstl",
            "0",
            True,
            formats=["wrl"],
        )
    assert result.results[0].format == "wrl" and result.results[0].ok
    assert "not listed" not in caplog.text


def test_format_is_normalised(fake_openscad, params_csv, tmp_path):
    result = batch_export(
        SCAD, params_csv, str(tmp_path / "o"), fake_openscad, "binstl", "0", True, formats=[".PNG"]
    )
    assert result.results[0].output_path.endswith("first.png")


def test_image_options_are_passed_through(fake_openscad, params_csv, tmp_path):
    out = tmp_path / "o"
    batch_export(
        SCAD,
        params_csv,
        str(out),
        fake_openscad,
        "binstl",
        "0",
        True,
        formats=["png"],
        image_options={"camera": "0,0,0,55,0,25,140", "imgsize": "640,480", "colorscheme": None},
    )

    lines = (out / "first.png").read_text().splitlines()
    assert "--camera=0,0,0,55,0,25,140" in lines and "--imgsize=640,480" in lines
    assert not any(line.startswith("--colorscheme") for line in lines)


def test_unknown_image_option_is_rejected(fake_openscad, params_csv, tmp_path):
    with pytest.raises(ValueError, match="Unknown image option"):
        batch_export(
            SCAD,
            params_csv,
            str(tmp_path / "o"),
            fake_openscad,
            "binstl",
            None,
            True,
            image_options={"projection": "ortho"},
        )


def probe_lines(log_path):
    """All lines from the fake engine's per-process probe logs (log_path.<pid>)."""
    lines = []
    for part in sorted(log_path.parent.glob(log_path.name + ".*")):
        lines += part.read_text().splitlines()
    return lines


def max_concurrent(log_path):
    """Peak number of fake OpenSCAD processes alive at once, from its start/end logs."""
    events = []
    for line in probe_lines(log_path):
        kind, stamp, _pid = line.split()
        if kind == "term":
            continue
        events.append((float(stamp), 1 if kind == "start" else -1))
    peak = alive = 0
    for _, delta in sorted(events):
        alive += delta
        peak = max(peak, alive)
    return peak


@pytest.fixture
def four_cases(tmp_path):
    p = tmp_path / "four.csv"
    p.write_text("exported_filename,size\na,1\nb,2\nc,3\nd,4\n")
    return str(p)


@pytest.mark.parametrize("jobs", [1, 2])
def test_jobs_bounds_how_many_openscad_processes_run_at_once(
    fake_openscad, four_cases, tmp_path, monkeypatch, jobs
):
    log_path = tmp_path / "probe.log"
    monkeypatch.setenv("FAKE_OPENSCAD_LOG", str(log_path))
    # Long enough that process start-up jitter (slow on Windows runners) cannot hide the overlap.
    monkeypatch.setenv("FAKE_OPENSCAD_SLEEP", "1.0")

    result = batch_export(
        SCAD, four_cases, str(tmp_path / "o"), fake_openscad, "binstl", None, False, jobs=jobs
    )

    assert [r.name for r in result.results] == ["a", "b", "c", "d"]
    assert max_concurrent(log_path) == jobs


def test_jobs_defaults_to_cpu_count(fake_openscad, params_csv, tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="openscad_export"):
        batch_export(SCAD, params_csv, str(tmp_path / "o"), fake_openscad, "binstl", None, False)

    expected = os.cpu_count() or 1
    if expected == 1:
        assert "Running exports sequentially." in caplog.text
    else:
        assert f"Running exports with up to {expected} parallel jobs." in caplog.text


def test_sequential_forces_one_job(fake_openscad, params_csv, tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="openscad_export"):
        batch_export(
            SCAD, params_csv, str(tmp_path / "o"), fake_openscad, "binstl", None, True, jobs=8
        )

    assert "Running exports sequentially." in caplog.text


@pytest.mark.parametrize("jobs", [0, -1, "2", 2.0, True])
def test_invalid_jobs_is_rejected_before_anything_runs(fake_openscad, params_csv, tmp_path, jobs):
    with pytest.raises(ValueError, match="jobs must be a positive integer"):
        batch_export(
            SCAD, params_csv, str(tmp_path / "o"), fake_openscad, "binstl", None, False, jobs=jobs
        )
    assert not (tmp_path / "o").exists()


@pytest.mark.skipif(os.name == "nt", reason="SIGINT delivery to self is POSIX-specific")
@pytest.mark.parametrize("jobs", [1, 2])
def test_interrupt_terminates_running_openscad_and_skips_the_rest(
    fake_openscad, four_cases, tmp_path, monkeypatch, jobs
):
    import signal
    import threading
    import time

    log_path = tmp_path / "probe.log"
    monkeypatch.setenv("FAKE_OPENSCAD_LOG", str(log_path))
    monkeypatch.setenv("FAKE_OPENSCAD_SLEEP", "10")
    monkeypatch.setenv("FAKE_OPENSCAD_PARTIAL", "1")  # a partial output must not survive
    threading.Timer(0.5, os.kill, args=(os.getpid(), signal.SIGINT)).start()
    started = time.monotonic()

    with pytest.raises(KeyboardInterrupt):
        batch_export(
            SCAD, four_cases, str(tmp_path / "o"), fake_openscad, "binstl", None, False, jobs=jobs
        )

    assert time.monotonic() - started < 5, "children were not terminated promptly"
    time.sleep(0.5)  # let the SIGTERM handlers in the children write their line
    lines = probe_lines(log_path)
    assert sum(line.startswith("start") for line in lines) == jobs  # only the running ones began
    assert (
        sum(line.startswith("term") for line in lines) == jobs
    )  # and every one of them was killed
    assert not any(line.startswith("end") for line in lines)  # none finished its 10 s sleep
    assert list((tmp_path / "o").iterdir()) == []  # no outputs, no .part leftovers


def test_process_registered_after_an_interrupt_is_terminated_on_arrival():
    """A worker that was between picking up its task and spawning OpenSCAD when the
    interrupt fired must not be left running to completion."""
    import subprocess
    import sys

    from openscad_export import runner

    registry = runner._ActiveProcesses()
    registry.terminate_all()
    late = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        registry.add(late)
        assert late.wait(timeout=5) != 0
    finally:
        if late.poll() is None:
            late.kill()
    registry.reset()
    assert registry.closed is False
