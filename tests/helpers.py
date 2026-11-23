"""What the offline tests share: a settings file and a MemeLearnerBot folder of their own,
in a temporary folder, and no internet (a test that needs Google or a model fakes it).

    py -m unittest discover tests        (from the translator's folder)
"""

import json
import os
import shutil
import tempfile
import unittest
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
