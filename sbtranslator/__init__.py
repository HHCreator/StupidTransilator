"""SBtranslator: translate English to Chinese in a stupid way, as a library other apps can use.

    import sbtranslator

    sbtranslator.translate("The butterfly is eating a pineapple.")            # stupid
    sbtranslator.translate("The butterfly is eating a pineapple.", mode="wordy")  # stupider
    sbtranslator.translate("Hello world", mode="plain")                        # word by word
    sbtranslator.translate("Hello world", mode="proper")                       # correct
    sbtranslator.translate("Long time no see", mode="classical")               # 文言文
    sbtranslator.translate("Long time no see", mode="wordy", rarity=1.5)       # stupidest
    sbtranslator.translate("Long time no see", check=True)                     # AI-checked
    sbtranslator.options("A long sentence ...")    # several versions + other meanings per word

Apps written in other languages can run the HTTP server instead: python -m sbtranslator.server

This file is the package's front door: everything outside the package (the HTTP server,
the overlay window, other people's apps) calls translate() here and doesn't need to know
which function in translator.py does the work for each mode.

    sbtranslator/
        __init__.py     translate(text, mode, rarity): the one function apps call
        translator.py   the translation code itself, and the command line
        inject.py       the stupid mode: normal translation with stupid words injected
        learn.py        the Wikipedia crawler that learns memes and names
        server.py       the HTTP API for apps in other languages
        overlay.py      the always-on-top window (and the Windows exe)
        check.py        proofreading by a local AI model (DeepSeek through Ollama)
        chat.py         reading live stream chat (Douyu, Twitch)
        learn_chat.py   learning memes from that chat
        data/           word lists, meme dictionaries, simplified -> traditional tables
"""

from .translator import (
    TARGET_RARITY,
    translate as _translate_proper,
    translate_classical,
    translate_word_by_word,
)

__all__ = ["MODES", "translate", "options", "adjust"]
__version__ = "0.1.0"

# The modes translate() accepts; the first one is the default
MODES = ("stupid", "wordy", "plain", "proper", "classical")


def translate(text, mode="stupid", rarity=TARGET_RARITY, check=False):
    """Translate English text to Chinese.

    mode: "stupid" (a normal translation with stupid words injected, the default), "wordy"
    (word by word with wrong-but-real meanings), "plain" (word by word, usual meanings),
    "proper" (correct translation) or "classical" (correct, in Classical Chinese with
    traditional characters).
    rarity: average rarity for "wordy" mode, from 0 (natural) to 3 (obscure).
    check: let a local AI model help (see check.py; needs Ollama with the model downloaded).
    In "stupid" mode it writes the sentence around the stupid words; in "wordy" and
    "plain" it picks the best of several versions and smooths it a little.

    Needs an internet connection. Raises ValueError for an unknown mode and RuntimeError
    when the online translator can't be reached.
    """
    # Each mode is one function (check.py wraps them when check=True)
    if mode == "stupid":
        if check:
            from .check import checked_injected
            return checked_injected(text)
        from .inject import translate_injected
        return translate_injected(text)
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


def options(text, mode="stupid", rarity=TARGET_RARITY, check=False, versions=4):
    """Translate and offer choices, like Google Translate's alternatives. Returns a dict:

        translation  the translation (as translate() would give it)
        versions     up to `versions` different whole sentences, the translation first
        words        stupid mode only: [{"english", "chosen", "options"}, ...], each stupid
                     word with the other stupid meanings it can switch to (see adjust())
        proper       the normal translation, to pass to adjust()
        checked      True when the local model was asked (check=True)
        check_error  why the local model couldn't be asked, or None

    The stupid and wordy modes are random, so the versions really differ; plain, proper
    and classical give one version.
    """
    if mode == "stupid":
        from .inject import options as stupid_options
        return stupid_options(text, versions=versions, check=check)
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
    """
    from .inject import adjust as stupid_adjust
    return stupid_adjust(text, chosen, proper)
