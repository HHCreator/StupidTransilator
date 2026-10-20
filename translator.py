"""English -> Chinese translator using Google Translate (online).

By default it translates in a "stupid" way: every word is translated on its own,
with no context, so a full sentence comes out as a literal word-by-word mess.

Usage:
    py translator.py "Hello world"            # stupid word-by-word translation
    py translator.py --proper "Hello world"   # normal whole-sentence translation
    py translator.py                          # interactive mode, blank line or Ctrl+C to quit
"""

import json
import re
import sys
import urllib.parse
import urllib.request

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


def translate_word_by_word(text, source="en", target="zh-CN", timeout=10):
    """Translate each word separately, ignoring the sentence it sits in."""
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

    return "".join(lookup.get(t, PUNCTUATION.get(t, t)) for t in tokens)


def main():
    # Make sure Chinese prints correctly in the Windows console
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = sys.argv[1:]
    proper = "--proper" in args
    args = [a for a in args if a != "--proper"]
    convert = translate if proper else translate_word_by_word

    if args:
        print(convert(" ".join(args)))
        return

    mode = "proper" if proper else "stupid word-by-word"
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
