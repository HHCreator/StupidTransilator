"""A small always-on-top overlay window for SBtranslator.

    py overlay.py                 # or: sbtranslator-overlay

Type an English sentence and press Enter (Shift+Enter for a new line); the translation shows
below. Pick the translation mode with the buttons. The — button minimizes it to the taskbar,
and Ctrl+Alt+T hides and shows it from any app (Windows). Needs an internet connection, like the rest of the package.

How it works: the window is built with tkinter, which only allows the main thread to touch
the window. Anything slow runs in other threads instead, and they never touch the window:

    main thread      builds the window, reacts to clicks and keys, and every POLL_MS
                     milliseconds runs Overlay._poll(), which reads self.events
    worker thread    one per translation (Overlay._work): calls sbtranslator.translate()
                     and puts the result or the error in self.events
    hotkey thread    listen_for_hotkey(): waits for Ctrl+Alt+T and puts ("toggle",)
                     in self.events

self.events is a queue.Queue, which is safe to use from several threads.
"""

import ctypes
import queue
import threading
import time
import tkinter as tk
from tkinter import font as tkfont

from . import MODES, adjust, options
from .translator import TARGET_RARITY

TITLE = "SB Translator"
POLL_MS = 50  # how often the window checks for results, in milliseconds
ALPHA = 0.96  # window opacity: slightly see-through

# Colours: window border, background, panels (title bar, inputs), text and highlights
BORDER, BG, PANEL = "#4a4f6a", "#1c1d26", "#2b2d3a"
FG, MUTED, ACCENT, ACCENT_HOVER, ERROR = "#ececf3", "#8b8fa6", "#6f8cff", "#93a8ff", "#ff7b7b"

# Label on the button and a one-line description, for each mode in sbtranslator.MODES
MODE_INFO = {
    "stupid": ("Stupid", "A normal sentence with stupid words injected"),
    "wordy": ("逐词", "Word by word, with wrong-but-real meanings"),
    "plain": ("Plain", "Word by word, with the usual meanings"),
    "proper": ("Proper", "A normal, correct translation"),
    "classical": ("文言文", "A correct translation in Classical Chinese"),
}
# Fonts that can show Chinese, in order of preference; the first one installed is used
CJK_FONTS = ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "SimHei")

# The global hotkey, in the numbers the Windows API uses for it
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
        registered = False  # ctypes.windll only exists on Windows
    events.put(("hotkey", bool(registered)))
    if not registered:
        return
    # Windows message loop: GetMessageW waits until Windows sends this thread a message
    message = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        if message.message == WM_HOTKEY:
            events.put(("toggle",))


class Overlay:
    """The overlay window: mode buttons, rarity slider, input box, buttons and output box."""

    def __init__(self, root):
        """Build the window inside root (a tk.Tk), place it, and start the hotkey thread."""
        self.root = root
        self.events = queue.Queue()  # results and hotkey presses coming from other threads
        self.request = 0  # id of the latest translation, older ones are dropped
        self.mode = tk.StringVar(value=MODES[0])
        self.rarity = tk.DoubleVar(value=TARGET_RARITY)
        self.check = tk.BooleanVar(value=False)  # proofread by the local AI model (check.py)

        families = set(tkfont.families(root))
        self.cjk_font = next((f for f in CJK_FONTS if f in families), "TkDefaultFont")
        self._build()
        self._on_mode()

        # Start near the top right corner of the screen
        root.update_idletasks()
        x = root.winfo_screenwidth() - root.winfo_reqwidth() - 40
        root.geometry(f"+{max(x, 0)}+60")
        root.after(150, self.input.focus_force)

        threading.Thread(target=listen_for_hotkey, args=(self.events,), daemon=True).start()
        root.after(POLL_MS, self._poll)

    # -- layout ---------------------------------------------------------------------------

    def _build(self):
        """Create every widget, top to bottom: title bar, modes, rarity, input, buttons, output."""
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
        # Minimize to the taskbar; click the taskbar button to bring it back
        minimize = tk.Label(bar, text="—", bg=PANEL, fg=MUTED, font=("Segoe UI", 10), padx=12)
        minimize.pack(side="right", fill="y")
        minimize.bind("<Button-1>", lambda e: self.minimize())
        minimize.bind("<Enter>", lambda e: minimize.config(bg=ACCENT, fg=BG))
        minimize.bind("<Leave>", lambda e: minimize.config(bg=PANEL, fg=MUTED))
        # Coming back from the taskbar: draw our own title bar again
        root.bind("<Map>", self._on_restore)
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

        # Rarity slider, only used by the word-by-word stupid mode
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
        # AI check, for the stupid and word-by-word modes (needs Ollama with the model downloaded)
        self.check_box = tk.Checkbutton(
            actions, text="AI 校对", variable=self.check, bd=0, cursor="hand2", takefocus=False,
            bg=BG, fg=FG, activebackground=BG, activeforeground=FG, selectcolor=PANEL,
            font=(self.cjk_font, 9))
        self.check_box.pack(side="left", padx=(10, 0))
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

        # More choices after a translation, like Google Translate's alternatives: other
        # whole versions, and each stupid word to switch to another meaning (_show_choices)
        self.choices = tk.Frame(content, bg=BG)
        self.choices.pack(fill="x")
        self.last = None  # the latest translation's text, normal translation and choices

    def _button(self, parent, text, command, accent=False):
        """Make a flat button; accent=True makes it the highlighted main button."""
        bg, fg = (ACCENT, BG) if accent else (PANEL, FG)
        return tk.Button(
            parent, text=text, command=command, bd=0, relief="flat", cursor="hand2",
            takefocus=False, bg=bg, fg=fg, activebackground=ACCENT if not accent else FG,
            activeforeground=BG, font=("Segoe UI", 9, "bold" if accent else "normal"),
            padx=14, pady=4,
        )

    # -- events ---------------------------------------------------------------------------

    def _drag_start(self, event):
        """Remember where in the window the mouse grabbed the title bar."""
        self._drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag_move(self, event):
        """Move the window with the mouse while the title bar is held."""
        dx, dy = self._drag_offset
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _on_mode(self):
        """A mode button was clicked: show its description, and the slider for wordy mode."""
        mode = self.mode.get()
        self.mode_hint.config(text=MODE_INFO.get(mode, ("", ""))[1])
        if mode == "wordy":  # rarity only matters for the word-by-word stupid mode
            self.rarity_row.pack(fill="x", pady=(6, 0), before=self.input_frame)
        else:
            self.rarity_row.pack_forget()
        # The AI check works on the stupid and word-by-word modes
        self.check_box.config(state="normal" if mode in ("stupid", "wordy", "plain") else "disabled")

    def _on_rarity(self, value=None):
        """The slider moved: show the new rarity next to it."""
        self.rarity_label.config(text=f"Rarity {self.rarity.get():.1f}")

    def _set_status(self, text, error=False):
        """Show a short message next to the buttons (red for errors)."""
        self.status.config(text=text, fg=ERROR if error else MUTED)

    def _show(self, text, error=False):
        """Put text in the read-only output box (red for errors)."""
        self.output.config(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text, "error" if error else "")
        self.output.config(state="disabled")

    def minimize(self):
        """Shrink the window to the taskbar.

        The window has no system title bar (overrideredirect), and such a window can't be
        minimized and has no taskbar button. So it gets the normal window frame back just
        while it is minimized; _on_restore() takes it away again.
        """
        self.root.overrideredirect(False)
        self.root.iconify()

    def _on_restore(self, event=None):
        """The window was brought back from the taskbar: remove the system frame again."""
        if event is not None and event.widget is not self.root:
            return  # <Map> also fires for every widget inside the window
        if self.root.state() == "normal" and not self.root.overrideredirect():
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
            self.input.focus_force()

    def toggle(self):
        """Hide the window, or bring it back on top with the cursor in the input box."""
        if self.root.state() in ("withdrawn", "iconic"):  # hidden, or in the taskbar
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.lift()
            self.input.focus_force()
        else:
            self.root.withdraw()

    # -- translating ----------------------------------------------------------------------

    def translate(self, event=None):
        """Start translating the input in a worker thread, so the window doesn't freeze."""
        text = self.input.get("1.0", "end").strip()
        if not text:
            return "break"
        # Number each request: if the user translates again before an answer arrives,
        # _poll() only shows the answer to the newest request
        self.request += 1
        self._clear_choices()
        mode, rarity = self.mode.get(), round(self.rarity.get(), 1)
        check = self.check.get() and mode in ("stupid", "wordy", "plain")
        self._set_status("Translating and checking…" if check else "Translating…")
        threading.Thread(target=self._work, args=(self.request, text, mode, rarity, check),
                         daemon=True).start()
        return "break"  # don't type the newline into the input

    def _work(self, request, text, mode, rarity, check=False):
        """Translate in the worker thread and hand the result to the main thread via events."""
        # Runs in a worker thread: the network calls would freeze the window
        started = time.monotonic()
        try:
            result = options(text, mode=mode, rarity=rarity, check=check)
        except Exception as error:
            self.events.put(("error", request, str(error)))
        else:
            result["text"] = text
            self.events.put(("result", request, result, mode, time.monotonic() - started))

    # -- choosing other versions and words ------------------------------------------------

    def _clear_choices(self):
        for widget in self.choices.winfo_children():
            widget.destroy()

    def _show_choices(self):
        """Show the other versions and the stupid words of the latest translation."""
        self._clear_choices()
        result = self.last
        others = [v for v in result["versions"] if v != result["shown"]]
        if others:
            tk.Label(self.choices, text="其他版本，点一下换上", bg=BG, fg=MUTED, anchor="w",
                     font=(self.cjk_font, 8)).pack(fill="x", pady=(8, 2))
            for version in others:
                label = tk.Label(self.choices, text=version, bg=PANEL, fg=FG, anchor="w",
                                 justify="left", wraplength=380, cursor="hand2",
                                 font=(self.cjk_font, 10), padx=8, pady=3)
                label.pack(fill="x", pady=1)
                label.bind("<Button-1>", lambda e, v=version: self._use_version(v))
        if result["words"]:
            tk.Label(self.choices, text="点蠢词换个意思", bg=BG, fg=MUTED, anchor="w",
                     font=(self.cjk_font, 8)).pack(fill="x", pady=(8, 2))
            row = None
            for i, word in enumerate(result["words"]):
                if i % 3 == 0:  # three words per row
                    row = tk.Frame(self.choices, bg=BG)
                    row.pack(fill="x")
                current = result["chosen"].get(word["english"]) or "正常"
                button = tk.Menubutton(
                    row, text=f"{word['english']} → {current} ▾", bg=PANEL, fg=FG,
                    activebackground=ACCENT, activeforeground=BG, relief="flat", bd=0,
                    cursor="hand2", font=(self.cjk_font, 9), padx=6, pady=2)
                menu = tk.Menu(button, tearoff=False, font=(self.cjk_font, 10))
                for option in word["options"]:
                    menu.add_command(label=option,
                                     command=lambda w=word["english"], o=option: self._switch(w, o))
                menu.add_separator()
                menu.add_command(label="正常翻译",
                                 command=lambda w=word["english"]: self._switch(w, None))
                button.config(menu=menu)
                button.pack(side="left", padx=(0, 4), pady=2)

    def _use_version(self, version):
        """Show another whole version instead of the current one."""
        self.last["shown"] = version
        self._show(version)
        self._set_status("换成了另一个版本")
        self._show_choices()

    def _switch(self, english, option):
        """Switch one stupid word, then rebuild the sentence in a worker thread."""
        self.last["chosen"][english] = option
        self.request += 1
        self._set_status("重新造句…")
        threading.Thread(target=self._rebuild, args=(self.request, dict(self.last["chosen"])),
                         daemon=True).start()

    def _rebuild(self, request, chosen):
        """Worker thread: the sentence with the switched words, sent back via events."""
        try:
            sentence = adjust(self.last["text"], chosen, self.last["proper"])
        except Exception as error:
            self.events.put(("error", request, str(error)))
        else:
            self.events.put(("adjusted", request, sentence))

    def copy(self):
        """Copy the translation to the clipboard."""
        text = self.output.get("1.0", "end").strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self._set_status("Copied")

    def _poll(self):
        """Handle everything other threads put in self.events, then check again in POLL_MS.

        Events: ("toggle",) from the hotkey, ("hotkey", ok) once the hotkey thread starts,
        ("result", request, options dict, mode, seconds), ("adjusted", request, sentence) and
        ("error", request, message) from workers.
        """
        try:
            while True:
                kind, *args = self.events.get_nowait()
                if kind == "toggle":
                    self.toggle()
                elif kind == "hotkey" and not args[0]:
                    self.hotkey_hint.config(text="")  # the hotkey doesn't work, so don't offer it
                elif kind == "adjusted" and args[0] == self.request:
                    self.last["shown"] = args[1]
                    self._show(args[1])
                    self._show_choices()
                    self._set_status("换好了")
                elif kind in ("result", "error") and args[0] == self.request:
                    if kind == "result":
                        _, result, mode, seconds = args
                        result["shown"] = result["translation"]
                        result["chosen"] = {w["english"]: w["chosen"] for w in result["words"]}
                        self.last = result
                        self._show(result["translation"])
                        self._show_choices()
                        self._set_status(f"{MODE_INFO.get(mode, (mode,))[0]} · {seconds:.1f}s")
                    else:
                        self._show(args[1], error=True)
                        self._set_status("Translation failed", error=True)
        except queue.Empty:
            pass  # nothing left to handle for now
        self.root.after(POLL_MS, self._poll)


def main():
    """Open the overlay window and run it until it is closed."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on scaled displays
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    Overlay(root)
    root.mainloop()


if __name__ == "__main__":
    main()
