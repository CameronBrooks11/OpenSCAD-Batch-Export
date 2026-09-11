"""End-to-end tests that drive the CLI against a real OpenSCAD executable.

Skipped as a whole when `openscad` is not on PATH.
"""

import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("openscad") is None, reason="openscad not on PATH")

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
SIMPLE_CUBE = EXAMPLES / "simpleCube"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "openscad_export.export", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def read_stl(path):
    """Return (triangle_count, max_coordinate) for a binary or ASCII STL."""
    data = path.read_bytes()
    if data.startswith(b"solid") and b"facet normal" in data[:512]:
        text = data.decode()
        coords = [
            float(v)
            for line in text.splitlines()
            if line.strip().startswith("vertex")
            for v in line.split()[1:]
        ]
        return text.count("facet normal"), max(coords)
    (count,) = struct.unpack_from("<I", data, 80)
    assert len(data) == 84 + 50 * count, f"binary STL length mismatch in {path.name}"
    max_coord = float("-inf")
    for i in range(count):
        values = struct.unpack_from("<12f", data, 84 + 50 * i)
        max_coord = max(max_coord, *values[3:])  # skip the normal
    return count, max_coord


CUBES = {"cube_small": 10, "cube_medium": 20, "cube_large": 30}


@pytest.mark.parametrize("parameter_file", ["simpleCube.csv", "simpleCube.json"])
def test_exports_every_parameter_set_as_valid_stl(parameter_file, tmp_path):
    result = run_cli(
        "export", SIMPLE_CUBE / "simpleCube.scad", SIMPLE_CUBE / parameter_file, tmp_path
    )

    assert result.returncode == 0, result.stderr
    assert sorted(p.stem for p in tmp_path.glob("*.stl")) == sorted(CUBES)
    for name, size in CUBES.items():
        triangles, max_coord = read_stl(tmp_path / f"{name}.stl")
        assert triangles == 12, name
        assert max_coord == pytest.approx(size), name


def test_sequential_matches_parallel(tmp_path):
    parallel, sequential = tmp_path / "par", tmp_path / "seq"
    run_cli("export", SIMPLE_CUBE / "simpleCube.scad", SIMPLE_CUBE / "simpleCube.csv", parallel)
    run_cli(
        "export",
        SIMPLE_CUBE / "simpleCube.scad",
        SIMPLE_CUBE / "simpleCube.csv",
        sequential,
        "--sequential",
    )

    for name in CUBES:
        assert (parallel / f"{name}.stl").read_bytes() == (sequential / f"{name}.stl").read_bytes()


def test_ascii_stl_format(tmp_path):
    run_cli(
        "export",
        SIMPLE_CUBE / "simpleCube.scad",
        SIMPLE_CUBE / "simpleCube.csv",
        tmp_path,
        "--export_format",
        "asciistl",
    )

    out = tmp_path / "cube_small.stl"
    assert out.read_bytes().startswith(b"solid")
    assert read_stl(out) == (12, pytest.approx(10))


def test_select_limits_which_sets_are_exported(tmp_path):
    result = run_cli(
        "export",
        SIMPLE_CUBE / "simpleCube.scad",
        SIMPLE_CUBE / "simpleCube.csv",
        tmp_path,
        "--select",
        "0,2",
    )

    assert result.returncode == 0, result.stderr
    assert sorted(p.stem for p in tmp_path.glob("*.stl")) == ["cube_large", "cube_small"]


def test_failing_case_does_not_stop_the_batch(tmp_path):
    scad = tmp_path / "guarded.scad"
    scad.write_text('size = 1;\nassert(size > 0, "size must be positive");\ncube(size);\n')
    params = tmp_path / "params.csv"
    params.write_text("exported_filename,size\ngood,5\nbad,-1\n")
    out = tmp_path / "out"

    result = run_cli("export", scad, params, out)

    assert result.returncode == 1
    assert (out / "good.stl").exists()
    assert not (out / "bad.stl").exists()
    assert "Successful exports: 1" in result.stdout
    assert "Failed exports: 1" in result.stdout
    assert "size must be positive" in result.stdout


def test_literal_serialization_survives_openscad(tmp_path):
    """Values with quotes, backslashes, nested vectors, exponents and undef reach the model
    intact; the model asserts on every one of them."""
    scad = tmp_path / "check.scad"
    scad.write_text(
        'label = "x"; pts = [0]; code = "0"; n = 0; tiny = 1; path = "p"; maybe = 1;\n'
        'assert(label == "say \\"hi\\"", str("label=", label));\n'
        'assert(pts == [1, [2, 3], "a b"], str("pts=", pts));\n'
        'assert(code == "007", str("code=", code));\n'
        'assert(n == 1000, str("n=", n));\n'
        'assert(tiny == 0.00001, str("tiny=", tiny));\n'
        'assert(path == "C:\\\\dir\\\\f", str("path=", path));\n'
        'assert(maybe == undef, str("maybe=", maybe));\n'
        "cube(1);\n"
    )
    params = tmp_path / "params.csv"
    params.write_text(
        "exported_filename,label,pts,code,n,tiny,path,maybe\n"
        'ok,"say ""hi""","[1,[2,3],""a b""]","""007""",1e3,1e-05,C:\\dir\\f,undef\n'
    )

    result = run_cli("export", scad, params, tmp_path / "out")

    assert result.returncode == 0, result.stdout
    assert (tmp_path / "out" / "ok.stl").exists()
