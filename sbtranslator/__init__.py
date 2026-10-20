"""SBtranslator: translate English to Chinese in a stupid way, as a library other apps can use.

    import sbtranslator

    sbtranslator.translate("The butterfly is eating a pineapple.")            # stupid
    sbtranslator.translate("Hello world", mode="plain")                        # word by word
    sbtranslator.translate("Hello world", mode="proper")                       # correct
    sbtranslator.translate("Long time no see", mode="classical")               # 文言文
    sbtranslator.translate("Long time no see", rarity=1.5)                     # stupider

Apps written in other languages can run the HTTP server instead: python -m sbtranslator.server
"""

from .translator import (
    TARGET_RARITY,
    translate as _translate_proper,
    translate_classical,
    translate_word_by_word,
)

__all__ = ["MODES", "translate"]
__version__ = "0.1.0"

MODES = ("stupid", "plain", "proper", "classical")


def translate(text, mode="stupid", rarity=TARGET_RARITY):
    """Translate English text to Chinese.

    mode: "stupid" (word by word with wrong-but-real meanings, the default), "plain" (word by
    word, usual meanings), "proper" (correct translation) or "classical" (correct, in
    Classical Chinese with traditional characters).
    rarity: average rarity for "stupid" mode, from 0 (natural) to 3 (obscure).

    Needs an internet connection. Raises ValueError for an unknown mode and RuntimeError
    when the online translator can't be reached.
    """
    if mode == "stupid":
        return translate_word_by_word(text, target_rarity=rarity)
    if mode == "plain":
        return translate_word_by_word(text, rare=False)
    if mode == "proper":
        return _translate_proper(text)
    if mode == "classical":
        return translate_classical(text)
    raise ValueError(f"Unknown mode {mode!r}, expected one of {', '.join(MODES)}")
