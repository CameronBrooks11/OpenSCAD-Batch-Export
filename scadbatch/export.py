"""Compatibility shim.

The implementation moved to :mod:`scadbatch.params`, :mod:`scadbatch.runner`
and :mod:`scadbatch.cli`. This module re-exports the old names so existing imports
and ``python -m scadbatch.export`` keep working.
"""

import sys

from scadbatch.cli import main, parse_arguments
from scadbatch.params import (
    construct_d_flags,
    csv_to_json,
    json_to_csv,
    parse_selection,
    read_csv,
    read_json,
    read_parameters,
)
from scadbatch.runner import (
    BatchResult,
    ExportResult,
    batch_export,
    ensure_output_folder,
    export_stl,
)

__all__ = [
    "BatchResult",
    "ExportResult",
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
    "read_parameters",
]

if __name__ == "__main__":
    sys.exit(main())
