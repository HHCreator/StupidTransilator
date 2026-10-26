"""SBtranslator: translate English to Chinese in a stupid way, as a library other apps can use.

    import sbtranslator

    sbtranslator.translate("The butterfly is eating a pineapple.")            # stupid
    sbtranslator.translate("Hello world", mode="plain")                        # word by word
    sbtranslator.translate("Hello world", mode="proper")                       # correct
    sbtranslator.translate("Long time no see", mode="classical")               # 文言文
    sbtranslator.translate("Long time no see", rarity=1.5)                     # stupider
    sbtranslator.translate("Long time no see", check=True)                     # AI-checked

Apps written in other languages can run the HTTP server instead: python -m sbtranslator.server

This file is the package's front door: everything outside the package (the HTTP server,
the overlay window, other people's apps) calls translate() here and doesn't need to know
which function in translator.py does the work for each mode.

    sbtranslator/
        __init__.py     translate(text, mode, rarity): the one function apps call
        translator.py   the translation code itself, and the command line
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

__all__ = ["MODES", "translate"]
__version__ = "0.1.0"

# The modes translate() accepts; the first one is the default
MODES = ("stupid", "plain", "proper", "classical")


def translate(text, mode="stupid", rarity=TARGET_RARITY, check=False):
    """Translate English text to Chinese.

    mode: "stupid" (word by word with wrong-but-real meanings, the default), "plain" (word by
    word, usual meanings), "proper" (correct translation) or "classical" (correct, in
    Classical Chinese with traditional characters).
    rarity: average rarity for "stupid" mode, from 0 (natural) to 3 (obscure).
    check: for "stupid" and "plain", let a local AI model pick the best of several versions
    and smooth it a little (see check.py; needs Ollama with the model downloaded).

    Needs an internet connection. Raises ValueError for an unknown mode and RuntimeError
    when the online translator can't be reached.
    """
    # Each mode is one function in translator.py (check.py wraps the word-by-word ones)
    if check and mode in ("stupid", "plain"):
        from .check import checked_translation
        return checked_translation(text, rarity=rarity, rare=(mode == "stupid"))
    if mode == "stupid":
        return translate_word_by_word(text, target_rarity=rarity)
    if mode == "plain":
        return translate_word_by_word(text, rare=False)
    if mode == "proper":
        return _translate_proper(text)
    if mode == "classical":
        return translate_classical(text)
    raise ValueError(f"Unknown mode {mode!r}, expected one of {', '.join(MODES)}")
