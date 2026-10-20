"""English -> Chinese translator using Google Translate (online).

Usage:
    py translator.py "Hello world"     # translate once
    py translator.py                   # interactive mode, blank line or Ctrl+C to quit
"""

import json
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


def main():
    # Make sure Chinese prints correctly in the Windows console
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) > 1:
        print(translate(" ".join(sys.argv[1:])))
        return

    print("English -> Chinese. Enter a blank line to quit.")
    while True:
        try:
            text = input("EN> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            break
        try:
            print("ZH>", translate(text))
        except Exception as error:
            print(f"Translation failed: {error}")


if __name__ == "__main__":
    main()
