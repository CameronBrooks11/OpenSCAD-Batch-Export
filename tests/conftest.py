import os
import stat
import sys
import textwrap

import pytest

FAKE_OPENSCAD = textwrap.dedent(
    """\
    import sys

    # Minimal stand-in for `openscad -o OUT --export-format=F -Dk=v ... FILE`.
    # Writes the parameter flags to OUT; exits 1 with a message if any -D sets fail=true.
    args = sys.argv[1:]
    out = args[args.index("-o") + 1]
    d_flags = [a for a in args if a.startswith("-D")]
    if "-Dfail=true" in d_flags:
        sys.stderr.write("boom: fail requested\\n")
        sys.exit(1)
    with open(out, "w") as f:
        f.write("\\n".join(d_flags))
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
