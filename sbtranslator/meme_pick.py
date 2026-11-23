"""Which of the bot's memes go into a stupid sentence, and where (bot_memes.py).

    Chovy gave up again lol  ->  【超威同意了】 again 【英雄联盟】  ->  超威同意了，英雄联盟

The stupid mode (inject.py) asks start() first, before it picks the stupid words:

    1. Find each meme's English cues (meme_cues.py) in the sentence: whole words, where
       gave, give, gives and giving count as one word (stem()), and {X} is any player or
       team (is_name()).
    2. Leave out what isn't allowed: every meme at the 玩梗程度 none, memes turned off in
       the ⚙ window, and cues marked "confirm", which need a model's yes for this sentence.
    3. Keep the most specific cues (more words first), as many as the 玩梗程度 allows: one
       a sentence at some, one a clause and three at most at max. Equally specific memes
       take turns, so the same one doesn't win every time.
    4. Fill a template meme's name (fill()): the meme's own name gives the meme itself (Chovy
       gave up -> 超威同意了), another name the form the bot already has for it (a variant,
       with the name or one of its nicknames from the bot's table), else the name in English
       (T1 gave up -> t1同意了).

inject.py writes the memes into the English inside 【】, like the stupid words: the words a
meme takes get no stupid word, and the rules leave the words next to it alone, so Google
doesn't run a meme and a stupid word together.
"""

import collections
import json
import os
import re
import threading

from . import bot_memes, meme_cues
from . import translator as t
from .meme_cues import SLOT

HERE = os.path.dirname(os.path.abspath(__file__))
NAME_FILES = [os.path.join(HERE, "data", name) for name in ("esports_names.txt", "players.txt")]
NICKNAMES_FILE = os.path.join(HERE, "data", "nicknames.json")  # {中文: player}
PER_SENTENCE = {"none": 0, "some": 1, "max": 3}  # memes a sentence gets at each 玩梗程度
PER_CLAUSE = {"none": 0, "some": 1, "max": 1}
MAX_OPTIONS = 6  # memes offered to switch to, per meme in a sentence
CLAUSE_END = set(",.!?;:…，。！？；：")

# Chat words that are never a player's name, though they aren't English words either
SLANG = set("""lol lul lmao lmfao rofl gg ggs ggwp wp ff kekw pog poggers omegalul omg wtf
xd ez afk bm op mvp ace rip glhf ty thx pls plz bro dude guys ok okay yes no yeah nah""".split())

# Forms of irregular words, as their usual form: gave and given are give (see stem())
IRREGULAR = {}
for _base, _forms in {
        "be": "am is are was were been being", "have": "has had having",
        "do": "does did done doing", "go": "goes went gone going", "give": "gave given",
        "take": "took taken", "throw": "threw thrown", "win": "won winning",
        "lose": "lost losing", "get": "got gotten getting", "make": "made", "come": "came",
        "run": "ran running", "see": "saw seen", "say": "said says", "think": "thought",
        "feel": "felt", "leave": "left", "buy": "bought", "bring": "brought",
        "fall": "fell fallen", "eat": "ate eaten", "beat": "beaten", "shake": "shook shaken",
        "break": "broke broken", "fly": "flew flown flies", "drive": "drove driven",
        "know": "knew known", "tell": "told", "find": "found", "keep": "kept",
        "hold": "held", "stand": "stood", "sit": "sat", "lead": "led", "feed": "fed",
        "meet": "met", "pay": "paid", "sell": "sold", "send": "sent", "spend": "spent",
        "build": "built", "teach": "taught", "catch": "caught", "fight": "fought",
        "become": "became", "begin": "began begun", "forget": "forgot forgotten",
        "hide": "hid hidden", "ride": "rode ridden", "steal": "stole stolen",
        "write": "wrote written", "choose": "chose chosen", "speak": "spoke spoken",
        "blow": "blew blown", "grow": "grew grown", "draw": "drew drawn",
        "wear": "wore worn", "bite": "bit bitten", "shoot": "shot", "it": "its",
        "cry": "cried cries"}.items():
    for _form in _forms.split():
        IRREGULAR[_form] = _base

Candidate = collections.namedtuple(
    "Candidate", "first last key phrase zh cue confirm weight name")

_turns = collections.Counter()  # how often each meme was used, so equal ones take turns
_index_cache = None  # (meme_cues.entries() it was made from, {stem: [cues]})
_built_in_names = None  # the names in the translator's own files, see known_names()
_names_cache = None  # (bot_memes.nicknames() it was made from, set of names)
_forms_cache = None  # (meme_cues.entries() it was made from, (forms, templates))
_lock = threading.Lock()


def stem(word):
    """A word as cues are compared: gave, give, gives, giving and given all become giv, so a
    cue matches every form of its words. Not real English stems: only the same for the
    forms of one word, which is all a comparison needs."""
    w = word.lower().replace("’", "'")
    w = IRREGULAR.get(w, w)
    if w.endswith("'s"):
        w = w[:-2]
    w = IRREGULAR.get(w.replace("'", ""), w.replace("'", ""))
    for _ in range(2):  # speeds -> speed -> spe, the same as speed -> spe
        if len(w) > 4 and w.endswith(("ies", "ied")):
            w = w[:-3] + "y"
        elif len(w) > 5 and w.endswith("ing"):
            w = w[:-3]
        elif len(w) > 4 and w.endswith("ed"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("es") and w[-3] in "sxzh":
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
            w = w[:-1]
        else:
            break
    if len(w) > 3 and w.endswith("e"):
        w = w[:-1]  # give and giving: giv
    if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "aeiou":
        w = w[:-1]  # stopped -> stopp -> stop, and miss -> mis like missed
    return w


# -- names, for {X} -------------------------------------------------------------------------

def _read_names():
    """The names in the translator's own files (see known_names())."""
    names = set()
    for path in NAME_FILES:
        try:
            with open(path, encoding="utf-8") as f:
                names |= {line.strip() for line in f if line.strip() and not line.startswith("#")}
        except OSError:
            pass
    try:
        with open(NICKNAMES_FILE, encoding="utf-8") as f:
            names |= {player for nickname, player in json.load(f).items()
                      if isinstance(player, str) and not nickname.startswith("_")}
    except (OSError, ValueError, AttributeError):
        pass
    return {bot_memes.squeezed(name) for name in names}


def known_names():
    """Players and teams the translator knows, as bot_memes.squeezed() writes them: the bot's
    nickname table (players and their nicknames), data/esports_names.txt, the Counter-Strike
    handles in data/players.txt and the players in data/nicknames.json."""
    global _built_in_names, _names_cache
    table = bot_memes.nicknames()
    if _names_cache is None or not (_names_cache[0] is table or not (_names_cache[0] or table)):
        if _built_in_names is None:
            _built_in_names = _read_names()
        names = set(_built_in_names)
        for player, nicknames in table.items():
            names |= {bot_memes.squeezed(n) for n in [player] + nicknames
                      if re.search(r"[A-Za-z0-9]", n)}
        _names_cache = (table, names)
    return _names_cache[1]


def is_name(token, first=False):
    """Whether a word in a sentence is a player or team, for a {X}: one the translator knows
    (known_names()), or a word that isn't English or chat slang and looks like a name: with
    a digit (T1, G2), in capitals (TES), or capitalized (Faker) when it doesn't start the
    sentence (first) or a clause, where any word is."""
    if bot_memes.squeezed(token) in known_names():
        return True
    word = token.lower()
    t._load_memes()  # loads the common English words into t._all_words
    if word in SLANG or word in t._all_words or not re.fullmatch(r"[A-Za-z0-9]+", token):
        return False
    if re.search(r"\d", token) and re.search(r"[A-Za-z]", token):
        return True
    if len(token) >= 2 and token.isupper():
        return True
    return token[:1].isupper() and not first


def fill(phrase, entry, name):
    """The meme with a name in its template (step 4 at the top of this file); the meme
    itself without a template or a name."""
    template = entry.get("template") if entry else ""
    if not template or not name:
        return phrase
    wanted = bot_memes.squeezed(name)
    if entry.get("name") and bot_memes.squeezed(entry["name"]) == wanted:
        return phrase
    forms = []
    for player, nicknames in bot_memes.nicknames().items():
        if wanted in {bot_memes.squeezed(n) for n in [player] + nicknames}:
            forms += [player] + nicknames
    forms.append(name)
    meme = bot_memes.memes().get(phrase, {})
    existing = [phrase] + meme.get("variants", [])
    for form in forms:
        filled = template.replace(SLOT, form).lower()
        found = next((e for e in existing if e.lower() == filled), None)
        if found:
            return found
    return template.replace(SLOT, name.lower())


# -- finding them in a sentence -------------------------------------------------------------

def _index(entries):
    """{a cue's first word that isn't {X}, as stem(): [(where that word is in the cue,
    phrase, cue, the cue's stems)]}, for the memes that may be used."""
    global _index_cache
    if _index_cache and _index_cache[0] is entries:
        return _index_cache[1]
    index = collections.defaultdict(list)
    for phrase, entry in entries.items():
        if not entry.get("use"):
            continue
        for cue in entry.get("cues", []):
            stems = [SLOT if w == SLOT else stem(w) for w in cue["en"].split()]
            offset = next((k for k, s in enumerate(stems) if s != SLOT), None)
            if offset is not None:
                index[stems[offset]].append((offset, phrase, cue, stems))
    _index_cache = (entries, index)
    return index


def _adjacent(tokens, i, j):
    return i < j and all(not tok.strip() for tok in tokens[i + 1:j])


def _starts(tokens, words):
    """The positions in words that start the sentence or a clause."""
    found = set()
    for n, i in enumerate(words):
        before = [tok for tok in tokens[(words[n - 1] + 1 if n else 0):i] if tok.strip()]
        if n == 0 or any(tok in CLAUSE_END for tok in before):
            found.add(n)
    return found


def candidates(tokens, words):
    """Every meme whose cue is in the sentence (step 1), as Candidates: tokens first..last
    become the Chinese zh; key is the English they show as (lowercase), weight how specific
    the cue is, name the word in its {X} (or None). tokens and words are the sentence split
    as inject.tokenize() splits it."""
    entries = meme_cues.entries()
    index = _index(entries)
    stems = [stem(tokens[i]) for i in words]
    starts = _starts(tokens, words)
    found = []
    for n in range(len(words)):
        for offset, phrase, cue, cue_stems in index.get(stems[n], ()):
            start, end = n - offset, n - offset + len(cue_stems) - 1
            if start < 0 or end >= len(words):
                continue
            name = None
            for k, wanted in enumerate(cue_stems):
                m = start + k
                if k and not _adjacent(tokens, words[m - 1], words[m]):
                    break
                if wanted == SLOT:
                    if not is_name(tokens[words[m]], m in starts):
                        break
                    name = tokens[words[m]]
                elif stems[m] != wanted:
                    break
            else:
                fixed = [s for s in cue_stems if s != SLOT]
                key = " ".join(tokens[words[m]].lower() for m in range(start, end + 1))
                found.append(Candidate(
                    words[start], words[end], key, phrase, fill(phrase, entries[phrase], name),
                    cue["en"], cue["confirm"], 10 * len(fixed) + 4 * (len(cue_stems) - len(fixed))
                    + sum(map(len, fixed)) / 100, name))
    return found


def _clause(tokens, i):
    """Which clause of the sentence token i is in: the number of clause ends before it."""
    return sum(1 for tok in tokens[:i] if tok in CLAUSE_END)


def choose(found, level, tokens):
    """Step 3: the candidates to use, as many as the 玩梗程度 allows, without overlaps."""
    chosen, taken, clauses = [], set(), collections.Counter()
    with _lock:
        for c in sorted(found, key=lambda c: (-c.weight, _turns[c.phrase], c.first)):
            if len(chosen) >= PER_SENTENCE[level]:
                break
            span, clause = set(range(c.first, c.last + 1)), _clause(tokens, c.first)
            if span & taken or clauses[clause] >= PER_CLAUSE[level]:
                continue
            chosen.append(c)
            taken |= span
            clauses[clause] += 1
        for c in chosen:
            _turns[c.phrase] += 1
    return sorted(chosen, key=lambda c: c.first)


class Planning:
    """The memes for one sentence, found by start(). result() gives them as [(first token,
    last token, key, Chinese)], with a note to show (or None) when a meme was left out."""

    def __init__(self, tokens, words, level):
        self.tokens, self.words, self.level = tokens, words, level
        self.found = candidates(tokens, words) if PER_SENTENCE[level] else []
        self.note = None
        if any(c.confirm for c in self.found):
            self.note = "要确认的梗没用上：还没有模型来确认"

    def result(self):
        usable = [c for c in self.found if not c.confirm]
        return [(c.first, c.last, c.key, c.zh)
                for c in choose(usable, self.level, self.tokens)], self.note


def start(tokens, words, level):
    """Start finding the memes for a sentence at a 玩梗程度 (see Planning). Also has the
    missing cues written in the background (meme_cues.fill_in_background())."""
    if PER_SENTENCE[level]:
        meme_cues.fill_in_background()
    return Planning(tokens, words, level)


# -- memes a person picked, and the ones they can switch to ---------------------------------

def _forms(entries):
    """Every way the bot's memes are written, lowercase, and the templates."""
    global _forms_cache
    if _forms_cache and _forms_cache[0] is entries:
        return _forms_cache[1]
    memes = bot_memes.memes()
    forms = {p.lower() for p in memes} | {v.lower() for m in memes.values() for v in m["variants"]}
    templates = {e["template"] for e in entries.values() if e.get("template")}
    _forms_cache = (entries, (forms, templates))
    return forms, templates


def is_meme(zh):
    """Whether Chinese is one of the bot's memes: a meme, a variant or a filled template."""
    forms, templates = _forms(meme_cues.entries())
    return zh.lower() in forms or any(meme_cues.fits(tp, zh) for tp in templates)


def forced(tokens, words, chosen):
    """The memes a person kept (inject.adjust() and the other versions in options()): for
    each entry of chosen ({English: Chinese}) whose Chinese is one of the bot's memes, where
    its English words are: [(first token, last token, key, Chinese)]."""
    lowered = [tokens[i].lower() for i in words]
    spans, taken = [], set()
    for key, zh in chosen.items():
        if not zh or not is_meme(zh):
            continue
        parts = key.split()
        for n in range(len(words) - len(parts) + 1):
            span = range(words[n], words[n + len(parts) - 1] + 1)
            if (lowered[n:n + len(parts)] == parts and not taken & set(span)
                    and all(_adjacent(tokens, words[m], words[m + 1])
                            for m in range(n, n + len(parts) - 1))):
                spans.append((span[0], span[-1], key, zh))
                taken |= set(span)
                break
    return sorted(spans)


def options(tokens, words, key, zh):
    """The memes one picked meme can switch to, the picked one first: the other memes whose
    cue matched the same words, and other forms of it (its variants; for a template meme
    the name's other forms, like 超威同意了 and chovy同意了)."""
    found = [zh]
    entries = meme_cues.entries()
    same = [c for c in candidates(tokens, words) if c.key == key]
    for c in same:
        meme = bot_memes.memes().get(c.phrase, {})
        entry = entries.get(c.phrase, {})
        if entry.get("template") and c.name:
            wanted = bot_memes.squeezed(c.name)
            names = [c.name.lower()] + [n for player, nicknames in bot_memes.nicknames().items()
                                        if wanted in {bot_memes.squeezed(x)
                                                      for x in [player] + nicknames}
                                        for n in [player] + nicknames]
            others = [v for v in [c.phrase] + meme.get("variants", [])
                      if any(n.lower() in v.lower() for n in names)]
            others += [entry["template"].replace(SLOT, n) for n in names]
        else:
            others = [c.phrase] + meme.get("variants", [])
        for other in [c.zh] + others:
            if other.lower() not in [f.lower() for f in found]:
                found.append(other)
    return found[:MAX_OPTIONS]
