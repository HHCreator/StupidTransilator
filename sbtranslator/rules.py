"""Stupid words that come from rules over Google's own data instead of hand-written tables.

Hao's favourite memes follow a few patterns, and Google's dictionary data can reproduce
them for any word:

    default meaning   the word's usual translation, when this sentence     send -> 发送,
                      means something else (and not just a synonym)        boring -> 钻孔
    -ing as a verb    fucking read as fuck: before a verb it is "V着",      让我们草着走,
                      "is a fucking beast" becomes "正在V着"                 他正在草着一头野兽
    literal idiom     two words Google translates into something that      holy shit -> 圣粪便
                      shares no character with their own meanings
    near-synonym      a noun or adjective Google translated normally        home -> house -> 房子
                      becomes one of its English synonyms, translated       animal -> beast -> 野兽
    curse spelling    curses spelled the way people type them online        他妈的 -> 踏马, 操 -> 草

Google's dictionary (dt=bd) lists each Chinese meaning of a word with its English
back-translations, so two meanings that share a back-translation are synonyms: swapping
one for the other wouldn't read as a wrong meaning. Google has no Chinese thesaurus, but it
has an English one (dt=ss), so near-synonyms go through English: home -> house -> 房子.

inject.py asks plan() and near_synonym_choices() about the words its tables leave alone.
"""

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from . import translator as t

TIMEOUT = 10
CHINESE_WORD = re.compile(r"[一-鿿]+")

# Closed-class words (articles, pronouns, be/have/do, prepositions...): never made stupid
# by the rules, and a pair with one of them is never read as an idiom
FUNCTION_WORDS = set("""a an the i me my mine you your yours he him his she her hers it its
we us our they them their this that these those is are was were am be been being do does
did have has had will would can could shall should may might must not no and or but if so
as at in on of to for with by from than then there here what which who whom whose how why
when where let let's very too just also all some any""".split())
BE_WORDS = {"is", "are", "was", "were", "am"}
BE_ENDINGS = ("'s", "'re", "'m")  # he's a fucking beast: 's is "is" here
ARTICLES = {"a", "an"}
INTENSIFIERS = {"so", "very", "too", "really"}

# Curses spelled the way people type them online. Google's dictionary only has the formal
# word for fuck (性交), so it is respelled too. 他妈妈 (his mom) and 操作/操场 stay as they are.
CURSE_SPELLING = [(re.compile(r"他妈的"), "踏马"), (re.compile(r"他妈(?!妈)"), "踏马"),
                  (re.compile(r"性交"), "草"),
                  (re.compile(r"操(?=[你他她它我！!，,。.？?…\s]|$)"), "草")]

# Near-synonyms: at most one word in NEAR_SYNONYM_SHARE content words gets one (at least one
# per sentence), so most words stay normal. NEAR_SYNONYM_CHOICES are kept per word for the
# other versions. Synonym groups Google labels rare, formal or informal are skipped (abode,
# digs), and a synonym must list the word among its own synonyms too.
NEAR_SYNONYM_SHARE = 3
NEAR_SYNONYM_CHOICES = 5
NEAR_SYNONYM_TRIES = 12  # English synonyms looked at per word: each costs a request, once
SKIPPED_LABELS = {"rare", "formal", "informal", "archaic", "literary", "dated"}
# Found near-synonyms are saved next to the round-trip cache, so a word costs requests once
NEAR_SYNONYMS_FILE = os.path.join(os.path.dirname(t.CACHE_FILE), "near_synonyms.json")

_plain = {}  # English word or phrase -> its usual Chinese
_senses = {}  # English word -> its dictionary entry, see senses()
_thesaurus = {}  # English word -> its synonym groups, see thesaurus()
_near = None  # "word|part of speech" -> near-synonyms, read from and saved to the file
_near_lock = threading.Lock()  # words are looked up in parallel and share the file
chosen_near = {}  # English word -> the near-synonyms offered for it (for word_options)


# -- Google's data ------------------------------------------------------------------------

def _google(params, wanted=None):
    """Ask Google's dictionary endpoint: the Chrome extension's first, then the classic one
    if that fails or (with wanted) if its answer lacks what wanted() looks for."""
    data, error = None, None
    for url, client in (("https://clients5.google.com/translate_a/single", "dict-chrome-ex"),
                        ("https://translate.googleapis.com/translate_a/single", "gtx")):
        try:
            data = t._get_json(url, [("client", client)] + params, TIMEOUT)
        except Exception as exc:
            error = exc
            continue
        if wanted is None or wanted(data):
            return data
    if data is None:
        raise RuntimeError(f"Google dictionary request failed: {error}")
    return data


def plain(word):
    """The usual Chinese for an English word or phrase, without a trailing 的 (cached)."""
    if word not in _plain:
        _plain[word] = t.translate(word).rstrip("的")
    return _plain[word]


def plain_many(texts):
    """plain() for many words or phrases, in one request for the ones not asked yet."""
    todo = [x for x in dict.fromkeys(texts) if x not in _plain]
    if todo:
        try:
            found = t._translate_words_chrome_ex(todo, "en", "zh-CN", TIMEOUT)
        except Exception:
            found = t._translate_words_gtx(todo, "en", "zh-CN", TIMEOUT)
        for text, chinese in zip(todo, found):
            _plain[text] = chinese.rstrip("的")
    return [_plain[x] for x in texts]


def senses(word):
    """Google's dictionary entry for a word, most common part of speech first:
    [(part of speech, [(Chinese, {English back-translations}), ...]), ...], or []."""
    w = word.lower()
    if w not in _senses:
        entries = []
        try:
            data = _google([("sl", "en"), ("tl", "zh-CN"), ("dt", "bd"), ("q", w)])
            for entry in (data[1] if len(data) > 1 and data[1] else []):
                if entry[3].endswith("-"):
                    continue  # an affix like "im-" for "I'm", not the word itself
                meanings = [(term[0].replace("...", "").replace(" ", "").rstrip("的"),
                             {b.lower() for b in term[1] or []}) for term in entry[2]]
                entries.append((entry[0], [(zh, backs) for zh, backs in meanings if zh]))
        except Exception:
            pass  # no dictionary entry: the word just isn't made stupid by these rules
        _senses[w] = entries
    return _senses[w]


def parts_of_speech(word):
    return [pos for pos, meanings in senses(word)]


def used_as(word, proper):
    """The part of speech whose meaning the normal translation uses (still: 仍然 is an
    adverb, not the adjective 静止), or None. A one-character meaning counts if it is
    there once (家 in 送他们回家)."""
    for pos, meanings in senses(word):
        for zh, backs in meanings:
            if zh in proper and (len(zh) >= 2 or proper.count(zh) == 1):
                return pos
    return None


def thesaurus(word):
    """Google's English synonyms: [(part of speech, [(labels, [synonyms]), ...]), ...]."""
    w = word.lower()
    if w not in _thesaurus:
        groups = []
        try:
            data = _google([("sl", "en"), ("tl", "zh-CN"), ("dt", "ss"), ("q", w)],
                           wanted=lambda d: len(d) > 11 and d[11])
            for entry in (data[11] if len(data) > 11 and data[11] else []):
                pos, found = entry[0], []
                for group in entry[1]:
                    labels = {label for labelled in (group[2] if len(group) > 2 and group[2]
                                                     else []) for label in labelled or []}
                    found.append((labels, group[0]))
                groups.append((pos, found))
        except Exception:
            pass
        _thesaurus[w] = groups
    return _thesaurus[w]


# -- the rules for one word ---------------------------------------------------------------

def two_characters(word, chinese):
    """A lone character becomes a dictionary word containing it (好 -> 良好): one character
    rarely stands alone in a sentence."""
    if len(chinese) == 1:
        for pos, meanings in senses(word):
            for zh, backs in meanings:
                if len(zh) >= 2 and chinese in zh:
                    return zh
    return chinese


def default_meaning(word, proper):
    """The word's usual translation if the sentence (proper) means something else by it:
    send -> 发送 in 送他们回家. None if the usual one is there, or only a synonym of it is
    (they share an English back-translation, so it wouldn't read as a wrong meaning)."""
    usual = plain(word)
    if not CHINESE_WORD.search(usual) or usual in proper:
        return None
    w = word.lower()
    meanings = [(zh, backs - {w}) for pos, found in senses(word) for zh, backs in found]
    mine = set().union(*(backs for zh, backs in meanings if zh == usual))
    if any(zh in proper and mine & backs for zh, backs in meanings):
        return None
    return two_characters(word, usual)


def ing_verb(word):
    """The verb an -ing word comes from (fucking -> fuck, boring -> bore), or None. Nouns
    like building keep their own meaning."""
    w = word.lower()
    if not w.endswith("ing") or len(w) < 6 or parts_of_speech(w)[:1] == ["noun"]:
        return None
    stem = w[:-3]
    for base in (stem, stem + "e", stem[:-1] if stem[-1:] == stem[-2:-1] else None):
        if base and "verb" in parts_of_speech(base):
            return base
    return None


def verb_meaning(word, base):
    """The Chinese of the verb itself (fuck -> 性交), not of the -ing word (他妈的)."""
    usual = plain(base)
    if CHINESE_WORD.search(usual) and usual != plain(word):
        return usual
    verbs = [zh for pos, found in senses(base) if pos == "verb" for zh, backs in found]
    return verbs[0] if verbs else None


def literal_idiom(first, second):
    """Two words read literally (holy shit -> 圣粪便) when Google translates them together
    into something sharing no character with their own meanings (天哪), else None. After an
    adjective the second word is read as a noun: shit -> 粪便, not 狗屎."""
    whole = plain(f"{first} {second}")
    nouns = [zh for pos, found in senses(second) if pos == "noun" for zh, backs in found]
    if nouns and "adjective" in parts_of_speech(first):
        second_zh = two_characters(second, nouns[0])
    else:
        second_zh = plain(second)
    parts = plain(first) + second_zh
    if CHINESE_WORD.fullmatch(parts) and whole and not set(whole) & set(parts):
        return parts
    return None


def near_synonyms(word, pos):
    """Chinese near-synonyms of a word used as pos (noun, adjective...), nearest first:
    home -> 房子 宿舍 地址 地方 栖息地.

    They are Google's English synonyms of the word, translated. A synonym must list the
    word among its own synonyms too, and the earlier the two are in each other's lists, the
    nearer they are. Saved to NEAR_SYNONYMS_FILE, so each word costs requests only once.
    """
    global _near
    w, key = word.lower(), f"{word.lower()}|{pos}"
    with _near_lock:
        if _near is None:
            try:
                with open(NEAR_SYNONYMS_FILE, encoding="utf-8") as f:
                    _near = json.load(f)
            except (OSError, ValueError):
                _near = {}  # no cache yet, or a broken one: start empty
        if key in _near:
            return _near[key]
    distance = {}  # synonym -> how far down the word's list it is
    for p, groups in thesaurus(w):
        for g, (labels, synonyms) in enumerate(groups):
            if p != pos or labels & SKIPPED_LABELS:
                continue
            for s, synonym in enumerate(synonyms):
                if " " not in synonym and "/" not in synonym and synonym != w:
                    distance.setdefault(synonym, g * 3 + s)
    tried = sorted(distance, key=distance.get)[:NEAR_SYNONYM_TRIES]
    with ThreadPoolExecutor(max_workers=4) as pool:
        their_lists = dict(zip(tried, pool.map(thesaurus, tried)))
    nearest = []
    for synonym in tried:
        back = [g * 3 + s for p, groups in their_lists[synonym]
                for g, (labels, synonyms) in enumerate(groups)
                for s, other in enumerate(synonyms) if other == w]
        if back:
            nearest.append((distance[synonym] + min(back), synonym))
    names = [synonym for _, synonym in sorted(nearest)]
    chinese = plain_many(names)
    # A lone character reads better as the word Google uses in a sentence: 兽 -> 野兽
    lone = [name for name, zh in zip(names, chinese) if len(zh) == 1]
    in_sentence = dict(zip(lone, plain_many([f"the {name}" for name in lone])))
    own, choices = plain(word), []
    for name, zh in zip(names, chinese):
        if len(zh) == 1 and 2 <= len(in_sentence[name]) <= 3:
            zh = in_sentence[name]
        if (len(zh) >= 2 and CHINESE_WORD.fullmatch(zh) and own not in zh
                and zh not in choices):
            choices.append(zh)
    choices = choices[:NEAR_SYNONYM_CHOICES]
    with _near_lock:
        _near[key] = choices
        try:
            os.makedirs(os.path.dirname(NEAR_SYNONYMS_FILE), exist_ok=True)
            with open(NEAR_SYNONYMS_FILE, "w", encoding="utf-8") as f:
                json.dump(_near, f, ensure_ascii=False, indent=0)
        except OSError:
            pass  # a read-only folder only means no cache
    return choices


def spell(text):
    """Spell curses the way people type them online: 他妈的 -> 踏马, 操 -> 草."""
    for formal, online in CURSE_SPELLING:
        text = formal.sub(online, text)
    return text


def where(word, text):
    """The Chinese the word became in text (its longest dictionary meaning found), or None.
    A one-character meaning (送 for send) only counts when it is in the text once."""
    meanings = {zh for pos, found in senses(word) for zh, backs in found} | {plain(word)}
    for zh in sorted(meanings, key=len, reverse=True):
        if CHINESE_WORD.fullmatch(zh) and zh in text and (len(zh) >= 2 or text.count(zh) == 1):
            return zh
    return None


# -- the rules for a sentence -------------------------------------------------------------

def _content_words(tokens, words):
    return [i for i in words if tokens[i].lower() not in FUNCTION_WORDS
            and re.fullmatch(r"[A-Za-z]+", tokens[i])]


def _adjacent(tokens, i, j):
    return i < j and all(not tok.strip() for tok in tokens[i + 1:j])


def plan(tokens, words, proper, skip=()):
    """Choose the rule-based stupid words of a sentence.

    tokens is the sentence split as in inject.inject(), words the indexes of its word
    tokens, proper its normal translation, and skip the indexes the tables already took.
    Returns {first token index: (last token index, key, Chinese, before, after)}: those
    tokens become before + 【Chinese】 + after, and key is the English the choice shows as.
    """
    content = _content_words(tokens, words)
    pairs = [(i, j) for i, j in zip(content, content[1:]) if _adjacent(tokens, i, j)]
    # Ask for everything at once: words and pairs in one request, dictionaries in parallel
    plain_many([tokens[i] for i in content] + [f"{tokens[i]} {tokens[j]}" for i, j in pairs])
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(senses, [tokens[i] for i in content]))
    found, taken = {}, set(skip)

    # Idioms first: they take both words
    for i, j in pairs:
        if i not in taken and j not in taken:
            literal = literal_idiom(tokens[i], tokens[j])
            if literal:
                found[i] = (j, f"{tokens[i]} {tokens[j]}".lower(), literal, "", "")
                taken.update((i, j))

    swallowed = {i for i, j in pairs if plain(f"{tokens[i]} {tokens[j]}") == plain(tokens[j])}
    for n, i in enumerate(words):
        word = tokens[i].lower()
        if i in taken or i not in content or i in swallowed:
            continue  # right now -> 现在: "right" has no Chinese of its own here
        before = words[n - 1] if n > 0 and _adjacent(tokens, words[n - 1], i) else None
        before2 = (words[n - 2] if before is not None and n > 1
                   and _adjacent(tokens, words[n - 2], before) else None)
        after = (words[n + 1] if n + 1 < len(words) and _adjacent(tokens, i, words[n + 1])
                 else None)
        prev = tokens[before].lower() if before is not None else ""
        prev2 = tokens[before2].lower() if before2 is not None else ""
        nxt = tokens[after].lower() if after is not None else ""
        next_pos = parts_of_speech(nxt) if nxt and nxt not in FUNCTION_WORDS else []
        base = ing_verb(word)
        verb = verb_meaning(word, base) if base else None
        if base and prev in INTENSIFIERS and "adjective" in next_pos:
            continue  # so fucking good: only a curse for emphasis, Google's 他妈的 is right
        if verb and prev in ARTICLES and "noun" in next_pos and before2 is not None and (
                prev2 in BE_WORDS or prev2.endswith(BE_ENDINGS)) and before2 not in taken:
            # he's a fucking beast -> he 【正在性交着】 a beast -> 他正在草着一头野兽
            subject = next((prev2[:-len(e)] for e in BE_ENDINGS if prev2.endswith(e)), "")
            keep = tokens[before2][:len(subject)] + " " if subject else ""
            found[before2] = (i, f"{prev2} {prev} {word}", "正在" + verb + "着", keep,
                              " " + tokens[before])
            taken.update(range(before2, i + 1))
            continue
        if verb and "verb" in next_pos and "adjective" not in next_pos:
            found[i] = (i, f"{word} {nxt}", verb + "着", "", "")  # let's fucking go -> 性交着走
        elif verb and prev in INTENSIFIERS:
            found[i] = (i, f"{prev} {word}", verb, "", "")  # so boring -> 太钻孔了
        elif verb and after is None and n == len(words) - 1:
            found[i] = (i, word, "正在" + verb, "", "")
        elif before not in taken and after not in skip:
            # Two stupid words in a row confuse Google (sick play -> 生病可爱)
            usual = default_meaning(tokens[i], proper)
            if usual:
                found[i] = (i, word, usual, "", "")
        if i in found:
            taken.add(i)
    return found


def near_synonym_choices(tokens, words, proper, skip=()):
    """{token index: near-synonyms} for the words that get one: nouns and adjectives Google
    translated normally, at most one in NEAR_SYNONYM_SHARE content words (at least one).
    Names have no dictionary entry, so they never get one."""
    content = _content_words(tokens, words)
    budget = max(1, len(content) // NEAR_SYNONYM_SHARE)
    found = {}
    for n, i in enumerate(words):
        if len(found) >= budget:
            break
        if i not in content or i in skip or len(tokens[i]) < 3:
            continue
        before = words[n - 1] if n > 0 and _adjacent(tokens, words[n - 1], i) else None
        if before in skip or before in found:
            continue  # right after a stupid word: Google needs English around it
        pos = used_as(tokens[i], proper)
        if (pos not in ("noun", "adjective") or plain(tokens[i]) not in proper
                or {"adverb", "conjunction", "preposition"} & set(parts_of_speech(tokens[i]))):
            continue  # still, even, well: Google files 仍然 under "adjective", so skip those
        choices = [zh for zh in near_synonyms(tokens[i], pos) if zh not in proper]
        if choices:
            found[i] = choices
            chosen_near[tokens[i].lower()] = choices
    return found
