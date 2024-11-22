# OpenSCAD-Batch-Exporter

This repository provides a tool to automate the export of STL models from OpenSCAD using CSV or JSON files of parameters. It is a simple and user-friendly solution for batch exporting models with different parameter sets. Inspired by:

[18107/OpenSCAD-batch-export-stl](https://github.com/18107/OpenSCAD-batch-export-stl)

[OutwardBuckle/OpenSCAD-Bulk-Export](https://github.com/OutwardBuckle/OpenSCAD-Bulk-Export)

## Features

- Batch export STL files with parameters defined in CSV or JSON files.
- Convert between CSV and JSON parameter files.
- Easy-to-use command-line interface.
- Handles boolean, numeric, and string parameter types correctly.
- Includes multiple example projects to get started.

## Requirements

- Python 3.6 or later.
- OpenSCAD installed and added to your system PATH.

## Installation

1. **Clone the repository:**

    ```
    git clone https://github.com/CameronBrooks11/OpenSCAD-Batch-Exporter.git
    ```

    ```
    cd OpenSCAD-Batch-Exporter
    ```

2. **Install the Python library:**

    ```
    pip install .
    ```

3. **Ensure OpenSCAD is installed and accessible from the command line. Add it to your PATH if necessary.**

4. **If you encounter the following warning:**

    ```
    WARNING: The script openscad-export.exe is installed in 'C:\Users\<YourUserName>\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.11_<somenumbers>\LocalCache\local-packages\Python311\Scripts' which is not on PATH.
    Consider adding this directory to PATH or, if you prefer to suppress this warning, use --no-warn-script-location.
    ```

    **You can resolve it by adding the directory returned by:**

    ```
    python -m site --user-base
    ```

    **Append the Scripts subdirectory of the output path to your system's PATH. For example:**

    ```
    C:\Users\<YourUserName>\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.11_<somenumbers>\LocalCache\local-packages\Python311\Scripts
    ```

5. **To modify the tool, reinstall it after making changes:**

    ```
    pip install --upgrade .
    ```

## Usage

Once installed, the tool can be called from anywhere using the `openscad-export` command. The tool provides three subcommands:

1. **Export STL Files**
2. **Convert CSV to JSON**
3. **Convert JSON to CSV**

### 1. Export STL Files

Export STL files using either a CSV or JSON parameter file.

**Command Structure:**

```
openscad-export export <scad_file> <parameter_file> <output_folder> [--openscad_path PATH] [--export_format asciistl|binstl]
```

**Parameters:**

- `<scad_file>`: Path to the OpenSCAD `.scad` file.
- `<parameter_file>`: Path to the CSV or JSON file containing parameters.
- `<output_folder>`: Directory where STL files will be saved.

**Options:**

- `--openscad_path`: Path to the OpenSCAD executable. Defaults to `"openscad"` assuming it is in PATH.
- `--export_format`: Export format, either `asciistl` or `binstl`. Defaults to `binstl`.

**Example with CSV:**

```
openscad-export export examples/simpleCube/simpleCube.scad examples/simpleCube/simpleCube.csv output_stls
```

**Example with JSON:**

First, convert the CSV file to JSON:

```
openscad-export csv2json examples/simpleCube/simpleCube.csv examples/simpleCube/simpleCube.json
```

Then, use the JSON file for export:

```
openscad-export export examples/simpleCube/simpleCube.scad examples/simpleCube/simpleCube.json output_stls
```

This will generate STL files for each set of parameters in the specified file and save them in the `output_stls` folder.

### 2. Convert Between CSV and JSON

#### Convert CSV to JSON

Convert a CSV parameter file to JSON format compatible with OpenSCAD's customizer.

**Command Structure:**

```
openscad-export csv2json <csv_file> <json_file>
```

**Example:**

```
openscad-export csv2json examples/candleStand/candleStand.csv examples/candleStand/candleStand.json
```

#### Convert JSON to CSV

Convert a JSON parameter file back to CSV format.

**Command Structure:**

```
openscad-export json2csv <json_file> <csv_file>
```

**Example:**

```
openscad-export json2csv examples/sign/sign.json examples/sign/sign_converted.csv
```

## CSV File Structure

- The CSV file should have a header row with parameter names.
- Each subsequent row defines a set of parameters for the OpenSCAD model.
- A column named `exported_filename` is required to specify the output filenames.

**Example CSV file (`simpleCube.csv`):**

| exported_filename | depth | height | width |
|-------------------|-------|--------|-------|
| cube_small        | 10    | 10     | 10    |
| cube_medium       | 20    | 20     | 20    |
| cube_large        | 30    | 30     | 30    |

## JSON File Structure

The JSON file should follow the structure used by OpenSCAD's customizer profiles. It should contain a `parameterSets` object, where each key is the `exported_filename` and its value is a dictionary of parameters.

**Example JSON file (`simpleCube.json`):**

```
{
    "parameterSets": {
        "cube_small": {
            "width": "10",
            "height": "10",
            "depth": "10"
        },
        "cube_medium": {
            "width": "20",
            "height": "20",
            "depth": "20"
        },
        "cube_large": {
            "width": "30",
            "height": "30",
            "depth": "30"
        }
    },
    "fileFormatVersion": "1"
}
```

## OpenSCAD File Structure

The OpenSCAD file must define a module that uses parameters from the parameter file. For example:

**Example OpenSCAD file (`simpleCube.scad`):**

```
module model() { cube([width, height, depth]); }
```

The script will call this module with the parameters defined in each row of the CSV file or each parameter set in the JSON file.

## Example Files

The `examples/` directory contains multiple projects demonstrating how to use the exporter with different OpenSCAD models.

### 1. Simple Cube

- **Files:**
  - `examples/simpleCube/simpleCube.scad`
  - `examples/simpleCube/simpleCube.json`
  - `examples/simpleCube/simpleCube.csv`

- **Description:**
  A basic example of a customizable cube with varying dimensions.

### 2. Candle Stand

- **Files:**
  - `examples/candleStand/candleStand.scad`
  - `examples/candleStand/candleStand.json`
  - `examples/candleStand/candleStand.csv`

- **Description:**
  A more complex model featuring a candle stand with options for center candles, number of holders, and support structures.

### 3. Sign

- **Files:**
  - `examples/sign/sign.scad`
  - `examples/sign/sign.json`
  - `examples/sign/sign.csv`

- **Description:**
  An example of a customizable sign with adjustable message, size, and resolution parameters.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request with improvements or suggestions.

## License

This project is licensed under the AGPL v3 License. See the LICENSE file for details.
