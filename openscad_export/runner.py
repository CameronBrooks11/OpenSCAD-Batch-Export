"""Running OpenSCAD: exporting a single parameter set and driving a whole batch."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import subprocess
import time
from dataclasses import dataclass

from openscad_export.engine import detect_engine
from openscad_export.params import (
    construct_d_flags,
    is_parameter_set_file,
    parse_selection,
    read_parameters,
)

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
    format: str = "stl"


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


def export_stl(openscad_path, scad_file, output_file, export_format, param_args, extra_args=()):
    """
    Export one file using OpenSCAD with the specified parameters. The output format is
    chosen by ``output_file``'s extension, as OpenSCAD's ``-o`` does.

    Args:
        openscad_path (str): Path to the OpenSCAD executable.
        scad_file (str): Path to the OpenSCAD (.scad) file.
        output_file (str): Path where the file will be saved.
        export_format (str or None): ``--export-format`` value ('asciistl' or 'binstl'
            for STL output); None to let the extension decide.
        param_args (list of str): Arguments that supply the parameters: either -D flags
            or ``["-p", file, "-P", set_name]``.
        extra_args (list of str): Further OpenSCAD options, e.g. ``--camera=...``.

    Returns:
        ExportResult
    """
    name, ext = os.path.splitext(os.path.basename(output_file))
    command = [openscad_path, "-o", output_file]
    if export_format:
        command.append(f"--export-format={export_format}")
    command += list(extra_args)
    command += param_args
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
        format=ext.lstrip(".").lower(),
    )


IMAGE_OPTIONS = ("camera", "imgsize", "colorscheme")


def batch_export(
    scad_file,
    parameter_file,
    output_folder,
    openscad_path,
    export_format,
    selection,
    sequential,
    formats=("stl",),
    image_options=None,
):
    """
    Perform batch export of files based on parameter sets.

    Args:
        scad_file (str): Path to the OpenSCAD (.scad) file.
        parameter_file (str): Path to the CSV or JSON file containing parameters.
        output_folder (str): Directory where STL files will be saved.
        openscad_path (str or None): Path to or name of the OpenSCAD executable; None to
            discover it (see :func:`openscad_export.engine.find_openscad`).
        export_format (str): Export format ('asciistl' or 'binstl').
        selection (str or None): Selection string to specify which parameter sets to export.
        sequential (bool): Whether to process exports sequentially.
        formats (sequence of str): Output extensions, e.g. ``("stl", "png")``; every case
            is exported in every format. Validated against what the engine's ``--help``
            lists for ``-o`` when that is readable.
        image_options (dict or None): ``camera``, ``imgsize``, ``colorscheme`` values
            passed through as OpenSCAD's ``--camera=``, ``--imgsize=``, ``--colorscheme=``.

    Customizer JSON parameter sets are passed to OpenSCAD with ``-p FILE -P SET`` when
    the engine supports it (2019.05+); CSV rows are passed as ``-D`` flags. A case never
    gets both. (If both were given, OpenSCAD applies the parameter set over the -D
    values — observed on 2021.01 and 2026.09.)

    Returns:
        BatchResult: Per-case results in input order.

    Raises:
        OpenSCADError: If no usable OpenSCAD executable is found.
        ValueError: If the parameter file format, the selection string, or a requested
            output format is invalid.
    """
    engine = detect_engine(openscad_path)
    formats = [f.lstrip(".").lower() for f in formats]
    if not formats:
        raise ValueError("At least one output format is required")
    if engine.export_formats is not None:
        unsupported = [f for f in formats if f not in engine.export_formats]
        if unsupported:
            raise ValueError(
                f"Output format(s) {', '.join(unsupported)} not supported by OpenSCAD "
                f"{engine.version}; it accepts: {', '.join(sorted(engine.export_formats))}"
            )
    extra_args = [f"--{key}={value}" for key, value in (image_options or {}).items() if value]
    unknown = set(image_options or {}) - set(IMAGE_OPTIONS)
    if unknown:
        raise ValueError(f"Unknown image option(s): {', '.join(sorted(unknown))}")
    parameters = read_parameters(parameter_file)
    ensure_output_folder(output_folder)

    # Customizer JSON goes to OpenSCAD natively (-p FILE -P SET) when the engine can
    # take it, so values are typed by the model's own defaults and unset keys keep
    # them. CSV, and engines older than 2019.05, get the values as -D flags.
    use_parameter_sets = is_parameter_set_file(parameter_file) and engine.supports_parameter_sets
    if use_parameter_sets:
        log.info("Passing parameter sets natively with -p/-P.")
    else:
        log.info("Passing parameters as -D flags.")

    jobs = list(enumerate(parameters))
    if selection:
        selected = set(parse_selection(selection, len(parameters)))
        log.info("Selected parameter set indices: %s", sorted(selected))
        jobs = [(idx, params) for idx, params in jobs if idx in selected]

    def process_export(idx, param_set, fmt):
        filename = param_set.get("exported_filename", f"model_{idx}")
        output_file = os.path.join(output_folder, f"{filename}.{fmt}")
        try:
            if use_parameter_sets:
                param_args = ["-p", os.fspath(parameter_file), "-P", param_set["exported_filename"]]
            else:
                param_args = construct_d_flags(param_set)
        except ValueError as e:
            result = ExportResult(filename, output_file, False, None, str(e), 0.0, fmt)
        else:
            result = export_stl(
                engine.path,
                scad_file,
                output_file,
                export_format if fmt == "stl" else None,
                param_args,
                extra_args,
            )
        if result.ok:
            log.info("Exported: %s in %.2f seconds.", result.output_path, result.duration)
        else:
            log.error(
                "Error exporting %s: %s (Time: %.2f seconds)",
                result.output_path,
                result.stderr,
                result.duration,
            )
        return (idx, formats.index(fmt)), result

    tasks = [(idx, params, fmt) for idx, params in jobs for fmt in formats]
    total_start_time = time.perf_counter()
    if sequential:
        log.info("Running exports sequentially.")
        indexed = [process_export(*task) for task in tasks]
    else:
        log.info("Running exports in parallel.")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(process_export, *task) for task in tasks]
            indexed = [f.result() for f in concurrent.futures.as_completed(futures)]
    total_duration = time.perf_counter() - total_start_time

    indexed.sort(key=lambda pair: pair[0])
    return BatchResult([result for _, result in indexed], total_duration)
