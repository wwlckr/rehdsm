"""Graphical interface (tkinter) of the save manager.

Everything is read-only except deleting slots.
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .dnd import enable_file_drop
from .model import SaveFile, SaveFormatError, find_gog_saves, find_steam_saves, format_time, gog_save_dir

APP_DIR = Path(sys.argv[0]).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
BACKUP_DIR = APP_DIR / "backups"

BG = "#16130f"
PANEL = "#211d18"
FIELD = "#2c2721"
FG = "#e9e4da"
MUTED = "#a39a8c"
ACCENT = "#c8a25a"
SLOT_COLORS = {  # same colours as the in-game "Load" menu
    "very_easy": "#ff4dff",
    "easy": "#45e845",
    "normal": "#f2f2f2",
    "hard": "#ff4545",
    "real_survival": "#6f8dff",
    "invisible_enemy": "#ffa62b",
    "empty": "#8a8276",
}
FONT = ("Segoe UI", 10)
WINDOW_WIDTH, WINDOW_HEIGHT = 980, 540
MAX_PATH_CHARS = 100
RIGHT_PAD = 13  # width of the empty last column of the slot list (measured: equal left/right margins)


def work_area(root: tk.Tk) -> tuple[int, int, int, int]:
    """Usable screen area (left, top, right, bottom): the screen minus the taskbar."""
    try:
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def centered_position(root: tk.Tk) -> tuple[int, int]:
    """Top-left corner that centres the window (title bar and borders included) in the work area."""
    left, top, right, bottom = work_area(root)
    outer_w, outer_h = WINDOW_WIDTH + 16, WINDOW_HEIGHT + 39  # approx. borders and title bar
    x = left + max(0, (right - left - outer_w) // 2)
    y = top + max(0, (bottom - top - outer_h) // 2)  # never above the top: the title bar stays reachable
    return x, y


class SaveManagerApp:
    def __init__(self, root: tk.Tk, initial: str | None = None):
        self.root = root
        self.save: SaveFile | None = None
        self.current: int | None = None  # index 0-7 of the selected slot

        root.title(f"RE HD Remaster · Save Manager {__version__}")
        x, y = centered_position(root)
        root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")
        root.resizable(False, False)  # fixed size: the layout is designed for it
        icon = Path(__file__).with_name("data") / "icon.ico"  # optional: used once the icon exists
        if icon.exists():
            try:
                root.iconbitmap(default=str(icon))
            except tk.TclError:
                pass
        root.configure(bg=BG)
        self._style()
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Control-s>", lambda e: self.save_file())
        root.bind("<Control-o>", lambda e: self.open_dialog())
        root.bind("<Delete>", lambda e: self.delete_slot())
        self.drop_enabled = enable_file_drop(root, self.on_drop)

        if initial:
            self.load(Path(initial))
        else:
            self.root.after(100, self.startup_detect)

    # ------------------------------------------------------------------ UI
    def _style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=FG, font=FONT, fieldbackground=FIELD,
                     bordercolor="#3a342c", lightcolor=PANEL, darkcolor=PANEL)
        st.configure("Panel.TFrame", background=PANEL)
        st.configure("Panel.TLabel", background=PANEL, foreground=FG)
        st.configure("Value.TLabel", background=PANEL, foreground=FG, font=("Segoe UI", 11))
        st.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        st.configure("Bar.TLabel", background=BG, foreground=MUTED)
        st.configure("Title.TLabel", background=BG, foreground=ACCENT, font=("Segoe UI Semibold", 15))
        st.configure("Slot.TLabel", background=PANEL, font=("Segoe UI Semibold", 16))
        st.configure("TButton", background="#3a342c", foreground=FG, padding=(12, 6), borderwidth=0)
        st.map("TButton", background=[("active", "#4a4238"), ("disabled", "#2a251f")],
               foreground=[("disabled", "#6d665b")])
        st.configure("Accent.TButton", background=ACCENT, foreground="#1a1712")
        st.map("Accent.TButton", background=[("active", "#ddb76c"), ("disabled", "#5a4d33")])
        st.configure("Danger.TButton", background="#6b2a24", foreground=FG)
        st.map("Danger.TButton", background=[("active", "#8a362e"), ("disabled", "#2a251f")])
        st.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                     rowheight=34, borderwidth=0, font=("Segoe UI", 11))
        st.configure("Treeview.Heading", background="#2c2721", foreground=MUTED,
                     font=("Segoe UI Semibold", 9), relief="flat", padding=(6, 4))
        # Only the selected background is mapped. Tk 8.6.9 (Python 3.8, used for the Windows 7 builds) also maps
        # foreground/background for "!selected" rows by default, which hides the per-slot tag colours.
        st.map("Treeview", background=[("selected", "#3d3529")], foreground=[])
        st.map("Treeview.Heading", background=[("active", "#2c2721")])

    def _build(self):
        top = ttk.Frame(self.root, padding=(16, 12, 16, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Resident Evil HD Remaster — Saves", style="Title.TLabel").pack(side="left")
        self.btn_save = ttk.Button(top, text="Save", style="Accent.TButton", command=self.save_file)
        self.btn_save.pack(side="right")
        ttk.Button(top, text="Save as…", command=self.save_as).pack(side="right", padx=6)
        ttk.Button(top, text="Open…", command=self.open_dialog).pack(side="right")
        ttk.Button(top, text="Find on GOG", command=self.find_gog).pack(side="right", padx=6)
        ttk.Button(top, text="Find on Steam", command=lambda: self.auto_detect(explicit=True)).pack(side="right")

        self.path_var = tk.StringVar(value="No file open")
        ttk.Label(self.root, textvariable=self.path_var, style="Bar.TLabel", padding=(16, 0)).pack(fill="x")

        body = ttk.Frame(self.root, padding=(16, 10))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2, minsize=340)
        body.rowconfigure(0, weight=1)

        # --- slot list
        # "pad" is an empty trailing column so that the play time keeps the same distance from the
        # right edge as the slot number has from the left edge (the "#" column is centred).
        cols = ("slot", "char", "count", "diff", "time", "pad")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", selectmode="browse", height=8)
        for col, text, width, anchor in (
            ("slot", "#", 42, "center"), ("char", "Character", 90, "w"), ("count", "Saves", 60, "center"),
            ("diff", "Difficulty / mode", 210, "w"), ("time", "Play time", 90, "e"), ("pad", "", RIGHT_PAD, "e")):
            self.tree.heading(col, text=text, anchor=anchor)
            self.tree.column(col, width=width, minwidth=width, anchor=anchor, stretch=col == "diff")
        for key, color in SLOT_COLORS.items():
            self.tree.tag_configure(key, foreground=color)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # --- detail panel (read-only)
        panel = ttk.Frame(body, style="Panel.TFrame", padding=18)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.columnconfigure(1, weight=1)

        self.slot_title = ttk.Label(panel, text="Select a slot", style="Slot.TLabel")
        self.slot_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        self.info_vars: dict[str, tk.StringVar] = {}
        self.info_rows: dict[str, tuple[ttk.Label, ttk.Label]] = {}
        fields = (("mode", "Mode"), ("diff", "Difficulty"), ("once", "Once again.."),
                  ("odz", "One Dangerous Zombie"), ("costume", "Costume"),
                  ("count", "Saves"), ("time", "Play time"), ("health", "Health"))
        for r, (key, label) in enumerate(fields, start=1):
            name = ttk.Label(panel, text=label, style="Muted.TLabel")
            name.grid(row=r, column=0, sticky="w", pady=3, padx=(0, 18))
            var = tk.StringVar(value="—")
            value = ttk.Label(panel, textvariable=var, style="Value.TLabel")
            value.grid(row=r, column=1, sticky="w")
            self.info_vars[key] = var
            self.info_rows[key] = (name, value)

        ttk.Separator(panel).grid(row=10, column=0, columnspan=2, sticky="ew", pady=14)
        self.btn_delete = ttk.Button(panel, text="Delete slot…", style="Danger.TButton", command=self.delete_slot)
        self.btn_delete.grid(row=11, column=0, columnspan=2, sticky="w")
        panel.rowconfigure(12, weight=1)

        self.status_var = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.status_var, style="Bar.TLabel", padding=(16, 4, 16, 10)).pack(fill="x")

        self.btn_delete.state(["disabled"])
        self.btn_save.state(["disabled"])

    # ------------------------------------------------------------ file
    def startup_detect(self):
        """On start-up: Steam first; only if Steam has no save, fall back to GOG."""
        steam = find_steam_saves()
        if steam:
            self.auto_detect()
            return
        gog = find_gog_saves()
        if gog and self.load(gog[0], source="GOG"):
            self.status("No Steam save found; the GOG save was opened.")
            return
        self.status("No save found on Steam or GOG. Use \"Open…\" or drag a biodata.bin onto this window.")

    def find_gog(self):
        """Look for the save in the GOG Galaxy folder (only on request; start-up uses Steam)."""
        saves = find_gog_saves()
        if not saves:
            folder = gog_save_dir()
            messagebox.showinfo("GOG", "No Resident Evil HD Remaster save was found in the GOG Galaxy folder:\n\n"
                                       f"{folder}\n\nUse \"Open…\" to choose the file manually.")
            return
        if not self.confirm_discard():
            return
        if self.load(saves[0], source="GOG") and len(saves) > 1:
            self.status(f"{len(saves)} candidate files in the GOG folder; the most recent one was opened.")

    def auto_detect(self, explicit: bool = False):
        saves = find_steam_saves()
        if not saves:
            if explicit:
                messagebox.showinfo("Steam", "No Resident Evil HD Remaster biodata.bin was found in the "
                                             "Steam folders. Use \"Open…\".")
            self.status("Use \"Open…\" or \"Find on Steam\" to load a biodata.bin.")
            return
        if explicit and not self.confirm_discard():
            return
        self.load(saves[0])
        if len(saves) > 1:
            self.status(f"{len(saves)} Steam accounts have saves; the most recent one was opened.")

    def open_dialog(self):
        if not self.confirm_discard():
            return
        path = filedialog.askopenfilename(title="Open biodata.bin",
                                          filetypes=[("RE HD save", "biodata.bin *.bin"), ("All files", "*.*")])
        if path:
            self.load(Path(path))

    def on_drop(self, paths: list[str]):
        """A file was dragged onto the window: open it like "Open…"."""
        files = [Path(p) for p in paths if Path(p).is_file()]
        if not files:
            self.status("Drop a biodata.bin file (folders are not supported).")
            return
        if not self.confirm_discard():
            return
        if self.load(files[0]) and len(files) > 1:
            self.status("Several files were dropped; only the first one was opened.")

    def load(self, path: Path, source: str | None = None) -> bool:
        try:
            save = SaveFile.load(path)
        except (OSError, SaveFormatError, ValueError) as exc:
            note = ("\n\nNote: GOG saves have not been verified yet; the GOG version may use a different format."
                    if source == "GOG" else "")
            messagebox.showerror("Could not open the file", f"{path}\n\n{exc}{note}")
            return False
        self.save = save
        self.current = None
        self.show_path()
        self.refresh_list()
        first = next((i for i, s in enumerate(save.slots) if not s.is_empty), 0)
        self.tree.selection_set(str(first))
        self.tree.focus(str(first))
        self.status(f"Opened. Checksum OK. {sum(not s.is_empty for s in save.slots)} slots in use.")
        self.update_dirty()
        return True

    def save_file(self):
        if self.save and self.save.dirty:
            self._write(self.save.path)

    def save_as(self):
        if not self.save:
            return
        path = filedialog.asksaveasfilename(title="Save as", initialfile="biodata.bin",
                                            defaultextension=".bin", filetypes=[("RE HD save", "*.bin")])
        if path:
            self._write(Path(path))

    def _write(self, path: Path):
        if not messagebox.askokcancel(
                "Save",
                f"This will overwrite:\n{path}\n\n"
                "• Make sure the game is closed.\n"
                f"• A backup will be saved first in:\n  {BACKUP_DIR}"):
            return
        try:
            backup = self.save.save(path, backup_dir=BACKUP_DIR)
        except (OSError, SaveFormatError, ValueError) as exc:
            messagebox.showerror("Error while saving", str(exc))
            return
        self.show_path()
        msg = "Saved successfully."
        if backup:
            msg += f" Backup: {backup.name}"
        self.status(msg)
        self.update_dirty()

    # ------------------------------------------------------------ slots
    def refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        for i, s in enumerate(self.save.slots):
            if s.is_empty:
                values = (s.number, "No data", "", "", "")
                tag = "empty"
            else:
                values = (s.number, s.character, f"{s.save_count:02d}", s.summary, format_time(s.play_time))
                tag = s.color_key
            self.tree.insert("", "end", iid=str(i), values=values, tags=(tag,))
        if self.current is not None:
            self.tree.selection_set(str(self.current))

    def on_select(self, _event=None):
        sel = self.tree.selection()
        if sel and int(sel[0]) != self.current:
            self.current = int(sel[0])
            self.refresh_detail()

    def slot(self):
        return self.save.slots[self.current] if self.save and self.current is not None else None

    def refresh_detail(self):
        s = self.slot()
        if s is None:
            return
        def show_row(key, visible):
            for widget in self.info_rows[key]:
                widget.grid() if visible else widget.grid_remove()

        if s.is_empty:
            self.slot_title.configure(text=f"Slot {s.number} · No data", foreground=SLOT_COLORS["empty"])
            for var in self.info_vars.values():
                var.set("—")
            show_row("diff", True)
            show_row("once", True)
            self.btn_delete.state(["disabled"])
            return
        title = f"Slot {s.number} · {s.character}" + (" · Cleared" if s.is_cleared else "")
        self.slot_title.configure(text=title, foreground=SLOT_COLORS[s.color_key])
        v = self.info_vars
        v["mode"].set(s.mode)
        # Real Survival has no selectable difficulty: the mode itself is the difficulty.
        show_row("diff", s.difficulty is not None)
        if s.difficulty is not None:
            v["diff"].set(s.difficulty)
        # "Once again.." can only be told apart in Standard mode.
        show_row("once", s.is_once_again is not None)
        if s.is_once_again is not None:
            v["once"].set("Yes" if s.is_once_again else "No")
        v["odz"].set("Yes" if s.has_odz else "No")
        v["costume"].set(s.costume)
        v["count"].set(f"{s.save_count:02d}")
        v["time"].set(format_time(s.play_time))
        v["health"].set(f"{s.health} / {s.max_health}")
        self.btn_delete.state(["!disabled"])

    def delete_slot(self):
        s = self.slot()
        if s is None or s.is_empty:
            return
        if not messagebox.askyesno(
                "Delete slot",
                f"Delete slot {s.number} ({s.character}, {s.summary}, {format_time(s.play_time)})?\n\n"
                "It will show as \"No data\". Nothing is written to the file until you press \"Save\".",
                icon="warning"):
            return
        s.clear()
        self.refresh_list()
        self.refresh_detail()
        self.update_dirty()
        self.status(f"Slot {s.number} deleted. Press \"Save\" to write the file.")

    # ------------------------------------------------------------ helpers
    def update_dirty(self):
        dirty = bool(self.save and self.save.dirty)
        self.btn_save.state(["!disabled"] if dirty else ["disabled"])
        base = self.root.title().lstrip("● ")
        self.root.title(("● " if dirty else "") + base)

    def show_path(self):
        path = str(self.save.path)
        if len(path) > MAX_PATH_CHARS:  # the window has a fixed size: shorten in the middle
            keep = MAX_PATH_CHARS - 1
            path = path[:keep // 2] + "…" + path[-(keep - keep // 2):]
        self.path_var.set(f"Last saved in game: {self.save.last_saved:%Y-%m-%d %H:%M}   ·   {path}")

    def status(self, text: str):
        self.status_var.set(text)

    def confirm_discard(self) -> bool:
        if self.save and self.save.dirty:
            return messagebox.askyesno("Unsaved changes", "There are unsaved changes. Discard them?")
        return True

    def on_close(self):
        if self.confirm_discard():
            self.root.destroy()


def main(argv: list[str] | None = None):
    argv = sys.argv[1:] if argv is None else argv
    try:  # crisp text on scaled displays
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # Windows 8.1+
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()  # Windows 7 / 8
    except Exception:
        pass
    root = tk.Tk()
    SaveManagerApp(root, argv[0] if argv else None)
    root.mainloop()
