import os
import stat
import sys
import textwrap

import pytest

FAKE_OPENSCAD = textwrap.dedent(
    """\
    import sys

    # Minimal stand-in for `openscad --version` and
    # `openscad -o OUT --export-format=F (-Dk=v ... | -p FILE -P SET) FILE`.
    # Writes the parameter arguments to OUT, one per line; exits 1 with a message if a
    # -D flag or a parameter set asks for fail=true. FAKE_OPENSCAD_VERSION overrides
    # the reported version.
    import json
    import os

    args = sys.argv[1:]
    if args == ["--version"]:
        version = os.environ.get("FAKE_OPENSCAD_VERSION", "2021.01")
        sys.stderr.write(f"OpenSCAD version {version}\\n")  # the real one prints to stderr
        sys.exit(0)
    out = args[args.index("-o") + 1]
    param_args = [a for a in args if a.startswith("-D")]
    if "-p" in args:
        sets_file, set_name = args[args.index("-p") + 1], args[args.index("-P") + 1]
        param_args += ["-p", sets_file, "-P", set_name]
        with open(sets_file) as f:
            values = json.load(f)["parameterSets"][set_name]
        if str(values.get("fail", "")).lower() == "true":
            sys.stderr.write("boom: fail requested\\n")
            sys.exit(1)
    if "-Dfail=true" in param_args:
        sys.stderr.write("boom: fail requested\\n")
        sys.exit(1)
    with open(out, "w") as f:
        f.write("\\n".join(param_args))
    """
)


@pytest.fixture
def fake_openscad(tmp_path):
    """Path to an executable that mimics OpenSCAD's CLI contract for the runner."""
    script = tmp_path / "fake_openscad.py"
    script.write_text(FAKE_OPENSCAD)
    if os.name == "nt":
        exe = tmp_path / "openscad.cmd"
        exe.write_text(f'@echo off\n"{sys.executable}" "{script}" %*\n')
    else:
        exe = tmp_path / "openscad"
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return str(exe)
