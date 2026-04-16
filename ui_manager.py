# ui_manager.py - UI components and overlays

import threading
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk
from config import THEME, SEARCH_MODES, SORT_MODES

class RegionOverlay(threading.Thread):
    """Displays selected WBT region overlay (letters) and optional turn-gate region (green)."""
    
    def __init__(self):
        super().__init__()
        self.daemon = True
        self._region = None
        self._turn_region = None
        self._bundle_visible = True
        self.ready = threading.Event()
        self.start()

    def run(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.4)
        self.root.overrideredirect(True)

        self.canvas = tk.Canvas(self.root, bg=THEME["bg"], highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_rectangle(0, 0, 0, 0, outline=THEME["accent"], width=2, tags="border")

        self.turn_win = tk.Toplevel(self.root)
        self.turn_win.withdraw()
        self.turn_win.attributes("-topmost", True)
        self.turn_win.attributes("-alpha", 0.4)
        self.turn_win.overrideredirect(True)
        self.turn_canvas = tk.Canvas(self.turn_win, bg=THEME["bg"], highlightthickness=0)
        self.turn_canvas.pack(fill=tk.BOTH, expand=True)
        self.turn_canvas.create_rectangle(
            0, 0, 0, 0, outline=THEME["success"], width=2, tags="turn_border"
        )

        self.ready.set()
        self.root.mainloop()

    def _apply_region_geometry(self):
        if not self._region:
            return
        x, y = self._region["left"], self._region["top"]
        w, h = self._region["width"], self._region["height"]
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.canvas.coords("border", 2, 2, w - 2, h - 2)

    def _apply_turn_region_geometry(self):
        if not self._turn_region:
            return
        x, y = self._turn_region["left"], self._turn_region["top"]
        w, h = self._turn_region["width"], self._turn_region["height"]
        self.turn_win.geometry(f"{w}x{h}+{x}+{y}")
        self.turn_canvas.coords("turn_border", 2, 2, w - 2, h - 2)

    def set_bundle_visible(self, visible: bool):
        """Show or hide the overlay with the log window; keeps the selected region data."""
        self.ready.wait()
        self._bundle_visible = visible
        if not self._region:
            self.root.withdraw()
            self.turn_win.withdraw()
        else:
            self._apply_region_geometry()
            if visible:
                self.root.deiconify()
            else:
                self.root.withdraw()
        if self._turn_region:
            self._apply_turn_region_geometry()
            if visible:
                self.turn_win.deiconify()
            else:
                self.turn_win.withdraw()
        else:
            self.turn_win.withdraw()

    def show_region(self, new_region, turn_region=None):
        """Display letter region (blue outline) and optional turn gate region (green)."""
        self.ready.wait()
        self._region = new_region
        self._turn_region = turn_region
        if not self._region:
            self.root.withdraw()
            self.turn_win.withdraw()
            return

        self._apply_region_geometry()
        if self._turn_region:
            self._apply_turn_region_geometry()
            if self._bundle_visible:
                self.turn_win.deiconify()
            else:
                self.turn_win.withdraw()
        else:
            self.turn_win.withdraw()

        if self._bundle_visible:
            self.root.deiconify()
        else:
            self.root.withdraw()

class RegionSelector:
    """Interactive region selection UI."""
    
    @staticmethod
    def select_region():
        """
        Open fullscreen interactive region selector.
        
        Returns:
            Dictionary with 'left', 'top', 'width', 'height' keys
        """
        root = tk.Tk()
        root.attributes("-fullscreen", True)
        root.attributes("-alpha", 0.3)
        root.attributes("-topmost", True)
        root.wait_visibility(root)
        
        canvas = tk.Canvas(root, cursor="cross", bg="black")
        canvas.pack(fill=tk.BOTH, expand=True)

        start_x = start_y = 0
        rect = None
        result = {}

        def on_mouse_down(e):
            nonlocal start_x, start_y, rect
            start_x, start_y = e.x, e.y
            rect = canvas.create_rectangle(start_x, start_y, e.x, e.y, 
                                           outline=THEME["accent"], width=2)

        def on_mouse_move(e):
            if rect:
                canvas.coords(rect, start_x, start_y, e.x, e.y)

        def on_mouse_up(e):
            x1, y1 = min(start_x, e.x), min(start_y, e.y)
            x2, y2 = max(start_x, e.x), max(start_y, e.y)
            result["region"] = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
            root.quit()

        def on_escape(e):
            root.quit()

        canvas.bind("<ButtonPress-1>", on_mouse_down)
        canvas.bind("<B1-Motion>", on_mouse_move)
        canvas.bind("<ButtonRelease-1>", on_mouse_up)
        root.bind("<Escape>", on_escape)

        root.mainloop()
        root.destroy()

        if "region" not in result or result["region"]["width"] <= 0:
            raise RuntimeError("Region selection cancelled")

        return result["region"]

class LogDisplay(threading.Thread):
    """Main UI window with logging and controls."""
    
    def __init__(
        self,
        log_queue,
        callbacks: dict,
        on_visibility_changed: Optional[Callable[[bool], None]] = None,
    ):
        super().__init__()
        self.daemon = True
        self.log_queue = log_queue
        self.callbacks = callbacks
        self.on_visibility_changed = on_visibility_changed
        self.root = None
        self.text_widget = None
        self.visible = True
        self.start()

    def run(self):
        self.root = tk.Tk()
        self.root.title("WBT")
        self.root.geometry("750x350+10+10")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", THEME["unfocused_alpha"])
        self.root.resizable(True, True)
        self.root.config(bg=THEME["bg"])

        # Style
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=THEME["bg"], foreground=THEME["fg"],
                       font=(THEME["font_family"], THEME["font_size"]))

        # Menu
        menubar = tk.Menu(self.root, tearoff=0)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        options_menu = tk.Menu(menubar, tearoff=0)
        help_menu = tk.Menu(menubar, tearoff=0)

        menubar.add_cascade(label="File", menu=file_menu)
        menubar.add_cascade(label="Options", menu=options_menu)
        menubar.add_cascade(label="Help", menu=help_menu)

        file_menu.add_command(label="Exit", command=self.callbacks['exit'])
        
        options_menu.add_command(label="Select Region", 
                                command=self.callbacks['select_region'], accelerator="Tab")
        if self.callbacks.get("clear_turn_region"):
            options_menu.add_command(
                label="Clear turn region",
                command=self.callbacks["clear_turn_region"],
                accelerator="Ctrl+F2",
            )
        options_menu.add_separator()
        
        search_menu = tk.Menu(options_menu, tearoff=0)
        options_menu.add_cascade(label="Search Mode", menu=search_menu)
        for i, mode in enumerate(SEARCH_MODES):
            search_menu.add_radiobutton(label=mode, 
                                       command=lambda i=i: self.callbacks['set_search_mode'](i))
        
        sort_menu = tk.Menu(options_menu, tearoff=0)
        options_menu.add_cascade(label="Sort Mode", menu=sort_menu)
        for i, mode in enumerate(SORT_MODES):
            sort_menu.add_radiobutton(label=mode,
                                     command=lambda i=i: self.callbacks['set_sort_mode'](i))
        
        options_menu.add_command(
            label="Typing delay...",
            command=self.callbacks["set_typing_delay"],
        )
        options_menu.add_command(
            label="OCR interval...",
            command=self.callbacks["set_ocr_interval"],
        )
        options_menu.add_separator()
        options_menu.add_command(label="Clear Typed History", 
                                command=self.callbacks['clear_history'], accelerator="Delete")
        options_menu.add_command(label="Undo Last Word", 
                                command=self.callbacks['undo_word'], accelerator="Ctrl+Z")

        help_menu.add_command(label="Show Hotkeys", 
                             command=self.callbacks['show_help'], accelerator=".")

        # Text Widget
        self.text_widget = tk.Text(self.root, bg=THEME["log_bg"], fg=THEME["log_fg"],
                                   font=(THEME["font_family"], THEME["font_size"]),
                                   relief=tk.FLAT, bd=0, insertbackground=THEME["fg"])
        self.text_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.root.bind("<FocusIn>", self.handle_focus_in)
        self.root.bind("<FocusOut>", self.handle_focus_out)
        self.root.protocol("WM_DELETE_WINDOW", self.callbacks['exit'])
        self.check_queue()
        self.root.mainloop()

    def check_queue(self):
        """Update log display from queue."""
        messages = self.log_queue.pop_all()
        for message, color in messages:
            self.text_widget.insert(tk.END, message + "\n")
            self.text_widget.tag_config(color, foreground=color)
            self.text_widget.tag_add(color, f"{self.text_widget.index('end')}-1c linestart",
                                    f"{self.text_widget.index('end')}-1c lineend")
            self.text_widget.see(tk.END)
        
        if self.root:
            self.root.after(100, self.check_queue)

    def toggle_visibility(self):
        """Toggle window visibility."""
        if self.root:
            self.root.after(0, self._toggle_visibility)

    def _toggle_visibility(self):
        if not hasattr(self, 'root') or not self.root:
            return
            
        try:
            if self.root.state() == 'withdrawn' or not self.root.winfo_viewable():
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
                self.visible = True
                if self.on_visibility_changed:
                    self.on_visibility_changed(True)
            else:
                self.root.withdraw()
                self.visible = False
                if self.on_visibility_changed:
                    self.on_visibility_changed(False)
        except tk.TclError:
            # Handle case where window was already destroyed
            pass

    def handle_focus_in(self, event=None):
        """Make window opaque on focus in."""
        if self.root:
            self.root.attributes("-alpha", THEME["focused_alpha"])

    def handle_focus_out(self, event=None):
        """Make window transparent on focus out."""
        if self.root:
            self.root.attributes("-alpha", THEME["unfocused_alpha"])

class HelpWindow:
    """Help/hotkeys display window."""
    
    @staticmethod
    def show(parent_root, help_text: str):
        """Create and display help window."""
        help_win = tk.Toplevel(parent_root)
        help_win.title("Help & Hotkeys")
        help_win.geometry("500x450")
        help_win.attributes("-topmost", True)
        help_win.config(bg=THEME["bg"])

        text_widget = tk.Text(help_win, font=(THEME["font_family"], THEME["font_size"]),
                             relief=tk.FLAT, background=THEME["bg"], foreground=THEME["fg"],
                             wrap=tk.WORD, padx=10, pady=10)
        text_widget.pack(fill=tk.BOTH, expand=True)
        text_widget.insert(tk.END, help_text.strip())
        text_widget.config(state=tk.DISABLED)

        close_button = ttk.Button(help_win, text="Close", command=help_win.destroy)
        close_button.pack(pady=10)
        help_win.bind("<Escape>", lambda e: help_win.destroy())
        
        return help_win

class DefinitionPopup:
    """Popup to display word definitions."""
    def_win = None

    @staticmethod
    def show(parent_root, word: str, definitions: list):
        """Create and display definition window."""

        if DefinitionPopup.def_win and DefinitionPopup.def_win.winfo_exists():
            DefinitionPopup.def_win.destroy()
            DefinitionPopup.def_win = None

        if not definitions:
            return None

        DefinitionPopup.def_win = tk.Toplevel(parent_root)
        DefinitionPopup.def_win.title(f"Definition of '{word}'")
        DefinitionPopup.def_win.attributes("-topmost", True)
        DefinitionPopup.def_win.attributes("-alpha", THEME["unfocused_alpha"])
        DefinitionPopup.def_win.state('zoomed')
        DefinitionPopup.def_win.grab_set()
        DefinitionPopup.def_win.config(bg=THEME["bg"])

        text_widget = tk.Text(DefinitionPopup.def_win, font=(THEME["font_family"], THEME["definition_font_size"]),
                             relief=tk.FLAT, bd=1, background=THEME["log_bg"], foreground=THEME["log_fg"],
                             wrap=tk.WORD, padx=10, pady=10)
        text_widget.pack(fill=tk.BOTH, expand=True)

        if definitions:
            for i, definition in enumerate(definitions):
                text_widget.insert(tk.END, f"{i+1}. {definition.strip()}\n\n")
        else:
            text_widget.insert(tk.END, "No definitions found.")

        text_widget.config(state=tk.DISABLED)
        text_widget.bind("<Button-1>", DefinitionPopup.set_opaque)

        close_button = ttk.Button(DefinitionPopup.def_win, text="Close", command=DefinitionPopup.def_win.destroy)
        close_button.pack(pady=10)
        DefinitionPopup.def_win.bind("<Escape>", lambda e: DefinitionPopup.def_win.destroy())

        parent_root.wait_window(DefinitionPopup.def_win)

        return DefinitionPopup.def_win

    @staticmethod
    def set_opaque(event=None):
        """Set the window to be fully opaque."""
        if DefinitionPopup.def_win:
            DefinitionPopup.def_win.attributes("-alpha", THEME["focused_alpha"])
