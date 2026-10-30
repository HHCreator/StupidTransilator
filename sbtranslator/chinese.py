"""Chinese in, stupid Chinese out: the stupid mode for people who type Chinese.

    sbtranslator.translate("@teses: frozen，你到现在还是零个major冠军，lol", mode="chinese")
    -> @滔搏搏：冰雪奇缘，你到现在还是零个主要冠军，英雄联盟

Stream chat is mostly Chinese with English names and abbreviations mixed in (teses,
frozen, major, lol). Those English words are the ones to make stupid; the person's own
Chinese around them stays as it is, so the sentence keeps its word order:

    1. Every English word (or phrase from stream chat) gets its stupid Chinese, by the
       same rules as the English stupid mode (inject.stupid_word()). The person's own
       Chinese counts as the normal translation, so a word they kept in English is always
       stupid: they wrote major, not 主要, so 主要 is a stupid meaning here.
    2. The stupid Chinese replaces the English word in place, and English punctuation
       next to Chinese becomes Chinese punctuation.

options() also offers a machine-translated version: the sentence is translated to English
(Google keeps the English words as they are) and back with the same stupid words
injected, so the Chinese around them gets reworded too. Only the words the person typed
in English are stupid there as well; English words Google wrote (good, conductor) are not.
"""

import random
import re
import warnings

from . import inject
from . import translator as t

CHINESE = "\u4e00-\u9fff，。：；！？"  # Chinese characters and Chinese punctuation
_english = {}  # {Chinese text: its English translation}


def has_chinese(text):
    """True if text has Chinese characters in it."""
    return re.search(r"[\u4e00-\u9fff]", text) is not None


def to_english(text):
    """The English translation of Chinese text (cached); English text is returned as is."""
    if not has_chinese(text):
        return text
    if text not in _english:
        _english[text] = t.translate(text, source="zh-CN", target="en")
    return _english[text]


def in_place(text, forced=None):
    """Steps 1 and 2: return (sentence, {English word: stupid Chinese}).

    forced, when given, decides the stupid words instead of the rules (see inject.inject()).
    """
    _, sentence, picks = inject.inject(text, wrap=("", ""), forced=forced, proper=text,
                                       use_rules=False)
    # English punctuation that ends a part of the sentence: ", " -> "，"
    sentence = re.sub(r"([,:;!?])(?=\s|$|[" + CHINESE + r"])\s*",
                      lambda m: t.PUNCTUATION[m.group(1)], sentence)
    # No spaces next to Chinese, and no double plural (teses们 -> 滔搏们们 -> 滔搏们)
    sentence = re.sub(r"(?<=[" + CHINESE + r"]) +| +(?=[" + CHINESE + "])", "", sentence)
    sentence = sentence.replace("们们", "们")
    return sentence, picks


def machine_translated(text, picks):
    """The machine-translated version: to English and back, with picks injected."""
    if not picks:
        return t.translate(to_english(text))
    return inject.translate_injected(to_english(text), forced=picks, proper=text,
                                     use_rules=False)


def _written_by_model(text, sentence, picks):
    """Have the local model write the sentence around the stupid words (check.py)."""
    from .check import build_injected
    details = {"english": to_english(text), "proper": text, "words": picks, "result": sentence}
    return build_injected(details)


def translate_chinese(text, check=False):
    """The stupid Chinese for Chinese text (see the top of this file).

    With check=True the local model writes the sentence around the stupid words instead.
    """
    sentence, picks = in_place(text)
    if not picks:
        return machine_translated(text, picks)  # no English to make stupid: just reword it
    if check:
        from .check import CheckUnavailable
        try:
            return _written_by_model(text, sentence, picks)
        except CheckUnavailable as error:
            warnings.warn(f"Sentence not written by the model: {error}")
    return sentence


def options(text, versions=inject.VERSIONS, check=False):
    """Like inject.options(), for Chinese text. The versions are the in-place sentence,
    the machine-translated one, then in-place ones with other stupid words; with check=True
    the local model's sentence comes first. Without English words, the machine-translated
    version is the only one."""
    sentence, picks = in_place(text)
    found = [sentence] if picks else []  # no English to make stupid: just reword it
    checked, check_error = False, None
    if check and picks:
        from .check import CheckUnavailable
        try:
            found.insert(0, _written_by_model(text, sentence, picks))
            checked = True
        except CheckUnavailable as error:
            check_error = str(error)  # no local model: keep the in-place sentence
    choices = {w: inject.word_options(w, zh, text) for w, zh in picks.items()}
    other = machine_translated(text, picks)
    if other not in found:
        found.append(other)
    for attempt in range(versions * 3 if picks else 0):
        if len(found) >= versions:
            break
        variant = {w: random.choice(o[1:]) if len(o) > 1 and random.random() < 0.6 else o[0]
                   for w, o in choices.items()}
        version = in_place(text, forced=variant)[0]
        if version not in found:
            found.append(version)
    words = [{"english": w, "chosen": picks[w], "options": choices[w]} for w in picks]
    return {"translation": found[0], "versions": found, "words": words, "proper": text,
            "checked": checked, "check_error": check_error, "english": to_english(text)}


def adjust(text, chosen, proper=None):
    """Like inject.adjust(), for Chinese text: chosen is {English word: stupid Chinese, or
    None to keep that word in English}. The word is switched in place."""
    return in_place(text, forced={w: zh for w, zh in chosen.items() if zh})[0]
