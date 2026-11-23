"""The overlay's 玩梗程度 switch and a meme's menu, and the ⚙ window's 机器人的梗 page, built
for real but never shown. Skipped without tkinter or a screen (on Linux: xvfb-run)."""

import os
import time
import unittest
from unittest import mock

from sbtranslator import meme_cues, settings

from helpers import Offline, save_cues

try:
    import tkinter as tk
    from sbtranslator import overlay, settings_window
except ImportError:  # a Python without tkinter
    tk = None

MEME_RESULT = {
    "translation": "已经结束了，现在这里是皮肤局",
    "versions": ["已经结束了，现在这里是皮肤局", "结束了，现在这是一场皮肤游戏"],
    "words": [{"english": "it's over", "chosen": "已经结束了", "options": ["已经结束了", "结束嘞"],
               "meme": True},
              {"english": "skin", "chosen": "皮肤", "options": ["皮肤", "外皮"]}],
    "proper": "结束了，现在这是一场皮肤游戏", "checked": False, "check_error": None,
    "language": "en", "suggested_mode": None,
    "meme_note": "没有模型确认梗：no model in the tests"}


@unittest.skipIf(tk is None, "no tkinter")
class Windows(Offline):
    def setUp(self):
        super().setUp()
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("no screen")
        self.root.withdraw()  # the windows are never shown, not even the ⚙ window
        self.patch(settings_window.SettingsWindow, "_place", lambda w: w.window.withdraw())
        self.patch(settings_window.SettingsWindow, "show")
        self.addCleanup(self.close)
        self.patch(meme_cues, "BUILT_IN_FILE", os.path.join(self.folder, "no built-in cues"))
        meme_cues._entries_cache = None
        self.options = self.patch(overlay, "options", return_value=dict(MEME_RESULT))
        self.overlay = overlay.Overlay(self.root)

    def close(self):
        for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            self.root.after_cancel(job)  # the overlay's polling, focus and offers
        self.root.destroy()

    def wait(self, done, seconds=3.0):
        """Let the window handle its events until done() or the time is up."""
        end = time.monotonic() + seconds
        while not done() and time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)
        self.root.update()

    def translate(self, result=None):
        if result:
            self.options.return_value = result
        self.overlay.input.insert("1.0", "it's over, this is a skin game now")
        self.overlay.last = None
        self.overlay.translate()
        self.wait(lambda: self.overlay.last is not None)

    def menus(self):
        """{button text: [menu labels]} for the words under the result."""
        found = {}
        for widget in self.overlay.choices.winfo_children():
            for button in [widget] + widget.winfo_children():
                if isinstance(button, tk.Menubutton):
                    menu = self.root.nametowidget(button.cget("menu"))
                    found[button.cget("text")] = [menu.entrycget(i, "label")
                                                  for i in range(menu.index("end") + 1)
                                                  if menu.type(i) != "separator"]
        return found

    def labels(self):
        return [w.cget("text") for w in self.overlay.choices.winfo_children()
                if isinstance(w, tk.Label)]

    def test_the_switch(self):
        button = self.overlay.memes_button
        self.assertEqual(button.cget("text"), "梗：适量 ▾")
        self.overlay.meme_level.set("max")
        self.assertEqual((button.cget("text"), settings.meme_level()), ("梗：尽量多 ▾", "max"))
        self.overlay.mode.set("proper")
        self.overlay._on_mode()
        self.assertEqual(str(button.cget("state")), "disabled")  # memes are for Stupid only
        self.translate()
        self.assertEqual(self.options.call_args[1]["memes"], "max")

    def test_a_meme_in_the_result(self):
        self.translate()
        self.assertEqual(self.options.call_args[1]["memes"], "some")
        menus = self.menus()
        self.assertEqual(menus["it's over → 已经结束了 ▾"],
                         ["已经结束了", "结束嘞", "正常翻译", "改「已经结束了」的说法或关掉它…"])
        self.assertEqual(menus["skin → 皮肤 ▾"], ["皮肤", "外皮", "正常翻译", "加进我的词表…"])
        self.assertIn("没有模型确认梗：no model in the tests", self.labels())
        self.assertTrue(self.overlay.status.cget("text").startswith("Stupid · "))

    def test_too_slow(self):
        self.translate(dict(MEME_RESULT, meme_note="梗模型超时"))
        self.assertTrue(self.overlay.status.cget("text").endswith(" · 梗模型超时"))
        self.assertNotIn("梗模型超时", self.labels())

    def test_the_bot_memes_page(self):
        save_cues()
        self.overlay.open_settings(meme="已经结束了")
        window = self.overlay.settings_window
        page = window.memes_page
        self.wait(lambda: False, 0.1)
        self.assertTrue(page.frame.winfo_manager())
        self.assertFalse(window.words_page.winfo_manager())
        self.assertEqual((page.phrase, page.cues.get()), ("已经结束了", "it's over?; gg it's over"))
        self.assertIn("8 个梗", page.source.cget("text"))

        page.cues.set("it's over?; gg it's over; its over")
        page.save()
        self.assertEqual(settings.meme_edits()["cues"],
                         {"已经结束了": ["it's over?", "gg it's over", "its over"]})
        self.assertEqual(page.listed["已经结束了"][1], "你改的")
        page.cues.set("{X} is over")
        page.save()  # no template: {X} doesn't work for this meme
        self.assertEqual(window.status.cget("fg"), overlay.ERROR)
        page.back_to_model()
        self.assertEqual(settings.meme_edits()["cues"], {})
        page.turn_off()
        self.assertEqual(settings.meme_edits()["off"], {"已经结束了"})
        self.assertEqual(page.off_button.cget("text"), "重新用")
        page.turn_off()
        self.assertEqual(settings.meme_edits()["off"], set())

        page.search.set("jungle")
        self.assertEqual(page.count.cget("text"), "1 / 8 个")
        window.table.set("everyday")
        window.show_table()
        self.assertTrue(window.words_page.winfo_manager())
        self.assertFalse(page.frame.winfo_manager())

    def test_a_reset_puts_the_switch_back(self):
        self.overlay.meme_level.set("none")
        self.overlay.open_settings()
        with mock.patch("sbtranslator.settings_window.messagebox.askyesno", return_value=True):
            self.overlay.settings_window.reset()
        self.assertEqual((self.overlay.meme_level.get(), settings.meme_level()),
                         ("some", "some"))
        self.assertEqual(self.overlay.memes_button.cget("text"), "梗：适量 ▾")

    def test_a_reset_on_the_bot_memes_page(self):
        settings.set_meme_off("合影")
        self.overlay.open_settings(meme="合影")
        page = self.overlay.settings_window.memes_page
        self.assertEqual(page.listed["合影"][1], "关掉了")
        with mock.patch("sbtranslator.settings_window.messagebox.askyesno", return_value=True):
            self.overlay.settings_window.reset()
        self.assertEqual(settings.meme_edits()["off"], set())
        self.assertEqual(page.listed["合影"][1], "还没写说法")  # no cues in this test


if __name__ == "__main__":
    unittest.main()
