"""Reading the memes MemeLearnerBot learned (bot_memes.py) and the 玩梗程度 setting."""

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

import sbtranslator
from sbtranslator import bot_memes, settings, translator

from helpers import MEMES, Offline, write_bot


def touch_later(path):
    """Give a file a new modification time, as an edit a second later would."""
    later = os.stat(path).st_mtime + 2
    os.utime(path, (later, later))


class WhereTheMemesComeFrom(Offline):
    def test_the_bot_folder_in_the_environment(self):
        self.assertEqual(set(bot_memes.memes()), set(MEMES))
        self.assertEqual(bot_memes.source(), f"{bot_memes.LOCAL} {self.bot}")
        self.assertEqual(bot_memes.memes()["野距"]["variants"], ["打野差距"])

    def test_the_folder_chosen_in_the_settings_wins(self):
        other = os.path.join(self.folder, "other bot")
        write_bot(other, memes={"别奶了": {"meaning": "别夸了"}})
        settings.set_bot_folder(other)
        self.assertEqual(list(bot_memes.memes()), ["别奶了"])
        self.assertEqual(bot_memes.bot_folder(), other)

    def test_the_folder_next_to_the_translators_own(self):
        with mock.patch.dict(os.environ, {"SBTRANSLATOR_BOT_FOLDER": ""}):
            self.patch(bot_memes, "SOURCE_ROOT", os.path.join(self.folder, "SBtranslator"))
            self.assertEqual(bot_memes.bot_folder(), self.bot)
            self.patch(bot_memes.sys, "frozen", True, create=True)
            self.assertIsNone(bot_memes.bot_folder())  # the exe must be told in the ⚙ window

    def test_a_chosen_folder_without_memes_is_not_used(self):
        settings.set_bot_folder(os.path.join(self.folder, "nothing here"))
        self.assertIsNone(bot_memes.bot_folder())
        self.assertEqual(bot_memes.memes(), {})  # no GitHub copy either: no memes, no crash

    def test_github_copy_without_a_bot_folder(self):
        settings.set_bot_folder(os.path.join(self.folder, "nothing here"))
        online = {"memes": {"别奶了": {"meaning": "别夸了", "english": "Don't jinx it"}}}
        files = {"memes.json": json.dumps(online, ensure_ascii=False).encode("utf-8"),
                 "nicknames.txt": "Doran = 多兰, 兰\n".encode("utf-8")}
        self.download.side_effect = lambda url, timeout=0: files[url.rsplit("/", 1)[1]]
        self.download.reset_mock()
        bot_memes.fetch()
        self.assertTrue(self.download.call_args_list[0][0][0].startswith(bot_memes.GITHUB))
        self.assertEqual(bot_memes.source(), bot_memes.GITHUB_COPY)
        self.assertEqual(list(bot_memes.memes()), ["别奶了"])
        self.assertEqual(bot_memes.nicknames(), {"Doran": ["多兰", "兰"]})
        self.download.reset_mock()
        bot_memes.files()  # the copy is new: no download
        self.assertFalse(self.download.called)

    def test_an_old_github_copy_is_downloaded_again_in_the_background(self):
        settings.set_bot_folder(os.path.join(self.folder, "nothing here"))
        self.download.reset_mock()
        with mock.patch.object(bot_memes.threading, "Thread") as thread:
            bot_memes.files()
            bot_memes.files()  # not again right away, after a failed try
        thread.assert_called_once()
        self.assertEqual(thread.call_args[1]["target"], bot_memes._fetch_in_background)

    def test_a_broken_download_replaces_nothing(self):
        settings.set_bot_folder(os.path.join(self.folder, "nothing here"))
        self.download.side_effect = lambda url, timeout=0: b"<html>rate limited</html>"
        with self.assertRaises(ValueError):
            bot_memes.fetch()
        self.assertFalse(os.path.exists(bot_memes.github_folder()))

    def test_the_exes_own_copy_comes_last(self):
        settings.set_bot_folder(os.path.join(self.folder, "nothing here"))
        os.makedirs(bot_memes.BUNDLED)
        with open(os.path.join(bot_memes.BUNDLED, "memes.json"), "w", encoding="utf-8") as f:
            json.dump({"memes": {"合影": {"meaning": "合影留念"}}}, f, ensure_ascii=False)
        self.assertEqual(bot_memes.source(), bot_memes.BUNDLED_COPY)
        self.assertEqual(list(bot_memes.memes()), ["合影"])


class ReadingTheFiles(Offline):
    def memes_file(self):
        return os.path.join(self.bot, *bot_memes.MEMES_FILE)

    def test_read_again_when_the_bot_changes_the_file(self):
        self.assertIn("野距", bot_memes.memes())
        write_bot(self.bot, memes={"已经结束了": MEMES["已经结束了"]})
        touch_later(self.memes_file())
        self.assertEqual(list(bot_memes.memes()), ["已经结束了"])

    def test_a_half_written_file_keeps_the_memes_read_before(self):
        bot_memes.memes()
        with open(self.memes_file(), "w", encoding="utf-8") as f:
            f.write('{"memes": {"野距"')
        touch_later(self.memes_file())
        self.assertEqual(set(bot_memes.memes()), set(MEMES))

    def test_broken_entries_are_skipped_and_missing_parts_filled_in(self):
        found = bot_memes.parse_memes(json.dumps({"memes": {
            "好兄弟": {"meaning": " 帮对面的选手 ", "variants": ["好兄弟", "多兰好兄弟", 3]},
            "坏的": "not a meme", "": {"meaning": "no phrase"}}}, ensure_ascii=False))
        self.assertEqual(found, {"好兄弟": {"meaning": "帮对面的选手", "english": "",
                                            "variants": ["多兰好兄弟"], "examples": [],
                                            "notes": [], "games": []}})

    def test_nickname_table(self):
        found = bot_memes.parse_nicknames(
            "# 说明\nChovy = 超威, 大超, chooovy  # 他的外号\nCanyon = 三叔，三姆斯\n"
            "Chovy = 超大哥\n没有等号的行\n")
        self.assertEqual(found, {"Chovy": ["超威", "大超", "超大哥"], "Canyon": ["三叔", "三姆斯"]})
        self.assertEqual(bot_memes.nicknames(), {"Chovy": ["超威", "大超"],
                                                 "Canyon": ["三叔", "三姆斯"]})
        self.assertEqual(bot_memes.squeezed("ＣＨＯooovy"), "chovy")


class MemeLevel(Offline):
    def test_default_and_saved_level(self):
        self.assertEqual(bot_memes.level_of(), "some")
        settings.set_meme_level("max")
        settings.reload()  # as if the program started again
        self.assertEqual(bot_memes.level_of(), "max")
        settings.set_meme_level("some")  # the default isn't written down
        with open(settings.settings_file(), encoding="utf-8") as f:
            self.assertNotIn("meme_level", json.load(f))
        settings.set_meme_level("none")
        settings.reset()
        self.assertEqual(settings.meme_level(), "some")

    def test_level_names(self):
        self.assertEqual(bot_memes.level_of("尽量多"), "max")
        self.assertEqual(bot_memes.level_of(" None "), "none")
        for wrong in ("lots", "", 2):
            with self.assertRaises(ValueError):
                bot_memes.level_of(wrong)
        with self.assertRaises(ValueError):
            settings.set_meme_level("lots")

    def test_an_unknown_level_is_refused_before_translating(self):
        with mock.patch.object(translator, "translate") as google:
            with self.assertRaises(ValueError):
                sbtranslator.translate("jungle gap", memes="lots")
            with self.assertRaises(ValueError):
                sbtranslator.options("jungle gap", mode="proper", memes="lots")
        google.assert_not_called()

    def test_command_line_flag(self):
        with mock.patch.object(sbtranslator, "translate", return_value="野距") as translate, \
                mock.patch.object(translator.sys, "argv", ["translator.py", "--memes", "max",
                                                           "jungle", "gap"]), \
                redirect_stdout(io.StringIO()) as out:
            translator.main()
        self.assertEqual(translate.call_args[1]["memes"], "max")
        self.assertEqual(translate.call_args[0][0], "jungle gap")
        self.assertEqual(out.getvalue().strip(), "野距")
        with mock.patch.object(translator.sys, "argv", ["translator.py", "--memes", "lots", "x"]), \
                redirect_stdout(io.StringIO()) as out:
            translator.main()
        self.assertIn("none, some or max", out.getvalue())

    def test_report(self):
        with redirect_stdout(io.StringIO()) as out:
            bot_memes.main()
        self.assertIn(f"{len(MEMES)} 个梗", out.getvalue())
        self.assertIn("适量", out.getvalue())


if __name__ == "__main__":
    unittest.main()
