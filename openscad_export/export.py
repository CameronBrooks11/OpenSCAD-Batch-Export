import os
import csv
import subprocess
import argparse
import sys


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Batch export STL files from OpenSCAD using CSV parameters."
    )
    parser.add_argument("scad_file", help="Path to the OpenSCAD (.scad) file.")
    parser.add_argument("csv_file", help="Path to the CSV file containing parameters.")
    parser.add_argument(
        "output_folder", help="Directory where STL files will be saved."
    )
    parser.add_argument(
        "--openscad_path",
        default="openscad",
        help='Path to the OpenSCAD executable. Defaults to "openscad" assuming it is in PATH.',
    )
    parser.add_argument(
        "--export_format",
        choices=["asciistl", "binstl"],
        default="binstl",
        help="Export format: asciistl or binstl. Defaults to binstl.",
    )
    return parser.parse_args()


def read_csv(csv_path):
    with open(csv_path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        parameters = [row for row in reader]
    return parameters


def ensure_output_folder(folder):
    if not os.path.exists(folder):
        os.makedirs(folder)


def generate_scad_commands(scad_file, params, temp_scad):
    with open(temp_scad, "w") as f:
        # Write each parameter into the SCAD file
        for key, value in params.items():
            if key != "exported_filename":
                f.write(f"{key} = {value};\n")
        # Reference the main SCAD file
        f.write(f"use <{scad_file}>;\n")
        # Call the `model()` module with parameters
        f.write("model();\n")


def export_stl(openscad_path, scad_file, output_file, export_format):
    command = [
        openscad_path,
        "-o",
        output_file,
        f"--export-format={export_format}",
        scad_file,
    ]
    try:
        subprocess.run(
            command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        print(f"Exported: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error exporting {output_file}: {e.stderr.decode()}")


def batch_export():
    args = parse_arguments()

    scad_file = os.path.abspath(args.scad_file)
    csv_file = os.path.abspath(args.csv_file)
    output_folder = os.path.abspath(args.output_folder)
    openscad_path = args.openscad_path
    export_format = args.export_format

    if not os.path.isfile(scad_file):
        print(f"Error: SCAD file '{scad_file}' does not exist.")
        sys.exit(1)
    if not os.path.isfile(csv_file):
        print(f"Error: CSV file '{csv_file}' does not exist.")
        sys.exit(1)

    parameters = read_csv(csv_file)
    ensure_output_folder(output_folder)

    temp_scad = os.path.join(output_folder, "temp.scad")

    for idx, param_set in enumerate(parameters, start=1):
        filename = param_set.get("exported_filename", f"model_{idx}")
        output_file = os.path.join(output_folder, f"{filename}.stl")
        # Generate the SCAD file with unique parameters
        generate_scad_commands(scad_file, param_set, temp_scad)
        # Export STL using OpenSCAD
        export_stl(openscad_path, temp_scad, output_file, export_format)

    # Cleanup temporary SCAD file
    if os.path.exists(temp_scad):
        os.remove(temp_scad)
    print("Batch export completed.")


if __name__ == "__main__":
    batch_export()
