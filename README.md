# OpenSCAD-Batch-Exporter

This repository provides a tool to automate the export of STL models from OpenSCAD using a CSV file of parameters. It is a simple and user-friendly solution for batch exporting models with different parameter sets. Inspired by:

[18107/OpenSCAD-batch-export-stl](https://github.com/18107/OpenSCAD-batch-export-stl)

[OutwardBuckle/OpenSCAD-Bulk-Export](https://github.com/OutwardBuckle/OpenSCAD-Bulk-Export)

## Features

- Batch export STL files with parameters defined in a CSV file.
- Easy-to-use command-line interface.
- Includes example files to get started.

## Requirements

- Python 3.6 or later.
- OpenSCAD installed and added to your system PATH.

## Installation

1. Clone the repository:

```git clone https://github.com/CameronBrooks11/OpenSCAD-Batch-Exporter.git cd OpenSCAD-Batch-Exporter```

2. Install the Python lib:

```pip install .```

3. Ensure OpenSCAD is installed and accessible from the command line. Add it to your PATH if necessary.

4. If you encounter the following warning:

```
WARNING: The script openscad-export.exe is installed in 'C:\Users\<YourUserName>\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.11_<somenumbers>\LocalCache\local-packages\Python311\Scripts' which is not on PATH.
Consider adding this directory to PATH or, if you prefer to suppress this warning, use --no-warn-script-location.
```

You can resolve it by adding the directory returned by:

```python -m site --user-base```

Append the Scripts subdirectory of the output path to your system's PATH. For example:

```C:\Users\<YourUserName>\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.11_<somenumbers>\LocalCache\local-packages\Python311\Scripts```

5. To modify the tool, reinstall it after making changes:

```pip install --upgrade .```

## Usage

Once installed, the tool can be called from anywhere:

```openscad-export <scad_file> <csv_file> <output_folder>```

### Example

To use the provided example files:

1. Navigate to the repository folder:

```cd OpenSCAD-Batch-Exporter```

2. Run the export script:

```openscad-export examples/example.scad examples/parameters.csv output_stls```

This will generate STL files for each set of parameters in the CSV file and save them in the `output_stls` folder.

### CSV File Structure

- The CSV file should have a header row with parameter names.
- Each subsequent row defines a set of parameters for the OpenSCAD model.
- A column named `exported_filename` is required to specify the output filenames.

Example CSV file:

| exported_filename | width | height | depth |
|--------------------|-------|--------|-------|
| cube_small         | 10    | 10     | 10    |
| cube_medium        | 20    | 20     | 20    |
| cube_large         | 30    | 30     | 30    |

### OpenSCAD File Structure

The OpenSCAD file must define a module (e.g., `model`) that uses parameters from the CSV file. For example:

```module model() { cube([width, height, depth]); }```

The script will call this module with the parameters defined in each row of the CSV file.

## Example Files

- `example.scad`: A sample OpenSCAD file defining a customizable cube.
- `parameters.csv`: A CSV file with parameters for exporting different cubes.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request with improvements or suggestions.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
