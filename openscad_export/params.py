"""Parameter-set handling: reading CSV and Customizer JSON files, selecting subsets,
serializing values as OpenSCAD -D flags, and converting between the two formats."""

import csv
import json
import logging
import os

log = logging.getLogger("openscad_export")


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
    with open(json_path) as jsonfile:
        data = json.load(jsonfile)
    parameter_sets = data.get("parameterSets", {})
    parameters = []
    for name, params in parameter_sets.items():
        param_set = params.copy()
        param_set["exported_filename"] = name
        parameters.append(param_set)
    return parameters


def read_parameters(parameter_file):
    """
    Read parameter sets from a CSV or JSON file, chosen by extension.

    Args:
        parameter_file (str): Path to the CSV or JSON file.

    Returns:
        list of dict: List of parameter dictionaries.

    Raises:
        ValueError: If the file extension is not .csv or .json.
    """
    ext = os.path.splitext(str(parameter_file))[1].lower()
    if ext == ".csv":
        return read_csv(parameter_file)
    if ext == ".json":
        return read_json(parameter_file)
    raise ValueError(f"Unsupported parameter file format: {ext}")


def parse_selection(selection_str, total_params):
    """
    Parse a selection string and return a sorted list of unique indices.

    Args:
        selection_str (str): Selection string
            (e.g., "0-5,7,10-12, every:2 in 0-10, from:15, up_to:20").
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
                        raise ValueError(f"Index {i} out of range (0-{total_params - 1}).")
                    selected_indices.add(i)
            except ValueError as ve:
                raise ValueError(f"Invalid step selection '{part}': {ve}") from ve
        elif part.startswith("from:"):
            try:
                _, start_str = part.split(":", 1)
                start = int(start_str)
                if start < 0 or start >= total_params:
                    raise ValueError(f"Start index {start} out of range (0-{total_params - 1}).")
                for i in range(start, total_params):
                    selected_indices.add(i)
            except ValueError as ve:
                raise ValueError(f"Invalid 'from' selection '{part}': {ve}") from ve
        elif part.startswith("up_to:"):
            try:
                _, end_str = part.split(":", 1)
                end = int(end_str)
                if end < 0 or end >= total_params:
                    raise ValueError(f"End index {end} out of range (0-{total_params - 1}).")
                for i in range(0, end + 1):
                    selected_indices.add(i)
            except ValueError as ve:
                raise ValueError(f"Invalid 'up_to' selection '{part}': {ve}") from ve
        elif "-" in part:
            try:
                start, end = map(int, part.split("-"))
                if start > end:
                    raise ValueError(f"Invalid range '{part}': start > end.")
                for i in range(start, end + 1):
                    if i < 0 or i >= total_params:
                        raise ValueError(f"Index {i} out of range (0-{total_params - 1}).")
                    selected_indices.add(i)
            except ValueError as ve:
                raise ValueError(f"Invalid range '{part}': {ve}") from ve
        else:
            try:
                index = int(part)
                if index < 0 or index >= total_params:
                    raise ValueError(f"Index {index} out of range (0-{total_params - 1}).")
                selected_indices.add(index)
            except ValueError as ve:
                raise ValueError(f"Invalid index '{part}': {ve}") from ve
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
                    # Check if the string represents an array or object
                    stripped_value = value.strip()
                    if (stripped_value.startswith("[") and stripped_value.endswith("]")) or (
                        stripped_value.startswith("{") and stripped_value.endswith("}")
                    ):
                        # Pass arrays and objects as is
                        d_flags.append(f"-D{key}={value}")
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
            "exported_filename", f"model_{parameters.index(param_set) + 1}"
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
    log.info("Converted %s to %s.", csv_file, json_file)


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
    log.info("Converted %s to %s.", json_file, csv_file)
