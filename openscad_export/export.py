"""Compatibility shim.

The implementation moved to :mod:`openscad_export.params`, :mod:`openscad_export.runner`
and :mod:`openscad_export.cli`. This module re-exports the old names so existing imports
and ``python -m openscad_export.export`` keep working.
"""

from openscad_export.cli import main, parse_arguments
from openscad_export.params import (
    construct_d_flags,
    csv_to_json,
    json_to_csv,
    parse_selection,
    read_csv,
    read_json,
)
from openscad_export.runner import batch_export, ensure_output_folder, export_stl

__all__ = [
    "batch_export",
    "construct_d_flags",
    "csv_to_json",
    "ensure_output_folder",
    "export_stl",
    "json_to_csv",
    "main",
    "parse_arguments",
    "parse_selection",
    "read_csv",
    "read_json",
]

if __name__ == "__main__":
    main()
