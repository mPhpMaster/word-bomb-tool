# ui_manager.py - UI components and overlays

import threading
import tkinter as tk
from tkinter import ttk
from config import THEME, SEARCH_MODES, SORT_MODES

class RegionOverlay(threading.Thread):
    """Displays selected WBT region overlay."""
    
    def __init__(self):
        super().__init__()
        self.daemon = True
        self._region = None
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

        self.ready.set()
        self.root.mainloop()

    def show_region(self, new_region):
        """Display region or hide if new_region is None."""
        self.ready.wait()
        self._region = new_region
        if not self._region:
            self.root.withdraw()
            return

        x, y = self._region["left"], self._region["top"]
        w, h = self._region["width"], self._region["height"]
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.canvas.coords("border", 2, 2, w - 2, h - 2)
        self.root.deiconify()

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
    
    def __init__(self, log_queue, callbacks: dict):
        super().__init__()
        self.daemon = True
        self.log_queue = log_queue
        self.callbacks = callbacks
        self.root = None
        self.text_widget = None
        self.visible = True
        self.start()

    def run(self):
        self.root = tk.Tk()
        self.root.title("WBT")
        self.root.geometry("550x450+10+10")
        self.root.attributes("-topmost", True)
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
            else:
                self.root.withdraw()
        except tk.TclError:
            # Handle case where window was already destroyed
            pass

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