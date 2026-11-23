"""Choosing the bot's memes for a sentence (meme_pick.py) and putting them in (inject.py)."""

import unittest

import sbtranslator
from sbtranslator import inject, meme_cues, meme_pick, settings

from helpers import MEMES, Translating, save_cues


def found(text, level="some"):
    """The memes meme_pick finds for text: [(English, Chinese)], and the note."""
    tokens, words = inject.tokenize(text)
    spans, note = meme_pick.start(tokens, words, level).result()
    return [(key, zh) for first, last, key, zh in spans], note


class Words(unittest.TestCase):
    def test_forms_of_a_word_are_the_same(self):
        for forms in (["give", "gives", "gave", "given", "giving"], ["miss", "missed", "misses",
                      "missing"], ["jinx", "jinxing", "jinxed", "jinxes"], ["shake", "shaking",
                      "shook", "shakes"], ["it's", "its", "it"], ["diff", "diffs"],
                      ["leg", "legs"], ["stop", "stopped", "stops"], ["is", "was", "are"]):
            self.assertEqual(len({meme_pick.stem(w) for w in forms}), 1, forms)
        self.assertNotEqual(meme_pick.stem("gap"), meme_pick.stem("gave"))
        self.assertNotEqual(meme_pick.stem("thanks"), meme_pick.stem("think"))


class Names(Translating):
    def test_names(self):
        for name in ("Chovy", "chovy", "chooovy", "Faker", "faker", "T1", "TES", "Knight",
                     "canyon", "G2"):
            self.assertTrue(meme_pick.is_name(name, first=True), name)
        for word in ("Bro", "lol", "GG", "game", "team", "he", "Someone", "the"):
            self.assertFalse(meme_pick.is_name(word, first=True), word)
        self.assertTrue(meme_pick.is_name("Zywoo", first=True))  # data/nicknames.json
        self.assertTrue(meme_pick.is_name("Yagao"))  # capitalized, not starting the sentence
        self.assertFalse(meme_pick.is_name("Yagao", first=True))

    def test_filling_the_name(self):
        entry = meme_cues.entries()["超威同意了"]
        self.assertEqual(meme_pick.fill("超威同意了", entry, "Chovy"), "超威同意了")
        self.assertEqual(meme_pick.fill("超威同意了", entry, "CHOOOVY"), "超威同意了")
        self.assertEqual(meme_pick.fill("超威同意了", entry, "T1"), "t1同意了")
        self.assertEqual(meme_pick.fill("野距", meme_cues.entries()["野距"], "T1"), "野距")

    def test_a_variant_with_the_name_or_its_nickname(self):
        memes = dict(MEMES, 超威同意了=dict(MEMES["超威同意了"], variants=["三叔同意了"]))
        from helpers import write_bot
        write_bot(self.bot, memes=memes)
        bot_memes_file_changed(self.bot)
        entry = meme_cues.entries()["超威同意了"]
        self.assertEqual(meme_pick.fill("超威同意了", entry, "Canyon"), "三叔同意了")


def bot_memes_file_changed(folder):
    import os
    from sbtranslator import bot_memes
    path = os.path.join(folder, *bot_memes.MEMES_FILE)
    later = os.stat(path).st_mtime + 2
    os.utime(path, (later, later))


class Finding(Translating):
    def test_a_cue_in_the_sentence(self):
        self.assertEqual(found("jungle gap lol"), ([("jungle gap", "野距")], None))
        self.assertEqual(found("JUNGLE DIFFS, gg"), ([("jungle diffs", "野距")], None))
        self.assertEqual(found("my legs were shaking"), ([("my legs were shaking", "我软脚了")], None))

    def test_whole_words_next_to_each_other(self):
        self.assertEqual(found("jungle, gap")[0], [])
        self.assertEqual(found("junglegap")[0], [])
        self.assertEqual(found("the jungle gaps")[0], [("jungle gaps", "野距")])

    def test_no_memes_at_none(self):
        self.assertEqual(found("jungle gap", "none"), ([], None))

    def test_a_cue_to_confirm_needs_a_model(self):
        spans, note = found("Chovy gave up again lol")
        self.assertEqual(spans, [])
        self.assertIn("确认", note)

    def test_memes_turned_off(self):
        settings.set_meme_off("野距")
        self.assertEqual(found("jungle gap")[0], [])

    def test_one_a_sentence_at_some_one_a_clause_at_max(self):
        text = "jungle gap, thanks doran, my legs are shaking, the goat"
        self.assertEqual(len(found(text, "some")[0]), 1)
        self.assertEqual(found(text, "some")[0][0][1], "我软脚了")  # the longest cue
        self.assertEqual([zh for key, zh in found(text, "max")[0]], ["野距", "感谢多兰", "我软脚了"])
        self.assertEqual(len(found("jungle gap thanks doran", "max")[0]), 1)  # one clause

    def test_equally_specific_memes_take_turns(self):
        answers = {"野距": {"cues": ["jungle gap"]}, "飞神": {"cues": ["jungle gap"]}}
        save_cues(answers=answers)
        first, second = found("jungle gap")[0], found("jungle gap")[0]
        self.assertEqual({first[0][1], second[0][1]}, {"野距", "飞神"})

    def test_a_template_meme_without_confirming(self):
        save_cues(answers={"超威同意了": {"template": "{X}同意了", "name": "Chovy",
                                          "cues": ["{X} gave up"]}})
        self.assertEqual(found("Chovy gave up again")[0], [("chovy gave up", "超威同意了")])
        self.assertEqual(found("lol T1 gave up")[0], [("t1 gave up", "t1同意了")])
        self.assertEqual(found("the team gave up")[0], [])  # team isn't a name
        self.assertEqual(found("Bro gave up")[0], [])


class PuttingThemIn(Translating):
    def test_the_meme_goes_into_the_sentence(self):
        details = inject.translate_injected("jungle gap lol", details=True, memes="some")
        self.assertEqual(details["result"], "野距英雄联盟")
        self.assertEqual(details["words"], {"jungle gap": "野距", "lol": "英雄联盟"})
        self.assertEqual(details["memes"], ["jungle gap"])
        self.assertNotIn("缺口", details["result"])  # gap is the meme's: no stupid word
        self.assertEqual(inject.translate_injected("jungle gap lol"), "打野缺口英雄联盟")

    def test_translate_uses_the_setting(self):
        self.assertEqual(sbtranslator.translate("jungle gap lol"), "野距英雄联盟")
        settings.set_meme_level("none")
        self.assertEqual(sbtranslator.translate("jungle gap lol"), "打野缺口英雄联盟")
        self.assertEqual(sbtranslator.translate("jungle gap lol", memes="max"), "野距英雄联盟")
        self.assertEqual(sbtranslator.translate("jungle gap lol", mode="proper"), "打野差距哈哈")

    def test_options_offer_other_memes_and_a_version_without(self):
        result = sbtranslator.options("jungle gap lol", versions=3)
        self.assertEqual(result["translation"], "野距英雄联盟")
        self.assertEqual(result["versions"][1], "打野差距英雄联盟")
        meme = next(w for w in result["words"] if w["english"] == "jungle gap")
        self.assertEqual((meme["chosen"], meme["options"], meme["meme"]), ("野距", ["野距", "打野差距"], True))
        self.assertNotIn("meme", next(w for w in result["words"] if w["english"] == "lol"))
        self.assertIsNone(result["meme_note"])

    def test_switching_a_meme_or_leaving_it_out(self):
        self.assertEqual(sbtranslator.adjust("jungle gap lol", {"jungle gap": "打野差距", "lol": None}),
                         "打野差距哈哈")
        self.assertEqual(sbtranslator.adjust("jungle gap lol", {"jungle gap": None, "lol": "英雄联盟"}),
                         "打野差距英雄联盟")

    def test_memes_a_person_kept(self):
        tokens, words = inject.tokenize("Chovy gave up, lol")
        self.assertEqual(meme_pick.forced(tokens, words, {"chovy gave up": "t1同意了", "lol": "英雄联盟",
                                                          "up": "向上"}),
                         [(0, 4, "chovy gave up", "t1同意了")])

    def test_check_passes_the_memes_on(self):
        from sbtranslator import check
        with unittest.mock.patch.object(check, "build_injected", side_effect=lambda d, model=None: d["words"]):
            self.assertEqual(check.checked_injected("jungle gap", memes="some"), {"jungle gap": "野距"})


if __name__ == "__main__":
    unittest.main()
