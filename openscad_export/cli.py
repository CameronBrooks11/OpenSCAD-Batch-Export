"""Command-line interface.

Available subcommands:
- export: Batch export STL files.
- csv2json: Convert CSV parameter files to JSON.
- json2csv: Convert JSON parameter files to CSV.
- gui: Launch the graphical user interface."""

import argparse
import sys

from openscad_export.params import csv_to_json, json_to_csv
from openscad_export.runner import batch_export


def parse_arguments():
    """
    Parse and return the command-line arguments.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Batch export STL files from OpenSCAD using CSV or JSON parameters, "
            "and convert between CSV and JSON."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Sub-commands")

    # Export subcommand
    export_parser = subparsers.add_parser(
        "export", help="Export STL files from OpenSCAD using CSV or JSON parameters."
    )
    export_parser.add_argument("scad_file", help="Path to the OpenSCAD (.scad) file.")
    export_parser.add_argument(
        "parameter_file", help="Path to the CSV or JSON file containing parameters."
    )
    export_parser.add_argument("output_folder", help="Directory where STL files will be saved.")
    export_parser.add_argument(
        "--openscad_path",
        default="openscad",
        help='Path to the OpenSCAD executable. Defaults to "openscad" assuming it is in PATH.',
    )
    export_parser.add_argument(
        "--export_format",
        choices=["asciistl", "binstl"],
        default="binstl",
        help="Export format: asciistl or binstl. Defaults to binstl.",
    )
    export_parser.add_argument(
        "--select",
        type=str,
        default=None,
        help=(
            "Select specific parameter sets to export using indices and ranges. "
            "Supported formats: "
            "'0-5' (range), '1-3,7,10-12' (multiple ranges and indices), "
            "'2,4' (specific indices), "
            "'every:2 in 0-10' (every 2nd index in range), "
            "'from:5' (from index 5 onward), "
            "'up_to:4' (up to index 4 inclusive). "
            "You can combine multiple selections separated by commas. "
            "Indices are zero-based."
        ),
    )
    export_parser.add_argument(
        "--sequential",
        action="store_true",
        help="Disable parallel processing and export sequentially.",
    )

    # csv2json subcommand
    csv2json_parser = subparsers.add_parser("csv2json", help="Convert CSV parameter file to JSON.")
    csv2json_parser.add_argument("csv_file", help="Path to the CSV file.")
    csv2json_parser.add_argument("json_file", help="Path to the output JSON file.")

    # json2csv subcommand
    json2csv_parser = subparsers.add_parser("json2csv", help="Convert JSON parameter file to CSV.")
    json2csv_parser.add_argument("json_file", help="Path to the JSON file.")
    json2csv_parser.add_argument("csv_file", help="Path to the output CSV file.")

    # GUI subcommand
    subparsers.add_parser("gui", help="Launch the graphical user interface.")

    return parser.parse_args()


def main():
    """
    Entry point of the module. Parses arguments and executes the corresponding subcommand.
    """
    args = parse_arguments()

    if args.command == "export":
        batch_export(
            args.scad_file,
            args.parameter_file,
            args.output_folder,
            args.openscad_path,
            args.export_format,
            args.select,
            args.sequential,
        )
    elif args.command == "csv2json":
        csv_to_json(args.csv_file, args.json_file)
    elif args.command == "json2csv":
        json_to_csv(args.json_file, args.csv_file)
    elif args.command == "gui":
        try:
            from . import gui  # Relative import

            gui.main()
        except ImportError:
            print(
                "GUI module not found. "
                "Please ensure 'gui.py' is part of the 'openscad_export' package."
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
