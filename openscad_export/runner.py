"""Running OpenSCAD: exporting a single parameter set and driving a whole batch."""

import concurrent.futures
import os
import subprocess
import sys
import time

from openscad_export.params import construct_d_flags, parse_selection, read_csv, read_json


def ensure_output_folder(folder):
    """
    Ensure that the output folder exists; create it if it does not.

    Args:
        folder (str): Path to the output folder.
    """
    if not os.path.exists(folder):
        os.makedirs(folder)


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
        subprocess.run(command, check=True, capture_output=True)
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
                print(f"Error exporting {output_file}: {error} (Time: {duration:.2f} seconds)")
    else:
        print("Running exports in parallel.")
        # Use ThreadPoolExecutor for I/O-bound operations
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Prepare iterable of (index, param_set)
            iterable = enumerate(parameters)
            # Submit all tasks
            future_to_export = {
                executor.submit(process_export, idx_param): idx_param for idx_param in iterable
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
                    print(f"Error exporting {info[0]}: {info[1]} (Time: {duration:.2f} seconds)")

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
