"""The overlay's ⚙ window: your own word table entries, the rarity, importing and exporting
your settings, and the desktop shortcut.

Every change is saved at once (settings.py keeps it in a file outside the program folder)
and used from the next translation on, so nobody has to edit the data files by hand:

    稀有度       the 逐词 mode's slider: the same variable as the overlay's slider, remembered
    词表         one table at a time (梗和名字, 日常意思, 缩写, 短语, 外号). Pick a row to change
                 or delete it, or type a new English word and its Chinese and press Enter
    buttons      导入设置… / 导出设置… (a .json file; an old data/*.json table imports too),
                 恢复默认, and 在桌面放快捷方式 (shortcut.py, Windows)

The overlay opens it with Overlay.open_settings(), also from a stupid word's menu
("加进我的词表…"), which calls prefill() with that word and its chosen meaning.
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from . import settings, shortcut
from . import translator as t
from .overlay import ACCENT, ACCENT_HOVER, BG, ERROR, FG, MUTED, PANEL, TITLE

# Each table's button, what it does, and the heading of its second column
TABLE_INFO = {
    "memes": ("梗和名字", "总是换掉（除了 Proper 和文言文，每个模式都用）："
                         "frozen → 冰雪奇缘，lol → 英雄联盟", "换成"),
    "everyday": ("日常意思", "句子本来不是这个意思时才换（Stupid 和中文模式）："
                            "major → 主要，top → 顶部", "换成"),
    "acronyms": ("缩写", "先展开成英文，再一个词一个词地翻（Stupid 和中文模式）："
                        "hltv → half life tv → 一半生活电视", "展开成"),
    "phrases": ("短语", "几个词一起换（Stupid 和中文模式）：zywoo play → 载物玩耍", "换成"),
    "nicknames": ("外号", "选手名换成中文外号（Stupid 和中文模式）：zywoo → 载物", "外号"),
}
YOURS = (settings.MINE, settings.CHANGED)  # the labels of rows that are your own entries


class SettingsWindow:
    """The ⚙ window of an Overlay (it uses the overlay's fonts and rarity variable)."""

    def __init__(self, overlay):
        self.overlay = overlay
        self.font = overlay.cjk_font
        self.items = {}  # Treeview item -> its English, for the rows shown now
        self.everything = {}  # English -> (Chinese, label), the whole table shown now
        window = self.window = tk.Toplevel(overlay.root)
        window.title(f"{TITLE} 设置")
        window.configure(bg=BG)
        window.attributes("-topmost", True)  # the overlay is always on top, so this is too
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.bind("<Escape>", lambda e: self.close())
        self.table = tk.StringVar(value=settings.TABLES[0])
        self.search = tk.StringVar()
        self.english = tk.StringVar()
        self.chinese = tk.StringVar()
        self._style()
        self._build()
        self.show_table()
        self.search.trace_add("write", lambda *args: self._fill())
        self.english.trace_add("write", lambda *args: self._on_typing())
        self._place()
        self.english_box.focus_set()

    # -- layout ---------------------------------------------------------------------------

    def _style(self):
        """Dark colours for the table and its scrollbar (ttk widgets, styled by name)."""
        style = ttk.Style(self.window)
        style.theme_use("clam")  # Windows' own theme ignores colours; clam can be dark
        row_height = tkfont.Font(root=self.window, family=self.font, size=10).metrics("linespace")
        style.configure("SB.Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                        borderwidth=0, rowheight=row_height + 8, font=(self.font, 10))
        style.map("SB.Treeview", background=[("selected", ACCENT)], foreground=[("selected", BG)])
        style.layout("SB.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # no frame
        style.configure("SB.Treeview.Heading", background=BG, foreground=MUTED, borderwidth=0,
                        relief="flat", font=(self.font, 9))
        style.map("SB.Treeview.Heading", background=[("active", BG)], foreground=[("active", FG)])
        style.configure("SB.Vertical.TScrollbar", background=PANEL, troughcolor=BG,
                        bordercolor=BG, lightcolor=PANEL, darkcolor=PANEL, arrowcolor=MUTED,
                        gripcount=0)
        style.map("SB.Vertical.TScrollbar", background=[("active", ACCENT)])

    def _build(self):
        """Create the widgets, top to bottom: rarity, table buttons, table, editor, buttons."""
        body = tk.Frame(self.window, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        # Rarity: the overlay's own variable, so both sliders move together
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x")
        tk.Label(row, text="稀有度", bg=BG, fg=FG, font=(self.font, 10, "bold")).pack(side="left")
        tk.Scale(
            row, variable=self.overlay.rarity, from_=0, to=t.MAX_RARITY, resolution=0.1,
            orient="horizontal", showvalue=False, bd=0, highlightthickness=0,
            sliderrelief="flat", sliderlength=18, width=14, bg=ACCENT,
            activebackground=ACCENT_HOVER, troughcolor=PANEL, length=150,
        ).pack(side="left", padx=(10, 6))
        self.rarity_label = tk.Label(row, bg=BG, fg=FG, width=4, anchor="w", font=("Segoe UI", 10))
        self.rarity_label.pack(side="left")
        tk.Label(row, text=f"只管逐词模式：0 正常，3 离谱，默认 {t.TARGET_RARITY}", bg=BG,
                 fg=MUTED, font=(self.font, 8)).pack(side="left")
        self.show_rarity()

        # Which table
        tk.Label(body, text="词表", bg=BG, fg=FG, anchor="w",
                 font=(self.font, 10, "bold")).pack(fill="x", pady=(14, 4))
        tables = tk.Frame(body, bg=BG)
        tables.pack(fill="x")
        for column, table in enumerate(settings.TABLES):
            tables.columnconfigure(column, weight=1, uniform="table")
            tk.Radiobutton(
                tables, text=TABLE_INFO[table][0], value=table, variable=self.table,
                command=self.show_table, indicatoron=False, bd=0, relief="flat",
                cursor="hand2", takefocus=False, bg=PANEL, fg=FG, activebackground=ACCENT,
                activeforeground=BG, selectcolor=ACCENT, font=(self.font, 10), padx=6, pady=4,
            ).grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 3, 0))
        self.about = tk.Label(body, bg=BG, fg=MUTED, anchor="w", justify="left",
                              wraplength=520, font=(self.font, 9))
        self.about.pack(fill="x", pady=(6, 6))

        # Search, and how many rows
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x")
        tk.Label(row, text="搜索", bg=BG, fg=MUTED, font=(self.font, 9)).pack(side="left")
        self._entry(row, self.search, width=18).pack(side="left", padx=(6, 0))
        self.count = tk.Label(row, bg=BG, fg=MUTED, font=(self.font, 8))
        self.count.pack(side="right")

        # The table
        frame = tk.Frame(body, bg=PANEL)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(frame, columns=("english", "chinese", "source"),
                                 show="headings", selectmode="browse", style="SB.Treeview",
                                 height=10)
        for column, heading, width in (("english", "英文", 160), ("chinese", "换成", 220),
                                       ("source", "来源", 70)):
            self.tree.heading(column, text=heading, anchor="w")
            self.tree.column(column, width=width, minwidth=50, anchor="w",
                             stretch=column != "source")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview,
                                  style="SB.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Delete>", lambda e: self.delete())

        # The entry being added or changed
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(8, 0))
        self.english_box = self._entry(row, self.english, width=16)
        self.english_box.pack(side="left")
        tk.Label(row, text="→", bg=BG, fg=MUTED, font=("Segoe UI", 11)).pack(side="left", padx=6)
        chinese_box = self._entry(row, self.chinese, width=16)
        chinese_box.pack(side="left", fill="x", expand=True)
        for box in (self.english_box, chinese_box):
            box.bind("<Return>", lambda e: self.save())
        self.save_button = self._button(row, "添加", self.save, accent=True)
        self.save_button.pack(side="left", padx=(8, 0))
        self.delete_button = self._button(row, "删除", self.delete)
        self.delete_button.pack(side="left", padx=(6, 0))
        self.status = tk.Label(body, bg=BG, fg=MUTED, anchor="w", justify="left",
                               wraplength=520, font=(self.font, 9))
        self.status.pack(fill="x", pady=(6, 0))
        self._say("点一行可以改它或删掉；新词写在上面两格里，按回车。改了马上生效。")

        # Import, export, reset, and the desktop shortcut
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(12, 0))
        self._button(row, "导入设置…", self.import_settings).pack(side="left")
        self._button(row, "导出设置…", self.export_settings).pack(side="left", padx=(6, 0))
        self._button(row, "恢复默认", self.reset).pack(side="left", padx=(6, 0))
        button = self._button(row, "在桌面放快捷方式", self.make_shortcut)
        button.pack(side="right")
        if not shortcut.available():
            button.config(state="disabled")  # only Windows has .lnk shortcuts

        # Where the settings are kept; on Windows a click opens the folder
        where = tk.Label(body, text=f"设置存在 {settings.settings_file()}", bg=BG, fg=MUTED,
                         anchor="w", justify="left", wraplength=520, font=(self.font, 8))
        where.pack(fill="x", pady=(10, 0))
        if os.name == "nt":
            where.config(cursor="hand2")
            where.bind("<Button-1>", lambda e: self._open_folder())

    def _entry(self, parent, variable, width):
        return tk.Entry(parent, textvariable=variable, width=width, bd=0, relief="flat",
                        bg=PANEL, fg=FG, insertbackground=FG, selectbackground=ACCENT,
                        selectforeground=BG, highlightthickness=1, highlightbackground=PANEL,
                        highlightcolor=ACCENT, font=(self.font, 10))

    def _button(self, parent, text, command, accent=False):
        bg, fg = (ACCENT, BG) if accent else (PANEL, FG)
        return tk.Button(parent, text=text, command=command, bd=0, relief="flat",
                         cursor="hand2", takefocus=False, bg=bg, fg=fg,
                         activebackground=FG if accent else ACCENT, activeforeground=BG,
                         disabledforeground=MUTED, font=(self.font, 9), padx=12, pady=3)

    def _place(self):
        """Put the window next to the overlay: on its left, or on its right if no room."""
        window, root = self.window, self.overlay.root
        window.update_idletasks()
        width, height = window.winfo_reqwidth(), window.winfo_reqheight()
        x = root.winfo_x() - width - 12
        if x < 0:
            x = min(root.winfo_x() + root.winfo_width() + 12, window.winfo_screenwidth() - width)
        y = min(root.winfo_y(), window.winfo_screenheight() - height - 60)
        window.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def show(self):
        """Bring the window back to the front."""
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self):
        self.overlay.settings_window = None
        self.window.destroy()

    # -- the table ------------------------------------------------------------------------

    def show_rarity(self):
        self.rarity_label.config(text=f"{self.overlay.rarity.get():.1f}")

    def show_table(self, select=None):
        """Show the chosen table (with the row for select, an English word, picked)."""
        label, about, heading = TABLE_INFO[self.table.get()]
        self.about.config(text=about)
        self.tree.heading("chinese", text=heading)
        self._fill(select)
        self._on_typing()

    def _fill(self, select=None):
        """List the table's rows that match the search."""
        query = self.search.get().strip().lower()
        rows = settings.rows(self.table.get())
        self.everything = {english: (chinese, label) for english, chinese, label in rows}
        self.tree.delete(*self.tree.get_children())
        self.items = {}
        for english, chinese, label in rows:
            if query and query not in english and query not in chinese.lower():
                continue
            item = self.tree.insert("", "end", values=(english, chinese, label))
            self.items[item] = english
        shown = len(self.items)
        self.count.config(text=f"{shown} 条" if shown == len(rows) else f"{shown} / {len(rows)} 条")
        if select:
            item = next((i for i, english in self.items.items() if english == select), None)
            if item:
                self.tree.selection_set(item)
                self.tree.see(item)

    def _on_select(self, event=None):
        """A row was picked: put it in the two boxes below, to change or delete it."""
        picked = self.tree.selection()
        if not picked or picked[0] not in self.items:
            return
        english = self.items[picked[0]]
        if english == settings.clean_english(self.english.get()):
            return  # that word is in the boxes already: keep what was typed for it
        self.english.set(english)
        self.chinese.set(self.everything[english][0])

    def _on_typing(self):
        """The English box changed: the buttons say what they would do with that word."""
        row = self.everything.get(settings.clean_english(self.english.get()))
        self.save_button.config(text="修改" if row else "添加")
        if row and row[1] == settings.CHANGED:
            self.delete_button.config(text="恢复内置", state="normal")
        else:
            self.delete_button.config(text="删除", state="normal" if row else "disabled")

    def _say(self, text, error=False):
        self.status.config(text=text, fg=ERROR if error else MUTED)

    def prefill(self, english, chinese):
        """Show english with chinese in the boxes, ready to save, in the table that has the
        word already (or 日常意思 for an English word, 梗和名字 for a name)."""
        english = settings.clean_english(english)
        table = next((name for name in settings.TABLES
                      if any(row[0] == english for row in settings.rows(name))), None)
        if table is None:
            t._load_memes()  # loads the common word list, t._all_words
            table = "everyday" if english in t._all_words else "memes"
        self.table.set(table)
        self.search.set("")
        self.english.set(english)
        self.chinese.set(chinese or "")
        self.show_table(select=english)
        self._say("看看右边的中文对不对、词表选得对不对，再按「添加」或「修改」。")
        self.show()

    # -- changing the table ---------------------------------------------------------------

    def save(self):
        """Add the entry in the boxes, or change the word's entry."""
        try:
            english = settings.set_entry(self.table.get(), self.english.get(), self.chinese.get())
        except ValueError as problem:
            return self._say(str(problem), error=True)
        except OSError as error:
            return self._say(f"设置存不下：{error}", error=True)
        self._fill(select=english)
        self._on_typing()
        chinese = self.everything.get(english, ("",))[0]
        self._say(f"存好了：{english} → {chinese}。下次翻译就用上。")

    def delete(self):
        """Delete the word in the English box, or undo your change to a built-in one."""
        table, english = self.table.get(), settings.clean_english(self.english.get())
        row = self.everything.get(english)
        if not row:
            return
        chinese, label = row
        try:
            if label == settings.CHANGED:
                settings.restore_entry(table, english)
                self._fill(select=english)
                self.chinese.set(self.everything.get(english, ("",))[0])
                self._on_typing()
                return self._say(f"{english} 又用回了内置的「{self.chinese.get()}」。")
            question = f"删掉 {english} → {chinese}？"
            if label not in YOURS:
                question += "\n\n这是程序自带的词条。要找回来，可以再加一次，或者点「恢复默认」（你自己的改动也会一起撤销）。"
            if not messagebox.askyesno(TITLE, question, parent=self.window):
                return
            settings.delete_entry(table, english)
        except OSError as error:
            return self._say(f"设置存不下：{error}", error=True)
        self.english.set("")
        self.chinese.set("")
        self._fill()
        self._say(f"删了：{english} → {chinese}。")

    def reset(self):
        """Undo all your entries, changes and deletions, and the rarity."""
        if not messagebox.askyesno(
                TITLE, "全部恢复默认吗？你加的、改的、删的词条都会撤销，稀有度回到 "
                f"{t.TARGET_RARITY}。\n\n想留个备份，先点「导出设置…」。", parent=self.window):
            return
        try:
            settings.reset()
        except OSError as error:
            return self._say(f"设置存不下：{error}", error=True)
        self.overlay.rarity.set(settings.rarity())
        self._fill()
        self._on_typing()
        self._say("恢复默认了。")

    # -- import, export, shortcut ---------------------------------------------------------

    def import_settings(self):
        path = filedialog.askopenfilename(
            parent=self.window, title="导入设置",
            filetypes=[("设置文件", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            found = settings.import_file(path)
        except (OSError, ValueError) as error:
            return self._say(f"导入不了：{error}", error=True)
        self.overlay.rarity.set(settings.rarity())
        self._fill()
        self._on_typing()
        parts = [f"{found['words']} 个词条"]
        if found["removed"]:
            parts.append(f"删掉 {found['removed']} 个内置词条")
        if found["rarity"] is not None:
            parts.append(f"稀有度 {found['rarity']}")
        skipped = f"（{found['skipped']} 个不合格式，没导入）" if found["skipped"] else ""
        self._say(f"导入了：{'，'.join(parts)}{skipped}。同一个词以导入的为准。")

    def export_settings(self):
        path = filedialog.asksaveasfilename(
            parent=self.window, title="导出设置", defaultextension=".json",
            initialfile="SBtranslator设置.json", filetypes=[("设置文件", "*.json")])
        if not path:
            return
        try:
            settings.export_file(path)
        except OSError as error:
            return self._say(f"导出不了：{error}", error=True)
        self._say(f"导出到了 {path}。别的电脑上点「导入设置…」选它就行。")

    def make_shortcut(self):
        try:
            path = shortcut.create()
        except Exception as error:  # OSError from Windows, or anything else ctypes raises
            return self._say(f"快捷方式没建成：{error}", error=True)
        try:
            settings.set_state("shortcut_asked", sys.executable)  # no need to offer it again
        except OSError:
            pass
        self.overlay.hide_notice()
        self._say(f"桌面上放好了「{os.path.splitext(os.path.basename(path))[0]}」，双击就能打开翻译器。")

    def _open_folder(self):
        folder = os.path.dirname(os.path.abspath(settings.settings_file()))
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)  # Windows only, see _build()
