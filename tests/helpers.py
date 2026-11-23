"""What the offline tests share: a settings file and a MemeLearnerBot folder of their own,
in a temporary folder, and no internet (a test that needs Google or a model fakes it).

    py -m unittest discover tests        (from the translator's folder)
"""

import json
import os
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest import mock

from sbtranslator import bot_memes, settings

# A few of the bot's real memes, shortened
MEMES = {
    "野距": {"meaning": "两队打野水平差距大", "english": "jungle gap",
             "variants": ["打野差距"], "examples": ["野距太大了"], "games": ["lol"]},
    "超威同意了": {"meaning": "嘲讽 Chovy 关键比赛里「同意」输掉", "english":
                   "A meme mocking Chovy for agreeing to lose", "variants": ["超威又同意了"],
                   "examples": ["超威同意了"], "games": ["lol"]},
    "已经结束了": {"meaning": "胜负已定", "english": "It's already over",
                   "variants": ["结束嘞"], "examples": ["已经结束了"], "games": ["lol"]},
    "感谢多兰": {"meaning": "反讽地感谢多兰，他的失误帮了对面", "english": "Sarcastic thanks to Doran",
                 "examples": ["感谢多兰"], "games": ["lol"]},
    "我软脚了": {"meaning": "看比赛紧张到腿软", "english": "My legs have gone weak",
                 "examples": ["我软脚了"], "games": ["lol"]},
    "合影": {"meaning": "人数到了整数，大家合影留念", "english": "group photo",
             "examples": ["合影"], "games": ["lol"]},
    "飞神": {"meaning": "对 Faker 的尊称", "english": "A reverent nickname for Faker",
             "examples": ["飞神来了"], "games": ["lol"]},
    "吓哭了": {"meaning": "被厉害的操作吓到", "english": "scared to tears",
               "variants": ["blg吓哭了"], "examples": ["吓哭了"], "games": ["lol"]},
}
NICKNAMES = "# 选手外号表\nChovy = 超威, 大超, chooovy\nCanyon = 三叔, 三姆斯\n"


def write_bot(folder, memes=None, nicknames=NICKNAMES):
    """Make a MemeLearnerBot folder with these memes and this nickname table."""
    data = os.path.join(folder, *bot_memes.MEMES_FILE[:-1])
    os.makedirs(data, exist_ok=True)
    with open(os.path.join(data, "memes.json"), "w", encoding="utf-8") as f:
        json.dump({"_comment": "test", "version": 2, "memes": MEMES if memes is None else memes,
                   "rejected": {}}, f, ensure_ascii=False)
    with open(os.path.join(data, "nicknames.txt"), "w", encoding="utf-8") as f:
        f.write(nicknames)


class Offline(unittest.TestCase):
    """A test with its own settings file and bot folder (self.bot), and no internet."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="sbtranslator-test-")
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.bot = os.path.join(self.folder, "MemeLearnerBot")
        write_bot(self.bot)
        self.addCleanup(settings.reload)  # runs last: back to the real settings
        environment = mock.patch.dict(os.environ, {
            "SBTRANSLATOR_SETTINGS": os.path.join(self.folder, "settings", "settings.json"),
            "SBTRANSLATOR_BOT_FOLDER": self.bot})
        environment.start()
        self.addCleanup(environment.stop)
        settings.reload()
        # Nothing goes online: Google, DeepSeek, Ollama and GitHub fail at once unless a
        # test fakes them
        self.patch(urllib.request, "urlopen",
                   side_effect=urllib.error.URLError("no internet in the tests"))
        self.download = self.patch(bot_memes, "_download",
                                   side_effect=OSError("no internet in the tests"))
        self.patch(bot_memes, "_fetch_in_background")  # no download behind a test's back
        self.patch(bot_memes, "BUNDLED", os.path.join(self.folder, "bundled"))
        bot_memes._read_cache.clear()
        bot_memes._last_try, bot_memes._fetching = 0.0, False

    def patch(self, target, name, *args, **kwargs):
        """mock.patch.object for the length of the test; returns the mock."""
        patcher = mock.patch.object(target, name, *args, **kwargs)
        found = patcher.start()
        self.addCleanup(patcher.stop)
        return found


# What a model answers about each meme's cues (meme_cues.write()), for the memes in MEMES
CUE_ANSWERS = {
    "野距": {"use": True, "cues": ["jungle gap", "jungle diff", "jg diff"]},
    "超威同意了": {"use": True, "insult": True, "template": "{X}同意了", "name": "Chovy",
                   "cues": ["{X} gave up?", "{X} wants to ff?"]},
    "已经结束了": {"use": True, "cues": ["it's over?", "gg it's over"]},
    "感谢多兰": {"use": True, "cues": ["thanks doran", "thank you doran"]},
    "我软脚了": {"use": True, "cues": ["my legs are shaking", "i'm so nervous"]},
    "合影": {"use": False, "cues": []},
    "飞神": {"use": True, "cues": ["the goat"]},
    "吓哭了": {"use": True, "cues": ["what is this?"]},
}

# Words the fake Google knows (fake_google()): enough for the sentences in the tests
GOOGLE_WORDS = {"jungle": "打野", "gap": "差距", "diff": "差距", "lol": "哈哈", "again": "又",
                "gave": "放弃", "up": "了", "the": "", "dragon": "小龙", "for": "换", "baron": "大龙",
                "believe": "相信", "in": "", "thanks": "谢谢", "doran": "多兰", "he": "他",
                "plays": "打", "other": "对面", "team": "队伍", "my": "我的", "legs": "腿",
                "are": "在", "shaking": "发抖", "here": "", "we": "我们", "go": "来了",
                "game": "第", "5": "五局", "faker": "Faker", "1v3": "一打三", "what": "什么",
                "is": "是", "this": "这", "chovy": "Chovy", "it's": "它", "over": "结束了",
                "gg": "gg", "t1": "T1", "ig": "IG"}


def fake_google(text, source="en", target="zh-CN", timeout=10):
    """A Google Translate for the tests: word by word from GOOGLE_WORDS, keeping what is in
    【】 or 「」 as it is."""
    out = []
    for part in __import__("re").findall(r"【[^】]*】|「[^」]*」|[A-Za-z0-9']+|[,.!?]|\s+", text):
        if part.startswith(("【", "「")) or not part.strip():
            out.append(part.strip() and part)
        elif part in ",.!?":
            out.append({",": "，", ".": "。", "!": "！", "?": "？"}[part])
        else:
            out.append(GOOGLE_WORDS.get(part.lower(), part))
    return "".join(out)


def save_cues(memes=None, answers=None):
    """Write the cues of CUE_ANSWERS into this computer's cues file, as a model would."""
    from sbtranslator import meme_cues
    memes, answers = memes or MEMES, answers or CUE_ANSWERS
    meme_cues.save({phrase: meme_cues.clean(answers[phrase], phrase,
                                            bot_memes.parse_memes(__import__("json").dumps(
                                                {"memes": {phrase: memes[phrase]}}))[phrase],
                                            "fake-model")
                    for phrase in answers if phrase in memes})


class Translating(Offline):
    """An Offline test with the cues written, a fake Google, no rules (they ask Google's
    dictionary) and only a few stupid words: lol -> 英雄联盟, gap -> 缺口."""

    STUPID = {"lol": "英雄联盟", "gap": "缺口"}

    def setUp(self):
        super().setUp()
        from sbtranslator import inject, meme_cues, meme_model, meme_pick, rules
        from sbtranslator import translator as t
        meme_pick._turns.clear()
        meme_pick._answers.clear()
        self.model = self.patch(meme_model, "ask", side_effect=meme_model.Unavailable(
            "no model in the tests"))
        self.patch(meme_cues, "BUILT_IN_FILE", os.path.join(self.folder, "no built-in cues"))
        self.patch(meme_cues, "fill_in_background")
        meme_cues._entries_cache = None
        save_cues()
        self.google = self.patch(t, "translate", side_effect=fake_google)
        import sbtranslator
        self.patch(sbtranslator, "_translate_proper", side_effect=fake_google)
        self.patch(inject, "stupid_word", side_effect=lambda token, proper: self.STUPID.get(
            token.lower()))
        self.patch(rules, "plan", return_value={})
        self.patch(rules, "near_synonym_choices", return_value={})
