"""Parameter-set handling: reading CSV and Customizer JSON files, selecting subsets,
serializing values as OpenSCAD -D flags, and converting between the two formats."""

import csv
import json
import logging
import math
import os
import re
from typing import NamedTuple

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


def is_parameter_set_file(parameter_file):
    """True if the file is a Customizer JSON parameter-set file (by extension)."""
    return os.path.splitext(str(parameter_file))[1].lower() == ".json"


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


_NUMBER = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
_INTEGER = re.compile(r"[+-]?\d+")


class ScadRange(NamedTuple):
    """An OpenSCAD range literal, ``[start : end]`` or ``[start : step : end]``."""

    start: float
    end: float
    step: float | None = None


_STRING_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\t": "\\t", "\r": "\\r"}


def to_scad_literal(value):
    """
    Serialize a Python value as an OpenSCAD literal for use in a -D flag.

    bool -> true/false, int/float -> number, str -> quoted and escaped string,
    list/tuple -> vector (recursively), ScadRange -> range, None -> undef.

    Raises:
        ValueError: For non-finite floats, which OpenSCAD has no literal for.
        TypeError: For any other type.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Cannot serialize non-finite number {value!r} as an OpenSCAD literal")
        return repr(value)
    if isinstance(value, str):
        escaped = "".join(_STRING_ESCAPES.get(ch, ch) for ch in value)
        return f'"{escaped}"'
    if isinstance(value, ScadRange):
        parts = (
            [value.start, value.end] if value.step is None else [value.start, value.step, value.end]
        )
        return "[" + " : ".join(to_scad_literal(v) for v in parts) + "]"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(to_scad_literal(v) for v in value) + "]"
    if value is None:
        return "undef"
    raise TypeError(f"Cannot serialize {type(value).__name__} as an OpenSCAD literal")


def coerce_cell(text):
    """
    Decide what a parameter value written as text (a CSV cell, or a Customizer JSON
    string) means, using OpenSCAD's own syntax:

    - ``true`` / ``false`` (any case) -> bool; ``undef`` -> None
    - a number in OpenSCAD's grammar (``12``, ``-2.5``, ``.5``, ``1e3``) -> int or float
    - text wrapped in double quotes (``"007"``) -> that string, verbatim. This is how to
      keep a numeric-looking value as a string.
    - text starting with ``[`` -> a vector or range literal, parsed and validated.
      Strings inside follow OpenSCAD escape rules (``\\n``, ``\\"``, ``\\u00e9``...).
      Only literals are accepted: expressions such as ``[1+2, a]`` are rejected.
    - anything else -> the string as written

    Raises:
        ValueError: If a vector is malformed or a number is out of range.
    """
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered == "undef":
        return None
    if _NUMBER.fullmatch(stripped):
        if _INTEGER.fullmatch(stripped):
            return int(stripped)
        number = float(stripped)
        if not math.isfinite(number):
            raise ValueError(f"Number {stripped!r} is out of range")
        return number
    if len(stripped) >= 2 and stripped[0] == '"' and stripped[-1] == '"':
        return stripped[1:-1]
    if stripped.startswith("["):
        return _parse_vector(stripped)
    return text


_SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}
_HEX_ESCAPE_WIDTH = {"x": 2, "u": 4, "U": 6}


def _parse_vector(text):
    """Parse an OpenSCAD vector or range literal: numbers, strings, bools, undef, nested
    vectors and ``[a : b]`` / ``[a : b : c]`` ranges. Expressions are not accepted."""
    pos = 0

    def error(message):
        return ValueError(f"Invalid vector {text!r}: {message} at position {pos}")

    def skip_ws():
        nonlocal pos
        while pos < len(text) and text[pos].isspace():
            pos += 1

    def parse_value():
        nonlocal pos
        skip_ws()
        if pos >= len(text):
            raise error("unexpected end")
        ch = text[pos]
        if ch == "[":
            pos += 1
            items = []
            skip_ws()
            if pos < len(text) and text[pos] == "]":
                pos += 1
                return items
            separator = None
            while True:
                items.append(parse_value())
                skip_ws()
                if pos >= len(text):
                    raise error("missing ']'")
                if text[pos] in ",:" and separator in (None, text[pos]):
                    separator = text[pos]
                    pos += 1
                    skip_ws()
                    if separator == "," and pos < len(text) and text[pos] == "]":
                        pos += 1  # trailing comma, as OpenSCAD allows
                        return items
                    continue
                if text[pos] == "]":
                    pos += 1
                    if separator != ":":
                        return items
                    if len(items) == 2:
                        return ScadRange(items[0], items[1])
                    if len(items) == 3:
                        return ScadRange(items[0], items[2], items[1])
                    raise error("a range has two or three parts")
                raise error(f"unexpected {text[pos]!r}")
        if ch == '"':
            pos += 1
            chars = []
            while pos < len(text) and text[pos] != '"':
                if text[pos] == "\\":
                    pos += 1
                    if pos >= len(text):
                        break
                    esc = text[pos]
                    if esc in _SIMPLE_ESCAPES:
                        chars.append(_SIMPLE_ESCAPES[esc])
                    elif esc in _HEX_ESCAPE_WIDTH:
                        width = _HEX_ESCAPE_WIDTH[esc]
                        digits = text[pos + 1 : pos + 1 + width]
                        if len(digits) != width or not all(
                            c in "0123456789abcdefABCDEF" for c in digits
                        ):
                            raise error(f"bad \\{esc} escape")
                        chars.append(chr(int(digits, 16)))
                        pos += width
                    else:
                        chars.append("\\" + esc)  # unknown escape: keep as written
                else:
                    chars.append(text[pos])
                pos += 1
            if pos >= len(text):
                raise error("unterminated string")
            pos += 1
            return "".join(chars)
        match = _NUMBER.match(text, pos)
        if match:
            pos = match.end()
            token = match.group(0)
            return int(token) if _INTEGER.fullmatch(token) else float(token)
        for word, value in (("true", True), ("false", False), ("undef", None)):
            if text.startswith(word, pos):
                pos += len(word)
                return value
        raise error(f"unexpected {ch!r}")

    try:
        result = parse_value()
    except RecursionError:
        raise error("nesting too deep") from None
    skip_ws()
    if pos != len(text):
        raise error("trailing characters")
    return result


def construct_d_flags(params):
    """
    Construct a list of -D flags for OpenSCAD based on parameters.

    String values are interpreted with :func:`coerce_cell`; other values are serialized
    directly with :func:`to_scad_literal`.

    Args:
        params (dict): Dictionary of parameters.

    Returns:
        list of str: List of -D flags.
    """
    d_flags = []
    for key, value in params.items():
        if key == "exported_filename":
            continue
        try:
            if isinstance(value, str):
                value = coerce_cell(value)
            d_flags.append(f"-D{key}={to_scad_literal(value)}")
        except (TypeError, ValueError) as e:
            raise ValueError(f"Parameter '{key}': {e}") from e
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
