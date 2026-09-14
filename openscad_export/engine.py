"""Finding the OpenSCAD executable and learning what it can do."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

log = logging.getLogger("openscad_export")

ENV_VAR = "OPENSCAD"

# Where the official installers put the executable when it is not on PATH.
PLATFORM_DEFAULTS = {
    "win32": [
        r"C:\Program Files\OpenSCAD\openscad.com",
        r"C:\Program Files\OpenSCAD\openscad.exe",
        r"C:\Program Files (x86)\OpenSCAD\openscad.exe",
    ],
    "darwin": ["/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"],
}

_VERSION_RE = re.compile(r"OpenSCAD version (\S+)")
# The -o paragraph of --help: "the file extension specifies the type: stl, off, ..."
_FORMATS_RE = re.compile(r"the type:\s*([a-z0-9]+(?:\s*,\s*[a-z0-9]+)*)", re.IGNORECASE)


class OpenSCADError(Exception):
    """OpenSCAD could not be found, started, or understood."""


class OpenSCADNotFound(OpenSCADError):
    """No usable OpenSCAD executable was found."""


@dataclass(frozen=True)
class Engine:
    """A resolved OpenSCAD executable and its capabilities."""

    path: str
    version: str
    version_tuple: tuple[int, ...]
    export_formats: frozenset[str] | None = None
    """Output extensions this build accepts for ``-o``, or None if --help was unreadable."""

    @property
    def supports_parameter_sets(self) -> bool:
        """``-p FILE -P SET`` (Customizer parameter sets), added in 2019.05."""
        return self.version_tuple >= (2019, 5)


def find_openscad(explicit: str | None = None) -> str:
    """
    Resolve the OpenSCAD executable to run.

    Order: ``explicit`` (a path or a command name), then ``$OPENSCAD``, then
    ``openscad`` on PATH, then the platform's default install location. An explicit
    value or environment variable that does not resolve is an error rather than a
    fallback, since the user asked for that one.

    Raises:
        OpenSCADNotFound: With a message listing what was tried.
    """
    if explicit:
        candidates = [(f"--openscad-path {explicit!r}", explicit)]
    elif os.environ.get(ENV_VAR):
        candidates = [(f"${ENV_VAR}={os.environ[ENV_VAR]!r}", os.environ[ENV_VAR])]
    else:
        candidates = [("'openscad' on PATH", "openscad")]
        candidates += [(p, p) for p in PLATFORM_DEFAULTS.get(sys.platform, [])]

    for _, candidate in candidates:
        resolved = _resolve(candidate)
        if resolved:
            return resolved
    tried = ", ".join(label for label, _ in candidates)
    hint = f"Install OpenSCAD, add it to PATH, or pass --openscad-path / set ${ENV_VAR}."
    for _, candidate in candidates:
        if os.path.dirname(candidate) and os.path.isfile(candidate):
            raise OpenSCADNotFound(f"{candidate!r} exists but is not executable. {hint}")
    raise OpenSCADNotFound(f"OpenSCAD executable not found (tried {tried}). {hint}")


def _resolve(candidate: str) -> str | None:
    if os.path.dirname(candidate):
        return candidate if os.path.isfile(candidate) and os.access(candidate, os.X_OK) else None
    return shutil.which(candidate)


def parse_version(text: str) -> tuple[str, tuple[int, ...]]:
    """
    Extract the version from ``openscad --version`` output.

    Returns the version string as printed and its leading numeric components,
    e.g. ``("2021.01", (2021, 1))`` or ``("2026.09.05", (2026, 9, 5))``.

    Raises:
        OpenSCADError: If no version line is present.
    """
    match = _VERSION_RE.search(text)
    if not match:
        raise OpenSCADError(f"Could not parse OpenSCAD version from: {text.strip()!r}")
    version = match.group(1)
    numbers = []
    for part in version.split("."):
        if not part.isdigit():
            break
        numbers.append(int(part))
    if not numbers:
        raise OpenSCADError(f"Unrecognised OpenSCAD version {version!r}")
    return version, tuple(numbers)


def parse_export_formats(help_text: str) -> frozenset[str] | None:
    """
    Extract the ``-o`` output extensions from ``openscad --help`` output, or None if
    the list is not where this build's help puts it.
    """
    match = _FORMATS_RE.search(" ".join(help_text.split()))
    if not match:
        return None
    return frozenset(token.strip().lower() for token in match.group(1).split(","))


def detect_engine(explicit: str | None = None) -> Engine:
    """
    Find OpenSCAD and ask it for its version.

    Raises:
        OpenSCADNotFound: If no executable resolves.
        OpenSCADError: If it cannot be run or its version output is not understood.
    """
    path = find_openscad(explicit)
    try:
        completed = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise OpenSCADError(f"Could not run {path!r}: {e}") from e
    if completed.returncode != 0:
        raise OpenSCADError(
            f"{path!r} --version exited with {completed.returncode}: {completed.stderr.strip()}"
        )
    # OpenSCAD prints its version on stderr; look at both streams.
    version, version_tuple = parse_version(completed.stdout + completed.stderr)
    log.info("Using OpenSCAD version %s at %s", version, path)
    export_formats = None
    try:
        help_run = subprocess.run(
            [path, "--help"],
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=60,
        )
        export_formats = parse_export_formats(help_run.stdout + help_run.stderr)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if export_formats is None:
        log.debug("Could not read the supported output formats from --help; not validating.")
    return Engine(path, version, version_tuple, export_formats)
