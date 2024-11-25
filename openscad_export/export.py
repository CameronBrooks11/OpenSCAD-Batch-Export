# openscad_export/export.py

"""
Module for batch exporting STL files from OpenSCAD and converting parameter files between CSV and JSON formats.

This module provides command-line interfaces for exporting STL files using parameter sets defined in CSV or JSON files,
as well as tools for converting between these formats.

Available subcommands:
- export: Batch export STL files.
- csv2json: Convert CSV parameter files to JSON.
- json2csv: Convert JSON parameter files to CSV.
- gui: Launch the graphical user interface.
"""

import os
import csv
import json
import subprocess
import argparse
import sys
import concurrent.futures
import time


def parse_arguments():
    """
    Parse and return the command-line arguments.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
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

    # GUI subcommand
    gui_parser = subparsers.add_parser(
        "gui", help="Launch the graphical user interface."
    )

    return parser.parse_args()


def read_csv(csv_path):
    """
    Read parameters from a CSV file.

    Args:
        csv_path (str): Path to the CSV file.

    Returns:
        list of dict: List of parameter dictionaries.
    """
    with open(csv_path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        parameters = [row for row in reader]
    return parameters


def read_json(json_path):
    """
    Read parameters from a JSON file.

    Args:
        json_path (str): Path to the JSON file.

    Returns:
        list of dict: List of parameter dictionaries with 'exported_filename' added.
    """
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
    """
    Ensure that the output folder exists; create it if it does not.

    Args:
        folder (str): Path to the output folder.
    """
    if not os.path.exists(folder):
        os.makedirs(folder)


def parse_selection(selection_str, total_params):
    """
    Parse a selection string and return a sorted list of unique indices.

    Args:
        selection_str (str): Selection string (e.g., "0-5,7,10-12, every:2 in 0-10, from:15, up_to:20").
        total_params (int): Total number of parameter sets.

    Returns:
        list of int: Sorted list of unique selected indices.

    Raises:
        ValueError: If the selection string is invalid.
    """
    selected_indices = set()
    parts = selection_str.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("every:"):
            try:
                _, rest = part.split(":", 1)
                step, range_part = rest.split(" in ")
                step = int(step)
                start, end = map(int, range_part.split("-"))
                if start > end:
                    raise ValueError(f"Invalid range '{range_part}': start > end.")
                for i in range(start, end + 1, step):
                    if i < 0 or i >= total_params:
                        raise ValueError(
                            f"Index {i} out of range (0-{total_params -1})."
                        )
                    selected_indices.add(i)
            except ValueError as ve:
                raise ValueError(f"Invalid step selection '{part}': {ve}")
        elif part.startswith("from:"):
            try:
                _, start_str = part.split(":", 1)
                start = int(start_str)
                if start < 0 or start >= total_params:
                    raise ValueError(
                        f"Start index {start} out of range (0-{total_params -1})."
                    )
                for i in range(start, total_params):
                    selected_indices.add(i)
            except ValueError as ve:
                raise ValueError(f"Invalid 'from' selection '{part}': {ve}")
        elif part.startswith("up_to:"):
            try:
                _, end_str = part.split(":", 1)
                end = int(end_str)
                if end < 0 or end >= total_params:
                    raise ValueError(
                        f"End index {end} out of range (0-{total_params -1})."
                    )
                for i in range(0, end + 1):
                    selected_indices.add(i)
            except ValueError as ve:
                raise ValueError(f"Invalid 'up_to' selection '{part}': {ve}")
        elif "-" in part:
            try:
                start, end = map(int, part.split("-"))
                if start > end:
                    raise ValueError(f"Invalid range '{part}': start > end.")
                for i in range(start, end + 1):
                    if i < 0 or i >= total_params:
                        raise ValueError(
                            f"Index {i} out of range (0-{total_params -1})."
                        )
                    selected_indices.add(i)
            except ValueError as ve:
                raise ValueError(f"Invalid range '{part}': {ve}")
        else:
            try:
                index = int(part)
                if index < 0 or index >= total_params:
                    raise ValueError(
                        f"Index {index} out of range (0-{total_params -1})."
                    )
                selected_indices.add(index)
            except ValueError as ve:
                raise ValueError(f"Invalid index '{part}': {ve}")
    return sorted(selected_indices)


def construct_d_flags(params):
    """
    Construct a list of -D flags for OpenSCAD based on parameters.

    Args:
        params (dict): Dictionary of parameters.

    Returns:
        list of str: List of -D flags.
    """
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
    """
    Export an STL file using OpenSCAD with the specified parameters.

    Args:
        openscad_path (str): Path to the OpenSCAD executable.
        scad_file (str): Path to the OpenSCAD (.scad) file.
        output_file (str): Path where the STL file will be saved.
        export_format (str): Export format ('asciistl' or 'binstl').
        d_flags (list of str): List of -D flags for OpenSCAD.

    Returns:
        tuple:
            bool: Success status.
            str: Error message if any.
            float: Duration of the export process in seconds.
    """
    start_time = time.perf_counter()
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
        end_time = time.perf_counter()
        duration = end_time - start_time
        return True, "", duration
    except subprocess.CalledProcessError as e:
        error_message = e.stderr.decode().strip()
        end_time = time.perf_counter()
        duration = end_time - start_time
        return False, error_message, duration


def batch_export(
    scad_file,
    parameter_file,
    output_folder,
    openscad_path,
    export_format,
    selection,
    sequential,
):
    """
    Perform batch export of STL files based on parameter sets.

    Args:
        scad_file (str): Path to the OpenSCAD (.scad) file.
        parameter_file (str): Path to the CSV or JSON file containing parameters.
        output_folder (str): Directory where STL files will be saved.
        openscad_path (str): Path to the OpenSCAD executable.
        export_format (str): Export format ('asciistl' or 'binstl').
        selection (str or None): Selection string to specify which parameter sets to export.
        sequential (bool): Whether to process exports sequentially.
    """
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

    total_params = len(parameters)
    selected_indices = None
    if selection:
        try:
            selected_indices = parse_selection(selection, total_params)
            print(f"Selected parameter set indices: {selected_indices}")
        except ValueError as ve:
            print(f"Selection parsing error: {ve}")
            sys.exit(1)

    successes = []
    failures = []
    export_times = []
    total_start_time = time.perf_counter()

    def process_export(idx_param):
        """
        Helper function to process a single export task.

        Args:
            idx_param (tuple): Tuple containing index and parameter set.

        Returns:
            tuple or None: Result of the export process or None if skipped.
        """
        idx, param_set = idx_param
        if selected_indices is not None and idx not in selected_indices:
            return None  # Skip non-selected parameter sets

        filename = param_set.get("exported_filename", f"model_{idx}")
        output_file = os.path.join(output_folder, f"{filename}.stl")

        # Construct -D flags
        d_flags = construct_d_flags(param_set)

        # Export STL using OpenSCAD with -D flags
        success, error, duration = export_stl(
            openscad_path, scad_file, output_file, export_format, d_flags
        )
        if success:
            return ("success", output_file, duration)
        else:
            return ("failure", (output_file, error), duration)

    if sequential:
        print("Running exports sequentially.")
        for idx, param_set in enumerate(parameters):
            if selected_indices is not None and idx not in selected_indices:
                continue  # Skip non-selected parameter sets

            filename = param_set.get("exported_filename", f"model_{idx}")
            output_file = os.path.join(output_folder, f"{filename}.stl")

            # Construct -D flags
            d_flags = construct_d_flags(param_set)

            # Export STL using OpenSCAD with -D flags
            success, error, duration = export_stl(
                openscad_path, scad_file, output_file, export_format, d_flags
            )
            if success:
                successes.append(output_file)
                export_times.append(duration)
                print(f"Exported: {output_file} in {duration:.2f} seconds.")
            else:
                failures.append((output_file, error))
                export_times.append(duration)
                print(
                    f"Error exporting {output_file}: {error} (Time: {duration:.2f} seconds)"
                )
    else:
        print("Running exports in parallel.")
        # Use ThreadPoolExecutor for I/O-bound operations
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Prepare iterable of (index, param_set)
            iterable = enumerate(parameters)
            # Submit all tasks
            future_to_export = {
                executor.submit(process_export, idx_param): idx_param
                for idx_param in iterable
            }

            for future in concurrent.futures.as_completed(future_to_export):
                result = future.result()
                if result is None:
                    continue  # Skipped parameter set
                status, info, duration = result
                if status == "success":
                    successes.append(info)
                    export_times.append(duration)
                    print(f"Exported: {info} in {duration:.2f} seconds.")
                elif status == "failure":
                    failures.append(info)
                    export_times.append(duration)
                    print(
                        f"Error exporting {info[0]}: {info[1]} (Time: {duration:.2f} seconds)"
                    )

    total_end_time = time.perf_counter()
    total_duration = total_end_time - total_start_time

    # Summary of the batch export process
    print("\nBatch export completed.")
    print(f"Total exports attempted: {len(successes) + len(failures)}")
    print(f"Successful exports: {len(successes)}")
    if successes:
        print("Successfully exported files:")
        for file in successes:
            print(f"  - {file}")
    print(f"Failed exports: {len(failures)}")
    if failures:
        print("Failed to export the following files:")
        for file, error in failures:
            print(f"  - {file}: {error}")
    print(f"\nTotal time taken: {total_duration:.2f} seconds.")


def csv_to_json(csv_file, json_file):
    """
    Convert a CSV parameter file to JSON format.

    Args:
        csv_file (str): Path to the input CSV file.
        json_file (str): Path to the output JSON file.
    """
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
    """
    Convert a JSON parameter file to CSV format.

    Args:
        json_file (str): Path to the input JSON file.
        csv_file (str): Path to the output CSV file.
    """
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
                "GUI module not found. Please ensure 'gui.py' is part of the 'openscad_export' package."
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
