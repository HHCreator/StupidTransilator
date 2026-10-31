"""SBtranslator: translate English to Chinese in a stupid way, as a library other apps can use.

    import sbtranslator

    sbtranslator.translate("The butterfly is eating a pineapple.")            # stupid
    sbtranslator.translate("The butterfly is eating a pineapple.", mode="wordy")  # stupider
    sbtranslator.translate("Hello world", mode="plain")                        # word by word
    sbtranslator.translate("Hello world", mode="proper")                       # correct
    sbtranslator.translate("Long time no see", mode="classical")               # 文言文
    sbtranslator.translate("Long time no see", mode="wordy", rarity=1.5)       # stupidest
    sbtranslator.translate("Long time no see", check=True)                     # AI-checked
    sbtranslator.translate("frozen你这个major打得跟teses一样", mode="chinese")  # Chinese in
    sbtranslator.options("A long sentence ...")    # several versions + other meanings per word
    sbtranslator.suggest_mode("今天天气很好", "stupid")  # ("zh", "chinese"): wrong mode

Apps written in other languages can run the HTTP server instead: python -m sbtranslator.server

This file is the package's front door: everything outside the package (the HTTP server,
the overlay window, other people's apps) calls translate() here and doesn't need to know
which function in translator.py does the work for each mode.

    sbtranslator/
        __init__.py     translate(text, mode, rarity): the one function apps call
        translator.py   the translation code itself, and the command line
        inject.py       the stupid mode: normal translation with stupid words injected
        rules.py        its stupid words that need no table (default meanings, near-synonyms)
        chinese.py      the stupid mode for Chinese input: its English words made stupid
        learn.py        the Wikipedia crawler that learns memes and names
        server.py       the HTTP API for apps in other languages
        overlay.py      the always-on-top window (and the Windows exe)
        settings_window.py  its ⚙ window: your word table entries, rarity, import/export
        settings.py     your own settings, saved outside the program folder
        shortcut.py     the desktop shortcut (Windows)
        check.py        proofreading by a local AI model (DeepSeek through Ollama)
        chat.py         reading live stream chat (Douyu, Twitch)
        learn_chat.py   learning memes from that chat
        data/           word lists, meme dictionaries, simplified -> traditional tables
"""

from . import settings
from .translator import (
    TARGET_RARITY,  # noqa: F401 (the built-in default rarity, as sbtranslator.TARGET_RARITY)
    clean_text,
    guess_language,
    translate as _translate_proper,
    translate_classical,
    translate_word_by_word,
)

__all__ = ["MODES", "translate", "options", "adjust", "suggest_mode"]
__version__ = "0.1.0"

# The modes translate() accepts; the first one is the default
MODES = ("stupid", "chinese", "wordy", "plain", "proper", "classical")
ENGLISH_MODES = ("stupid", "wordy", "plain", "proper", "classical")  # the others take Chinese


def translate(text, mode="stupid", rarity=None, check=False):
    """Translate English text to Chinese.

    mode: "stupid" (a normal translation with stupid words injected, the default),
    "chinese" (the text is Chinese with English names mixed in, and those go stupid), "wordy"
    (word by word with wrong-but-real meanings), "plain" (word by word, usual meanings),
    "proper" (correct translation) or "classical" (correct, in Classical Chinese with
    traditional characters).
    rarity: average rarity for "wordy" mode, from 0 (natural) to 3 (obscure). None means
    the one set in the overlay's ⚙ window, or TARGET_RARITY (see settings.py).
    check: let a local AI model help (see check.py; needs Ollama with the model downloaded).
    In "stupid" mode it writes the sentence around the stupid words; in "wordy" and
    "plain" it picks the best of several versions and smooths it a little.

    Needs an internet connection. Raises ValueError for an unknown mode and RuntimeError
    when the online translator can't be reached.
    """
    text = clean_text(text)  # ｌｏｌ -> lol, don’t -> don't
    settings.refresh()  # word tables changed in the ⚙ window, maybe by another program
    rarity = settings.rarity() if rarity is None else rarity
    # Each mode is one function (check.py wraps them when check=True)
    if mode == "stupid":
        if check:
            from .check import checked_injected
            return checked_injected(text)
        from .inject import translate_injected
        return translate_injected(text)
    if mode == "chinese":
        from .chinese import translate_chinese
        return translate_chinese(text, check=check)
    if check and mode in ("wordy", "plain"):
        from .check import checked_translation
        return checked_translation(text, rarity=rarity, rare=(mode == "wordy"))
    if mode == "wordy":
        return translate_word_by_word(text, target_rarity=rarity)
    if mode == "plain":
        return translate_word_by_word(text, rare=False)
    if mode == "proper":
        return _translate_proper(text)
    if mode == "classical":
        return translate_classical(text)
    raise ValueError(f"Unknown mode {mode!r}, expected one of {', '.join(MODES)}")


def options(text, mode="stupid", rarity=None, check=False, versions=4):
    """Translate and offer choices, like Google Translate's alternatives. Returns a dict:

        translation  the translation (as translate() would give it)
        versions     up to `versions` different whole sentences, the translation first
        words        stupid mode only: [{"english", "chosen", "options"}, ...], each stupid
                     word with the other stupid meanings it can switch to (see adjust())
        proper       the normal translation, to pass to adjust()
        checked      True when the local model was asked (check=True)
        check_error  why the local model couldn't be asked, or None
        language     what the text is in: "en", "zh", another language's code ("ja"...)
        suggested_mode
                     the mode made for that language when it isn't this one, or None
                     (both from suggest_mode())

    The stupid and wordy modes are random, so the versions really differ; plain, proper
    and classical give one version.
    """
    text = clean_text(text)
    settings.refresh()
    rarity = settings.rarity() if rarity is None else rarity
    found = _options(text, mode, rarity, check, versions)
    found["language"], found["suggested_mode"] = suggest_mode(text, mode)
    return found


def _options(text, mode, rarity, check, versions):
    """What options() returns, without the language."""
    if mode == "stupid":
        from .inject import options as stupid_options
        return stupid_options(text, versions=versions, check=check)
    if mode == "chinese":
        from .chinese import options as chinese_options
        return chinese_options(text, versions=versions, check=check)
    if mode in ("wordy", "plain"):
        found = translate_word_by_word(text, rare=(mode == "wordy"), target_rarity=rarity,
                                       variants=versions if mode == "wordy" else 1)
        checked, check_error = False, None
        if check:
            # The local model picks the best version, which goes first
            from .check import CheckUnavailable, proofread
            try:
                best = proofread(text, found, _translate_proper(text))
                found = [best] + [f for f in found if f != best]
                checked = True
            except CheckUnavailable as error:
                check_error = str(error)
        return {"translation": found[0], "versions": found, "words": [], "proper": None,
                "checked": checked, "check_error": check_error}
    one = translate(text, mode=mode, rarity=rarity, check=check)
    return {"translation": one, "versions": [one], "words": [], "proper": None,
            "checked": False, "check_error": None}


def adjust(text, chosen, proper=None):
    """Rebuild a stupid-mode sentence after a person switched words (see options()).

    chosen is {English word: stupid Chinese, or None to translate that word normally}.
    Text with Chinese in it is rebuilt the way the "chinese" mode made it (see chinese.py).
    """
    from .chinese import adjust as chinese_adjust, has_chinese
    text = clean_text(text)  # as options() saw it
    settings.refresh()
    if has_chinese(text):
        return chinese_adjust(text, chosen, proper)
    from .inject import adjust as stupid_adjust
    return stupid_adjust(text, chosen, proper)


def suggest_mode(text, mode):
    """Whether text fits the mode, like Google Translate offering "Translate from: English"
    when the source language is set to German. Returns (language, suggested_mode):

        language        "en", "zh", Google's code for another language ("ja", "es"...), or
                        None when there is nothing to tell it by (see guess_language())
        suggested_mode  "chinese" for Chinese text in a mode made for English, "stupid" for
                        English text without a word of Chinese in the chinese mode, else None

    Only English and Chinese are translated (the jokes are English-Chinese ones): text in
    another language gets no suggestion, and is translated as if it were English (Chinese
    in the chinese mode), which mostly leaves it as it was.
    """
    from .chinese import has_chinese
    text = clean_text(text)
    language = guess_language(text)
    if language == "zh" and mode in ENGLISH_MODES:
        return language, "chinese"
    if language == "en" and mode == "chinese" and not has_chinese(text):
        return language, "stupid"
    return language, None
