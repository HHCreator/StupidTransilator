"""The ⚙ window's 机器人的梗 page: the memes MemeLearnerBot learned, as the Stupid mode uses
them, and your changes to them. Every change is saved in your settings (settings.py) and
used from the next sentence on:

    where from      how many memes there are and where they come from (bot_memes.py), and
                    选机器人的文件夹… for the exe, which can't find the bot's folder by itself
    the list        every meme, its English cues and its state (meme_cues.rows())
    below it        the picked meme's meaning, and its cues to change: ; between them, ? at
                    the end for a cue the model confirms, {X} for any player or team.
                    用回模型写的 undoes your change; 关掉 stops using the meme

The overlay opens this page from a meme's menu ("改「…」的说法或关掉它…"), which calls
SettingsWindow.show_meme() and so select().
"""

import os
import tkinter as tk
from tkinter import filedialog, ttk

from . import bot_memes, meme_cues, settings
from .overlay import BG, FG, MUTED, PANEL

ABOUT = ("机器人学到的梗：英文里出现一个梗的英文说法时，Stupid 模式把那几个词换成这个梗"
         "（每句几个看上面的玩梗程度）。说法是模型写的，你可以改；不想要的梗可以关掉。")
HINT = ("说法之间用 ; 隔开，每条 1 到 6 个英文词。末尾带 ? 的要模型确认这句真是这个意思才用；"
        "{X} 代表任何选手或战队，只用在「名字 + 固定说法」的梗上（{X}同意了）。")


class BotMemesPage:
    """The 机器人的梗 page of a SettingsWindow (it uses the window's widgets and status line).
    frame is what the window shows or hides."""

    def __init__(self, window, parent):
        self.window = window
        self.font = window.font
        self.frame = tk.Frame(parent, bg=BG)
        self.memes = {}  # the bot's memes, as listed now
        self.listed = {}  # phrase -> (its cues as text, its state), every meme
        self.items = {}  # Treeview item -> phrase, for the rows shown now
        self.phrase = None  # the meme picked now
        self.search = tk.StringVar()
        self.cues = tk.StringVar()
        self._build()
        self.search.trace_add("write", lambda *args: self._fill())

    def _build(self):
        """The widgets, top to bottom: about, where from, search, list, picked meme, hint."""
        page = self.frame
        tk.Label(page, text=ABOUT, bg=BG, fg=MUTED, anchor="w", justify="left",
                 wraplength=520, font=(self.font, 9)).pack(fill="x", pady=(6, 6))

        # Where the memes come from, and the bot's folder
        self.source_row = row = tk.Frame(page, bg=BG)
        row.pack(fill="x")
        self.source = tk.Label(row, bg=BG, fg=FG, anchor="w", justify="left", wraplength=300,
                               font=(self.font, 9))
        self.source.pack(side="left", fill="x", expand=True)
        self.forget_button = self.window._button(row, "改回自动找", self.forget_folder)
        self.forget_button.pack(side="right", padx=(6, 0))
        self.window._button(row, "选机器人的文件夹…", self.choose_folder).pack(side="right")
        self.missing = tk.Label(page, bg=BG, fg=MUTED, anchor="w", justify="left",
                                wraplength=520, font=(self.font, 8))

        # Search, and how many
        row = tk.Frame(page, bg=BG)
        row.pack(fill="x", pady=(6, 0))
        tk.Label(row, text="搜索", bg=BG, fg=MUTED, font=(self.font, 9)).pack(side="left")
        self.window._entry(row, self.search, width=18).pack(side="left", padx=(6, 0))
        self.count = tk.Label(row, bg=BG, fg=MUTED, font=(self.font, 8))
        self.count.pack(side="right")

        # The list
        frame = tk.Frame(page, bg=PANEL)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(frame, columns=("meme", "cues", "state"), show="headings",
                                 selectmode="browse", style="SB.Treeview", height=8)
        for column, heading, width in (("meme", "梗", 120), ("cues", "英文说法", 250),
                                       ("state", "状态", 90)):
            self.tree.heading(column, text=heading, anchor="w")
            self.tree.column(column, width=width, minwidth=50, anchor="w",
                             stretch=column == "cues")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview,
                                  style="SB.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # The picked meme: what it means, and its cues to change
        self.detail = tk.Label(page, bg=BG, fg=FG, anchor="w", justify="left", wraplength=520,
                               font=(self.font, 9))
        self.detail.pack(fill="x", pady=(8, 0))
        row = tk.Frame(page, bg=BG)
        row.pack(fill="x", pady=(4, 0))
        tk.Label(row, text="说法", bg=BG, fg=MUTED, font=(self.font, 9)).pack(side="left")
        box = self.window._entry(row, self.cues, width=28)
        box.pack(side="left", fill="x", expand=True, padx=(6, 0))
        box.bind("<Return>", lambda e: self.save())
        self.save_button = self.window._button(row, "存说法", self.save, accent=True)
        self.save_button.pack(side="left", padx=(8, 0))
        self.model_button = self.window._button(row, "用回模型写的", self.back_to_model)
        self.model_button.pack(side="left", padx=(6, 0))
        self.off_button = self.window._button(row, "关掉", self.turn_off)
        self.off_button.pack(side="left", padx=(6, 0))
        tk.Label(page, text=HINT, bg=BG, fg=MUTED, anchor="w", justify="left", wraplength=520,
                 font=(self.font, 8)).pack(fill="x", pady=(4, 0))
        self._show_picked(None)

    # -- the list ---------------------------------------------------------------------------

    def refresh(self, select=None):
        """Read the memes again (the bot may have learned more meanwhile) and list them, with
        select (a meme) or the one picked before still picked."""
        self.memes = bot_memes.memes()
        chosen = settings.bot_folder()
        if self.memes:
            text = f"{len(self.memes)} 个梗 · {bot_memes.source()}"
        else:
            text = "没找到机器人的梗：选机器人的文件夹，或者连上网，等它从 GitHub 下载。"
        if chosen and not bot_memes.is_bot_folder(chosen):
            text += f"\n选的 {chosen} 里没有 memelearner\\data\\memes.json"
        self.source.config(text=text)
        self.forget_button.config(state="normal" if chosen else "disabled")
        self.listed = {phrase: (cues, state) for phrase, cues, state in meme_cues.rows()}
        missing = sum(state == meme_cues.NOT_WRITTEN for cues, state in self.listed.values())
        if missing:
            self.missing.config(text=f"还有 {missing} 个梗没写英文说法：翻译时在后台写（先用 "
                                     "DeepSeek flash，没有就用本地的 qwen3:14b）。")
            self.missing.pack(fill="x", pady=(4, 0), after=self.source_row)
        else:
            self.missing.pack_forget()
        picked = select or self.phrase
        self._fill(picked)
        self._show_picked(picked if picked in self.listed else None)

    def _fill(self, select=None):
        """List the memes that match the search (in the meme, its meaning or its cues)."""
        query = self.search.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        self.items = {}
        for phrase, (cues, state) in self.listed.items():
            meaning = (self.memes.get(phrase) or {}).get("meaning", "")
            if query and not any(query in part.lower() for part in (phrase, meaning, cues, state)):
                continue
            item = self.tree.insert("", "end", values=(phrase, cues or "—", state))
            self.items[item] = phrase
        shown, total = len(self.items), len(self.listed)
        self.count.config(text=f"{shown} 个" if shown == total else f"{shown} / {total} 个")
        item = next((i for i, phrase in self.items.items() if phrase == select), None)
        if item:
            self.tree.selection_set(item)
            self.tree.see(item)

    def _on_select(self, event=None):
        picked = self.tree.selection()
        if picked and picked[0] in self.items and self.items[picked[0]] != self.phrase:
            self._show_picked(self.items[picked[0]])  # not the same one: keep what was typed

    def _show_picked(self, phrase):
        """Show what a meme means and its cues in the box below the list (None: nothing)."""
        self.phrase = phrase
        buttons = (self.save_button, self.model_button, self.off_button)
        if phrase is None:
            self.detail.config(text="点上面的一个梗：看它的意思，改它的英文说法，或者关掉它。")
            self.cues.set("")
            for button in buttons:
                button.config(state="disabled")
            return
        meme, entry = self.memes.get(phrase, {}), meme_cues.entries().get(phrase) or {}
        lines = [f"{phrase}：{meme.get('meaning') or meme.get('english') or '（机器人没写意思）'}"]
        more = []
        if meme.get("variants"):
            more.append("变体 " + "、".join(meme["variants"][:6]))
        if entry.get("template"):
            more.append(f"模板 {entry['template']}")
        if entry.get("why"):
            more.append(f"模型说：{entry['why']}")
        if more:
            lines.append("；".join(more))
        self.detail.config(text="\n".join(lines))
        self.cues.set(self.listed.get(phrase, ("", ""))[0])
        edits = settings.meme_edits()
        self.save_button.config(state="normal")
        self.model_button.config(state="normal" if phrase in edits["cues"] else "disabled")
        self.off_button.config(text="重新用" if phrase in edits["off"] else "关掉", state="normal")

    def select(self, phrase):
        """Show one meme, picked, with the search cleared."""
        self.search.set("")
        self.refresh(phrase)

    # -- changing a meme ----------------------------------------------------------------------

    def _changed(self, phrase, said):
        self.refresh(phrase)  # the list and the box below it as they are saved now
        self.window._say(said)

    def save(self):
        """Use the cues in the box for the picked meme instead of the model's."""
        phrase = self.phrase
        if phrase is None:
            return
        texts = meme_cues.split_cues(self.cues.get())
        if not texts:
            return self.window._say("说法是空的。不想用这个梗就点「关掉」。", error=True)
        good, bad = meme_cues.check_yours(phrase, texts)
        if bad:
            return self.window._say(
                f"这几条不行：{'；'.join(bad)}。每条是 1 到 {meme_cues.MAX_CUE_WORDS} 个英文词，"
                "{X} 只用在带模板的梗上。", error=True)
        if "; ".join(good) == self.listed.get(phrase, ("",))[0]:
            return self.window._say("说法没变。")
        try:
            settings.set_meme_cues(phrase, good)
        except OSError as error:
            return self.window._say(f"设置存不下：{error}", error=True)
        self._changed(phrase, f"存好了：「{phrase}」的说法是 {'; '.join(good)}。下一句翻译就用上。")

    def back_to_model(self):
        """Undo your cues for the picked meme: the model's are used again."""
        phrase = self.phrase
        try:
            settings.set_meme_cues(phrase, None)
        except OSError as error:
            return self.window._say(f"设置存不下：{error}", error=True)
        self._changed(phrase, f"「{phrase}」又用模型写的说法了。")

    def turn_off(self):
        """Stop using the picked meme, or use it again."""
        phrase = self.phrase
        off = phrase not in settings.meme_edits()["off"]
        try:
            settings.set_meme_off(phrase, off)
        except OSError as error:
            return self.window._say(f"设置存不下：{error}", error=True)
        self._changed(phrase, f"关掉了「{phrase}」：翻译时不用它了。" if off
                      else f"「{phrase}」又会用上了。")

    # -- the bot's folder ---------------------------------------------------------------------

    def choose_folder(self):
        """Read the memes from a bot's folder picked by hand (the exe can't find it itself)."""
        path = filedialog.askdirectory(parent=self.window.window, mustexist=True,
                                       title="选 MemeLearnerBot 的文件夹")
        if not path:
            return
        path = os.path.normpath(path)
        if not bot_memes.is_bot_folder(path):
            return self.window._say(f"{path} 里没有 memelearner\\data\\memes.json，"
                                    "不像机器人的文件夹。", error=True)
        try:
            settings.set_bot_folder(path)
        except OSError as error:
            return self.window._say(f"设置存不下：{error}", error=True)
        self.refresh()
        self.window._say(f"以后从 {path} 读机器人的梗：你在机器人的报告里加了梗，下一句翻译就用上。")

    def forget_folder(self):
        """Forget the folder picked by hand: look for the bot's memes by themselves again."""
        try:
            settings.set_bot_folder(None)
        except OSError as error:
            return self.window._say(f"设置存不下：{error}", error=True)
        self.refresh()
        self.window._say("改回自动找机器人的梗了。")
