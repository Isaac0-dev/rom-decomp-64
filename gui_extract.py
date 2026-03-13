#!/usr/bin/env python3

import os
import sys
import threading
import subprocess
import queue
import traceback
import urllib.parse
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any, cast

try:
    import sv_ttk
except ImportError:
    sv_ttk = cast(Any, None)

try:
    from tkinterdnd2 import TkinterDnD, DND_ALL, DND_FILES, DND_TEXT

    HAS_DND = True
    BaseWindow: Any = TkinterDnD.Tk
except ImportError:
    HAS_DND = False
    BaseWindow = tk.Tk
    DND_ALL = None
    DND_FILES = None
    DND_TEXT = None

import extract


class _QueueWriter:
    """File-like object that mirrors writes to a queue and an optional fallback stream."""

    def __init__(self, log_queue, fallback_stream=None, stop_event=None):
        self.log_queue = log_queue
        self.fallback_stream = fallback_stream
        self.stop_event = stop_event

    def write(self, data):
        if self.stop_event and self.stop_event.is_set():
            raise SystemExit("Extraction stopped by user")
        if not data:
            return
        try:
            self.log_queue.put(data)
        except Exception:
            pass
        if self.fallback_stream:
            try:
                self.fallback_stream.write(data)
            except Exception:
                pass

    def flush(self):
        if self.fallback_stream and hasattr(self.fallback_stream, "flush"):
            try:
                self.fallback_stream.flush()
            except Exception:
                pass


def _resource_path(*parts):
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, *parts)


def _runtime_base_dir():
    return os.path.dirname(os.path.abspath(sys.argv[0]))


class ExtractGUI(BaseWindow):
    def __init__(self):
        super().__init__()
        self.title("rom-decomp-64")
        self.geometry("720x480")

        # Apply the modern theme immediately after the root window is created.
        if sv_ttk is not None:
            for theme in ("adaptive", "dark", "light"):
                try:
                    set_theme = getattr(sv_ttk, "set_theme", None)
                    if set_theme:
                        set_theme(theme)
                    break
                except Exception as e:
                    if theme != "light":
                        print(f"Warning: Failed to set theme '{theme}'. Trying next fallback...")
                    else:
                        print(f"Warning: Failed to set theme '{theme}'. Error: {e}")

        self.worker = None
        self.log_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self.output_dir = None
        self.status_labels = {}
        self._components = [
            ("sequences", "Sequences"),
            ("level_scripts", "Level Scripts"),
            ("text", "Text Extraction"),
        ]

        self._build_ui()
        self._reset_statuses()
        self._poll_log_queue()

        # Enable DND on the root window
        if HAS_DND:
            cast(Any, self).drop_target_register(DND_FILES, DND_TEXT)
            cast(Any, self).dnd_bind("<<Drop>>", self._handle_drop)

            # X11 requires all layered widgets to be explicitly registered, otherwise they act as invisible shields.
            self.after(100, lambda: self._apply_dnd_recursively(self))

    def _apply_dnd_recursively(self, widget):
        """Recursively apply DND registration to literally every child widget."""
        if not HAS_DND:
            return

        try:
            cast(Any, widget).drop_target_register(DND_FILES, DND_TEXT)
            cast(Any, widget).dnd_bind("<<Drop>>", self._handle_drop)
        except Exception:
            pass

        for child in widget.winfo_children():
            self._apply_dnd_recursively(child)

    def _handle_drop(self, event):
        print(f"DEBUG _handle_drop fired with data: {repr(event.data)}")
        try:
            paths = self.tk.splitlist(event.data)
            print(f"DEBUG splitlist result: {paths}")
            if paths:
                path = paths[0].strip("{}")
                if path.startswith("file://"):
                    path = urllib.parse.unquote(path[7:])
                print(f"DEBUG parsed path: {path}")
                self.rom_var.set(path)
                self.after(50, self._start_extract)
        except Exception as e:
            print(f"DEBUG _handle_drop exception: {e}")
        return event.action

    def _build_ui(self):

        # ROM picker row
        rom_frame = ttk.Frame(self)
        rom_frame.pack(fill="x", padx=8, pady=6)
        ttk.Label(rom_frame, text="ROM file:").pack(side="left")
        self.rom_var = tk.StringVar(value=_resource_path("baserom.us.z64"))

        # If tkinterdnd2 is present, just use standard ttk.Entry but configure it dynamically
        rom_entry = ttk.Entry(rom_frame, textvariable=self.rom_var)

        rom_entry.pack(side="left", fill="x", expand=True, padx=6)

        # Make sure the entry is registered as a drop target
        if HAS_DND:
            try:
                cast(Any, rom_entry).drop_target_register(DND_FILES, DND_TEXT)
                cast(Any, rom_entry).dnd_bind("<<Drop>>", self._handle_drop)
            except Exception:
                pass

        ttk.Button(rom_frame, text="Browse", command=self._choose_rom).pack(side="left")

        # Control buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=8, pady=6)
        self.start_btn = ttk.Button(btn_frame, text="Start Extraction", command=self._start_extract)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(
            btn_frame, text="Stop", command=self._stop_extract, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=6)
        self.output_btn = ttk.Button(
            btn_frame, text="Open Output", command=self._open_output, state="disabled"
        )
        self.output_btn.pack(side="left", padx=6)
        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(btn_frame, textvariable=self.status_var).pack(side="left", padx=12)

        # Status overview
        status_frame = ttk.LabelFrame(self, text="Progress")
        status_frame.pack(fill="x", padx=8, pady=6)
        for key, label in self._components:
            row = ttk.Frame(status_frame)
            row.pack(fill="x", padx=4, pady=2)
            ttk.Label(row, text=f"{label}:").pack(side="left")
            val = tk.Label(row, text="", anchor="w")
            val.pack(side="left", padx=6)
            self.status_labels[key] = val

        # Log window
        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True, padx=8, pady=6)
        self.log_text = tk.Text(log_frame, wrap="word", state="normal")
        self.log_text.bind("<Key>", lambda e: "break")
        self.log_text.bind("<Button-1>", lambda e: self.log_text.focus_set())

        if HAS_DND:
            try:
                cast(Any, self.log_text).drop_target_register(DND_FILES, DND_TEXT)
                cast(Any, self.log_text).dnd_bind("<<Drop>>", self._handle_drop)
            except Exception:
                pass

        self.log_text.pack(fill="both", expand=True)
        ttk.Scrollbar(log_frame, command=self.log_text.yview).pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=lambda *args: None)

    # On linux, we can use zenity to open the more intuitive file browser
    def _run_native_linux_dialog(self, title, filetypes):
        if not sys.platform.startswith("linux"):
            return None
        cmd = ["zenity", "--file-selection", f"--title={title}"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=10)
            path = result.stdout.strip()
            if result.returncode == 0 and path:
                return path
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            pass
        return None

    def _choose_rom(self):
        path = self._run_native_linux_dialog(
            title="Select ROM", filetypes=[("Z64 ROM", "*.z64"), ("All files", "*.*")]
        )

        # Fall back to the cross-platform Tkinter dialog
        if not path:
            path = filedialog.askopenfilename(
                title="Select ROM", filetypes=[("Z64 ROM", "*.z64"), ("All files", "*.*")]
            )

        if path:
            self.rom_var.set(path)

    def _append_log(self, line):
        self.log_text.insert("end", line)
        self.log_text.see("end")

    def _reset_statuses(self):
        for key, _ in self._components:
            label = self.status_labels.get(key)
            if label:
                label.config(text="Not started", fg="gray")

    def _set_status(self, component, state):
        label = self.status_labels.get(component)
        if not label:
            return
        state_lower = state.lower()
        color = "black"
        display = state
        if state_lower in ("start", "processing"):
            display = "Processing"
            color = "blue"
        elif state_lower in ("done", "complete", "globals_done"):
            display = "Complete"
            color = "green"
        elif state_lower in ("skipped", "not_found"):
            display = "Skipped" if state_lower == "skipped" else "Not found"
            color = "gray"
        elif state_lower == "error":
            display = "Error"
            color = "red"
        label.config(text=display, fg=color)

    def _handle_status_line(self, line):
        stripped = line.strip()
        if not stripped.startswith("STATUS|"):
            return False
        parts = stripped.split("|")
        if len(parts) >= 3 and parts[0] == "STATUS":
            component = parts[1]
            state = "|".join(parts[2:])
            self._set_status(component, state)
            return True
        return False

    def _poll_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._handle_status_line(line)
                self._append_log(line)
                self.status_var.set("Running")
        except queue.Empty:
            pass
        # If worker finished, update status
        if self.worker and not self.worker.is_alive():
            if self._stop_event.is_set():
                self.status_var.set("Stopped")
            else:
                self.status_var.set("Done")
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.worker = None
        self.after(100, self._poll_log_queue)

    def _start_extract(self):
        if self.worker and self.worker.is_alive():
            return
        rom_path = self.rom_var.get().strip()
        if not rom_path:
            self.status_var.set("Choose a ROM first")
            return
        if not os.path.isfile(rom_path) and not (
            rom_path.startswith("http://") or rom_path.startswith("https://")
        ):
            self.status_var.set("ROM path invalid")
            return
        self.status_var.set("Starting...")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="enabled")
        self.output_btn.configure(state="normal")
        self._stop_event.clear()
        self._reset_statuses()

        # clear log widget
        self.log_text.delete("1.0", "end")

        # remove any pending log lines
        try:
            while True:
                self.log_queue.get_nowait()
        except queue.Empty:
            pass

        # track expected output directory for convenience
        base_dir = _runtime_base_dir()
        self.output_dir = os.path.join(base_dir, "out", os.path.basename(rom_path))

        # Spawn worker thread that calls extract in-process
        self.worker = threading.Thread(target=self._run_extract, args=(rom_path,), daemon=True)
        self.worker.start()

    def _run_extract(self, rom_path):
        # Mirror stdout/stderr into the GUI log queue while running extraction
        orig_out, orig_err = sys.stdout, sys.stderr
        proxy = _QueueWriter(self.log_queue, orig_out, self._stop_event)
        sys.stdout = proxy
        sys.stderr = proxy
        try:
            extract.main(
                filename_override=rom_path,
                output_status_override=True,
                called_by_main_override=False,
            )
        except SystemExit as e:
            # Respect explicit sys.exit from extract but surface exit code
            self.log_queue.put(f"Extraction exited with code: {getattr(e, 'code', 0)}\n")
        except Exception:
            tb = traceback.format_exc()
            self.log_queue.put(tb)
        finally:
            sys.stdout = orig_out
            sys.stderr = orig_err
            # Flush a newline to keep log rendering clean
            try:
                self.log_queue.put("\n")
            except Exception:
                pass

    def _stop_extract(self):
        self._stop_event.set()
        self.stop_btn.configure(state="disabled")
        for key, _ in self._components:
            label = self.status_labels.get(key)
            if label and label.cget("text") == "Processing":
                label.config(text="Stopped", fg="gray")

    def _open_output(self):
        # Prefer the most recent run's directory; fallback to base "out"
        path = self.output_dir
        if not path:
            path = os.path.join(_runtime_base_dir(), "out")
        os.makedirs(path, exist_ok=True)
        try:
            if sys.platform.startswith("darwin"):
                subprocess.Popen(["open", path])
            elif os.name == "nt":
                startfile = getattr(os, "startfile", None)
                if startfile:
                    startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self.status_var.set(f"Open failed: {e}")


if __name__ == "__main__":
    app = ExtractGUI()
    app.mainloop()
