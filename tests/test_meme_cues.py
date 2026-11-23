"""Each meme's English cues (meme_cues.py) and the models that write them (meme_model.py)."""

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from sbtranslator import meme_cues, meme_model, settings

from helpers import MEMES, Offline

# What the model answers for each meme of helpers.MEMES
ANSWERS = {
    "野距": {"use": True, "cues": [{"en": "jungle gap", "confirm": False},
                                   {"en": "Jungle Diff!", "confirm": False}, "jg diff"],
             "why": "都是说打野差距大"},
    "超威同意了": {"use": True, "insult": True, "template": "XX同意了", "name": "Chovy",
                   "cues": [{"en": "{X} gave up", "confirm": True}, "{x} wants to ff?"]},
    "已经结束了": {"use": True, "cues": ["it's over?", "gg it's over"]},
    "感谢多兰": {"use": True, "cues": ["thanks doran", "thank you doran"]},
    "我软脚了": {"use": True, "cues": ["my legs are shaking", "i'm so nervous"]},
    "合影": {"use": False, "cues": ["group photo"], "why": "英文弹幕里没有"},
    "飞神": {"use": True, "cues": ["faker", "the goat"]},
    "吓哭了": {"use": True, "cues": ["what is this?"]},
}


def fake_ask(instructions, question, timeout):
    return ANSWERS[question["梗"]], "fake-model"


class Cues(Offline):
    def test_cue_text(self):
        self.assertEqual(meme_cues.cue_words("{X} Gave up!"), ["{X}", "gave", "up"])
        self.assertEqual(meme_cues.cue_words("XX wants to ff"), ["{X}", "wants", "to", "ff"])
        for wrong in ("", "{X}", "{X} vs {X}", "野距", "a b c d e f g", "jungle_gap"):
            self.assertIsNone(meme_cues.cue_words(wrong), wrong)
        cue = meme_cues.parse_cue(" {X} gave up？")
        self.assertEqual(cue, {"en": "{X} gave up", "confirm": True})
        self.assertEqual(meme_cues.cue_text(cue), "{X} gave up?")
        self.assertTrue(meme_cues.fits("{X}同意了", "超威同意了"))
        self.assertTrue(meme_cues.fits("相信{X}", "相信IG"))
        self.assertFalse(meme_cues.fits("{X}同意了", "同意了"))

    def test_what_the_model_writes_is_cleaned(self):
        entry = meme_cues.clean(ANSWERS["超威同意了"], "超威同意了", MEMES["超威同意了"], "m")
        self.assertEqual(entry["template"], "{X}同意了")
        self.assertEqual(entry["name"], "Chovy")
        self.assertTrue(entry["insult"])
        self.assertEqual(entry["cues"], [{"en": "{X} gave up", "confirm": True},
                                         {"en": "{X} wants to ff", "confirm": True}])
        self.assertEqual(entry["from"], meme_cues.fingerprint(MEMES["超威同意了"]))
        jungle = meme_cues.clean(ANSWERS["野距"], "野距", MEMES["野距"], "m")
        self.assertEqual([c["en"] for c in jungle["cues"]], ["jungle gap", "jungle diff", "jg diff"])
        self.assertEqual(jungle["template"], "")

    def test_rules_the_model_may_break(self):
        # A template that doesn't make the meme, a slot without a template, a bare name
        entry = meme_cues.clean({"template": "{X}牛逼", "cues": ["{X} gave up", "faker", "chovy",
                                                                 "the goat", "goat"] + ["a"] * 9},
                                "飞神", MEMES["飞神"], "m")
        self.assertEqual(entry["template"], "")
        self.assertEqual([c["en"] for c in entry["cues"]], ["the goat", "goat", "a"])
        not_used = meme_cues.clean(ANSWERS["合影"], "合影", MEMES["合影"], "m")
        self.assertEqual((not_used["use"], not_used["cues"]), (False, []))
        self.assertEqual(meme_cues.clean({"cues": "jungle gap"}, "野距", MEMES["野距"], "m")["cues"], [])
        many = meme_cues.clean({"cues": [f"cue {n}" for n in range(10)]}, "野距", MEMES["野距"], "m")
        self.assertEqual(len(many["cues"]), meme_cues.MAX_CUES)

    def test_write_asks_the_model_about_one_meme(self):
        with mock.patch.object(meme_model, "ask", side_effect=fake_ask) as ask:
            entry = meme_cues.write("野距", MEMES["野距"])
        question = ask.call_args[0][1]
        self.assertEqual((question["梗"], question["意思"]), ("野距", "两队打野水平差距大"))
        self.assertEqual(entry["by"], "fake-model")


class WhereCuesAreKept(Offline):
    def setUp(self):
        super().setUp()
        self.built_in = os.path.join(self.folder, "built-in cues.json")
        self.patch(meme_cues, "BUILT_IN_FILE", self.built_in)
        meme_cues._entries_cache = None

    def entry(self, phrase, **changes):
        return dict(meme_cues.clean(ANSWERS[phrase], phrase, MEMES[phrase], "m"), **changes)

    def test_built_in_cues_then_yours_then_your_settings(self):
        meme_cues.save({"野距": self.entry("野距"), "已经结束了": self.entry("已经结束了")},
                       self.built_in)
        self.assertEqual(sorted(meme_cues.entries()), ["已经结束了", "野距"])
        self.assertEqual(len(meme_cues.missing()), len(MEMES) - 2)
        meme_cues.save({"野距": self.entry("野距", cues=[{"en": "jg gap", "confirm": False}])})
        self.assertEqual(meme_cues.entries()["野距"]["cues"], [{"en": "jg gap", "confirm": False}])
        settings.set_meme_cues("野距", ["jungle diff", "{X} gave up?", "野距"])
        self.assertEqual(meme_cues.entries()["野距"]["cues"], [{"en": "jungle diff", "confirm": False}])
        self.assertEqual(meme_cues.entries()["野距"]["by"], "你")
        settings.set_meme_off("已经结束了")
        self.assertFalse(meme_cues.entries()["已经结束了"]["use"])
        settings.set_meme_off("已经结束了", False)
        settings.set_meme_cues("野距", None)
        self.assertTrue(meme_cues.entries()["已经结束了"]["use"])
        self.assertEqual(meme_cues.entries()["野距"]["cues"], [{"en": "jg gap", "confirm": False}])

    def test_cues_for_an_old_meaning_are_written_again(self):
        meme_cues.save({"野距": self.entry("野距", **{"from": "an old meaning"})})
        self.assertNotIn("野距", meme_cues.entries())
        self.assertIn("野距", meme_cues.missing())

    def test_your_own_cues_for_a_meme_without_any(self):
        settings.set_meme_cues("合影", ["group photo"])
        self.assertEqual(meme_cues.entries()["合影"]["cues"], [{"en": "group photo", "confirm": False}])

    def test_writing_the_missing_ones_in_the_background(self):
        with mock.patch.object(meme_model, "ask", side_effect=fake_ask):
            meme_cues._fill()
        self.assertEqual(meme_cues.missing(), [])
        with open(meme_cues.yours_file(), encoding="utf-8") as f:
            kept = json.load(f)
        self.assertEqual(set(kept["cues"]), set(MEMES))
        self.assertFalse(kept["cues"]["合影"]["use"])

    def test_no_model_pauses_the_background_writing(self):
        with mock.patch.object(meme_model, "ask", side_effect=meme_model.Unavailable("none")):
            meme_cues._fill()
        self.assertGreater(meme_cues._paused_until, 0)
        with mock.patch.object(meme_cues.threading, "Thread") as thread:
            meme_cues.fill_in_background()
        thread.assert_not_called()  # paused
        meme_cues._paused_until = 0.0
        with mock.patch.object(meme_cues.threading, "Thread") as thread:
            meme_cues.fill_in_background()
            meme_cues.fill_in_background()  # already running: not twice
        thread.assert_called_once()
        meme_cues._filling = False

    def test_command_line(self):
        into = os.path.join(self.folder, "out", "cues.json")
        with mock.patch.object(meme_model, "ask", side_effect=fake_ask), \
                redirect_stdout(io.StringIO()) as out:
            self.assertEqual(meme_cues.main(["--into", into]), 0)
        self.assertIn(f"[{len(MEMES)}/{len(MEMES)}]", out.getvalue())
        self.assertEqual(set(meme_cues.load(into)), set(MEMES))
        self.assertFalse(os.path.exists(meme_cues.yours_file()))  # only into the file asked
        with mock.patch.object(meme_model, "ask", side_effect=fake_ask) as ask, \
                redirect_stdout(io.StringIO()):
            meme_cues.main(["--into", into])  # nothing new to write
        ask.assert_not_called()
        meme_cues.save(meme_cues.load(into))
        with redirect_stdout(io.StringIO()) as out:
            meme_cues.main(["--show"])
        self.assertIn("超威同意了：{X} gave up?, {X} wants to ff?    模板 {X}同意了", out.getvalue())
        self.assertIn("合影：翻译时不用（英文弹幕里没有）", out.getvalue())


class Models(unittest.TestCase):
    def setUp(self):
        meme_model._down_until = 0.0
        for name in ("_ask_deepseek", "_ask_ollama"):
            patcher = mock.patch.object(meme_model, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self._ask_deepseek.return_value = 'Sure! {"use": true}'
        self._ask_ollama.return_value = '{"use": false}'

    def key(self, value):
        patcher = mock.patch.dict(os.environ, {meme_model.KEY_VARIABLE: value})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_deepseek_first(self):
        self.key("sk-test")
        self.assertEqual(meme_model.ask("i", {"q": 1}, 3),
                         ({"use": True}, meme_model.ONLINE_MODEL))
        messages = self._ask_deepseek.call_args[0][0]
        self.assertEqual(json.loads(messages[1]["content"]), {"q": 1})
        self._ask_ollama.assert_not_called()

    def test_the_local_model_without_a_key(self):
        self.key("")
        self.assertEqual(meme_model.ask("i", "q", 3), ({"use": False}, meme_model.LOCAL_MODEL))
        self._ask_deepseek.assert_not_called()

    def test_the_local_model_while_deepseek_is_down(self):
        self.key("sk-test")
        self._ask_deepseek.side_effect = meme_model._Unreachable("no balance")
        self.assertEqual(meme_model.ask("i", "q", 3)[1], meme_model.LOCAL_MODEL)
        self.assertEqual(meme_model.ask("i", "q", 3)[1], meme_model.LOCAL_MODEL)
        self.assertEqual(self._ask_deepseek.call_count, 1)  # left alone for DOWN_MINUTES

    def test_a_slow_deepseek_leaves_no_time_for_another(self):
        self.key("sk-test")
        self._ask_deepseek.side_effect = meme_model.Unavailable("no answer in time")
        with self.assertRaises(meme_model.Unavailable):
            meme_model.ask("i", "q", 3)
        self._ask_ollama.assert_not_called()
        self.assertTrue(meme_model.online_ready())  # slow isn't down

    def test_no_model_at_all(self):
        self.key("")
        self._ask_ollama.side_effect = meme_model.Unavailable("Ollama isn't running")
        with self.assertRaisesRegex(meme_model.Unavailable, "no DeepSeek key.*Ollama isn't running"):
            meme_model.ask("i", "q", 3)

    def test_the_key_never_shows(self):
        self.key("sk-secret")
        self._ask_deepseek.side_effect = meme_model._Unreachable(
            "DeepSeek refused the key in DEEPSEEK_API_KEY")
        self._ask_ollama.side_effect = meme_model.Unavailable("Ollama isn't running")
        with self.assertRaises(meme_model.Unavailable) as caught:
            meme_model.ask("i", "q", 3)
        self.assertNotIn("sk-secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
