"""English -> Chinese translator using Google Translate (online), plus Bing for 文言文.

By default it translates in a "stupid" way: every word is translated on its own,
with no context. Some words keep their natural meaning so the sentence still flows and
others get a far-off meaning; TARGET_RARITY (or --rarity) sets the average.

Usage:
    py translator.py "Hello world"            # stupid: word by word, wrong-but-real meanings
    py translator.py --rarity 2.5 "Hello"     # same, rarer on average (0 = natural, 3 = obscure)
    py translator.py --plain "Hello world"    # word by word, usual meanings
    py translator.py --proper "Hello world"   # normal whole-sentence translation
    py translator.py --classical "Hello"      # correct translation in Classical Chinese (文言文)
    py translator.py                          # interactive mode, blank line or Ctrl+C to quit
"""

import json
import math
import os
import random
import re
import sys
import urllib.parse
import http.cookiejar
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


# Google Translate has no Classical Chinese, so classical mode uses Bing Translator's web
# page instead ("lzh" = 文言文). Bing needs a session (cookies + tokens from its page),
# which we fetch once and reuse.
_bing_session = None
BING_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
}


def _get_bing_session(timeout):
    global _bing_session
    if _bing_session is None:
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        request = urllib.request.Request("https://www.bing.com/translator", headers=BING_HEADERS)
        html = opener.open(request, timeout=timeout).read().decode("utf-8", "ignore")
        ig = re.search(r'IG:"([^"]+)"', html)
        iid = re.search(r'data-iid="([^"]+)"', html)
        abuse = re.search(r'params_AbusePreventionHelper\s*=\s*\[(\d+),"([^"]+)"', html)
        if not (ig and iid and abuse):
            raise RuntimeError("Could not read a session from the Bing Translator page")
        _bing_session = (opener, ig.group(1), iid.group(1), abuse.group(1), abuse.group(2))
    return _bing_session


# Simplified -> traditional tables from OpenCC (data/opencc). Phrases are matched first,
# longest match wins, so words like 头发 -> 頭髮 and 千里 -> 千里 come out right.
OPENCC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "opencc")
_s2t_table = None


def _load_s2t_table():
    global _s2t_table
    if _s2t_table is None:
        _s2t_table = {}
        for name in ("STCharacters.txt", "STPhrases.txt"):
            with open(os.path.join(OPENCC_DIR, name), encoding="utf-8") as f:
                for line in f:
                    if line.startswith("#") or "\t" not in line:
                        continue
                    simplified, traditional = line.rstrip("\n").split("\t", 1)
                    _s2t_table[simplified] = traditional.split(" ")[0]  # first = most common
    return _s2t_table


def has_simplified(text):
    """Check whether text contains simplified characters that have a traditional form."""
    table = _load_s2t_table()
    return any(table.get(c, c) != c for c in text)


def to_traditional(text):
    """Convert simplified Chinese characters in text to traditional ones."""
    table = _load_s2t_table()
    max_length = max(len(key) for key in table)
    result, i = [], 0
    while i < len(text):
        for length in range(min(max_length, len(text) - i), 0, -1):
            chunk = text[i:i + length]
            if chunk in table:
                result.append(table[chunk])
                i += length
                break
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


def translate_classical(text, source="en", timeout=15):
    """Translate text correctly into Classical Chinese (文言文, traditional characters) using Bing."""
    global _bing_session
    for attempt in range(2):
        opener, ig, iid, key, token = _get_bing_session(timeout)
        body = urllib.parse.urlencode(
            {"fromLang": source, "to": "lzh", "text": text, "key": key, "token": token}).encode()
        request = urllib.request.Request(
            f"https://www.bing.com/ttranslatev3?isVertical=1&IG={ig}&IID={iid}",
            data=body,
            headers={**BING_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            data = json.loads(opener.open(request, timeout=timeout).read().decode("utf-8"))
            result = data[0]["translations"][0]["text"]
            # Bing mixes in ASCII punctuation and spaces, so switch to Chinese punctuation
            result = "".join(PUNCTUATION.get(c, c) for c in result if c != " ")
            # Classical Chinese should be in traditional characters, but Bing sometimes
            # answers in simplified ones
            if has_simplified(result):
                result = to_traditional(result)
            return result
        except Exception as exc:
            _bing_session = None  # the session may have expired, get a fresh one and retry
            error = exc
    raise RuntimeError(f"Bing Translator request failed: {error}")


PUNCTUATION = {",": "，", ".": "。", "!": "！", "?": "？", ":": "：", ";": "；"}


# How rare the chosen meanings should be. Each dictionary meaning gets a rarity weight of
# -log10(frequency): 0 = the only meaning, 1 = used 10% of the time, 2 = 1%, 3 = 0.1%.
# The meaning that fits the sentence counts as rarity 0. Rarity is spread unevenly over
# the words: some keep their fitting meaning so the sentence still flows, others get a far
# off meaning, and the AVERAGE over the sentence's words is close to TARGET_RARITY.
# Meanings rarer than MAX_RARITY are too obscure and never used.
TARGET_RARITY = 0.8
MAX_RARITY = 3.0


# Irregular past tense / past participle forms. When one of these is also a word on its
# own (saw, left, rose, felt, found...), the stupid modes use that word's own meaning
# (saw -> 锯, left -> 左) instead of the past tense of the verb (see -> 看见, leave -> 离开).
IRREGULAR_PAST_FORMS = set("""
    arose awoke bore born bound bent bet bit bitten bled blew bred brought broke broken
    built burnt burst bought cast caught chose chosen clung came cost crept cut dealt dug
    dove drew drawn dreamt drank drunk drove driven ate eaten fell fed felt fought found
    fled flung flew flown forbade forgot forgave froze frozen got gotten gave given went
    gone ground grew grown hung had heard hid hidden hit held hurt kept knelt knew known
    laid led leapt learnt left lent let lay lain lit lost made meant met paid put quit
    read rode ridden rang rung rose risen ran said saw seen sought sold sent set shook
    shed shone shot showed shown shut sang sung sank sunk sat slept slid slung slit
    smelt sped spent spilt spun spat split spoilt spread sprang stood stole stolen stuck
    stung stank struck strung strove swore sworn swept swam swum swung took taken taught
    tore torn told thought threw thrown thrust trod understood woke wore worn wove woven
    wept won wound wrung wrote written
""".split())


def dictionary_meanings(word, source="en", target="zh-CN", timeout=10, standalone_only=False):
    """Return [(rarity, meaning), ...] for a word from Google's dictionary data.

    With standalone_only=True, only meanings of the word itself are kept, not meanings
    Google lists under a different base word.
    """
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
        if standalone_only and base_word.lower() != word.lower():
            continue
        for term in entry[2]:
            frequency = term[3] if len(term) > 3 and term[3] else 1e-9
            # Drop placeholders like "在 ... 之上" (on) so the sentence reads as one run
            meaning = term[0].replace("...", "").replace(" ", "")
            meanings.append((-math.log10(frequency), meaning))
    return meanings


# Compound words that split into common words are translated part by part in the stupid
# modes: butterfly -> butter + fly -> 黄油苍蝇. Parts must be common words (data/words),
# at least 3 letters unless listed in SHORT_PARTS, and not a suffix from NOT_PARTS.
WORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "words",
                          "common_english.txt")
SHORT_PARTS = {"a", "i", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is",
               "it", "me", "my", "no", "of", "on", "or", "so", "to", "up", "us", "we"}
NOT_PARTS = {"ing", "ion", "ions", "ted", "ent", "est", "ers", "ist", "ate", "ant", "ous",
             "ive", "ies", "ism", "ful", "less", "ness", "ment", "tion", "able", "ure"}
_part_words = None


def _load_part_words():
    global _part_words
    if _part_words is None:
        with open(WORDS_FILE, encoding="utf-8") as f:
            words = {line.strip().lower() for line in f if line.strip()}
        _part_words = {w for w in words if (len(w) >= 3 or w in SHORT_PARTS) and w not in NOT_PARTS}
        _part_words |= SHORT_PARTS - {"a", "i"}  # "a" and "i" alone make silly splits like "a"+"go"
    return _part_words


def _best_split(w, parts_set):
    best = {0: []}  # best[i] = best split of w[:i]
    for end in range(1, len(w) + 1):
        options = [best[start] + [w[start:end]] for start in range(end)
                   if start in best and w[start:end] in parts_set and (start, end) != (0, len(w))]
        if options:
            best[end] = min(options, key=lambda p: (len(p), -min(map(len, p))))
    split = best.get(len(w))
    return split if split and len(split) >= 2 else None


_is_real_word_cache = {}


def _is_real_word(part, timeout=10):
    # The word list has some junk (names, abbreviations like "fri"), so check that
    # Google's dictionary has an entry for the part itself
    if part not in _is_real_word_cache:
        try:
            data = _get_json(
                "https://clients5.google.com/translate_a/single",
                {"client": "dict-chrome-ex", "sl": "en", "tl": "zh-CN", "dt": "bd", "q": part},
                timeout,
            )
            _is_real_word_cache[part] = any(e[3].lower() == part for e in data[1] or [])
        except Exception:
            _is_real_word_cache[part] = True  # can't check, trust the word list
    return _is_real_word_cache[part]


def split_compound(word, timeout=10):
    """Split a word into two or more real words (butterfly -> [butter, fly]), or return
    None if it can't be split. Prefers the fewest parts, then the longest shortest part."""
    parts_set = set(_load_part_words())
    w = word.lower()
    while True:
        split = _best_split(w, parts_set)
        if split is None:
            return None
        bad = [part for part in split if not _is_real_word(part, timeout)]
        if not bad:
            return split
        parts_set -= set(bad)  # try again without the junk parts


def standalone_meaning(word, source="en", target="zh-CN", timeout=10):
    """For a past tense form that is also a word (saw, left...), return that word's
    most common meaning. Returns None for other words."""
    if word.lower() not in IRREGULAR_PAST_FORMS:
        return None
    try:
        meanings = dictionary_meanings(word, source, target, timeout, standalone_only=True)
    except Exception:
        return None
    return min(meanings)[1] if meanings else None


def spread_rarity(options, target_rarity=TARGET_RARITY, max_rarity=MAX_RARITY, rng=random,
                  stats=None):
    """Pick one meaning per word so the average rarity is about target_rarity.

    options maps word -> [(rarity, meaning), ...], where rarity 0 is the meaning that fits
    the sentence. Words are visited in random order; each takes a random share of the
    remaining rarity budget, so a few words go far off while the rest stay natural.
    """
    budget = target_rarity * len(options)
    picks = {}
    for word in rng.sample(list(options), len(options)):
        # Never overspend the budget, so the average doesn't end up above the target
        choices = [o for o in options[word] if o[0] <= min(max_rarity, budget)] or options[word][:1]
        wanted = min(budget, rng.uniform(0, max_rarity))
        rarity, meaning = min(choices, key=lambda o: abs(o[0] - wanted))
        picks[word] = meaning
        budget -= rarity
    if stats is not None and options:
        stats["average_rarity"] = target_rarity - budget / len(options)
    return picks


def translate_word_by_word(text, source="en", target="zh-CN", timeout=10, rare=True,
                           target_rarity=TARGET_RARITY):
    """Translate each word separately, ignoring the sentence it sits in.

    Compound words are split into parts first (see split_compound). Past tense forms that are also words on their own use that word's meaning
    (see IRREGULAR_PAST_FORMS). With rare=True every other word uses a less common
    meaning: some words stay natural and some go far off, averaging TARGET_RARITY.
    """
    tokens = re.findall(r"[A-Za-z0-9']+|[^\sA-Za-z0-9']", text)
    # Split compound words into their parts and translate each part on its own
    tokens = [part for t in tokens for part in (split_compound(t) or [t])]
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

    # Past tense forms that are also words on their own take that word's meaning
    past_forms = [w for w in words if w.lower() in IRREGULAR_PAST_FORMS]
    with ThreadPoolExecutor(max_workers=4) as pool:
        standalone = dict(zip(past_forms, pool.map(
            lambda w: standalone_meaning(w, source, target, timeout), past_forms)))
    for word, meaning in standalone.items():
        if meaning:
            lookup[word] = meaning

    if rare:
        # The proper translation tells us which meanings fit the sentence, so we can avoid them
        proper = translate(text, source, target, timeout)

        def word_options(word):
            # The fitting meaning (rarity 0) plus every other dictionary meaning
            try:
                meanings = dictionary_meanings(word, source, target, timeout)
            except Exception:
                meanings = []  # keep the usual translation for this word
            fitting = [m for _, m in meanings if m in proper]
            natural = max(fitting, key=len) if fitting else lookup[word]
            avoid = [natural, lookup[word]]
            others = [(r, m) for r, m in meanings
                      if not any(m in a or a in m for a in avoid if a)]
            return [(0.0, natural)] + others

        # Past tense forms already use their standalone meaning, so they sit this out
        rare_words = [w for w in words if not standalone.get(w)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            options = dict(zip(rare_words, pool.map(word_options, rare_words)))
        lookup.update(spread_rarity(options, target_rarity))

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
    classical = "--classical" in args
    args = [a for a in args if a not in ("--proper", "--plain", "--classical")]
    if classical:
        convert, mode = translate_classical, "Classical Chinese"
    elif proper:
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
