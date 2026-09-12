import os
import stat
import sys

import pytest

from openscad_export import engine
from openscad_export.engine import (
    Engine,
    OpenSCADError,
    OpenSCADNotFound,
    detect_engine,
    find_openscad,
    parse_version,
)


@pytest.mark.parametrize(
    ("text", "version", "numbers"),
    [
        ("OpenSCAD version 2021.01\n", "2021.01", (2021, 1)),
        ("OpenSCAD version 2019.05", "2019.05", (2019, 5)),
        ("OpenSCAD version 2026.09.05\n", "2026.09.05", (2026, 9, 5)),
        ("noise\nOpenSCAD version 2025.03.19.nightly\n", "2025.03.19.nightly", (2025, 3, 19)),
    ],
)
def test_parse_version(text, version, numbers):
    assert parse_version(text) == (version, numbers)


@pytest.mark.parametrize("text", ["", "openscad: command not found", "OpenSCAD version dev"])
def test_unparseable_version_is_an_error(text):
    with pytest.raises(OpenSCADError):
        parse_version(text)


@pytest.mark.parametrize(
    ("numbers", "expected"),
    [((2015, 3), False), ((2019, 5), True), ((2021, 1), True), ((2026, 9, 5), True)],
)
def test_parameter_set_support_starts_at_2019_05(numbers, expected):
    assert Engine("x", ".".join(map(str, numbers)), numbers).supports_parameter_sets is expected


@pytest.fixture
def no_openscad_anywhere(monkeypatch, tmp_path):
    """PATH with nothing on it, no $OPENSCAD, and no platform default present."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.delenv(engine.ENV_VAR, raising=False)
    monkeypatch.setattr(engine, "PLATFORM_DEFAULTS", {sys.platform: [str(tmp_path / "absent")]})
    return tmp_path


def test_explicit_path_wins(fake_openscad, no_openscad_anywhere, monkeypatch):
    monkeypatch.setenv(engine.ENV_VAR, "/should/not/be/used")
    assert find_openscad(fake_openscad) == fake_openscad


def test_explicit_path_that_does_not_exist_is_an_error_not_a_fallback(fake_openscad, monkeypatch):
    monkeypatch.setenv(engine.ENV_VAR, fake_openscad)
    with pytest.raises(OpenSCADNotFound, match="--openscad-path '/nope/openscad'"):
        find_openscad("/nope/openscad")


def test_env_var_is_used_when_nothing_explicit(fake_openscad, no_openscad_anywhere, monkeypatch):
    monkeypatch.setenv(engine.ENV_VAR, fake_openscad)
    assert find_openscad() == fake_openscad


def test_env_var_that_does_not_resolve_is_an_error_even_with_path_available(
    fake_openscad, no_openscad_anywhere, monkeypatch
):
    monkeypatch.setenv("PATH", os.path.dirname(fake_openscad))
    monkeypatch.setenv(engine.ENV_VAR, "/nope/openscad")
    with pytest.raises(OpenSCADNotFound, match=r"\$OPENSCAD='/nope/openscad'"):
        find_openscad()


def test_env_var_beats_path(fake_openscad, no_openscad_anywhere, monkeypatch, tmp_path):
    other = _script(tmp_path / "other", "openscad", "import sys; sys.stderr.write('x')")
    monkeypatch.setenv("PATH", os.path.dirname(other))
    monkeypatch.setenv(engine.ENV_VAR, fake_openscad)
    assert find_openscad() == fake_openscad


def test_path_beats_platform_default(fake_openscad, no_openscad_anywhere, monkeypatch, tmp_path):
    other = _script(tmp_path / "default", "openscad", "import sys; sys.stderr.write('x')")
    monkeypatch.setenv("PATH", os.path.dirname(fake_openscad))
    monkeypatch.setattr(engine, "PLATFORM_DEFAULTS", {sys.platform: [other]})
    assert os.path.normcase(find_openscad()) == os.path.normcase(fake_openscad)


def test_existing_but_non_executable_file_is_named_as_such(tmp_path):
    plain = tmp_path / "notexec"
    plain.write_text("")
    with pytest.raises(OpenSCADNotFound, match="exists but is not executable"):
        find_openscad(str(plain))


def test_path_lookup_when_no_env_var(fake_openscad, no_openscad_anywhere, monkeypatch):
    monkeypatch.setenv("PATH", os.path.dirname(fake_openscad))
    # shutil.which on Windows returns the PATHEXT spelling of the extension (.CMD)
    assert os.path.normcase(find_openscad()) == os.path.normcase(fake_openscad)


def test_platform_default_is_last_resort(fake_openscad, no_openscad_anywhere, monkeypatch):
    monkeypatch.setattr(engine, "PLATFORM_DEFAULTS", {sys.platform: [fake_openscad]})
    assert find_openscad() == fake_openscad


def test_not_found_message_lists_what_was_tried(no_openscad_anywhere):
    with pytest.raises(OpenSCADNotFound) as info:
        find_openscad()
    message = str(info.value)
    assert "'openscad' on PATH" in message
    assert str(no_openscad_anywhere / "absent") in message
    assert "--openscad-path" in message and "$OPENSCAD" in message


def test_detect_engine_reads_the_version(fake_openscad):
    found = detect_engine(fake_openscad)
    assert found == Engine(fake_openscad, "2021.01", (2021, 1))


def _script(tmp_path, name, body):
    tmp_path.mkdir(exist_ok=True)
    script = tmp_path / f"{name}.py"
    script.write_text(body)
    if os.name == "nt":
        exe = tmp_path / f"{name}.cmd"
        exe.write_text(f'@echo off\n"{sys.executable}" "{script}" %*\n')
    else:
        exe = tmp_path / name
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return str(exe)


def test_detect_engine_rejects_a_program_that_is_not_openscad(tmp_path):
    impostor = _script(tmp_path, "impostor", "print('gcc (GCC) 14.2.0')\n")
    with pytest.raises(OpenSCADError, match="Could not parse OpenSCAD version"):
        detect_engine(impostor)


def test_detect_engine_reports_a_failing_version_call(tmp_path):
    broken = _script(tmp_path, "broken", "import sys; sys.stderr.write('bad'); sys.exit(3)\n")
    with pytest.raises(OpenSCADError, match="exited with 3: bad"):
        detect_engine(broken)
