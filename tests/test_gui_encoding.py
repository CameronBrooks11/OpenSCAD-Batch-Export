"""The GUI's parameter-file encoding field.

The widgets need a display and CI has none, so these drive the methods behind them with a
stand-in for the window. That covers the part with behaviour -- which encoding is resolved,
and whether it reaches the three calls -- and not the layout.
"""

import json

import pytest

from scadbatch import gui as gui_module
from scadbatch.gui import OpenSCADBatchExporterGUI as Gui
from scadbatch.params import DEFAULT_ENCODING


class Field:
    """Stands in for a tk.StringVar."""

    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


class FakeGui:
    """Stands in for the window: the attributes the worker methods touch, and nothing else."""

    def __init__(self, encoding=""):
        self.parameter_encoding = Field(encoding)
        self.log = []
        self.status_label = self
        self.enabled = False

    def append_log(self, message):
        self.log.append(message)

    def enable_controls(self):
        self.enabled = True

    def config(self, **kwargs):
        pass


@pytest.fixture
def no_dialogs(monkeypatch):
    """Collect what would have been shown, so nothing tries to open a window."""
    shown = []
    for kind in ("showerror", "showinfo"):
        monkeypatch.setattr(
            gui_module.messagebox,
            kind,
            lambda title, message, kind=kind: shown.append((kind, message)),
        )
    return shown


def test_a_blank_field_means_the_default_encoding(no_dialogs):
    """A user who never touches the field gets what the command line gives without
    --encoding."""
    assert Gui.chosen_encoding(FakeGui("")) == DEFAULT_ENCODING
    assert Gui.chosen_encoding(FakeGui("   ")) == DEFAULT_ENCODING
    assert no_dialogs == []


def test_a_named_encoding_is_used_as_written(no_dialogs):
    assert Gui.chosen_encoding(FakeGui("cp1252")) == "cp1252"
    assert no_dialogs == []


def test_an_unknown_encoding_is_refused_before_anything_runs(no_dialogs):
    """Returning None stops the caller, so the user sees the dialog rather than a traceback
    from a worker thread partway through a batch."""
    assert Gui.chosen_encoding(FakeGui("latin-9000")) is None

    (kind, message) = no_dialogs[0]
    assert kind == "showerror"
    assert "latin-9000" in message and "no such codec" in message


def test_csv_to_json_reads_the_chosen_encoding(tmp_path, no_dialogs):
    src = tmp_path / "p.csv"
    src.write_bytes("exported_filename,label\na,café\n".encode("cp1252"))
    out = tmp_path / "p.json"

    Gui.run_csv_to_json(FakeGui(), str(src), str(out), "cp1252")

    assert json.loads(out.read_text(encoding="utf-8"))["parameterSets"]["a"]["label"] == "café"


def test_json_to_csv_reads_the_chosen_encoding(tmp_path, no_dialogs):
    src = tmp_path / "p.json"
    # ensure_ascii, the default, would escape the accent and leave a pure-ASCII file, where
    # reading as cp1252 and as UTF-8 are the same thing and this would prove nothing.
    src.write_bytes(
        json.dumps({"parameterSets": {"a": {"label": "café"}}}, ensure_ascii=False).encode("cp1252")
    )
    out = tmp_path / "p.csv"

    Gui.run_json_to_csv(FakeGui(), str(src), str(out), "cp1252")

    assert "café" in out.read_text(encoding="utf-8")


def test_a_conversion_in_the_wrong_encoding_is_reported_not_raised(tmp_path, no_dialogs):
    src = tmp_path / "p.csv"
    src.write_bytes("exported_filename,label\na,café\n".encode("cp1252"))
    window = FakeGui()

    Gui.run_csv_to_json(window, str(src), str(tmp_path / "p.json"), DEFAULT_ENCODING)

    assert no_dialogs[0][0] == "showerror"
    assert "not valid utf-8-sig text" in no_dialogs[0][1]
    assert window.enabled, "the controls must come back after a failed conversion"


def test_export_passes_the_encoding_to_batch_export(monkeypatch, no_dialogs):
    captured = {}

    def fake_batch_export(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop here")  # nothing to summarise

    monkeypatch.setattr(gui_module, "batch_export", fake_batch_export)

    Gui.run_export(FakeGui(), "m.scad", "p.csv", "out", None, "binstl", None, False, "cp1252")

    assert captured["encoding"] == "cp1252"


@pytest.fixture
def window():
    """A real Tk root, where one can be had. Nothing above this needs a display; this does."""
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no display: {e}")
    root.withdraw()
    yield root
    root.destroy()


def test_the_window_builds_with_the_encoding_field(window):
    """The stand-in above cannot see a layout mistake -- a duplicated grid cell, a widget
    left out of state_widgets. CI runs the suite under xvfb on one job, which is where this
    one runs; everywhere else it skips."""
    app = Gui(window)

    assert app.parameter_encoding.get() == ""  # blank by default, so UTF-8 by default
    assert app.encoding_entry in app.state_widgets  # greyed out with the rest during a run
    placed = app.encoding_entry.grid_info()
    assert (int(placed["row"]), int(placed["column"])) == (2, 1)
    # the rows below it moved down rather than landing on top of it
    assert int(app.output_entry.grid_info()["row"]) == 3
    assert int(app.openscad_entry.grid_info()["row"]) == 4
