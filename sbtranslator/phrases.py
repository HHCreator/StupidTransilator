"""Turn short danmu into a phrase table: 载物玩耍 -> "zywoo play".

Most danmu don't play with translation, but the short lines a crowd spams often do: 生命游戏
is "life game" read word by word, 载物玩耍 is "ZywOo play" with the player's nickname. Those
make the best stupid phrases. So, from recorded chat (learn_chat.py):

    1. Take short Chinese danmu (MAX_CHARACTERS or fewer) sent by at least 3 people.
    2. Split them into words (split_words), checking each piece in Google's dictionary.
    3. Find the English for each word, in this order:
         the nickname table (data/nicknames.json)         载物 -> zywoo
         a player handle among its English meanings       设备 -> device (data/players.txt)
         its most common English meaning                  生命 -> life
    4. Join them into an English phrase: a candidate, "zywoo play" -> 载物玩耍.

Candidates wait in data/phrase_candidates.json until you approve them (py listen.py
--review); approved ones go into data/phrases.json, which the stupid mode (inject.py) uses,
longest phrase first. Nicknames also work on their own: zywoo -> 载物.
"""

import json
import os
import re

from .translator import _get_json

HERE = os.path.dirname(os.path.abspath(__file__))
NICKNAMES_FILE = os.path.join(HERE, "data", "nicknames.json")
PLAYERS_FILE = os.path.join(HERE, "data", "players.txt")
CANDIDATES_FILE = os.path.join(HERE, "data", "phrase_candidates.json")
PHRASES_FILE = os.path.join(HERE, "data", "phrases.json")

MAX_CHARACTERS = 8  # longer danmu are sentences, not phrases
MAX_PIECE = 4  # the longest Chinese word looked up as one piece
MAX_WORDS = 3  # danmu that split into more words are sentences, not phrases
PARTICLES = set("了呢吧啊吗的哦呀嘛")  # mood words that carry no meaning in a phrase
CJK_ONLY = re.compile(r"^[一-鿿]+$")
_dictionary_cache = {}


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")} if isinstance(data, dict) else data
    except (OSError, ValueError):
        return default


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def nicknames():
    """{Chinese nickname: player handle}, from data/nicknames.json."""
    return {k: v.lower() for k, v in _load(NICKNAMES_FILE, {}).items()}


def players():
    """The set of known player handles (lowercase), from data/players.txt."""
    try:
        with open(PLAYERS_FILE, encoding="utf-8") as f:
            return {line.strip().lower() for line in f if line.strip() and not line.startswith("#")}
    except OSError:
        return set()


def english_meanings(word):
    """Google's dictionary meanings of a Chinese word, most common first (cached)."""
    if word not in _dictionary_cache:
        data = _get_json("https://clients5.google.com/translate_a/single",
                         [("client", "dict-chrome-ex"), ("sl", "zh-CN"), ("tl", "en"),
                          ("dt", "t"), ("dt", "bd"), ("q", word)], 10)
        meanings = []
        for entry in data[1] or []:  # [pos, [terms], [[term, ...], ...], ...] like English
            meanings += [term[0].lower() for term in entry[2] if term[0].lower() not in meanings]
        if not meanings and data[0]:
            meanings = [data[0][0][0].lower()]  # no dictionary entry: the plain translation
        # Only words Google's dictionary knows count; plain translations of random character
        # pairs make junk (成大 -> "chengdu")
        _dictionary_cache[word] = (bool(data[1]), meanings)
    return _dictionary_cache[word]


def split_words(phrase):
    """Split a Chinese phrase into dictionary words (生命游戏 -> 生命, 游戏), or None.

    Pieces of 2 characters are preferred, as most Chinese words are; nicknames and words
    Google's dictionary knows count as words.
    """
    known = nicknames()
    best = {0: []}  # best[i] = best split of phrase[:i]
    for end in range(1, len(phrase) + 1):
        options = []
        for start in range(max(0, end - MAX_PIECE), end):
            piece = phrase[start:end]
            if start in best and (piece in known or english_meanings(piece)[0]):
                options.append(best[start] + [piece])
        if options:
            # Fewest pieces, then as many 2-character pieces as possible
            best[end] = min(options, key=lambda p: (len(p), -sum(len(x) == 2 for x in p)))
    return best.get(len(phrase))


def to_english(word, handles):
    """The English for one Chinese word: nickname, then a player handle, then the usual."""
    known = nicknames()
    if word in known:
        return known[word]
    meanings = english_meanings(word)[1]
    for meaning in meanings:
        if meaning in handles:
            return meaning  # 设备 -> device, a player's name
    return meanings[0] if meanings else None


def make_candidates(chinese_memes):
    """Turn {danmu: number of people} into phrase candidates and save the new ones.

    Returns the new candidates: {english phrase: {"chinese": danmu, "people": n}}.
    """
    approved = _load(PHRASES_FILE, {})
    stored = _load(CANDIDATES_FILE, {})
    rejected = set(stored.pop("rejected", []))
    handles = players()
    new = {}
    for danmu, people in sorted(chinese_memes.items(), key=lambda m: -m[1]):
        if not (2 <= len(danmu) <= MAX_CHARACTERS and CJK_ONLY.match(danmu)):
            continue
        words = split_words(danmu)
        words = [w for w in words or [] if w not in PARTICLES]  # 恶龙呢 -> 恶龙
        if not 2 <= len(words) <= MAX_WORDS:
            continue  # one word isn't a phrase; many words are a sentence
        english = [to_english(w, handles) for w in words]
        if None in english:
            continue
        phrase = " ".join(english)
        if phrase in approved or phrase in rejected or phrase in stored:
            continue
        new[phrase] = {"chinese": danmu, "people": people}
    stored.update(new)
    _save(CANDIDATES_FILE, {**stored, "rejected": sorted(rejected)})
    return new


def review():
    """Ask about each waiting candidate: y adds it to the phrase table, n rejects it."""
    stored = _load(CANDIDATES_FILE, {})
    rejected = set(stored.pop("rejected", []))
    approved = _load(PHRASES_FILE, {})
    if not stored:
        print("No phrase candidates waiting. Listen to some chat first (py listen.py douyu 6657).")
        return
    print("y = add to the phrase table, n = never suggest again, Enter = decide later, q = stop")
    for phrase, info in list(stored.items()):
        answer = input(f"  {phrase} -> {info['chinese']}  ({info['people']} people)  [y/n] ").strip().lower()
        if answer == "q":
            break
        if answer == "y":
            approved[phrase] = info["chinese"]
            del stored[phrase]
        elif answer == "n":
            rejected.add(phrase)
            del stored[phrase]
    try:  # keep the note at the top of the file
        with open(PHRASES_FILE, encoding="utf-8") as f:
            note = {k: v for k, v in json.load(f).items() if k.startswith("_")}
    except (OSError, ValueError):
        note = {}
    _save(PHRASES_FILE, {**note, **dict(sorted(approved.items()))})
    _save(CANDIDATES_FILE, {**stored, "rejected": sorted(rejected)})
    print(f"The phrase table has {len(approved)} phrases.")
