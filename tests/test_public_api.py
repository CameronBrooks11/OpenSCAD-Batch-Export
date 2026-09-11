import openscad_export
from openscad_export import cli, export, params, runner


def test_package_exposes_the_documented_api():
    for name in openscad_export.__all__:
        assert callable(getattr(openscad_export, name)), name
    assert openscad_export.batch_export is runner.batch_export
    assert openscad_export.parse_selection is params.parse_selection


def test_legacy_export_module_still_exposes_every_old_name():
    legacy = {
        "batch_export": runner.batch_export,
        "construct_d_flags": params.construct_d_flags,
        "csv_to_json": params.csv_to_json,
        "ensure_output_folder": runner.ensure_output_folder,
        "export_stl": runner.export_stl,
        "json_to_csv": params.json_to_csv,
        "main": cli.main,
        "parse_arguments": cli.parse_arguments,
        "parse_selection": params.parse_selection,
        "read_csv": params.read_csv,
        "read_json": params.read_json,
    }
    assert set(export.__all__) == set(legacy)
    for name, target in legacy.items():
        assert getattr(export, name) is target, name
