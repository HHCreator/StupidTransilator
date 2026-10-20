"""A small always-on-top overlay window for SBtranslator.

    py overlay.py                 # or: sbtranslator-overlay

Type an English sentence and press Enter (Shift+Enter for a new line); the translation shows
below. Pick the translation mode with the buttons. Ctrl+Alt+T hides and shows the overlay
from any app (Windows). Needs an internet connection, like the rest of the package.
"""

import ctypes
import queue
import threading
import time
import tkinter as tk
from tkinter import font as tkfont

from . import MODES, translate
from .translator import TARGET_RARITY

TITLE = "SB Translator"
POLL_MS = 50
ALPHA = 0.96

BORDER, BG, PANEL = "#4a4f6a", "#1c1d26", "#2b2d3a"
FG, MUTED, ACCENT, ACCENT_HOVER, ERROR = "#ececf3", "#8b8fa6", "#6f8cff", "#93a8ff", "#ff7b7b"

# Label on the button and a one-line description, for each mode in sbtranslator.MODES
MODE_INFO = {
    "stupid": ("Stupid", "Word by word, with wrong-but-real meanings"),
    "plain": ("Plain", "Word by word, with the usual meanings"),
    "proper": ("Proper", "A normal, correct translation"),
    "classical": ("文言文", "A correct translation in Classical Chinese"),
}
CJK_FONTS = ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "SimHei")

HOTKEY_NAME = "Ctrl+Alt+T"
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000
VK_T = 0x54
WM_HOTKEY = 0x0312


def listen_for_hotkey(events):
    """Register the global hotkey and put ("toggle",) in events each time it is pressed.

    Runs in its own thread: a hotkey is delivered to the thread that registered it.
    Puts ("hotkey", False) in events if the hotkey can't be registered (not on Windows, or
    another app already has it).
    """
    try:
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        registered = user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_T)
    except (AttributeError, OSError):
        registered = False
    events.put(("hotkey", bool(registered)))
    if not registered:
        return
    message = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        if message.message == WM_HOTKEY:
            events.put(("toggle",))


class Overlay:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()  # results and hotkey presses coming from other threads
        self.request = 0  # id of the latest translation, older ones are dropped
        self.mode = tk.StringVar(value=MODES[0])
        self.rarity = tk.DoubleVar(value=TARGET_RARITY)

        families = set(tkfont.families(root))
        self.cjk_font = next((f for f in CJK_FONTS if f in families), "TkDefaultFont")
        self._build()
        self._on_mode()

        root.update_idletasks()
        x = root.winfo_screenwidth() - root.winfo_reqwidth() - 40
        root.geometry(f"+{max(x, 0)}+60")
        root.after(150, self.input.focus_force)

        threading.Thread(target=listen_for_hotkey, args=(self.events,), daemon=True).start()
        root.after(POLL_MS, self._poll)

    # -- layout ---------------------------------------------------------------------------

    def _build(self):
        root = self.root
        root.title(TITLE)
        root.overrideredirect(True)  # no system title bar, we draw our own
        root.attributes("-topmost", True)
        root.attributes("-alpha", ALPHA)
        root.configure(bg=BORDER)

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=1, pady=1)

        # Title bar, drag it to move the overlay
        bar = tk.Frame(body, bg=PANEL)
        bar.pack(fill="x")
        title = tk.Label(bar, text=TITLE, bg=PANEL, fg=FG, font=("Segoe UI", 9, "bold"))
        title.pack(side="left", padx=10, pady=5)
        self.hotkey_hint = tk.Label(bar, text=f"{HOTKEY_NAME} to hide/show", bg=PANEL, fg=MUTED,
                                    font=("Segoe UI", 8))
        self.hotkey_hint.pack(side="left")
        close = tk.Label(bar, text="✕", bg=PANEL, fg=MUTED, font=("Segoe UI", 10), padx=12)
        close.pack(side="right", fill="y")
        close.bind("<Button-1>", lambda e: self.root.destroy())
        close.bind("<Enter>", lambda e: close.config(bg=ERROR, fg=BG))
        close.bind("<Leave>", lambda e: close.config(bg=PANEL, fg=MUTED))
        for widget in (bar, title, self.hotkey_hint):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        content = tk.Frame(body, bg=BG)
        content.pack(fill="both", expand=True, padx=10, pady=8)

        # Mode buttons
        modes = tk.Frame(content, bg=BG)
        modes.pack(fill="x")
        for column, mode in enumerate(MODES):
            label = MODE_INFO.get(mode, (mode.title(),))[0]
            modes.columnconfigure(column, weight=1, uniform="mode")
            tk.Radiobutton(
                modes, text=label, value=mode, variable=self.mode, command=self._on_mode,
                indicatoron=False, bd=0, relief="flat", cursor="hand2", takefocus=False,
                bg=PANEL, fg=FG, activebackground=ACCENT, activeforeground=BG,
                selectcolor=ACCENT, font=(self.cjk_font, 10), padx=6, pady=5,
            ).grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 3, 0))
        self.mode_hint = tk.Label(content, bg=BG, fg=MUTED, anchor="w", font=("Segoe UI", 8))
        self.mode_hint.pack(fill="x", pady=(4, 0))

        # Rarity slider, only used by the stupid mode
        self.rarity_row = tk.Frame(content, bg=BG)
        self.rarity_label = tk.Label(self.rarity_row, bg=BG, fg=FG, width=10, anchor="w",
                                     font=("Segoe UI", 9))
        self.rarity_label.pack(side="left")
        tk.Scale(
            self.rarity_row, variable=self.rarity, from_=0, to=3, resolution=0.1,
            orient="horizontal", showvalue=False, command=self._on_rarity, bd=0,
            highlightthickness=0, sliderrelief="flat", sliderlength=18, width=14,
            bg=ACCENT, activebackground=ACCENT_HOVER, troughcolor=PANEL, length=120,
        ).pack(side="left", fill="x", expand=True)
        tk.Label(self.rarity_row, text="0 natural · 3 obscure", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))
        self._on_rarity()

        # Input
        self.input_frame = tk.Frame(content, bg=BG)
        self.input_frame.pack(fill="x", pady=(8, 0))
        self.input = tk.Text(
            self.input_frame, width=42, height=3, wrap="word", bd=0, relief="flat",
            bg=PANEL, fg=FG, insertbackground=FG, selectbackground=ACCENT, selectforeground=BG,
            font=("Segoe UI", 11), padx=8, pady=6, undo=True,
        )
        self.input.pack(fill="x")
        self.input.bind("<Return>", self.translate)
        self.input.bind("<Shift-Return>", lambda e: None)  # keep the default: new line
        self.input.bind("<Control-Return>", self.translate)

        # Translate and copy buttons, and the status
        actions = tk.Frame(content, bg=BG)
        actions.pack(fill="x", pady=8)
        self._button(actions, "Translate", self.translate, accent=True).pack(side="left")
        self._button(actions, "Copy", self.copy).pack(side="left", padx=(6, 0))
        self.status = tk.Label(actions, bg=BG, fg=MUTED, anchor="e", font=("Segoe UI", 8))
        self.status.pack(side="right", fill="x", expand=True)

        # Output, read only
        self.output = tk.Text(
            content, width=42, height=5, wrap="char", bd=0, relief="flat", state="disabled",
            bg=PANEL, fg=FG, selectbackground=ACCENT, selectforeground=BG,
            font=(self.cjk_font, 13), padx=8, pady=6,
        )
        self.output.tag_config("error", foreground=ERROR, font=("Segoe UI", 9))
        self.output.pack(fill="x")

    def _button(self, parent, text, command, accent=False):
        bg, fg = (ACCENT, BG) if accent else (PANEL, FG)
        return tk.Button(
            parent, text=text, command=command, bd=0, relief="flat", cursor="hand2",
            takefocus=False, bg=bg, fg=fg, activebackground=ACCENT if not accent else FG,
            activeforeground=BG, font=("Segoe UI", 9, "bold" if accent else "normal"),
            padx=14, pady=4,
        )

    # -- events ---------------------------------------------------------------------------

    def _drag_start(self, event):
        self._drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag_move(self, event):
        dx, dy = self._drag_offset
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _on_mode(self):
        mode = self.mode.get()
        self.mode_hint.config(text=MODE_INFO.get(mode, ("", ""))[1])
        if mode == "stupid":
            self.rarity_row.pack(fill="x", pady=(6, 0), before=self.input_frame)
        else:
            self.rarity_row.pack_forget()

    def _on_rarity(self, value=None):
        self.rarity_label.config(text=f"Rarity {self.rarity.get():.1f}")

    def _set_status(self, text, error=False):
        self.status.config(text=text, fg=ERROR if error else MUTED)

    def _show(self, text, error=False):
        self.output.config(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text, "error" if error else "")
        self.output.config(state="disabled")

    def toggle(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.lift()
            self.input.focus_force()
        else:
            self.root.withdraw()

    # -- translating ----------------------------------------------------------------------

    def translate(self, event=None):
        text = self.input.get("1.0", "end").strip()
        if not text:
            return "break"
        self.request += 1
        mode, rarity = self.mode.get(), round(self.rarity.get(), 1)
        self._set_status("Translating…")
        threading.Thread(target=self._work, args=(self.request, text, mode, rarity),
                         daemon=True).start()
        return "break"  # don't type the newline into the input

    def _work(self, request, text, mode, rarity):
        # Runs in a worker thread: the network calls would freeze the window
        started = time.monotonic()
        try:
            result = translate(text, mode=mode, rarity=rarity)
        except Exception as error:
            self.events.put(("error", request, str(error)))
        else:
            self.events.put(("result", request, result, mode, time.monotonic() - started))

    def copy(self):
        text = self.output.get("1.0", "end").strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self._set_status("Copied")

    def _poll(self):
        try:
            while True:
                kind, *args = self.events.get_nowait()
                if kind == "toggle":
                    self.toggle()
                elif kind == "hotkey" and not args[0]:
                    self.hotkey_hint.config(text="")
                elif kind in ("result", "error") and args[0] == self.request:
                    if kind == "result":
                        _, text, mode, seconds = args
                        self._show(text)
                        self._set_status(f"{MODE_INFO.get(mode, (mode,))[0]} · {seconds:.1f}s")
                    else:
                        self._show(args[1], error=True)
                        self._set_status("Translation failed", error=True)
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._poll)


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on scaled displays
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    Overlay(root)
    root.mainloop()


if __name__ == "__main__":
    main()
