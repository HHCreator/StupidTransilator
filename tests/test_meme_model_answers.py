"""The model's part in choosing memes (meme_pick.Planning): confirming cues, finding more at
the 玩梗程度 max, the time limit, and remembering answers."""

import time
import unittest

import sbtranslator
from sbtranslator import inject, meme_pick, settings

from helpers import Translating, fake_google


def planned(text, level="some"):
    tokens, words = inject.tokenize(text)
    planning = meme_pick.start(text, tokens, words, level)
    spans, note = planning.result()
    return [(key, zh) for first, last, key, zh in spans], note, planning.report


class Confirming(Translating):
    def answer(self, check=(), find=(), model="fake-flash", wait=0.0):
        def ask(instructions, question, timeout):
            self.questions.append((instructions, question, timeout))
            time.sleep(wait)
            return {"check": list(check), "find": list(find)}, model
        self.questions = []
        self.model.side_effect = ask

    def test_the_model_says_the_cue_fits(self):
        self.answer(check=[{"id": 1, "fits": True}])
        spans, note, report = planned("Chovy gave up again lol")
        self.assertEqual((spans, note), ([("chovy gave up", "超威同意了")], None))
        self.assertEqual((report["model"], report["confirmed"]), ("fake-flash", ["chovy gave up"]))
        instructions, question, timeout = self.questions[0]
        self.assertEqual(question["check"], [{"id": 1, "english": "Chovy gave up", "meme": "超威同意了",
                                              "meaning": "嘲讽 Chovy 关键比赛里「同意」输掉",
                                              "insult": True}])
        self.assertFalse(question["find"])
        self.assertNotIn("梗表", instructions)  # at some, no list of every meme
        self.assertEqual(timeout, meme_pick.DEADLINE)

    def test_the_model_says_it_doesnt(self):
        self.answer(check=[{"id": 1, "fits": False}])
        spans, note, report = planned("Chovy gave up the dragon for baron")
        self.assertEqual((spans, note), ([], None))
        self.assertEqual(report["turned_down"], ["chovy gave up"])

    def test_no_question_without_a_cue_to_confirm_at_some(self):
        self.answer()
        self.assertEqual(planned("jungle gap")[0], [("jungle gap", "野距")])
        self.assertEqual(self.questions, [])

    def test_no_model(self):
        spans, note, report = planned("Chovy gave up again")
        self.assertEqual(spans, [])
        self.assertEqual(note, "没有模型确认梗：no model in the tests")

    def test_too_slow(self):
        self.patch(meme_pick, "DEADLINE", 0.2)
        self.answer(check=[{"id": 1, "fits": True}], wait=0.6)
        started = time.monotonic()
        spans, note, report = planned("Chovy gave up again")
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual((spans, note), ([], "梗模型超时"))
        time.sleep(0.6)  # the answer comes later, and is remembered for next time
        self.assertEqual(planned("Chovy gave up again")[0], [("chovy gave up", "超威同意了")])

    def test_answers_are_remembered(self):
        self.answer(check=[{"id": 1, "fits": True}])
        planned("Chovy gave up again")
        spans, note, report = planned("chovy  gave up AGAIN")
        self.assertEqual(spans, [("chovy gave up", "超威同意了")])
        self.assertTrue(report["remembered"])
        self.assertEqual(len(self.questions), 1)

    def test_finding_more_at_max(self):
        self.answer(find=[{"english": "Faker", "meme": "飞神"},
                          {"english": "what is this", "meme": "吓哭了"},
                          {"english": "not in the sentence", "meme": "野距"},
                          {"english": "1v3", "meme": "不是机器人的梗"},
                          {"english": "1v3", "meme": "合影"}])
        spans, note, report = planned("Faker 1v3, what is this", "max")
        self.assertEqual(spans, [("faker", "飞神"), ("what is this", "吓哭了")])
        instructions, question, timeout = self.questions[0]
        self.assertTrue(question["find"])
        self.assertIn("野距：两队打野水平差距大", instructions)
        self.assertNotIn("合影：", instructions)  # not used in translations
        self.assertEqual(report["found"], [("faker", "飞神"), ("what is this", "吓哭了")])

    def test_turned_off_memes_are_neither_listed_nor_used(self):
        settings.set_meme_off("飞神")
        self.answer(find=[{"english": "Faker", "meme": "飞神"}])
        spans, note, report = planned("Faker 1v3", "max")
        self.assertEqual(spans, [])
        self.assertNotIn("飞神：", self.questions[0][0])

    def test_a_variant_or_a_filled_template_counts(self):
        self.answer(find=[{"english": "T1 gave up", "meme": "t1同意了"},
                          {"english": "scared", "meme": "blg吓哭了"}])
        spans = planned("T1 gave up, I'm scared", "max")[0]
        self.assertEqual(spans, [("t1 gave up", "t1同意了"), ("scared", "blg吓哭了")])

    def test_options_for_a_meme_the_model_found(self):
        self.answer(find=[{"english": "what is this", "meme": "吓哭了"}])
        result = sbtranslator.options("what is this", memes="max", versions=2)
        meme = result["words"][0]
        self.assertEqual((meme["chosen"], meme["options"]), ("吓哭了", ["吓哭了", "blg吓哭了"]))
        self.assertEqual(result["translation"], "吓哭了")

    def test_the_model_works_while_google_translates(self):
        def slow_google(text, source="en", target="zh-CN", timeout=10):
            if "【" not in text:
                time.sleep(0.4)  # the normal translation, first
            return fake_google(text)
        self.google.side_effect = slow_google
        self.answer(check=[{"id": 1, "fits": True}], wait=0.4)
        started = time.monotonic()
        self.assertEqual(sbtranslator.translate("Chovy gave up"), "超威同意了")
        self.assertLess(time.monotonic() - started, 0.75)

    def test_a_note_when_a_meme_was_left_out(self):
        result = sbtranslator.options("Chovy gave up", versions=1)
        self.assertEqual(result["meme_note"], "没有模型确认梗：no model in the tests")


if __name__ == "__main__":
    unittest.main()
