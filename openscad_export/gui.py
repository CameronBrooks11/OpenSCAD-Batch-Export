# openscad_export/gui.py

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import os
import sys
import subprocess
from datetime import datetime

# Import functions from export.py
import openscad_export.export as export

class OpenSCADBatchExporterGUI:
    def __init__(self, master):
        self.master = master
        master.title("OpenSCAD Batch Exporter")
        master.geometry("1000x750")
        master.resizable(True, True)

        # Configure grid for the main window
        master.columnconfigure(0, weight=1)
        master.columnconfigure(1, weight=3)
        master.rowconfigure(0, weight=1)

        # Main Frame
        main_frame = ttk.Frame(master, padding="10 10 10 10")
        main_frame.grid(row=0, column=0, sticky=tk.NSEW)

        # Configure grid within the main frame
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(10, weight=1)

        # Variables
        self.scad_file = tk.StringVar()
        self.parameter_file = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.openscad_path = tk.StringVar(value="openscad")
        self.export_format = tk.StringVar(value="binstl")
        self.selection = tk.StringVar()
        self.sequential = tk.BooleanVar()
        self.export_thread = None
        self.stop_event = threading.Event()

        # Lists to keep track of widgets that support 'state'
        self.state_widgets = []

        # === Input Section Frame ===
        input_frame = ttk.LabelFrame(
            main_frame, text="Input Configuration", padding="10 10 10 10"
        )
        input_frame.grid(row=0, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)

        # Configure grid within input_frame
        for i in range(4):
            input_frame.columnconfigure(i, weight=1)

        # SCAD File
        ttk.Label(input_frame, text="OpenSCAD File:").grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.scad_entry = ttk.Entry(input_frame, textvariable=self.scad_file)
        self.scad_entry.grid(
            row=0, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5
        )
        self.state_widgets.append(self.scad_entry)
        scad_browse_btn = ttk.Button(
            input_frame, text="Browse", command=self.browse_scad
        )
        scad_browse_btn.grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        self.state_widgets.append(scad_browse_btn)

        # Parameter File
        ttk.Label(input_frame, text="Parameter File (CSV/JSON):").grid(
            row=1, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.param_entry = ttk.Entry(input_frame, textvariable=self.parameter_file)
        self.param_entry.grid(
            row=1, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5
        )
        self.state_widgets.append(self.param_entry)
        param_browse_btn = ttk.Button(
            input_frame, text="Browse", command=self.browse_parameter
        )
        param_browse_btn.grid(row=1, column=3, sticky=tk.W, padx=5, pady=5)
        self.state_widgets.append(param_browse_btn)

        # Output Folder
        ttk.Label(input_frame, text="Output Folder:").grid(
            row=2, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.output_entry = ttk.Entry(input_frame, textvariable=self.output_folder)
        self.output_entry.grid(
            row=2, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5
        )
        self.state_widgets.append(self.output_entry)
        output_browse_btn = ttk.Button(
            input_frame, text="Browse", command=self.browse_output
        )
        output_browse_btn.grid(row=2, column=3, sticky=tk.W, padx=5, pady=5)
        self.state_widgets.append(output_browse_btn)

        # OpenSCAD Path
        ttk.Label(input_frame, text="OpenSCAD Path:").grid(
            row=3, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.openscad_entry = ttk.Entry(input_frame, textvariable=self.openscad_path)
        self.openscad_entry.grid(
            row=3, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5
        )
        self.state_widgets.append(self.openscad_entry)
        openscad_browse_btn = ttk.Button(
            input_frame, text="Browse", command=self.browse_openscad
        )
        openscad_browse_btn.grid(row=3, column=3, sticky=tk.W, padx=5, pady=5)
        self.state_widgets.append(openscad_browse_btn)

        # === Settings Section Frame ===
        settings_frame = ttk.LabelFrame(
            main_frame, text="Export Settings", padding="10 10 10 10"
        )
        settings_frame.grid(row=1, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)

        # Configure grid within settings_frame
        settings_frame.columnconfigure(1, weight=1)

        # Export Format
        ttk.Label(settings_frame, text="Export Format:").grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=5
        )
        export_format_menu = ttk.Combobox(
            settings_frame,
            textvariable=self.export_format,
            values=["asciistl", "binstl"],
            state="readonly",
        )
        export_format_menu.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        export_format_menu.current(1)  # Default to binstl
        self.state_widgets.append(export_format_menu)

        # Selection
        ttk.Label(settings_frame, text="Selection:").grid(
            row=1, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.selection_entry = ttk.Entry(settings_frame, textvariable=self.selection)
        self.selection_entry.grid(
            row=1, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5
        )
        self.state_widgets.append(self.selection_entry)
        selection_info = (
            "e.g., '0-5', '1-3,7,10-12', 'every:2 in 0-10', 'from:5', 'up_to:4'"
        )
        ttk.Label(settings_frame, text=selection_info, foreground="gray").grid(
            row=1, column=3, sticky=tk.W, padx=5, pady=5
        )

        # Sequential Processing
        self.seq_check = ttk.Checkbutton(
            settings_frame, text="Sequential Processing", variable=self.sequential
        )
        self.seq_check.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        self.state_widgets.append(self.seq_check)

        # === Progress and Status Frame ===
        progress_frame = ttk.Frame(main_frame, padding="10 10 10 10")
        progress_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)

        # Progress Bar
        self.progress = ttk.Progressbar(
            progress_frame, orient="horizontal", mode="determinate"
        )
        self.progress.grid(row=0, column=0, sticky=tk.EW, padx=5, pady=5)
        progress_frame.columnconfigure(0, weight=1)

        # Status Label
        self.status_label = ttk.Label(
            progress_frame, text="Status: Idle", foreground="blue"
        )
        self.status_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)

        # === Buttons Frame ===
        buttons_frame = ttk.Frame(main_frame, padding="10 10 10 10")
        buttons_frame.grid(row=3, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)

        # Configure grid within buttons_frame
        for col in range(5):
            buttons_frame.columnconfigure(col, weight=1)

        # Export Button
        export_btn = ttk.Button(buttons_frame, text="Export", command=self.start_export)
        export_btn.grid(row=0, column=0, padx=5, pady=5, sticky=tk.EW)
        self.state_widgets.append(export_btn)

        # Convert CSV to JSON Button
        convert_csv_json_btn = ttk.Button(
            buttons_frame, text="Convert CSV to JSON", command=self.convert_csv_to_json
        )
        convert_csv_json_btn.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        self.state_widgets.append(convert_csv_json_btn)

        # Convert JSON to CSV Button
        convert_json_csv_btn = ttk.Button(
            buttons_frame, text="Convert JSON to CSV", command=self.convert_json_to_csv
        )
        convert_json_csv_btn.grid(row=0, column=2, padx=5, pady=5, sticky=tk.EW)
        self.state_widgets.append(convert_json_csv_btn)

        # Clear Log Button
        clear_log_btn = ttk.Button(
            buttons_frame, text="Clear Log", command=self.clear_log
        )
        clear_log_btn.grid(row=0, column=3, padx=5, pady=5, sticky=tk.EW)
        self.state_widgets.append(clear_log_btn)

        # Help Button
        help_btn = ttk.Button(buttons_frame, text="Help", command=self.show_help)
        help_btn.grid(row=0, column=4, padx=5, pady=5, sticky=tk.EW)
        # Do NOT append help_btn to self.state_widgets to keep it enabled during processing

        # === Log Output Frame ===
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="10 10 10 10")
        log_frame.grid(row=4, column=0, columnspan=2, sticky=tk.NSEW, padx=5, pady=5)

        # Configure grid within log_frame
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # Log Text Widget
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 5), pady=5)

        # Log Scrollbar
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky=tk.NS, pady=5)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def browse_scad(self):
        file_path = filedialog.askopenfilename(filetypes=[("OpenSCAD Files", "*.scad")])
        if file_path:
            self.scad_file.set(file_path)

    def browse_parameter(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv"), ("JSON Files", "*.json")]
        )
        if file_path:
            self.parameter_file.set(file_path)

    def browse_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder.set(folder)

    def browse_openscad(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Executable Files", "*.exe"), ("All Files", "*.*")]
        )
        if file_path:
            self.openscad_path.set(file_path)

    def append_log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_message = f"[{timestamp}] {message}"
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, full_message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def disable_controls(self):
        for widget in self.state_widgets:
            try:
                widget.state(["disabled"])
            except AttributeError:
                try:
                    widget.config(state=tk.DISABLED)
                except tk.TclError:
                    pass  # Widget does not support 'state'

    def enable_controls(self):
        for widget in self.state_widgets:
            try:
                if isinstance(widget, ttk.Combobox):
                    widget.state(["!disabled"])
                else:
                    widget.state(["!disabled"])
            except AttributeError:
                try:
                    if isinstance(widget, ttk.Combobox):
                        widget.config(state="readonly")
                    else:
                        widget.config(state=tk.NORMAL)
                except tk.TclError:
                    pass  # Widget does not support 'state'

    def is_executable(self, path):
        """
        Checks if the provided path is executable.
        """
        return os.path.isfile(path) and os.access(path, os.X_OK)

    def start_export(self):
        # Validate inputs
        scad = self.scad_file.get()
        param = self.parameter_file.get()
        output = self.output_folder.get()
        openscad = self.openscad_path.get()
        fmt = self.export_format.get()
        sel = self.selection.get()
        seq = self.sequential.get()

        if not scad or not os.path.isfile(scad):
            messagebox.showerror(
                "Error", "Please select a valid OpenSCAD (.scad) file."
            )
            return
        if not param or not os.path.isfile(param):
            messagebox.showerror(
                "Error", "Please select a valid parameter file (CSV or JSON)."
            )
            return
        if not output:
            messagebox.showerror("Error", "Please select an output folder.")
            return

        # Validate OpenSCAD Path
        if openscad.lower() != "openscad":
            if not os.path.isfile(openscad):
                messagebox.showerror(
                    "Error", "Please select a valid OpenSCAD executable."
                )
                return
            # Additionally, check if the executable can be run
            if not self.is_executable(openscad):
                messagebox.showerror(
                    "Error", "The selected OpenSCAD path is not executable."
                )
                return

        # Disable controls and reset progress
        self.disable_controls()
        self.progress["value"] = 0
        self.status_label.config(text="Status: Exporting...", foreground="green")
        self.append_log("Starting batch export...")

        # Start export in a separate thread to keep GUI responsive
        self.export_thread = threading.Thread(
            target=self.run_export,
            args=(scad, param, output, openscad, fmt, sel, seq),
            daemon=True,
        )
        self.export_thread.start()
        self.master.after(100, self.update_progress)

    def run_export(self, scad, param, output, openscad, fmt, sel, seq):
        try:
            # Redirect stdout to capture print statements
            original_stdout = sys.stdout
            sys.stdout = ExportLogger(self)
            export.batch_export(scad, param, output, openscad, fmt, sel, seq)
        except Exception as e:
            self.append_log(f"An error occurred: {str(e)}")
            messagebox.showerror("Error", f"An error occurred during export:\n{str(e)}")
        finally:
            sys.stdout = original_stdout
            self.enable_controls()
            self.status_label.config(text="Status: Idle", foreground="blue")
            self.append_log("Batch export completed.")

    def update_progress(self):
        if self.export_thread.is_alive():
            # Update the progress bar to indeterminate mode
            self.progress.config(mode="indeterminate")
            if not self.progress["value"]:
                self.progress.start(10)
            self.master.after(100, self.update_progress)
        else:
            self.progress.stop()
            self.progress.config(mode="determinate")
            self.progress["value"] = 100

    def convert_csv_to_json(self):
        # Prompt user to select CSV file
        csv_file = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if not csv_file:
            return
        # Prompt user to select JSON output file
        json_file = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON Files", "*.json")]
        )
        if not json_file:
            return

        # Disable controls during conversion
        self.disable_controls()
        self.append_log(f"Converting CSV to JSON: {csv_file} -> {json_file}")
        self.status_label.config(
            text="Status: Converting CSV to JSON...", foreground="orange"
        )

        # Start conversion in a separate thread
        threading.Thread(
            target=self.run_csv_to_json, args=(csv_file, json_file), daemon=True
        ).start()

    def run_csv_to_json(self, csv_file, json_file):
        try:
            export.csv_to_json(csv_file, json_file)
            self.append_log("CSV to JSON conversion completed successfully.")
            messagebox.showinfo(
                "Success", "CSV to JSON conversion completed successfully."
            )
        except Exception as e:
            self.append_log(f"Conversion failed: {str(e)}")
            messagebox.showerror("Error", f"CSV to JSON conversion failed:\n{str(e)}")
        finally:
            self.enable_controls()
            self.status_label.config(text="Status: Idle", foreground="blue")

    def convert_json_to_csv(self):
        # Prompt user to select JSON file
        json_file = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if not json_file:
            return
        # Prompt user to select CSV output file
        csv_file = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV Files", "*.csv")]
        )
        if not csv_file:
            return

        # Disable controls during conversion
        self.disable_controls()
        self.append_log(f"Converting JSON to CSV: {json_file} -> {csv_file}")
        self.status_label.config(
            text="Status: Converting JSON to CSV...", foreground="orange"
        )

        # Start conversion in a separate thread
        threading.Thread(
            target=self.run_json_to_csv, args=(json_file, csv_file), daemon=True
        ).start()

    def run_json_to_csv(self, json_file, csv_file):
        try:
            export.json_to_csv(json_file, csv_file)
            self.append_log("JSON to CSV conversion completed successfully.")
            messagebox.showinfo(
                "Success", "JSON to CSV conversion completed successfully."
            )
        except Exception as e:
            self.append_log(f"Conversion failed: {str(e)}")
            messagebox.showerror("Error", f"JSON to CSV conversion failed:\n{str(e)}")
        finally:
            self.enable_controls()
            self.status_label.config(text="Status: Idle", foreground="blue")

    def show_help(self):
        # Start a thread to fetch help text
        threading.Thread(target=self.fetch_and_display_help, daemon=True).start()

    def fetch_and_display_help(self):
        help_text = ""
        commands = [
            ["openscad-export", "--help"],
            ["openscad-export", "export", "--help"],
            ["openscad-export", "csv2json", "--help"],
            ["openscad-export", "json2csv", "--help"],
            ["openscad-export", "gui", "--help"],
        ]

        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                )
                help_text += f"{' '.join(cmd)}:\n{result.stdout}\n"
            except subprocess.CalledProcessError as e:
                help_text += f"{' '.join(cmd)} Error:\n{e.stderr}\n"
            except FileNotFoundError:
                help_text += f"Error: {' '.join(cmd)} command not found. Please ensure it is installed and in your system's PATH.\n"

        # Schedule the GUI update in the main thread
        self.master.after(0, self.display_help_window, help_text)

    def display_help_window(self, help_text):
        help_window = tk.Toplevel(self.master)
        help_window.title("Help")
        help_window.geometry("800x600")
        help_window.resizable(True, True)

        # Configure grid
        help_window.columnconfigure(0, weight=1)
        help_window.rowconfigure(0, weight=1)

        # Text widget with scrollbar
        text = tk.Text(
            help_window, wrap=tk.WORD, state=tk.NORMAL, font=("Consolas", 10)
        )
        text.insert(tk.END, help_text)
        text.configure(state=tk.DISABLED)
        text.grid(row=0, column=0, sticky=tk.NSEW, padx=10, pady=10)

        scrollbar = ttk.Scrollbar(help_window, command=text.yview)
        scrollbar.grid(row=0, column=1, sticky=tk.NS, pady=10)
        text.configure(yscrollcommand=scrollbar.set)


class ExportLogger:
    """
    A simple logger class to redirect stdout to the GUI log.
    """

    def __init__(self, gui):
        self.gui = gui

    def write(self, message):
        if message.strip():
            self.gui.append_log(message.strip())

    def flush(self):
        pass  # No action needed


def main():
    root = tk.Tk()
    # Apply a modern theme using ttk (optional)
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    elif "clam" in style.theme_names():
        style.theme_use("clam")
    else:
        style.theme_use(style.theme_names()[0])  # Default to the first available theme
    gui = OpenSCADBatchExporterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
