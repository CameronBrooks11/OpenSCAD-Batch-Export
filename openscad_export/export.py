# openscad_export/export.py

import os
import csv
import json
import subprocess
import argparse
import sys


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Batch export STL files from OpenSCAD using CSV or JSON parameters, and convert between CSV and JSON."
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Sub-commands"
    )

    # Export subcommand
    export_parser = subparsers.add_parser(
        "export", help="Export STL files from OpenSCAD using CSV or JSON parameters."
    )
    export_parser.add_argument("scad_file", help="Path to the OpenSCAD (.scad) file.")
    export_parser.add_argument(
        "parameter_file", help="Path to the CSV or JSON file containing parameters."
    )
    export_parser.add_argument(
        "output_folder", help="Directory where STL files will be saved."
    )
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

    # csv2json subcommand
    csv2json_parser = subparsers.add_parser(
        "csv2json", help="Convert CSV parameter file to JSON."
    )
    csv2json_parser.add_argument("csv_file", help="Path to the CSV file.")
    csv2json_parser.add_argument("json_file", help="Path to the output JSON file.")

    # json2csv subcommand
    json2csv_parser = subparsers.add_parser(
        "json2csv", help="Convert JSON parameter file to CSV."
    )
    json2csv_parser.add_argument("json_file", help="Path to the JSON file.")
    json2csv_parser.add_argument("csv_file", help="Path to the output CSV file.")

    return parser.parse_args()


def read_csv(csv_path):
    with open(csv_path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        parameters = [row for row in reader]
    return parameters


def read_json(json_path):
    with open(json_path, "r") as jsonfile:
        data = json.load(jsonfile)
    parameter_sets = data.get("parameterSets", {})
    parameters = []
    for name, params in parameter_sets.items():
        param_set = params.copy()
        param_set["exported_filename"] = name
        parameters.append(param_set)
    return parameters


def ensure_output_folder(folder):
    if not os.path.exists(folder):
        os.makedirs(folder)


def construct_d_flags(params):
    """Constructs a list of -D flags for OpenSCAD based on parameters."""
    d_flags = []
    for key, value in params.items():
        if key != "exported_filename":
            if isinstance(value, bool):
                # Booleans should be lowercased and not quoted
                d_flags.append(f"-D{key}={'true' if value else 'false'}")
            elif isinstance(value, (int, float)):
                # Numbers are passed as is
                d_flags.append(f"-D{key}={value}")
            elif isinstance(value, str):
                lowered = value.lower()
                if lowered == "true":
                    d_flags.append(f"-D{key}=true")
                elif lowered == "false":
                    d_flags.append(f"-D{key}=false")
                else:
                    # Attempt to convert to float
                    try:
                        numeric_value = float(value)
                        if numeric_value.is_integer():
                            numeric_value = int(numeric_value)
                        d_flags.append(f"-D{key}={numeric_value}")
                    except ValueError:
                        # It's a string, wrap it in quotes
                        d_flags.append(f'-D{key}="{value}"')
            else:
                # Default to string
                d_flags.append(f'-D{key}="{value}"')
    return d_flags


def export_stl(openscad_path, scad_file, output_file, export_format, d_flags):
    command = (
        [
            openscad_path,
            "-o",
            output_file,
            f"--export-format={export_format}",
        ]
        + d_flags
        + [scad_file]
    )
    print(f"Running command: {' '.join(command)}")  # Debug print
    try:
        subprocess.run(
            command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        print(f"Exported: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error exporting {output_file}: {e.stderr.decode()}")


def batch_export(
    scad_file, parameter_file, output_folder, openscad_path, export_format
):
    # Determine parameter file type based on extension
    _, ext = os.path.splitext(parameter_file)
    ext = ext.lower()
    if ext == ".csv":
        parameters = read_csv(parameter_file)
    elif ext == ".json":
        parameters = read_json(parameter_file)
    else:
        print(f"Unsupported parameter file format: {ext}")
        sys.exit(1)

    ensure_output_folder(output_folder)

    for idx, param_set in enumerate(parameters, start=1):
        filename = param_set.get("exported_filename", f"model_{idx}")
        output_file = os.path.join(output_folder, f"{filename}.stl")

        # Construct -D flags
        d_flags = construct_d_flags(param_set)

        # Export STL using OpenSCAD with -D flags
        export_stl(openscad_path, scad_file, output_file, export_format, d_flags)

    print("Batch export completed.")


def csv_to_json(csv_file, json_file):
    parameters = read_csv(csv_file)
    json_data = {"parameterSets": {}}
    for param_set in parameters:
        exported_filename = param_set.get(
            "exported_filename", f"model_{parameters.index(param_set)+1}"
        )
        # Remove exported_filename from the parameters
        params = {k: v for k, v in param_set.items() if k != "exported_filename"}
        # Attempt to convert "true"/"false" to booleans
        for k, v in params.items():
            if isinstance(v, str):
                lowered = v.lower()
                if lowered == "true":
                    params[k] = True
                elif lowered == "false":
                    params[k] = False
                else:
                    # Attempt to convert to int or float
                    try:
                        if "." in v:
                            params[k] = float(v)
                        else:
                            params[k] = int(v)
                    except ValueError:
                        pass  # keep as string
        json_data["parameterSets"][exported_filename] = params
    # Add fileFormatVersion
    json_data["fileFormatVersion"] = "1"
    # Write to JSON file
    with open(json_file, "w") as jf:
        json.dump(json_data, jf, indent=4)
    print(f"Converted {csv_file} to {json_file}.")


def json_to_csv(json_file, csv_file):
    parameter_sets = read_json(json_file)
    # Collect all unique keys
    all_keys = set()
    for params in parameter_sets:
        all_keys.update(params.keys())
    # Ensure 'exported_filename' is first column
    fieldnames = ["exported_filename"] + sorted(all_keys - {"exported_filename"})
    with open(csv_file, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for param_set in parameter_sets:
            row = {"exported_filename": param_set.get("exported_filename", "model")}
            for key in all_keys - {"exported_filename"}:
                value = param_set.get(key, "")
                # Convert booleans to "true"/"false" strings
                if isinstance(value, bool):
                    row[key] = "true" if value else "false"
                else:
                    row[key] = value
            writer.writerow(row)
    print(f"Converted {json_file} to {csv_file}.")


def main():
    args = parse_arguments()

    if args.command == "export":
        batch_export(
            args.scad_file,
            args.parameter_file,
            args.output_folder,
            args.openscad_path,
            args.export_format,
        )
    elif args.command == "csv2json":
        csv_to_json(args.csv_file, args.json_file)
    elif args.command == "json2csv":
        json_to_csv(args.json_file, args.csv_file)


if __name__ == "__main__":
    main()
