"""Running OpenSCAD: exporting a single parameter set and driving a whole batch."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import subprocess
import time
from dataclasses import dataclass

from openscad_export.engine import detect_engine
from openscad_export.params import construct_d_flags, parse_selection, read_parameters

log = logging.getLogger("openscad_export")


@dataclass
class ExportResult:
    """Outcome of exporting one parameter set."""

    name: str
    output_path: str
    ok: bool
    returncode: int | None
    stderr: str
    duration: float


@dataclass
class BatchResult:
    """Outcome of a whole batch, with per-case results in input order."""

    results: list[ExportResult]
    total_duration: float

    @property
    def successes(self):
        return [r for r in self.results if r.ok]

    @property
    def failures(self):
        return [r for r in self.results if not r.ok]

    def summary(self):
        """Human-readable summary of the batch."""
        lines = [
            "Batch export completed.",
            f"Total exports attempted: {len(self.results)}",
            f"Successful exports: {len(self.successes)}",
        ]
        if self.successes:
            lines.append("Successfully exported files:")
            lines.extend(f"  - {r.output_path}" for r in self.successes)
        lines.append(f"Failed exports: {len(self.failures)}")
        if self.failures:
            lines.append("Failed to export the following files:")
            lines.extend(f"  - {r.output_path}: {r.stderr}" for r in self.failures)
        lines.append("")
        lines.append(f"Total time taken: {self.total_duration:.2f} seconds.")
        return "\n".join(lines)


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
        ExportResult
    """
    name = os.path.splitext(os.path.basename(output_file))[0]
    command = [openscad_path, "-o", output_file, f"--export-format={export_format}"]
    command += d_flags
    command.append(scad_file)
    log.debug("Running command: %s", " ".join(command))
    start_time = time.perf_counter()
    completed = subprocess.run(command, capture_output=True)
    duration = time.perf_counter() - start_time
    stderr = completed.stderr.decode(errors="replace").strip()
    return ExportResult(
        name=name,
        output_path=output_file,
        ok=completed.returncode == 0,
        returncode=completed.returncode,
        stderr=stderr if completed.returncode != 0 else "",
        duration=duration,
    )


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
        openscad_path (str or None): Path to or name of the OpenSCAD executable; None to
            discover it (see :func:`openscad_export.engine.find_openscad`).
        export_format (str): Export format ('asciistl' or 'binstl').
        selection (str or None): Selection string to specify which parameter sets to export.
        sequential (bool): Whether to process exports sequentially.

    Returns:
        BatchResult: Per-case results in input order.

    Raises:
        OpenSCADError: If no usable OpenSCAD executable is found.
        ValueError: If the parameter file format or the selection string is invalid.
    """
    engine = detect_engine(openscad_path)
    parameters = read_parameters(parameter_file)
    ensure_output_folder(output_folder)

    jobs = list(enumerate(parameters))
    if selection:
        selected = set(parse_selection(selection, len(parameters)))
        log.info("Selected parameter set indices: %s", sorted(selected))
        jobs = [(idx, params) for idx, params in jobs if idx in selected]

    def process_export(idx, param_set):
        filename = param_set.get("exported_filename", f"model_{idx}")
        output_file = os.path.join(output_folder, f"{filename}.stl")
        try:
            d_flags = construct_d_flags(param_set)
        except ValueError as e:
            result = ExportResult(filename, output_file, False, None, str(e), 0.0)
        else:
            result = export_stl(engine.path, scad_file, output_file, export_format, d_flags)
        if result.ok:
            log.info("Exported: %s in %.2f seconds.", result.output_path, result.duration)
        else:
            log.error(
                "Error exporting %s: %s (Time: %.2f seconds)",
                result.output_path,
                result.stderr,
                result.duration,
            )
        return idx, result

    total_start_time = time.perf_counter()
    if sequential:
        log.info("Running exports sequentially.")
        indexed = [process_export(idx, params) for idx, params in jobs]
    else:
        log.info("Running exports in parallel.")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(process_export, idx, params) for idx, params in jobs]
            indexed = [f.result() for f in concurrent.futures.as_completed(futures)]
    total_duration = time.perf_counter() - total_start_time

    indexed.sort(key=lambda pair: pair[0])
    return BatchResult([result for _, result in indexed], total_duration)
