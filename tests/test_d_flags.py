import pytest

from openscad_export.export import construct_d_flags


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, "-Dk=true"),
        (False, "-Dk=false"),
        (5, "-Dk=5"),
        (2.5, "-Dk=2.5"),
        ("true", "-Dk=true"),
        ("False", "-Dk=false"),
        ("12", "-Dk=12"),
        ("2.5", "-Dk=2.5"),
        ("hello", '-Dk="hello"'),
        ("Welcome to...", '-Dk="Welcome to..."'),
        ("[1,2,3]", "-Dk=[1,2,3]"),
        ("[[0,0],[1,1]]", "-Dk=[[0,0],[1,1]]"),
    ],
)
def test_value_serialization(value, expected):
    assert construct_d_flags({"k": value}) == [expected]


def test_exported_filename_is_not_a_parameter():
    flags = construct_d_flags({"exported_filename": "part_a", "width": 10})
    assert flags == ["-Dwidth=10"]


def test_preserves_parameter_order():
    flags = construct_d_flags({"b": 1, "a": 2, "c": 3})
    assert flags == ["-Db=1", "-Da=2", "-Dc=3"]
