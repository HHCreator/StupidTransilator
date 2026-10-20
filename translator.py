"""English -> Chinese translator using Google Translate (online).

By default it translates in a "stupid" way: every word is translated on its own,
with no context, and each word uses a real but less common meaning that does not
fit the sentence. TARGET_RARITY below (or --rarity) sets how far off the meanings go.

Usage:
    py translator.py "Hello world"            # stupid: word by word, wrong-but-real meanings
    py translator.py --rarity 2.5 "Hello"     # same, with rarer meanings (0 = common, 3 = obscure)
    py translator.py --plain "Hello world"    # word by word, usual meanings
    py translator.py --proper "Hello world"   # normal whole-sentence translation
    py translator.py                          # interactive mode, blank line or Ctrl+C to quit
"""

import json
import math
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HEADERS = {"User-Agent": "Mozilla/5.0"}


def _get_json(url, params, timeout):
    request = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _translate_chrome_ex(text, source, target, timeout):
    # Endpoint used by the Google Translate Chrome extension. Returns ["译文"].
    data = _get_json(
        "https://clients5.google.com/translate_a/t",
        {"client": "dict-chrome-ex", "sl": source, "tl": target, "q": text},
        timeout,
    )
    result = data[0]
    # With sl=auto the item is ["译文", "detected_lang"] instead of a plain string
    return result[0] if isinstance(result, list) else result


def _translate_gtx(text, source, target, timeout):
    # Classic free endpoint. data[0] is a list of [translated_chunk, original_chunk, ...].
    data = _get_json(
        "https://translate.googleapis.com/translate_a/single",
        {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text},
        timeout,
    )
    return "".join(chunk[0] for chunk in data[0] if chunk and chunk[0])


def translate(text, source="en", target="zh-CN", timeout=10):
    """Translate text with Google Translate and return the translated string.

    Tries two public Google endpoints, since either one can get rate limited (HTTP 429).
    """
    error = None
    for backend in (_translate_chrome_ex, _translate_gtx):
        try:
            return backend(text, source, target, timeout)
        except Exception as exc:
            error = exc
    raise RuntimeError(f"Google Translate request failed: {error}")


def _translate_words_chrome_ex(words, source, target, timeout):
    # The Chrome extension endpoint accepts many q= params and returns one result per q
    params = [("client", "dict-chrome-ex"), ("sl", source), ("tl", target)]
    params += [("q", word) for word in words]
    data = _get_json("https://clients5.google.com/translate_a/t", params, timeout)
    return [item[0] if isinstance(item, list) else item for item in data]


def _translate_words_gtx(words, source, target, timeout):
    return [_translate_gtx(word, source, target, timeout) for word in words]


PUNCTUATION = {",": "，", ".": "。", "!": "！", "?": "？", ":": "：", ";": "；"}


# How rare the chosen meaning should be. Each dictionary meaning gets a rarity weight of
# -log10(frequency): 0 = the only meaning, 1 = used 10% of the time, 2 = 1%, 3 = 0.1%.
# We pick the meaning whose weight is closest to TARGET_RARITY, skip anything rarer than
# MAX_RARITY (too obscure), and skip meanings the proper sentence translation already uses.
TARGET_RARITY = 1.5
MAX_RARITY = 3.0


def dictionary_meanings(word, source="en", target="zh-CN", timeout=10):
    """Return [(rarity, meaning), ...] for a word from Google's dictionary data."""
    data = _get_json(
        "https://clients5.google.com/translate_a/single",
        {"client": "dict-chrome-ex", "sl": source, "tl": target, "dt": "bd", "q": word},
        timeout,
    )
    # data[1] is a list of parts of speech:
    # [pos, [terms], [[term, [back translations], None, frequency], ...], base_word, ...]
    meanings = []
    for entry in data[1] or []:
        base_word = entry[3]
        if base_word.endswith("-"):
            continue  # an affix like "im-" for "I'm", not the word itself
        for term in entry[2]:
            frequency = term[3] if len(term) > 3 and term[3] else 1e-9
            # Drop placeholders like "在 ... 之上" (on) so the sentence reads as one run
            meaning = term[0].replace("...", "").replace(" ", "")
            meanings.append((-math.log10(frequency), meaning))
    return meanings


def pick_wrong_meaning(meanings, avoid, target_rarity=TARGET_RARITY, max_rarity=MAX_RARITY):
    """Pick a well-known meaning that is not the one the sentence actually needs."""
    usable = [
        (rarity, meaning) for rarity, meaning in meanings
        if rarity <= max_rarity and not any(meaning in a or a in meaning for a in avoid)
    ]
    if not usable:
        return None
    return min(usable, key=lambda m: abs(m[0] - target_rarity))[1]


def translate_word_by_word(text, source="en", target="zh-CN", timeout=10, rare=True,
                           target_rarity=TARGET_RARITY):
    """Translate each word separately, ignoring the sentence it sits in.

    With rare=True each word uses a less common meaning that does not fit the sentence
    (see TARGET_RARITY), when the dictionary has one.
    """
    tokens = re.findall(r"[A-Za-z0-9']+|[^\sA-Za-z0-9']", text)
    words = list(dict.fromkeys(t for t in tokens if re.match(r"[A-Za-z0-9']", t)))
    if not words:
        return text

    error = None
    for backend in (_translate_words_chrome_ex, _translate_words_gtx):
        try:
            lookup = dict(zip(words, backend(words, source, target, timeout)))
            break
        except Exception as exc:
            error = exc
    else:
        raise RuntimeError(f"Google Translate request failed: {error}")

    if rare:
        # The proper translation tells us which meanings fit the sentence, so we can avoid them
        proper = translate(text, source, target, timeout)

        def lookup_rare(word):
            try:
                meanings = dictionary_meanings(word, source, target, timeout)
            except Exception:
                return None  # keep the usual translation for this word
            avoid = [m for m in (lookup[word],) if m] + [m for _, m in meanings if m in proper]
            return pick_wrong_meaning(meanings, avoid, target_rarity)

        with ThreadPoolExecutor(max_workers=4) as pool:
            for word, rare_term in zip(words, pool.map(lookup_rare, words)):
                if rare_term:
                    lookup[word] = rare_term

    return "".join(lookup.get(t, PUNCTUATION.get(t, t)) for t in tokens)


def main():
    # Make sure Chinese prints correctly in the Windows console
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = sys.argv[1:]
    proper = "--proper" in args
    plain = "--plain" in args
    target_rarity = TARGET_RARITY
    if "--rarity" in args:
        i = args.index("--rarity")
        target_rarity = float(args[i + 1])
        del args[i:i + 2]
    args = [a for a in args if a not in ("--proper", "--plain")]
    if proper:
        convert, mode = translate, "proper"
    elif plain:
        convert, mode = (lambda text: translate_word_by_word(text, rare=False)), "word by word"
    else:
        convert = lambda text: translate_word_by_word(text, target_rarity=target_rarity)
        mode = f"stupid: word by word, rarity {target_rarity}"

    if args:
        print(convert(" ".join(args)))
        return

    print(f"English -> Chinese ({mode}). Enter a blank line to quit.")
    while True:
        try:
            text = input("EN> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            break
        try:
            print("ZH>", convert(text))
        except Exception as error:
            print(f"Translation failed: {error}")


if __name__ == "__main__":
    main()
