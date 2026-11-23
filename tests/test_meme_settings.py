"""The bot's memes in your settings and around them: exporting and importing the 玩梗程度
and your changes to the memes, the ⚙ window's list of memes (meme_cues.rows()) and the cues
typed there, the HTTP server's memes=, and the memes the exe comes with."""

import json
import os
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from sbtranslator import bot_memes, meme_cues, server, settings

from helpers import CUE_ANSWERS, MEMES, Offline, save_cues


class ExportAndImport(Offline):
    def export(self):
        path = os.path.join(self.folder, "export.json")
        settings.export_file(path)
        with open(path, encoding="utf-8") as f:
            return path, json.load(f)

    def write(self, content):
        path = os.path.join(self.folder, "import.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)
        return path

    def test_an_export_has_the_meme_settings_but_not_the_folder(self):
        settings.set_meme_level("max")
        settings.set_meme_off("合影")
        settings.set_meme_cues("野距", ["jungle gap", "jg diff"])
        settings.set_bot_folder(self.bot)
        path, content = self.export()
        self.assertEqual(content["meme_level"], "max")
        self.assertEqual(content["bot_memes"], {"off": ["合影"],
                                                "cues": {"野距": ["jungle gap", "jg diff"]}})
        self.assertNotIn("bot_folder", content)  # only right on this computer

        settings.reset()
        self.assertEqual(settings.meme_level(), "some")
        self.assertEqual(settings.meme_edits(), {"off": set(), "cues": {}})
        self.assertEqual(settings.bot_folder(), self.bot)  # a reset keeps the folder too
        found = settings.import_file(path)
        self.assertEqual((found["meme_level"], found["memes"]), ("max", 2))
        self.assertEqual(settings.meme_level(), "max")
        self.assertEqual(settings.meme_edits(), {"off": {"合影"},
                                                 "cues": {"野距": ["jungle gap", "jg diff"]}})

    def test_defaults_are_not_exported(self):
        path, content = self.export()
        self.assertNotIn("meme_level", content)
        self.assertNotIn("bot_memes", content)

    def test_an_import_adds_to_your_changes(self):
        settings.set_meme_off("飞神")
        settings.set_meme_cues("野距", ["jungle gap"])
        found = settings.import_file(self.write({"words": {}, "bot_memes": {
            "off": ["合影"], "cues": {"野距": ["jg diff"], "感谢多兰": ["thanks doran"]}}}))
        self.assertEqual((found["meme_level"], found["memes"]), (None, 3))
        self.assertEqual(settings.meme_level(), "some")  # the file had none: yours stays
        self.assertEqual(settings.meme_edits(), {
            "off": {"飞神", "合影"}, "cues": {"野距": ["jg diff"], "感谢多兰": ["thanks doran"]}})

    def test_a_file_with_only_the_level(self):
        found = settings.import_file(self.write({"meme_level": "none"}))
        self.assertEqual((found["words"], found["meme_level"]), (0, "none"))
        self.assertEqual(settings.meme_level(), "none")
        self.assertEqual(settings.words("memes"), {})  # not a word "meme_level" -> "none"

    def test_a_file_without_settings(self):
        with self.assertRaises(ValueError):
            settings.import_file(self.write({"words": {}, "meme_level": "lots"}))


class TheListInTheSettingsWindow(Offline):
    def setUp(self):
        super().setUp()
        self.patch(meme_cues, "BUILT_IN_FILE", os.path.join(self.folder, "no built-in cues"))
        meme_cues._entries_cache = None
        answers = dict(CUE_ANSWERS)
        del answers["我软脚了"]  # no cues written for it yet
        save_cues(answers=answers)

    def states(self):
        return {phrase: (cues, state) for phrase, cues, state in meme_cues.rows()}

    def test_each_memes_state(self):
        found = self.states()
        self.assertEqual(list(found), list(MEMES))  # every meme, in the bot's order
        self.assertEqual(found["野距"], ("jungle gap; jungle diff; jg diff", meme_cues.USED))
        self.assertEqual(found["超威同意了"], ("{X} gave up?; {X} wants to ff?", meme_cues.INSULT))
        self.assertEqual(found["合影"], ("", meme_cues.NOT_USED))
        self.assertEqual(found["我软脚了"], ("", meme_cues.NOT_WRITTEN))

    def test_your_changes(self):
        settings.set_meme_off("飞神")
        settings.set_meme_cues("吓哭了", ["what is this", "omg?"])
        found = self.states()
        self.assertEqual(found["飞神"], ("the goat", meme_cues.OFF))
        self.assertEqual(found["吓哭了"], ("what is this; omg?", meme_cues.YOURS))

    def test_cues_typed_in_the_window(self):
        self.assertEqual(meme_cues.split_cues(" jungle gap; jg diff；\nwhat a gap ;"),
                         ["jungle gap", "jg diff", "what a gap"])
        self.assertEqual(meme_cues.check_yours("野距", ["jungle gap", "{X} diff", "打野差距",
                                                      "one two three four five six seven"]),
                         (["jungle gap"], ["{X} diff", "打野差距",
                                           "one two three four five six seven"]))
        # {X} works for a name and a pattern, ? asks the model first
        self.assertEqual(meme_cues.check_yours("超威同意了", ["{X} gave up?", "XX surrendered"]),
                         (["{X} gave up?", "XX surrendered"], []))


class TheHttpServer(Offline):
    def setUp(self):
        super().setUp()
        self.translate = self.patch(server, "translate", side_effect=self.fake_translate)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        httpd.RequestHandlerClass.log_message = lambda *args: None  # quiet tests
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.base = f"http://127.0.0.1:{httpd.server_port}"
        # Straight to the server, never through a proxy from the environment
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @staticmethod
    def fake_translate(text, mode="stupid", rarity=None, check=False, memes=None):
        return f"{text} {mode} {bot_memes.level_of(memes)}"  # unknown levels: ValueError

    def call(self, path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        try:
            with self.opener.open(self.base + path, data=data, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_memes_in_the_url(self):
        self.assertEqual(self.call("/translate?text=gg&memes=max"),
                         (200, {"text": "gg", "mode": "stupid", "translation": "gg stupid max"}))
        level = urllib.parse.quote("尽量多")
        self.assertEqual(self.call(f"/translate?text=gg&memes={level}")[1]["translation"],
                         "gg stupid max")

    def test_memes_in_json(self):
        self.assertEqual(self.call("/translate", {"text": "gg", "memes": "none"})[1]
                         ["translation"], "gg stupid none")

    def test_without_memes_the_overlays_level(self):
        self.assertEqual(self.call("/translate?text=gg")[1]["translation"], "gg stupid some")
        settings.set_meme_level("none")
        self.assertEqual(self.call("/translate?text=gg")[1]["translation"], "gg stupid none")

    def test_an_unknown_level(self):
        status, answer = self.call("/translate?text=gg&memes=lots")
        self.assertEqual(status, 400)
        self.assertIn("lots", answer["error"])

    def test_the_modes(self):
        status, answer = self.call("/modes")
        self.assertEqual((answer["memes"], answer["default_memes"]),
                         (["none", "some", "max"], "some"))


class TheExesCopy(Offline):
    def test_from_the_bots_folder(self):
        self.assertTrue(bot_memes.is_bot_folder(self.bot))
        self.assertFalse(bot_memes.is_bot_folder(self.folder))
        copy = os.path.join(self.folder, "build", "bot")
        self.assertEqual(bot_memes.bundle(copy), self.bot)
        self.assertEqual(sorted(os.listdir(copy)), ["memes.json", "nicknames.txt"])
        self.patch(bot_memes, "BUNDLED", copy)
        settings.set_bot_folder(os.path.join(self.folder, "nothing here"))
        self.assertEqual(bot_memes.source(), bot_memes.BUNDLED_COPY)
        self.assertEqual(set(bot_memes.memes()), set(MEMES))

    def test_from_github(self):
        settings.set_bot_folder(os.path.join(self.folder, "nothing here"))
        online = {"memes": {"别奶了": {"meaning": "别夸了"}}}
        files = {"memes.json": json.dumps(online, ensure_ascii=False).encode("utf-8"),
                 "nicknames.txt": b"Doran = \xe5\xa4\x9a\xe5\x85\xb0\n"}
        self.download.side_effect = lambda url, timeout=0: files[url.rsplit("/", 1)[1]]
        copy = os.path.join(self.folder, "build", "bot")
        self.assertEqual(bot_memes.bundle(copy), bot_memes.GITHUB)
        self.assertEqual(sorted(os.listdir(copy)), ["memes.json", "nicknames.txt"])

    def test_neither(self):
        settings.set_bot_folder(os.path.join(self.folder, "nothing here"))
        with self.assertRaises(OSError):
            bot_memes.bundle(os.path.join(self.folder, "build", "bot"))


if __name__ == "__main__":
    unittest.main()
