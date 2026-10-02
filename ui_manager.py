# ui_manager.py - UI components and overlays

import ctypes
import logging
import os
import threading
import webbrowser
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk
from config import (
    THEME, SEARCH_MODES, SORT_MODES, BASE_DIR, ASSETS_DIR,
    APP_NAME, APP_VERSION, APP_DESCRIPTION, APP_AUTHOR, APP_AUTHOR_EMAIL,
    APP_COPYRIGHT, APP_LICENSE_NAME, APP_REPOSITORY_URL, APP_LINKS,
)

logger = logging.getLogger(__name__)

# Pixels between the region and its outline, so the outline is drawn outside the
# captured area (on the region's edge it was read as an extra "i" or "l").
OVERLAY_OUTSET = 3
# Overlay interior color; made fully transparent (and click-through) by Windows.
_OVERLAY_KEY = "#ff00fe"
WDA_EXCLUDEFROMCAPTURE = 0x11


def _exclude_from_capture(win: tk.Misc) -> None:
    """Keep a window out of screen captures (Windows 10 2004+), so OCR never sees it."""
    try:
        win.update_idletasks()
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        if not user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
            logger.warning("SetWindowDisplayAffinity failed; the region outline may be captured")
    except Exception as e:
        logger.warning(f"Could not exclude overlay from capture: {e}")

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

    @staticmethod
    def _setup_outline_window(win, canvas_color, tag):
        """Frameless topmost window showing only an outline: the interior is a
        transparent color key, and the window is excluded from screen capture."""
        win.withdraw()
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.8)
        win.overrideredirect(True)
        win.config(bg=_OVERLAY_KEY)
        win.attributes("-transparentcolor", _OVERLAY_KEY)
        canvas = tk.Canvas(win, bg=_OVERLAY_KEY, highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_rectangle(0, 0, 0, 0, outline=canvas_color, width=2, tags=tag)
        _exclude_from_capture(win)
        return canvas

    def run(self):
        self.root = tk.Tk()
        self.canvas = self._setup_outline_window(self.root, THEME["accent"], "border")

        self.turn_win = tk.Toplevel(self.root)
        self.turn_canvas = self._setup_outline_window(self.turn_win, THEME["success"], "turn_border")

        self.ready.set()
        self.root.mainloop()

    @staticmethod
    def _place_outline(win, canvas, tag, region):
        """Positions the window OVERLAY_OUTSET px around the region, outline on its outer edge."""
        o = OVERLAY_OUTSET
        x, y = region["left"] - o, region["top"] - o
        w, h = region["width"] + 2 * o, region["height"] + 2 * o
        win.geometry(f"{w}x{h}+{x}+{y}")
        canvas.coords(tag, 1, 1, w - 1, h - 1)

    def _apply_region_geometry(self):
        if not self._region:
            return
        self._place_outline(self.root, self.canvas, "border", self._region)

    def _apply_turn_region_geometry(self):
        if not self._turn_region:
            return
        self._place_outline(self.turn_win, self.turn_canvas, "turn_border", self._turn_region)

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
        options_menu.add_command(
            label="Fast typing (on/off)",
            command=self.callbacks["toggle_fast_typing"],
        )
        options_menu.add_separator()
        options_menu.add_command(label="Clear Typed History", 
                                command=self.callbacks['clear_history'], accelerator="Delete")
        options_menu.add_command(label="Undo Last Word", 
                                command=self.callbacks['undo_word'], accelerator="Ctrl+Z")

        help_menu.add_command(label="Show Hotkeys", 
                             command=self.callbacks['show_help'], accelerator=".")
        help_menu.add_separator()
        help_menu.add_command(label=f"About {APP_NAME}\u2026", command=self.callbacks['show_about'])

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


class AboutWindow:
    """About window: author, version, description, links and legal documents."""

    BG = THEME["log_bg"]
    TEXT = THEME["fg"]
    MUTED = "#7f848e"
    LINE = THEME["select_bg"]
    FONT = "Segoe UI"
    AVATAR_SIZE = 84
    ICON_SIZE = 64

    _open = None

    @staticmethod
    def show(parent_root):
        """Shows the About window, or brings the open one to the front."""
        win = AboutWindow._open
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            win.focus_force()
            return win
        AboutWindow._open = AboutWindow._build(parent_root)
        return AboutWindow._open

    @staticmethod
    def _build(parent_root):
        from PIL import ImageTk

        c = AboutWindow
        win = tk.Toplevel(parent_root)
        win.withdraw()
        win.title(f"About {APP_NAME}")
        win.config(bg=c.BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.bind("<Escape>", lambda e: win.destroy())

        body = tk.Frame(win, bg=c.BG, padx=36, pady=26)
        body.pack(fill=tk.BOTH, expand=True)

        def label(parent, text, size=10, bold=False, color=None, **kw):
            return tk.Label(parent, text=text, bg=c.BG, fg=color or c.TEXT,
                            font=(c.FONT, size, "bold" if bold else "normal"), **kw)

        label(body, "About", 18, True).pack()

        images = tk.Frame(body, bg=c.BG)
        images.pack(pady=(14, 10))
        avatar = ImageTk.PhotoImage(c._avatar_image(c.AVATAR_SIZE), master=win)
        icon_img = c._icon_image(c.ICON_SIZE)
        avatar_label = tk.Label(images, image=avatar, bg=c.BG, bd=0)
        avatar_label.pack(side=tk.LEFT, padx=(0, 14))
        win._images = [avatar]  # keep references, or Tk shows blank images
        if icon_img is not None:
            icon = ImageTk.PhotoImage(icon_img, master=win)
            win._images.append(icon)
            tk.Label(images, image=icon, bg=c.BG, bd=0).pack(side=tk.LEFT)

        name = tk.Frame(body, bg=c.BG)
        name.pack()
        label(name, APP_NAME, 14, True).pack(side=tk.LEFT)
        label(name, f" v{APP_VERSION}", 10, color=c.MUTED).pack(side=tk.LEFT, anchor="s", pady=(0, 2))

        label(body, APP_DESCRIPTION, 10, color=c.MUTED, wraplength=400, justify=tk.CENTER).pack(pady=(6, 0))

        made = tk.Frame(body, bg=c.BG)
        made.pack(pady=(12, 0))
        label(made, "Made by", 10, padx=0).pack(side=tk.LEFT)
        label(made, APP_AUTHOR, 10, True, padx=0).pack(side=tk.LEFT, padx=(4, 0))
        label(body, APP_AUTHOR_EMAIL, 10, color=c.MUTED).pack()

        links = tk.Frame(body, bg=c.BG)
        links.pack(pady=(14, 0))
        for text, url in APP_LINKS:
            c._link_button(links, text, url).pack(side=tk.LEFT, padx=5)

        docs = tk.Frame(body, bg=c.BG)
        docs.pack(pady=(10, 0))
        targets = (("License", "LICENSE"), ("Third-party notices", "THIRD_PARTY_NOTICES.md"),
                   ("Source code", APP_REPOSITORY_URL))
        for i, (text, target) in enumerate(targets):
            if i:
                label(docs, "\u00b7", 10, color=c.MUTED).pack(side=tk.LEFT)
            c._small_link(docs, text, target).pack(side=tk.LEFT)

        legal = f"{APP_COPYRIGHT}\nLicensed under the {APP_LICENSE_NAME}.\n" \
                "This program comes with ABSOLUTELY NO WARRANTY."
        label(body, legal, 9, color=c.MUTED, justify=tk.CENTER).pack(pady=(8, 0))

        close = tk.Label(body, text="Close", bg=THEME["accent"], fg="#0b1a26",
                         font=(c.FONT, 11, "bold"), pady=9, cursor="hand2")
        close.pack(fill=tk.X, pady=(18, 0))
        close.bind("<Button-1>", lambda e: win.destroy())
        close.bind("<Enter>", lambda e: close.config(bg="#8cc4f5"))
        close.bind("<Leave>", lambda e: close.config(bg=THEME["accent"]))

        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 3
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        win.deiconify()
        win.lift()
        win.focus_force()
        return win

    @staticmethod
    def _link_button(parent, text, url):
        """Outlined link button (GitHub, LinkedIn, ...)."""
        c = AboutWindow
        b = tk.Label(parent, text=text, bg=c.BG, fg=c.TEXT, font=(c.FONT, 10, "bold"),
                     padx=14, pady=6, cursor="hand2", highlightthickness=1,
                     highlightbackground=c.LINE, highlightcolor=c.LINE)
        b.bind("<Button-1>", lambda e: c._open_target(url))
        b.bind("<Enter>", lambda e: b.config(fg="white", highlightbackground=THEME["accent"]))
        b.bind("<Leave>", lambda e: b.config(fg=c.TEXT, highlightbackground=c.LINE))
        return b

    @staticmethod
    def _small_link(parent, text, target):
        """Small text link (License, Third-party notices, Source code)."""
        c = AboutWindow
        b = tk.Label(parent, text=text, bg=c.BG, fg=c.MUTED, font=(c.FONT, 9),
                     padx=6, pady=2, cursor="hand2")
        b.bind("<Button-1>", lambda e: c._open_document(target))
        b.bind("<Enter>", lambda e: b.config(fg=THEME["accent"]))
        b.bind("<Leave>", lambda e: b.config(fg=c.MUTED))
        return b

    @staticmethod
    def _open_document(target):
        """Opens a document shipped next to the exe (or the project), or its copy on GitHub."""
        if target.startswith("http"):
            AboutWindow._open_target(target)
            return
        local = os.path.join(BASE_DIR, target)
        if os.path.exists(local):
            AboutWindow._open_target(local)
        else:
            AboutWindow._open_target(f"{APP_REPOSITORY_URL}/blob/main/{target}")

    @staticmethod
    def _open_target(target):
        try:
            if hasattr(os, "startfile"):
                os.startfile(target)
            else:
                webbrowser.open(target)
        except Exception as e:
            logger.error(f"Could not open {target}: {e}")

    @staticmethod
    def _avatar_image(size):
        """Round author photo from assets/author.jpg with a faint outline; initials if missing."""
        from PIL import Image, ImageDraw, ImageFont, ImageOps

        c = AboutWindow
        scale = 4  # draw large, then shrink: smooth circle edges
        big = size * scale
        bg = Image.new("RGB", (big, big), c.BG)
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
        photo = None
        path = os.path.join(ASSETS_DIR, "author.jpg")
        try:
            if os.path.exists(path):
                photo = ImageOps.fit(Image.open(path).convert("RGB"), (big, big))
        except Exception as e:
            logger.warning(f"Could not load author photo: {e}")
        if photo is None:
            photo = Image.new("RGB", (big, big), "#2c313a")
            draw = ImageDraw.Draw(photo)
            initials = "".join(part[0] for part in APP_AUTHOR.replace("-", " ").split()[:2]).upper()
            try:
                font = ImageFont.truetype("segoeuib.ttf", int(big * 0.32))
            except OSError:
                font = ImageFont.load_default()
            draw.text((big / 2, big / 2), initials, fill=THEME["accent"], font=font, anchor="mm")
        bg.paste(photo, (0, 0), mask)
        ring = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((1, 1, big - 2, big - 2), outline=(255, 255, 255, 60), width=scale)
        bg = Image.alpha_composite(bg.convert("RGBA"), ring)
        return bg.resize((size, size), Image.LANCZOS)

    @staticmethod
    def _icon_image(size):
        """The app icon from assets/appicon.png, or None if missing."""
        from PIL import Image

        path = os.path.join(ASSETS_DIR, "appicon.png")
        try:
            return Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
        except Exception as e:
            logger.warning(f"Could not load app icon: {e}")
            return None
