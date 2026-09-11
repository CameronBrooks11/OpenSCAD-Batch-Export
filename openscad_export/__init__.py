"""Batch export models from parametric OpenSCAD designs using CSV or Customizer JSON
parameter sets."""

import logging

from openscad_export.params import (
    ScadRange,
    coerce_cell,
    construct_d_flags,
    csv_to_json,
    json_to_csv,
    parse_selection,
    read_csv,
    read_json,
    read_parameters,
    to_scad_literal,
)
from openscad_export.runner import BatchResult, ExportResult, batch_export

# Library consumers configure logging themselves; without this, ERROR records would
# reach stderr through logging.lastResort.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "BatchResult",
    "ExportResult",
    "ScadRange",
    "batch_export",
    "coerce_cell",
    "construct_d_flags",
    "csv_to_json",
    "json_to_csv",
    "parse_selection",
    "read_csv",
    "read_json",
    "read_parameters",
    "to_scad_literal",
]
