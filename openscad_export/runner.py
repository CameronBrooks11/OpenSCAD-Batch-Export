"""Running OpenSCAD: exporting a single parameter set and driving a whole batch."""

from __future__ import annotations

import concurrent.futures
import contextlib
import json
import logging
import os
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata

from openscad_export.engine import Engine, detect_engine
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
            _signal_tree(proc, kill=False)

    def discard(self, proc):
        with self._lock:
            self._procs.discard(proc)

    def terminate_all(self):
        with self._lock:
            self.closed = True
            procs = list(self._procs)
        for proc in procs:
            if proc.poll() is None:
                _signal_tree(proc, kill=False)
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
    skipped: bool = False
    """True when the output already existed and skip_existing left it alone."""
    command: list[str] | None = None
    """The OpenSCAD command line for this case (None if it never got that far)."""
    warnings: list[str] = field(default_factory=list)
    """OpenSCAD's message lines from stderr (WARNING:, ECHO:, ERROR:, DEPRECATED:, ...)."""
    timed_out: bool = False
    """True when OpenSCAD was killed for exceeding the per-case timeout."""

    @property
    def status(self):
        if self.skipped:
            return "skipped"
        if self.timed_out:
            return "timeout"
        if self.ok:
            return "ok" if self.returncode is not None else "dry-run"
        return "failed"


@dataclass
class BatchResult:
    """Outcome of a whole batch, with per-case results in input order."""

    results: list[ExportResult]
    total_duration: float
    dry_run: bool = False
    engine: Engine | None = None
    """The OpenSCAD that ran the batch."""
    inputs: dict | None = None
    """What was asked for: scad_file, parameter_file, output_folder, formats, jobs, ..."""
    started_at: str | None = None
    """UTC start time of the batch, ISO 8601."""

    @property
    def successes(self):
        return [r for r in self.results if r.ok and not r.skipped]

    @property
    def failures(self):
        return [r for r in self.results if not r.ok]

    @property
    def skipped(self):
        return [r for r in self.results if r.skipped]

    def to_dict(self):
        """JSON-serialisable record of the whole batch: engine, inputs, per-case results."""
        return {
            "openscad_batch_export": _tool_version(),
            "started_at": self.started_at,
            "openscad": None
            if self.engine is None
            else {"path": self.engine.path, "version": self.engine.version},
            "inputs": self.inputs,
            "dry_run": self.dry_run,
            "total_duration": self.total_duration,
            "counts": {
                "ok": len(self.successes),
                "failed": len(self.failures),
                "timeout": sum(r.timed_out for r in self.results),
                "skipped": len(self.skipped),
            },
            "results": [
                {
                    "name": r.name,
                    "output_path": r.output_path,
                    "format": r.format,
                    "status": r.status,
                    "returncode": r.returncode,
                    "duration": r.duration,
                    "stderr": r.stderr,
                    "warnings": r.warnings,
                    "command": r.command,
                }
                for r in self.results
            ],
        }

    def write_summary(self, path):
        """Write :meth:`to_dict` as JSON to ``path``, creating its directory if needed."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
            f.write("\n")

    def summary(self):
        """Human-readable summary of the batch."""
        if self.dry_run:
            lines = [f"Dry run: {len(self.successes)} export(s) would run."]
            lines.extend(f"  - {r.output_path}" for r in self.successes)
            if self.skipped:
                lines.append(f"Skipped (already present): {len(self.skipped)}")
                lines.extend(f"  - {r.output_path}" for r in self.skipped)
            if self.failures:
                lines.append(f"Would fail before running: {len(self.failures)}")
                lines.extend(f"  - {r.output_path}: {r.stderr}" for r in self.failures)
            return "\n".join(lines)
        lines = [
            "Batch export completed.",
            f"Total exports attempted: {len(self.results) - len(self.skipped)}",
            f"Successful exports: {len(self.successes)}",
        ]
        if self.successes:
            lines.append("Successfully exported files:")
            lines.extend(f"  - {r.output_path}" for r in self.successes)
        if self.skipped:
            lines.append(f"Skipped (already present): {len(self.skipped)}")
            lines.extend(f"  - {r.output_path}" for r in self.skipped)
        lines.append(f"Failed exports: {len(self.failures)}")
        if self.failures:
            lines.append("Failed to export the following files:")
            lines.extend(f"  - {r.output_path}: {r.stderr}" for r in self.failures)
        # Failed cases already show their full stderr above; ECHO/TRACE chatter stays in
        # the per-case log and the JSON record.
        with_warnings = [
            (r, [w for w in r.warnings if not w.startswith(_CHATTER_PREFIXES)])
            for r in self.results
            if r.ok
        ]
        with_warnings = [(r, ws) for r, ws in with_warnings if ws]
        if with_warnings:
            lines.append(f"OpenSCAD warnings from {len(with_warnings)} successful case(s):")
            for r, ws in with_warnings:
                lines.append(f"  - {r.output_path}:")
                lines.extend(f"      {line}" for line in ws)
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


def export_stl(
    openscad_path, scad_file, output_file, export_format, param_args, extra_args=(), timeout=None
):
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
        timeout (float or None): Seconds after which OpenSCAD is killed and the case is
            reported as a failure with ``timed_out`` set.

    Every OpenSCAD message line on stderr (``WARNING:``, ``ECHO:``, ``ERROR:``,
    ``DEPRECATED:``, ``TRACE:``, ``EXPORT-WARNING:``, ...) is collected into
    ``ExportResult.warnings`` whether or not the export succeeded.

    OpenSCAD writes its output in place, so a failed or interrupted render would leave a
    truncated file behind. The render therefore goes to a ``.<name>.part<ext>`` sibling
    (same extension, so OpenSCAD still picks the format from it) and is moved onto
    ``output_file`` only when OpenSCAD exits 0; otherwise the partial file is removed.
    A present output file is thus a completed one, which is what ``skip_existing``
    relies on.

    Returns:
        ExportResult
    """
    name, ext = os.path.splitext(os.path.basename(output_file))
    partial = os.path.join(os.path.dirname(output_file), f".{name}.part{ext}")
    command = build_command(
        openscad_path, scad_file, partial, export_format, param_args, extra_args
    )
    log.debug("Running command: %s", format_command(command))
    start_time = time.perf_counter()
    proc = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True
    )
    _active.add(proc)
    timed_out = False
    try:
        try:
            _, stderr_bytes = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _signal_tree(proc, kill=True)
            _, stderr_bytes = proc.communicate()
    except KeyboardInterrupt:
        # Sequential mode: the interrupt lands here, in the main thread, while the
        # child is still running. (Worker threads never receive KeyboardInterrupt; the
        # parallel runner terminates their children instead.)
        _signal_tree(proc, kill=False)
        proc.wait(timeout=10)
        _remove_quietly(partial)
        log.warning("Interrupted: terminated the running OpenSCAD process.")
        raise
    finally:
        _active.discard(proc)
    duration = time.perf_counter() - start_time
    stderr = stderr_bytes.decode(errors="replace").strip()
    warnings = [line for line in stderr.splitlines() if line.startswith(_DIAGNOSTIC_PREFIXES)]
    returncode = proc.returncode
    ok = returncode == 0  # a killed process never exits 0
    if ok and os.path.exists(partial):
        os.replace(partial, output_file)
    else:
        _remove_quietly(partial)
    if timed_out:
        stderr = f"Timed out after {timeout:g} s"
    return ExportResult(
        name=name,
        output_path=output_file,
        ok=ok,
        returncode=returncode,
        stderr=stderr if not ok else "",
        duration=duration,
        format=ext.lstrip(".").lower(),
        command=command,
        warnings=warnings,
        timed_out=timed_out,
    )


# OpenSCAD's message groups, as printed at the start of a stderr line.
_DIAGNOSTIC_PREFIXES = (
    "WARNING:",
    "ECHO:",
    "DEPRECATED:",
    "TRACE:",
    "ERROR:",
    "PARSER-ERROR:",
    "UI-WARNING:",
    "UI-ERROR:",
    "EXPORT-WARNING:",
    "EXPORT-ERROR:",
    "FONT-WARNING:",
)
_CHATTER_PREFIXES = ("ECHO:", "TRACE:")


def build_command(openscad_path, scad_file, output_file, export_format, param_args, extra_args=()):
    """The OpenSCAD command line export_stl would run; see export_stl for the arguments."""
    command = [openscad_path, "-o", os.fspath(output_file)]
    if export_format:
        command.append(f"--export-format={export_format}")
    command += list(extra_args)
    command += list(param_args)
    command.append(os.fspath(scad_file))
    return command


def format_command(command):
    """Render an argv list as a shell-pasteable command line for this platform."""
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def _signal_tree(proc, kill):
    """Terminate (or, with kill=True, kill outright) the process and everything it started.

    OpenSCAD is rarely the direct child: the Linux AppImage runtime forks the real
    binary, and a .bat/.cmd or shell wrapper does the same. Signalling only the direct
    child would leave the render alive, holding our pipes, so export_stl starts each
    process in its own session and this signals the whole group: SIGTERM or SIGKILL on
    POSIX, taskkill /T (always forced) on Windows.
    """
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False
        )
        return
    sig = signal.SIGKILL if kill else signal.SIGTERM
    with contextlib.suppress(ProcessLookupError):  # already gone
        pgid = os.getpgid(proc.pid)
        if pgid == os.getpgrp():
            # Not a session leader (not started by export_stl): signalling the group
            # would hit ourselves. Fall back to the process alone.
            proc.send_signal(sig)
        else:
            os.killpg(pgid, sig)


def _tool_version():
    try:
        return metadata.version("openscad-batch-export")
    except metadata.PackageNotFoundError:
        return None


def _remove_quietly(path):
    with contextlib.suppress(FileNotFoundError):
        os.remove(path)


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
    skip_existing=False,
    dry_run=False,
    timeout=None,
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
        skip_existing (bool): Leave a case alone when its output file already exists
            (reported as skipped). Default is to overwrite.
        dry_run (bool): Build and log every command but run nothing and create nothing;
            each result carries the command it would have run.
        timeout (float or None): Seconds allowed per case; a case that exceeds it is
            killed and reported as a failure with ``timed_out`` set. The batch continues.

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
    if timeout is not None and (
        isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not timeout > 0
    ):
        raise ValueError(f"timeout must be a positive number of seconds, not {timeout!r}")
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
    if not dry_run:
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
            stl_flavour = export_format if fmt == "stl" else None
            if skip_existing and os.path.exists(output_file):
                log.info("Skipped (already present): %s", output_file)
                return (idx, formats.index(fmt)), ExportResult(
                    filename, output_file, True, None, "", 0.0, fmt, skipped=True
                )
            if dry_run:
                command = build_command(
                    engine.path, scad_file, output_file, stl_flavour, param_args, extra_args
                )
                log.info("Would run: %s", format_command(command))
                return (idx, formats.index(fmt)), ExportResult(
                    filename, output_file, True, None, "", 0.0, fmt, command=command
                )
            result = export_stl(
                engine.path,
                scad_file,
                output_file,
                stl_flavour,
                param_args,
                extra_args,
                timeout=timeout,
            )
        for line in result.warnings:
            level = (
                logging.WARNING if line.startswith(("WARNING:", "DEPRECATED:")) else logging.INFO
            )
            log.log(level, "%s: %s", result.output_path, line)
        if result.ok:
            log.info("Exported: %s in %.2f seconds.", result.output_path, result.duration)
        elif _active.closed:
            log.debug("Terminated: %s", result.output_path)
        elif dry_run:
            log.error("Would fail before running %s: %s", result.output_path, result.stderr)
        else:
            log.error(
                "Error exporting %s: %s (Time: %.2f seconds)",
                result.output_path,
                result.stderr,
                result.duration,
            )
        return (idx, formats.index(fmt)), result

    tasks = [(idx, params, fmt) for idx, params in cases for fmt in formats]
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
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
    inputs = {
        "scad_file": os.fspath(scad_file),
        "parameter_file": os.fspath(parameter_file),
        "output_folder": os.fspath(output_folder),
        "formats": formats,
        "export_format": export_format,
        "selection": selection,
        "jobs": jobs,
        "skip_existing": skip_existing,
        "timeout": timeout,
        "image_options": {k: v for k, v in (image_options or {}).items() if v},
    }
    return BatchResult(
        [result for _, result in indexed],
        total_duration,
        dry_run=dry_run,
        engine=engine,
        inputs=inputs,
        started_at=started_at,
    )


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
