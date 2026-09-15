"""Running OpenSCAD: exporting a single parameter set and driving a whole batch."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import subprocess
import threading
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


class _ActiveProcesses:
    """OpenSCAD processes currently running, so an interrupt can terminate them.

    After terminate_all() the registry is closed: a process registered later (a worker
    that was between picking up its task and spawning when the interrupt arrived) is
    terminated on arrival, so nothing slips through the gap. reset() reopens it.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._procs = set()
        self.closed = False

    def reset(self):
        with self._lock:
            self._procs.clear()
            self.closed = False

    def add(self, proc):
        with self._lock:
            self._procs.add(proc)
            late = self.closed
        if late:
            proc.terminate()

    def discard(self, proc):
        with self._lock:
            self._procs.discard(proc)

    def terminate_all(self):
        with self._lock:
            self.closed = True
            procs = list(self._procs)
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        return len(procs)


_active = _ActiveProcesses()


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
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _active.add(proc)
    try:
        _, stderr_bytes = proc.communicate()
    except KeyboardInterrupt:
        # Sequential mode: the interrupt lands here, in the main thread, while the
        # child is still running. (Worker threads never receive KeyboardInterrupt; the
        # parallel runner terminates their children instead.)
        proc.terminate()
        proc.wait(timeout=10)
        log.warning("Interrupted: terminated the running OpenSCAD process.")
        raise
    finally:
        _active.discard(proc)
    duration = time.perf_counter() - start_time
    stderr = stderr_bytes.decode(errors="replace").strip()
    returncode = proc.returncode
    return ExportResult(
        name=name,
        output_path=output_file,
        ok=returncode == 0,
        returncode=returncode,
        stderr=stderr if returncode != 0 else "",
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
    jobs=None,
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
        sequential (bool): Run one export at a time; the same as ``jobs=1``.
        jobs (int or None): Maximum number of OpenSCAD processes to run at once.
            Defaults to the CPU count. ``sequential`` forces 1.
        formats (sequence of str): Output extensions, e.g. ``("stl", "png")``; every case
            is exported in every format (duplicates collapsed). A format the engine's
            ``--help`` does not list for ``-o`` is warned about, not refused.
        image_options (dict or None): ``camera``, ``imgsize``, ``colorscheme`` values
            passed through as OpenSCAD's ``--camera=``, ``--imgsize=``, ``--colorscheme=``.

    Customizer JSON parameter sets are passed to OpenSCAD with ``-p FILE -P SET`` when
    the engine supports it (2019.05+); CSV rows are passed as ``-D`` flags. A case never
    gets both. (If both were given, OpenSCAD applies the parameter set over the -D
    values — observed on 2021.01 and 2026.09.)

    Returns:
        BatchResult: Per-case results in input order.

    Ctrl-C (KeyboardInterrupt) terminates the OpenSCAD processes still running,
    abandons the cases not yet started, and re-raises. The process registry this uses
    is per process, so an interrupt also stops any other batch running concurrently
    in the same Python process.

    Raises:
        OpenSCADError: If no usable OpenSCAD executable is found.
        ValueError: If the parameter file format, the selection string, an image
            option, or ``jobs`` is invalid.
    """
    if sequential:
        jobs = 1
    elif jobs is None:
        jobs = os.cpu_count() or 1
    if not isinstance(jobs, int) or isinstance(jobs, bool) or jobs < 1:
        raise ValueError(f"jobs must be a positive integer, not {jobs!r}")
    engine = detect_engine(openscad_path)
    formats = list(dict.fromkeys(f.lstrip(".").lower() for f in formats))
    if not formats:
        raise ValueError("At least one output format is required")
    if engine.export_formats is not None:
        # The --help list is what the build advertises, not everything it accepts
        # (2026 builds write .obj without listing it), so this is a warning; a format
        # OpenSCAD really cannot write fails per case with its own message.
        unlisted = [f for f in formats if f not in engine.export_formats]
        if unlisted:
            log.warning(
                "Output format(s) %s not listed by OpenSCAD %s, which advertises: %s",
                ", ".join(unlisted),
                engine.version,
                ", ".join(sorted(engine.export_formats)),
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

    cases = list(enumerate(parameters))
    if selection:
        selected = set(parse_selection(selection, len(parameters)))
        log.info("Selected parameter set indices: %s", sorted(selected))
        cases = [(idx, params) for idx, params in cases if idx in selected]

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
        elif _active.closed:
            log.debug("Terminated: %s", result.output_path)
        else:
            log.error(
                "Error exporting %s: %s (Time: %.2f seconds)",
                result.output_path,
                result.stderr,
                result.duration,
            )
        return (idx, formats.index(fmt)), result

    tasks = [(idx, params, fmt) for idx, params in cases for fmt in formats]
    total_start_time = time.perf_counter()
    _active.reset()
    if jobs == 1:
        log.info("Running exports sequentially.")
        indexed = [process_export(*task) for task in tasks]  # export_stl handles Ctrl-C
    else:
        log.info("Running exports with up to %d parallel jobs.", jobs)
        indexed = _run_parallel(process_export, tasks, jobs)
    total_duration = time.perf_counter() - total_start_time

    indexed.sort(key=lambda pair: pair[0])
    return BatchResult([result for _, result in indexed], total_duration)


def _on_interrupt():
    killed = _active.terminate_all()
    log.warning("Interrupted: terminated %d running OpenSCAD process(es).", killed)


def _run_parallel(func, tasks, jobs):
    """Run func(*task) for every task with at most `jobs` at once. On interrupt,
    terminate running OpenSCAD processes, drop unstarted tasks, and re-raise."""
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=jobs)
    futures = [executor.submit(func, *task) for task in tasks]
    try:
        return [f.result() for f in concurrent.futures.as_completed(futures)]
    except KeyboardInterrupt:
        for f in futures:
            f.cancel()
        _on_interrupt()
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
