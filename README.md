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
openscad-export export <scad_file> <parameter_file> <output_folder> [--openscad_path PATH] [--export_format asciistl|binstl] [--select SELECTION]
```

**Parameters:**

- `<scad_file>`: Path to the OpenSCAD `.scad` file.
- `<parameter_file>`: Path to the CSV or JSON file containing parameters.
- `<output_folder>`: Directory where STL files will be saved.

**Options:**

- `--openscad_path`: Path to the OpenSCAD executable. Defaults to `"openscad"` assuming it is in PATH.
- `--export_format`: Export format, either `asciistl` or `binstl`. Defaults to `binstl`.
- `--select SELECTION`: Select specific parameter sets to export using indices and ranges. Format examples: `'0-5'`, `'1-3,7,10-12'`, `'2,4'`. Indices are zero-based.

**Examples:**

- **Export with CSV:**

    ```
    openscad-export export examples/simpleCube/simpleCube.scad examples/simpleCube/simpleCube.csv output_stls
    ```

- **Export with JSON:**

    First, convert the CSV file to JSON:

    ```
    openscad-export csv2json examples/simpleCube/simpleCube.csv examples/simpleCube/simpleCube.json
    ```

    Then, use the JSON file for export:

    ```
    openscad-export export examples/simpleCube/simpleCube.scad examples/simpleCube/simpleCube.json output_stls
    ```

- **Selective Export:**

    - **Export a Range of Parameter Sets:**

        Export parameter sets from index 0 to 5:

        $$$
        openscad-export export examples/candleStand/candleStand.scad examples/candleStand/candleStand.csv output_stls --select "0-5"
        $$$

    - **Export Specific Indices:**

        Export parameter sets at indices 1, 3, and 4:

        $$$
        openscad-export export examples/sign/sign.scad examples/sign/sign.csv output_stls --select "1,3,4"
        $$$

    - **Export Multiple Ranges and Specific Indices:**

        Export parameter sets from indices 1 to 3, index 7, and from 10 to 12:

        $$$
        openscad-export export examples/candleStand/candleStand.scad examples/candleStand/candleStand.csv output_stls --select "1-3,7,10-12"
        $$$

    - **Export Every Xth Parameter Set in a Range:**

        Export every 2nd parameter set from index 0 to 10:

        $$$
        openscad-export export examples/candleStand/candleStand.scad examples/candleStand/candleStand.csv output_stls --select "every:2 in 0-10"
        $$$

    - **Export from a Specific Index Onward:**

        Export all parameter sets from index 5 to the end:

        $$$
        openscad-export export examples/sign/sign.scad examples/sign/sign.csv output_stls --select "from:5"
        $$$

    - **Export Up to a Specific Index:**

        Export all parameter sets up to index 4 inclusive:

        $$$
        openscad-export export examples/simpleCube/simpleCube.scad examples/simpleCube/simpleCube.csv output_stls --select "up_to:4"
        $$$

    - **Combine Multiple Selection Methods:**

        Export parameter sets from index 0 to 2, every 3rd set from 5 to 15, and index 20:

        $$$
        openscad-export export examples/candleStand/candleStand.scad examples/candleStand/candleStand.csv output_stls --select "0-2, every:3 in 5-15,20"
        $$$

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

The OpenSCAD file must define a model that uses parameters from the parameter file. For example:

**Example OpenSCAD file (`simpleCube.scad`):**

```
module model() { cube([width, height, depth]); }
```


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
