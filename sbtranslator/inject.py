"""The stupid mode: a normal translation with stupid words injected into it.

    py translator.py "@frozen: teses, your HLTV top is 0, lol"
    -> @冰雪奇缘：滔搏们，你的一半生活电视顶部是0，英雄联盟

Word-by-word translation reads like gibberish. The memes Hao likes read like fluent Chinese
that means nothing: only a few words are stupid, everything around them is normal. So:

    1. Translate the sentence normally (Google), to know what each word means here.
    2. Pick the words to make stupid, and their stupid Chinese (stupid_word()):
         phrases from stream chat (phrases.json, longest first)   zywoo play -> 载物玩耍
         names, memes and plurals                                  teses -> 滔搏们 / 一些滔搏
         players' Chinese nicknames (data/nicknames.json)          zywoo -> 载物
         acronyms, expanded then translated word by word           HLTV -> 一半生活电视
         player handles read as the nearest English word           s1mple -> simple -> 简单
         everyday meanings of jargon, unless the sentence means it major -> 主要, saw -> 锯子
         compound words                                            butterfly -> 黄油苍蝇
         unique words read as a typo of a famous name              karrigan -> 刀锋女王
         other unique words read as the nearest English word       broky -> broke -> 破产
    3. Write the stupid Chinese into the English sentence inside 【】 ("your 【主要】 champion")
       and translate the whole sentence. Google builds fluent Chinese around them.
    4. Remove the 【】 and put back any injected word Google changed (滔滔搏们 -> 滔搏们).

The tables are in data/stupid_words.json (hand-written) and data/phrases.json (approved
phrases from stream chat, see learn_chat.py). With check=True a local AI model writes the
sentence instead of Google, with every stupid word required word for word (check.py).
"""

import json
import os
import random
import re
from difflib import SequenceMatcher

from . import translator as t
from .phrases import nicknames

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES_FILE = os.path.join(HERE, "data", "stupid_words.json")
PHRASES_FILE = os.path.join(HERE, "data", "phrases.json")

# Player handles: digits read as letters (s1mple -> simple, m0NESY -> monesy)
LEET = str.maketrans("103457", "ioeast")
HANDLE_SEARCH_WORDS = 10000  # how many common words a handle is compared with (all of them)
_tables = None
_phrases = None
_word_cache = {}  # plain translations of single English words


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def tables():
    """The hand-written tables: {"names": {...}, "acronyms": {...}, "everyday": {...}}."""
    global _tables
    if _tables is None:
        loaded = _load_json(TABLES_FILE)
        _tables = {name: {k.lower(): v for k, v in loaded.get(name, {}).items()}
                   for name in ("names", "acronyms", "everyday")}
    return _tables


def phrases():
    """Approved multi-word phrases: {"zywoo play": "载物玩耍"}."""
    global _phrases
    if _phrases is None:
        _phrases = {k.lower(): v for k, v in _load_json(PHRASES_FILE).items()}
    return _phrases


def _plain(word):
    """The usual Chinese for one English word, without a trailing 的 (cached)."""
    if word not in _word_cache:
        _word_cache[word] = t.translate(word).rstrip("的")
    return _word_cache[word]


def handle_word(token, any_unique=False):
    """Read a player handle as the nearest common English word, or return None.

    Tokens that look like handles count: letters mixed with digits (s1mple, m0NESY) or a
    capital in the middle (ZywOo). With any_unique=True, so does any word that isn't an
    English word (broky -> broke, ropz -> rope). Digits are read as letters, then the word
    must be a common English word or one typo away from one.
    """
    if not re.search(r"[A-Za-z]", token):
        return None
    t._load_memes()  # loads the common word list into t._all_words
    looks_like_handle = re.search(r"\d", token) or re.search(r"[a-z][A-Z]", token)
    if not looks_like_handle:
        if not any_unique or token.lower() in t._all_words or t._is_real_word(token.lower()):
            return None
    word = token.translate(LEET).lower()
    if word in t._all_words:
        return word
    if len(word) >= 4:
        with open(t.WORDS_FILE, encoding="utf-8") as f:
            common = [line.strip().lower() for _, line in zip(range(HANDLE_SEARCH_WORDS), f)]
        for candidate in common:
            if len(candidate) >= 4 and t._typo_distance(word, candidate) == 1:
                return candidate
    return None


def stupid_word(token, proper):
    """Return the stupid Chinese for one English word in this sentence, or None to keep it.

    proper is the normal translation of the whole sentence: an everyday meaning that is
    already in it is the right meaning here, so it isn't stupid.
    """
    w = token.lower()
    names, memes = tables()["names"], t._load_memes()
    for table in (names, memes):
        if w in table:
            return table[w]
    # A player with a Chinese nickname: zywoo -> 载物
    by_handle = {handle: nickname for nickname, handle in nicknames().items()}
    if w in by_handle:
        return by_handle[w]
    # Plural of a name: teses -> 滔搏们 or 一些滔搏
    for ending in ("es", "s"):
        base = w[: -len(ending)]
        if w.endswith(ending) and (base in names or base in memes) and w not in t._all_words:
            name = names.get(base) or memes[base]
            return random.choice([name + "们", "一些" + name])
    if w in tables()["acronyms"]:
        return "".join(_plain(part) for part in tables()["acronyms"][w].split())
    handle = handle_word(token)
    if handle:
        return _plain(handle)
    everyday = tables()["everyday"].get(w)
    if everyday and everyday not in proper:
        return everyday
    parts = t.split_compound(token)
    if parts:
        return "".join(_plain(part) for part in parts)
    if w not in t._all_words:
        meme = t.meme_for(token)  # a unique word read as a typo of a famous name
        if meme:
            return meme
        handle = handle_word(token, any_unique=True)  # broky -> broke -> 破产
        if handle:
            return _plain(handle)
    return None


def _repair(output, wanted):
    """Remove the 【】 and put back injected words Google changed, by closest match."""
    def fix(match):
        inside = match.group(1)
        if not wanted:
            return inside
        best = max(wanted, key=lambda w: SequenceMatcher(None, inside, w).ratio())
        return best if SequenceMatcher(None, inside, best).ratio() >= 0.5 else inside
    output = re.sub(r"【([^】]*)】", fix, output)
    output = output.replace("【", "").replace("】", "")
    # Google sometimes doubles the first character of a name it doesn't know (滔滔搏们)
    for word in wanted:
        output = output.replace(word[0] + word, word)
    return output


def inject(text, wrap=("【", "】")):
    """Do steps 1 to 3; return (proper, injected English, {English: stupid Chinese})."""
    proper = t.translate(text)
    tokens = re.findall(r"[A-Za-z0-9']+|[^A-Za-z0-9'\s]|\s+", text)
    words = [i for i, tok in enumerate(tokens) if re.match(r"[A-Za-z0-9]", tok)]
    picks, out, i = {}, [], 0
    known_phrases = phrases()
    longest = max((len(p.split()) for p in known_phrases), default=0)
    while i < len(tokens):
        # A phrase from stream chat, longest first: "zywoo play" -> 载物玩耍
        if i in words and longest > 1:
            found = None
            position = words.index(i)
            for n in range(min(longest, len(words) - position), 1, -1):
                span = words[position:position + n]
                key = " ".join(tokens[j].lower() for j in span)
                if key in known_phrases:
                    found = (span[-1], key)
                    break
            if found:
                end, key = found
                picks[key] = known_phrases[key]
                out.append(wrap[0] + known_phrases[key] + wrap[1])
                i = end + 1
                continue
        token = tokens[i]
        if i in words:
            if token.lower() not in picks:
                stupid = stupid_word(token, proper)
                if stupid:
                    picks[token.lower()] = stupid
            if token.lower() in picks:
                out.append(wrap[0] + picks[token.lower()] + wrap[1])
                i += 1
                continue
        out.append(token)
        i += 1
    return proper, "".join(out), picks


def translate_injected(text, details=False):
    """The stupid translation of text (see the top of this file).

    With details=True, returns a dict with the proper translation, the injected English,
    the stupid words and the ones missing from the result, for check.py.
    """
    proper, injected, picks = inject(text)
    wanted = list(dict.fromkeys(picks.values()))
    result = _repair(t.translate(injected), wanted) if picks else proper
    missing = [w for w in wanted if w not in result]
    if missing:
        # Google sometimes rewrites an injected word (often a verb); try other brackets once
        retry_injected = injected.replace("【", "「").replace("】", "」")
        retry = t.translate(retry_injected).replace("「", "").replace("」", "")
        retry_missing = [w for w in wanted if w not in retry]
        if len(retry_missing) < len(missing):
            result, missing = retry, retry_missing
    if details:
        return {"english": text, "proper": proper, "injected": injected, "words": picks,
                "result": result, "missing": missing}
    return result
