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
    py translator.py --check "Hello world"    # stupid, then proofread by a local AI (check.py)
    py translator.py                          # interactive mode, blank line or Ctrl+C to quit

The four modes and the function behind each one:

    proper      translate()                          the whole sentence in one request
    plain       translate_word_by_word(rare=False)   every word on its own, usual meanings
    stupid      translate_word_by_word()             every word on its own, wrong meanings
    classical   translate_classical()                the whole sentence, in 文言文

How this file is laid out (each part starts with a banner comment):

    1. Google Translate        requests to Google's free translate endpoints
    2. Classical Chinese       文言文 through Bing, then simplified -> traditional characters
    3. Stupid-mode settings    the numbers and word lists to tune
    4. Dictionary meanings     every meaning Google's dictionary knows for a word
    5. Compound words          butterfly -> butter + fly
    6. Round trip              extra meanings via English -> Chinese -> English -> Chinese
    7. Past tense words        saw -> 锯 (the tool) instead of 看见
    8. Rarity                  which word gets which meaning
    9. Clean-up rules          can't -> can not, drop "the"
    10. Memes and names        lol -> 英雄联盟, teses -> 滔搏们
    11. The stupid pipeline    translate_word_by_word() puts parts 3-10 together
    12. Command line           main()

Everything is plain functions plus a few module-level caches (variables starting with _
that are filled the first time they are needed), so the module can be used from the
command line, from sbtranslator/__init__.py, the HTTP server and the overlay window alike.
"""

import json
import math
import os
import random
import re
import sys
import threading
import urllib.parse
import http.cookiejar
import urllib.request
from concurrent.futures import ThreadPoolExecutor


# =========================================================================================
# 1. Google Translate
#
# Google has no free official API, so this uses the public endpoints its own apps call.
# Every request goes through _get_json(). Each kind of request has two endpoints: if the
# first one fails (for example HTTP 429, "too many requests"), the second one is tried.
# =========================================================================================

# Google refuses requests that don't look like they come from a browser
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _get_json(url, params, timeout):
    """Send a GET request to url with the query parameters params; return the parsed JSON.

    params is a dict, or a list of (name, value) pairs when a name repeats (q=a&q=b).
    """
    request = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _translate_chrome_ex(text, source, target, timeout):
    """Translate text with the endpoint the Google Translate Chrome extension uses."""
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
    """Translate text with the classic free endpoint (the fallback; often rate limited)."""
    # Classic free endpoint. data[0] is a list of [translated_chunk, original_chunk, ...].
    data = _get_json(
        "https://translate.googleapis.com/translate_a/single",
        {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text},
        timeout,
    )
    # Long text comes back in chunks (about one per sentence), so join them
    return "".join(chunk[0] for chunk in data[0] if chunk and chunk[0])


def translate(text, source="en", target="zh-CN", timeout=10):
    """Translate text with Google Translate and return the translated string.

    Tries two public Google endpoints, since either one can get rate limited (HTTP 429).
    This is the "proper" mode, and the stupid mode also uses it to learn which meanings
    fit the sentence (so it can avoid them).
    """
    error = None
    for backend in (_translate_chrome_ex, _translate_gtx):
        try:
            return backend(text, source, target, timeout)
        except Exception as exc:
            error = exc  # remember why it failed and try the next endpoint
    raise RuntimeError(f"Google Translate request failed: {error}")


def _translate_words_chrome_ex(words, source, target, timeout):
    """Translate a list of words in one request; returns one translation per word, in order."""
    # The Chrome extension endpoint accepts many q= params and returns one result per q
    params = [("client", "dict-chrome-ex"), ("sl", source), ("tl", target)]
    params += [("q", word) for word in words]
    data = _get_json("https://clients5.google.com/translate_a/t", params, timeout)
    return [item[0] if isinstance(item, list) else item for item in data]


def _translate_words_gtx(words, source, target, timeout):
    """Fallback for _translate_words_chrome_ex(): one request per word, so it is slower."""
    return [_translate_gtx(word, source, target, timeout) for word in words]


# =========================================================================================
# 2. Classical Chinese (文言文)
#
# Google Translate has no Classical Chinese, so classical mode uses Bing Translator's web
# page instead ("lzh" = 文言文). Bing needs a session (cookies + tokens from its page),
# which we fetch once and reuse. Classical Chinese is written in traditional characters,
# but Bing sometimes answers in simplified ones, so the answer is converted with OpenCC's
# dictionaries (data/opencc).
# =========================================================================================

# (opener with cookies, IG, IID, key, token) once _get_bing_session() has run, else None
_bing_session = None
# Bing only hands out a session to something that looks like a real browser
BING_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
}


def _get_bing_session(timeout):
    """Return Bing's session: (opener with cookies, IG, IID, key, token).

    The first call loads https://www.bing.com/translator and reads the values its own
    JavaScript sends along with every translation; later calls reuse them. Set
    _bing_session back to None to force a fresh session.
    """
    global _bing_session
    if _bing_session is None:
        # The opener keeps the cookies Bing sets, and sends them with later requests
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        request = urllib.request.Request("https://www.bing.com/translator", headers=BING_HEADERS)
        html = opener.open(request, timeout=timeout).read().decode("utf-8", "ignore")
        # IG and IID identify this page view; key and token are Bing's anti-abuse values
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
_s2t_table = None  # {simplified: traditional}, loaded by _load_s2t_table()


def _load_s2t_table():
    """Load OpenCC's two tables into one dict {simplified: traditional} (only once).

    Each line of the files is "simplified<TAB>traditional [other traditional ...]"; the
    first traditional form is the most common one, so that is the one kept. The phrase
    table is loaded second, so a phrase entry wins over a character entry with the same key.
    """
    global _s2t_table
    if _s2t_table is None:
        _s2t_table = {}
        for name in ("STCharacters.txt", "STPhrases.txt"):
            with open(os.path.join(OPENCC_DIR, name), encoding="utf-8") as f:
                for line in f:
                    if line.startswith("#") or "\t" not in line:
                        continue  # comments and blank lines
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
    # Greedy longest match: at each position try the longest phrase first, so a whole
    # word (头发 -> 頭髮) wins over converting its characters one by one
    result, i = [], 0
    while i < len(text):
        for length in range(min(max_length, len(text) - i), 0, -1):
            chunk = text[i:i + length]
            if chunk in table:
                result.append(table[chunk])
                i += length
                break
        else:
            # No entry starts here (punctuation, English, already traditional): keep it
            result.append(text[i])
            i += 1
    return "".join(result)


def translate_classical(text, source="en", timeout=15):
    """Translate text correctly into Classical Chinese (文言文, traditional characters) using Bing."""
    global _bing_session
    # Two attempts: if the first one fails, the saved session may have expired
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
            result = "".join(PUNCTUATION.get(c, c) for c in result)
            # Drop spaces next to Chinese text, but keep them between English words
            result = re.sub(r" +(?=[^\x00-\x7f])|(?<=[^\x00-\x7f]) +", "", result)
            # Classical Chinese should be in traditional characters, but Bing sometimes
            # answers in simplified ones
            if has_simplified(result):
                result = to_traditional(result)
            return result
        except Exception as exc:
            _bing_session = None  # the session may have expired, get a fresh one and retry
            error = exc
    raise RuntimeError(f"Bing Translator request failed: {error}")


# English punctuation -> Chinese (full-width) punctuation. Used by the word-by-word modes
# when they put the sentence back together, and by classical mode.
PUNCTUATION = {",": "，", ".": "。", "!": "！", "?": "？", ":": "：", ";": "；"}


# =========================================================================================
# 3. Settings for the stupid modes
#
# The numbers and word lists that decide how stupid the translation gets. Change these to
# tune the results; the functions further down only read them.
# =========================================================================================

# How rare the chosen meanings should be. Each dictionary meaning gets a rarity weight of
# -log10(frequency): 0 = the only meaning, 1 = used 10% of the time, 2 = 1%, 3 = 0.1%.
# The meaning that fits the sentence counts as rarity 0. Rarity is spread unevenly over
# the words: some keep their fitting meaning so the sentence still flows, others get a far
# off meaning, and the AVERAGE over the sentence's words is close to TARGET_RARITY.
# Meanings rarer than MAX_RARITY are too obscure and never used.
TARGET_RARITY = 0.8
MAX_RARITY = 3.0
# Meanings of the capitalized word (may -> May -> 五月) count as at least this rare
CAPITALIZED_RARITY = 1.0

# Single characters that don't stand alone as a word in Chinese (measure words and bound
# characters). When the stupid mode picks one, it uses the standalone word instead, the
# way 次 on its own becomes 次数. Add more here as you find them.
STANDALONE_FORMS = {
    "次": "次数", "个": "个数", "遍": "遍数", "趟": "趟数", "倍": "倍数", "度": "度数",
    "偶": "偶数", "单": "清单", "善": "善良", "良": "良好", "魔": "魔鬼", "妖": "妖怪",
    "寿": "寿命", "命": "生命", "期": "期间", "时": "时候", "候": "时候", "辰": "时辰",
    "秋": "秋天", "途": "途径", "道": "道路", "方": "方向", "法": "方法", "样": "样子",
    "戏": "戏剧", "剧": "戏剧", "演": "表演", "谱": "乐谱", "乐": "乐曲", "啼": "啼哭",
    "鸣": "鸣叫", "喊": "喊叫", "号": "号码", "饥": "饥饿", "馁": "气馁", "汉": "汉族",
    "世": "世界", "身": "身体", "怪": "怪物", "甚": "甚至",
    "便": "方便", "然": "然而", "目": "目录", "表": "表格", "玩": "玩耍",
}

# Round trip: for common English words, look for extra meanings by going English ->
# Chinese -> English -> Chinese, and keep Chinese words whose default English translation
# is the original word (cry -> 哭 -> shout -> 叫声 -> "cry"). Each word costs about 10
# requests, so it only runs for the ROUND_TRIP_TOP_WORDS most common words in
# data/words/common_english.txt, and results are cached in .cache/round_trip.json (in the
# packaged exe the folder next to the code is temporary, so it goes to %LOCALAPPDATA%).
ROUND_TRIP_TOP_WORDS = 3000
ROUND_TRIP_RARITY = 1.5  # the rarity given to every meaning the round trip finds
ROUND_TRIP_BACK_WORDS = 12  # how many English back-translations to follow for each word
if getattr(sys, "frozen", False):
    CACHE_FILE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                              "SBtranslator", "round_trip.json")
else:
    CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "round_trip.json")

# Meanings Google's dictionary leaves out, such as the measure-word sense of "time"
# ("three times" = 三次), as (rarity, meaning).
EXTRA_MEANINGS = {
    "time": [(1.5, "次")],
}

# Memes learned from live stream chat by learn_chat.py (py listen.py douyu 6657): Chinese
# danmu memes become possible stupid meanings of an English word (dragon -> 恶龙呢), at
# this rarity. data/chat_meanings.json holds them as {english word: [memes]}.
CHAT_MEANINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                                  "chat_meanings.json")
CHAT_MEANING_RARITY = 1.0
_chat_meanings = None  # loaded by chat_meanings()


def chat_meanings(word):
    """Return the stream chat memes learned for an English word (often none)."""
    global _chat_meanings
    if _chat_meanings is None:
        try:
            with open(CHAT_MEANINGS_FILE, encoding="utf-8") as f:
                _chat_meanings = json.load(f)
        except (OSError, ValueError):
            _chat_meanings = {}  # nothing learned from chat yet
    return _chat_meanings.get(word.lower(), [])


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


# =========================================================================================
# 4. Dictionary meanings
#
# Besides a translation, Google can return its dictionary entry for a single word (dt=bd):
# every meaning, grouped by part of speech, with how often each one is used. The stupid
# mode picks its wrong-but-real meanings from these lists.
# =========================================================================================

def dictionary_meanings(word, source="en", target="zh-CN", timeout=10, standalone_only=False):
    """Return [(rarity, meaning), ...] for a word from Google's dictionary data.

    rarity is -log10(how often the meaning is used), so for "table" 表 (used 75% of the
    time) gets 0.1 and 桌子 (2%) gets 1.7. With standalone_only=True, only meanings of the
    word itself are kept, not meanings Google lists under a different base word.
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
            # A meaning without a frequency counts as extremely rare (rarity 9)
            frequency = term[3] if len(term) > 3 and term[3] else 1e-9
            # Drop placeholders like "在 ... 之上" (on) so the sentence reads as one run
            meaning = term[0].replace("...", "").replace(" ", "")
            meanings.append((-math.log10(frequency), meaning))
    return meanings


# =========================================================================================
# 5. Compound words: butterfly -> butter + fly
# =========================================================================================

# Compound words that split into common words are translated part by part in the stupid
# modes: butterfly -> butter + fly -> 黄油苍蝇. Parts must be common words (data/words),
# at least 3 letters unless listed in SHORT_PARTS, and not a suffix from NOT_PARTS.
WORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "words",
                          "common_english.txt")
SHORT_PARTS = {"a", "i", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is",
               "it", "me", "my", "no", "of", "on", "or", "so", "to", "up", "us", "we"}
NOT_PARTS = {"ing", "ion", "ions", "ted", "ent", "est", "ers", "ist", "ate", "ant", "ous",
             "ive", "ies", "ism", "ful", "less", "ness", "ment", "tion", "able", "ure", "ana"}
_part_words = None  # the set of allowed parts, built by _load_part_words()


def _load_part_words():
    """Build the set of words a compound may be split into (only once)."""
    global _part_words
    if _part_words is None:
        with open(WORDS_FILE, encoding="utf-8") as f:
            words = {line.strip().lower() for line in f if line.strip()}
        _part_words = {w for w in words if (len(w) >= 3 or w in SHORT_PARTS) and w not in NOT_PARTS}
        _part_words -= {"a", "i"}  # "a" and "i" alone make silly splits like "a"+"go", "a"+"sleep"
    return _part_words


def _best_split(w, parts_set):
    """Split w into words from parts_set with dynamic programming, or return None.

    best[i] holds the best way found to split the first i letters. For every end position,
    try every earlier start where the letters in between are a known part, and keep the
    option with the fewest parts, then the one whose shortest part is longest. The whole
    word on its own doesn't count as a split.
    """
    best = {0: []}  # best[i] = best split of w[:i]
    for end in range(1, len(w) + 1):
        options = [best[start] + [w[start:end]] for start in range(end)
                   if start in best and w[start:end] in parts_set and (start, end) != (0, len(w))]
        if options:
            best[end] = min(options, key=lambda p: (len(p), -min(map(len, p))))
    split = best.get(len(w))
    return split if split and len(split) >= 2 else None


_is_real_word_cache = {}  # {part: True/False}, so each part is only checked once per run


def _is_real_word(part, timeout=10):
    """Check that Google's dictionary has an entry for part itself.

    The word list has some junk (names, abbreviations like "fri"), so a split like
    friend -> fri + end is only accepted if every part is a real word.
    """
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


MIN_SPLIT_LETTERS = 4  # words this short or shorter are never split


def split_compound(word, timeout=10):
    """Split a word into two or more real words (butterfly -> [butter, fly]), or return
    None if it can't be split. Prefers the fewest parts, then the longest shortest part."""
    w = word.lower()
    if len(w) <= MIN_SPLIT_LETTERS:
        return None  # short words like "into" stay whole
    parts_set = set(_load_part_words())
    # _best_split() only knows the word list; if Google's dictionary rejects a part,
    # remove that part and look for another split
    while True:
        split = _best_split(w, parts_set)
        if split is None:
            return None
        bad = [part for part in split if not _is_real_word(part, timeout)]
        if not bad:
            return split
        parts_set -= set(bad)  # try again without the junk parts


# =========================================================================================
# 6. Round trip: extra meanings via English -> Chinese -> English -> Chinese
#
# Google's English -> Chinese dictionary misses some meanings, so for common words the
# translator looks further (see the round trip settings in part 3). Results are saved in
# CACHE_FILE, so each word only costs requests the first time it is seen.
# =========================================================================================

_top_words = None  # the ROUND_TRIP_TOP_WORDS most common words, as a set
_round_trip_cache = None  # {word: [meanings found]}, read from and written to CACHE_FILE
_round_trip_lock = threading.Lock()  # word lookups run in parallel and share the cache


def _dictionary(word, source, target, timeout):
    """Return Google's raw dictionary data (dt=bd) for a word, in either direction."""
    return _get_json(
        "https://clients5.google.com/translate_a/single",
        {"client": "dict-chrome-ex", "sl": source, "tl": target, "dt": "bd", "q": word},
        timeout,
    )


def _load_round_trip_state():
    """Load the common word list and the cache file the first time they are needed."""
    global _top_words, _round_trip_cache
    if _top_words is None:
        with open(WORDS_FILE, encoding="utf-8") as f:
            _top_words = {line.strip().lower() for _, line in zip(range(ROUND_TRIP_TOP_WORDS), f)}
    if _round_trip_cache is None:
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                _round_trip_cache = json.load(f)
        except (OSError, ValueError):
            _round_trip_cache = {}  # no cache yet, or a broken one: start empty


def round_trip_meanings(word, timeout=10):
    """Find extra Chinese meanings of a common English word by a round trip through
    Chinese and English (see ROUND_TRIP_TOP_WORDS). Returns a list of Chinese words.

    Example: life -> 生命, 寿命 ... -> lifetime, longevity ... -> 辈子, 一生 ... and 辈子 is
    kept because Google translates it back to exactly "life".
    """
    w = word.lower()
    with _round_trip_lock:
        _load_round_trip_state()
    if w not in _top_words:
        return []  # only common words are worth the requests
    if w in _round_trip_cache:
        return _round_trip_cache[w]

    # 1. English -> Chinese: the word's meanings, and the English words each meaning
    #    translates back to
    known, back = set(), []
    for entry in _dictionary(w, "en", "zh-CN", timeout)[1] or []:
        for term in entry[2]:
            known.add(term[0])
            back += [b for b in term[1] if b.lower() != w and b not in back]
    # 2. Those English words -> Chinese again
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda b: _dictionary(b, "en", "zh-CN", timeout),
                                back[:ROUND_TRIP_BACK_WORDS]))
    candidates = []
    for data in results:
        for entry in data[1] or []:
            for term in entry[2]:
                if term[0] not in known and term[0] not in candidates:
                    candidates.append(term[0])
    # 3. Keep the Chinese words whose default English translation is the original word
    found = []
    if candidates:
        params = [("client", "dict-chrome-ex"), ("sl", "zh-CN"), ("tl", "en")]
        params += [("q", c) for c in candidates]
        outputs = _get_json("https://clients5.google.com/translate_a/t", params, timeout)
        outputs = [o[0] if isinstance(o, list) else o for o in outputs]
        found = [c for c, o in zip(candidates, outputs) if o.strip().lower() == w]

    # Save the result (even an empty one) so this word never costs requests again
    with _round_trip_lock:
        _round_trip_cache[w] = found
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_round_trip_cache, f, ensure_ascii=False, indent=0)
        except OSError:
            pass  # a read-only folder only means no cache, not a failed translation
    return found


# =========================================================================================
# 7. Past tense words that are also words on their own: saw -> 锯, left -> 左
# =========================================================================================

def standalone_meaning(word, source="en", target="zh-CN", timeout=10):
    """For a past tense form that is also a word (saw, left...), return that word's
    most common meaning. Returns None for other words."""
    if word.lower() not in IRREGULAR_PAST_FORMS:
        return None
    try:
        meanings = dictionary_meanings(word, source, target, timeout, standalone_only=True)
    except Exception:
        return None
    # The lowest rarity is the most common meaning
    return min(meanings)[1] if meanings else None


# =========================================================================================
# 8. Rarity: which word gets which meaning
# =========================================================================================

def spread_rarity(options, target_rarity=TARGET_RARITY, max_rarity=MAX_RARITY, rng=random,
                  stats=None):
    """Pick one meaning per word so the average rarity is about target_rarity.

    options maps word -> [(rarity, meaning), ...], where rarity 0 is the meaning that fits
    the sentence. Words are visited in random order; each takes a random share of the
    remaining rarity budget, so a few words go far off while the rest stay natural.

    Example: 5 words at target 0.8 share a budget of 4.0. "time" might spend 1.5 on 次数
    and "good" 2.2 on 善良; the budget is then almost gone, so the other words keep their
    natural meaning. Pass a dict as stats to get the average rarity actually reached.
    """
    budget = target_rarity * len(options)  # total rarity the whole sentence may spend
    picks = {}
    for word in rng.sample(list(options), len(options)):  # every word once, random order
        # Never overspend the budget, so the average doesn't end up above the target
        choices = [o for o in options[word] if o[0] <= min(max_rarity, budget)] or options[word][:1]
        # How far off this word should go: a random amount, at most what is left
        wanted = min(budget, rng.uniform(0, max_rarity))
        rarity, meaning = min(choices, key=lambda o: abs(o[0] - wanted))
        picks[word] = meaning
        budget -= rarity
    if stats is not None and options:
        stats["average_rarity"] = target_rarity - budget / len(options)
    return picks


# =========================================================================================
# 9. Clean-up rules applied before translating
# =========================================================================================

# Contractions are expanded before translating, so "can't" is can + not instead of
# Google reading it as "cant" (斜面). 's is left alone since it is often possessive.
CONTRACTIONS = {"can't": ["can", "not"], "won't": ["will", "not"], "shan't": ["shall", "not"],
                "ain't": ["is", "not"]}
CONTRACTION_ENDINGS = {"n't": "not", "'m": "am", "'re": "are", "'ll": "will", "'ve": "have",
                       "'d": "would"}

# Words dropped in the stupid modes: Chinese has no articles, so "the" -> 这 reads wrong
SKIPPED_WORDS = {"the"}


def expand_contraction(token):
    """Split a contraction into words: "can't" -> ["can", "not"], "I'm" -> ["I", "am"].

    Any other token comes back unchanged, as a one-item list.
    """
    t = token.lower()
    if t in CONTRACTIONS:
        return CONTRACTIONS[t]  # irregular ones, where the first part changes
    for ending, word in CONTRACTION_ENDINGS.items():
        if t.endswith(ending) and len(t) > len(ending):
            return [token[: -len(ending)], word]
    return [token]


# =========================================================================================
# 10. Memes and names: lol -> 英雄联盟, frozen -> 冰雪奇缘, teses -> 滔搏们
# =========================================================================================

# Memes and names: learned from Wikipedia by learn.py (data/memes_learned.json) and from
# English stream chat by learn_chat.py (data/memes_chat.json, KEKW-style words), plus your
# own entries in data/memes.json, which win. These always replace the word in the stupid
# modes: lol -> 英雄联盟, teses -> 滔搏们 (plural), karrigan -> 刀锋女王 (near spelling).
MEMES_FILES = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", name)
               for name in ("memes_learned.json", "memes_chat.json", "memes.json")]
_memes = None  # {lowercase English word: Chinese}, loaded by _load_memes()
_all_words = None  # every word in the common word list, to tell ordinary words from names

# Unique words (player names and the like, not English words) are read as a typo of the
# most similar famous name in the meme dictionaries, the way Google guesses what a typo
# meant: karrigan -> kerrigan -> 刀锋女王. Only names of at least NEAR_NAME_MIN_LETTERS
# letters take part; a name may be 1 typo away, or 2 once the word has NEAR_NAME_LONG
# letters or more. A typo is one letter changed, added or removed, or two letters swapped.
NEAR_NAME_MIN_LETTERS = 5
NEAR_NAME_LONG = 7


def _load_memes():
    """Load the meme dictionaries into one dict {lowercase word: Chinese} (only once).

    memes.json is loaded last, so your own entries override learned ones. Keys starting
    with _ are notes for people (like "_comment"), not memes.
    """
    global _memes, _all_words
    if _memes is None:
        _memes = {}
        for path in MEMES_FILES:
            try:
                with open(path, encoding="utf-8") as f:
                    _memes.update({k.lower(): v for k, v in json.load(f).items()
                                   if not k.startswith("_")})
            except (OSError, ValueError):
                pass  # a missing or broken file just means no memes from it
        with open(WORDS_FILE, encoding="utf-8") as f:
            _all_words = {line.strip().lower() for line in f if line.strip()}
    return _memes


def _typo_distance(a, b):
    """How many typos turn a into b: letters changed, added or removed, or two
    neighbouring letters swapped (karrigan -> kerrigan is 1, karigan -> kerrigan is 2)."""
    # d[i][j] = typos between a[:i] and b[:j], filled in row by row
    d = [[i + j if i * j == 0 else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1,  # remove a letter
                          d[i][j - 1] + 1,  # add a letter
                          d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))  # change a letter
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)  # swap two letters
    return d[len(a)][len(b)]


def closest_name(word, names):
    """Return the name in names that word is most likely a typo of, or None.

    Allowed typos: 1, or 2 for words of NEAR_NAME_LONG letters or more (see the settings
    above). The fewest typos wins; on a tie, a name with the same first letter, then the
    one closest in length.
    """
    w = word.lower()
    if len(w) < NEAR_NAME_MIN_LETTERS:
        return None
    allowed = 2 if len(w) >= NEAR_NAME_LONG else 1
    candidates = []
    for name in names:
        if len(name) < NEAR_NAME_MIN_LETTERS or abs(len(name) - len(w)) > allowed:
            continue  # too short to guess from, or too different in length to be close
        typos = _typo_distance(w, name)
        if 0 < typos <= allowed:
            candidates.append((typos, name[0] != w[0], abs(len(name) - len(w)), name))
    return min(candidates)[3] if candidates else None


def meme_for(word):
    """Return the meme/name translation for a word, or None.

    Checked in this order: the word itself (lol), then, for words that aren't ordinary
    English words, a plural of a meme (teses -> tes + 们) and the most similar famous name
    (karrigan -> kerrigan -> 刀锋女王, see closest_name).
    """
    memes = _load_memes()
    w = word.lower()
    if w in memes:
        return memes[w]
    if w in _all_words:
        return None  # an ordinary word, leave it alone
    # Plural of a meme: teses -> tes + 们
    for ending in ("es", "s"):
        if w.endswith(ending) and w[: -len(ending)] in memes:
            return memes[w[: -len(ending)]] + "们"
    # A unique word read as a typo of a famous name: karrigan -> kerrigan. Words Google's
    # dictionary knows are real English words (just not common ones), so leave them alone.
    name = closest_name(w, memes)
    if name and not _is_real_word(w):
        return memes[name]
    return None


# =========================================================================================
# 11. The stupid pipeline: translate_word_by_word()
#
# The steps, numbered the same way in the code below:
#   1. Split the sentence into words and punctuation
#   2. Clean up: expand contractions, drop "the"
#   3. Memes and names replace their words outright
#   4. Split compound words into parts
#   5. Translate every remaining word on its own, all in one request (the "plain" result)
#   6. Past tense words that are also words take that word's meaning
#   7. Stupid mode only: collect each word's possible meanings and spread the rarity
#   8. Put the sentence back together
# =========================================================================================

def translate_word_by_word(text, source="en", target="zh-CN", timeout=10, rare=True,
                           target_rarity=TARGET_RARITY, variants=None):
    """Translate each word separately, ignoring the sentence it sits in.

    Contractions are expanded and "the" is dropped. Memes and names come first (see
    meme_for), then compound words are split into parts that keep their natural meaning
    (see split_compound). Past tense forms that are also words on their own use that
    word's meaning (see IRREGULAR_PAST_FORMS). With rare=True every other word uses a less
    common meaning: some words stay natural and some go far off, averaging TARGET_RARITY.

    With variants=N it returns a list of up to N different stupid versions instead of one
    string (check.py has a local AI model pick the best). They share every lookup, so N
    versions cost no more requests than one; only step 7's random draw is repeated.
    """
    # Step 1: words (letters, digits, apostrophes) and single punctuation marks
    tokens = re.findall(r"[A-Za-z0-9']+|[^\sA-Za-z0-9']", text)
    # Step 2: clean-up rules
    tokens = [part for t in tokens for part in expand_contraction(t)]
    tokens = [t for t in tokens if t.lower() not in SKIPPED_WORDS]
    # Step 3: memes and names win over everything else
    memes = {t: meme_for(t) for t in tokens if re.match(r"[A-Za-z0-9']", t)}
    memes = {t: m for t, m in memes.items() if m}
    # Step 4: split compound words into their parts and translate each part on its own
    split_tokens, compound_parts = [], set()
    for t in tokens:
        # Memes, and words with a meme meaning from stream chat (dragon), stay whole
        parts = None if t in memes or chat_meanings(t) else split_compound(t)
        split_tokens += parts or [t]
        compound_parts.update(parts or [])
    tokens = split_tokens
    # Split parts can be memes too (playoff -> play + off -> 关)
    memes.update({t: _load_memes()[t.lower()] for t in tokens if t.lower() in _load_memes()})
    # The words left to translate, each once (dict.fromkeys keeps their order)
    words = list(dict.fromkeys(t for t in tokens if re.match(r"[A-Za-z0-9']", t) and t not in memes))
    if not words:
        result = "".join(memes.get(t, PUNCTUATION.get(t, t)) for t in tokens)
        return [result] if variants else result

    # Step 5: the usual translation of every word, in one request (with a fallback)
    error = None
    for backend in (_translate_words_chrome_ex, _translate_words_gtx):
        try:
            lookup = dict(zip(words, backend(words, source, target, timeout)))
            break
        except Exception as exc:
            error = exc
    else:
        raise RuntimeError(f"Google Translate request failed: {error}")

    # Step 6: past tense forms that are also words on their own take that word's meaning
    past_forms = [w for w in words if w.lower() in IRREGULAR_PAST_FORMS]
    with ThreadPoolExecutor(max_workers=4) as pool:
        standalone = dict(zip(past_forms, pool.map(
            lambda w: standalone_meaning(w, source, target, timeout), past_forms)))
    for word, meaning in standalone.items():
        if meaning:
            lookup[word] = meaning

    # Step 7: stupid mode only, swap in wrong-but-real meanings
    if rare:
        # The proper translation tells us which meanings fit the sentence, so we can avoid them
        proper = translate(text, source, target, timeout)

        def word_options(word):
            """Return [(rarity, meaning), ...] for one word, its fitting meaning first.

            The fitting meaning (rarity 0) is the dictionary meaning that appears in the
            proper translation, or else the plain translation. The other meanings come
            from Google's dictionary, the capitalized word, EXTRA_MEANINGS, memes learned
            from stream chat and the round trip. Anything that is (part of) the fitting
            meaning or the plain translation is left out, so whatever gets picked really is
            a different meaning.
            """
            # The fitting meaning (rarity 0) plus every other dictionary meaning
            try:
                meanings = dictionary_meanings(word, source, target, timeout)
            except Exception:
                meanings = []  # keep the usual translation for this word
            if word.islower():
                # The capitalized word can mean something else entirely (may -> May -> 五月,
                # march -> March -> 三月). Count those meanings as at least CAPITALIZED_RARITY.
                try:
                    meanings += [(max(r, CAPITALIZED_RARITY), m) for r, m in
                                 dictionary_meanings(word.capitalize(), source, target, timeout)]
                except Exception:
                    pass
            fitting = [m for _, m in meanings if m in proper]
            natural = max(fitting, key=len) if fitting else lookup[word]
            avoid = [natural, lookup[word]]
            meanings += [(r, m) for r, m in EXTRA_MEANINGS.get(word.lower(), [])]
            try:
                meanings += [(ROUND_TRIP_RARITY, m) for m in round_trip_meanings(word, timeout)]
            except Exception:
                pass  # the round trip is a bonus, skip it if Google says no
            # others = {meaning: lowest rarity seen for it}, without the meanings to avoid
            others = {}
            for r, m in meanings:
                alone = STANDALONE_FORMS.get(m, m)  # 次 -> 次数
                if any(x in a or a in x for x in (m, alone) for a in avoid if a):
                    continue
                others[alone] = min(r, others.get(alone, r))
            # Memes from stream chat often contain the fitting meaning (恶龙呢 has 龙 in it);
            # that is the joke, so they only have to be different from it
            for m in chat_meanings(word):
                if m not in avoid:
                    others[m] = min(CHAT_MEANING_RARITY, others.get(m, CHAT_MEANING_RARITY))
            return [(0.0, natural)] + [(r, m) for m, r in others.items()]

        # Past tense forms already use their standalone meaning, so they sit this out
        # Compound parts keep their natural meaning: the split is stupid enough already
        rare_words = [w for w in words if not standalone.get(w) and w not in compound_parts]
        # Each word needs a few requests, so look the words up 4 at a time
        with ThreadPoolExecutor(max_workers=4) as pool:
            options = dict(zip(rare_words, pool.map(word_options, rare_words)))
        # One random draw per version asked for (just one without variants)
        draws = [spread_rarity(options, target_rarity) for _ in range(variants or 1)]
    else:
        draws = [{}]

    # Step 8: memes go in last so nothing overrides them; then rebuild the sentence with
    # Chinese punctuation (Chinese doesn't put spaces between words)
    sentences = []
    for draw in draws:
        chosen = {**lookup, **draw, **memes}
        sentence = "".join(chosen.get(t, PUNCTUATION.get(t, t)) for t in tokens)
        if sentence not in sentences:  # two draws can land on the same sentence
            sentences.append(sentence)
    return sentences if variants else sentences[0]


# =========================================================================================
# 12. Command line: py translator.py [--plain | --proper | --classical] [--rarity N] [text]
# =========================================================================================

def main():
    """Translate the text given on the command line, or ask for lines one at a time."""
    # Make sure Chinese prints correctly in the Windows console
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # Read the options; whatever is left is the text to translate
    args = sys.argv[1:]
    proper = "--proper" in args
    plain = "--plain" in args
    target_rarity = TARGET_RARITY
    if "--rarity" in args:
        i = args.index("--rarity")
        target_rarity = float(args[i + 1])
        del args[i:i + 2]
    classical = "--classical" in args
    check = "--check" in args
    args = [a for a in args if a not in ("--proper", "--plain", "--classical", "--check")]
    # convert is the function for the chosen mode: it takes English and returns Chinese
    if classical:
        convert, mode = translate_classical, "Classical Chinese"
    elif proper:
        convert, mode = translate, "proper"
    elif plain:
        convert, mode = (lambda text: translate_word_by_word(text, rare=False)), "word by word"
    else:
        convert = lambda text: translate_word_by_word(text, target_rarity=target_rarity)
        mode = f"stupid: word by word, rarity {target_rarity}"
    if check and (plain or not (classical or proper)):
        # A local AI model picks and smooths the result (check.py, needs Ollama running)
        from .check import MODEL, checked_translation
        convert = lambda text: checked_translation(text, rarity=target_rarity, rare=not plain)
        mode += f", checked by {MODEL}"

    # Text on the command line: translate it once and stop
    if args:
        print(convert(" ".join(args)))
        return

    # No text: interactive mode, one line at a time until a blank line or Ctrl+C
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
