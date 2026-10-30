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
       then, for the words the tables leave alone, the rules in rules.py (no tables):
         the usual meaning, when the sentence means another one    send -> 发送, boring -> 钻孔
         -ing words read as their verb                             let's fucking go -> 让我们草着走
         two words read literally                                  holy shit -> 圣粪便
         a near-synonym for a few nouns and adjectives             home -> house -> 房子
    3. Write the stupid Chinese into the English sentence inside 【】 ("your 【主要】 champion")
       and translate the whole sentence. Google builds fluent Chinese around them.
    4. Remove the 【】 and put back any injected word Google changed (滔滔搏们 -> 滔搏们). If
       Google garbled the sentence, swap the stupid words into the normal translation instead.
       Spell curses the way people type them (他妈的 -> 踏马).

The tables are in data/stupid_words.json (hand-written) and data/phrases.json (approved
phrases from stream chat, see learn_chat.py); a table entry wins over the rules. With
check=True a local AI model writes the sentence instead of Google, with every stupid word
required word for word (check.py).
"""

import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

from . import rules
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
    return rules.plain(word)


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


def plural_name(word):
    """The Chinese name a plural of a name stands for (teses -> 滔搏), or None."""
    w = word.lower()
    names, memes = tables()["names"], t._load_memes()
    for ending in ("es", "s"):
        base = w[: -len(ending)]
        if w.endswith(ending) and (base in names or base in memes) and w not in t._all_words:
            return names.get(base) or memes[base]
    return None


def plural_forms(name):
    """The ways to say a plural name: 滔搏们, 一些滔搏, and 滔搏搏 (tes = 滔搏, so the second
    es is another 搏)."""
    return [name + "们", "一些" + name, name + name[-1]]


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
    # Plural of a name: teses -> 滔搏们, 一些滔搏 or 滔搏搏
    name = plural_name(w)
    if name:
        return random.choice(plural_forms(name))
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


# What is still inside 【】 after Google is one of the injected words, maybe changed: it is
# put back when it shares this much with one (圣穹 -> 圣粪便 shares 0.4)
REPAIR_SIMILARITY = 0.3


def _defects(result, wanted, text, proper):
    """How bad a stupid sentence is: injected words that went missing, plus English words
    Google left untranslated that it translates in the normal sentence (患病 ilya)."""
    def english(s):
        return {w.lower() for w in re.findall(r"[A-Za-z]{2,}", s)}
    return sum(w not in result for w in wanted) + len(english(result) & english(text)
                                                      - english(proper))


def _swapped(proper, picks):
    """The normal translation with each stupid word put where its word's translation is:
    这个游戏太无聊了 -> 这个游戏太钻孔了. For when Google garbles the injected sentence."""
    for key, zh in picks.items():
        name = re.search(r"(?<![A-Za-z])" + re.escape(key) + r"(?![A-Za-z])", proper, re.I)
        if name:  # a name Google keeps in English: zywoo 的表演 -> 载物 的表演
            proper = proper[:name.start()] + zh + proper[name.end():]
            continue
        for part in key.split():
            spot = (rules.where(part, proper)
                    if part not in rules.FUNCTION_WORDS and "'" not in part else None)
            if spot:
                proper = proper.replace(spot, zh, 1)
                break
    return re.sub(r"(?<=[\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])", "", proper)


def _repair(output, wanted):
    """Remove the 【】 and put back injected words Google changed, by closest match."""
    def fix(match):
        inside = match.group(1)
        if not wanted:
            return inside
        best = max(wanted, key=lambda w: SequenceMatcher(None, inside, w).ratio())
        similar = SequenceMatcher(None, inside, best).ratio() >= REPAIR_SIMILARITY
        return best if similar else inside
    output = re.sub(r"【([^】]*)】", fix, output)
    output = output.replace("【", "").replace("】", "")
    # Google sometimes doubles the first character of a name it doesn't know (滔滔搏们)
    for word in wanted:
        output = output.replace(word[0] + word, word)
    return output


def inject(text, wrap=("【", "】"), forced=None, proper=None, use_rules=True):
    """Do steps 1 to 3; return (proper, injected English, {English: stupid Chinese}).

    forced, when given, decides the stupid words instead of the rules: {English word or
    phrase (lowercase): stupid Chinese}, and a word that isn't in it stays normal. That is
    how a person picks other options (see options() and adjust()). proper can be passed in
    to save asking Google for it again. With use_rules=False only the tables are used, not
    rules.py.
    """
    if proper is None:
        proper = t.translate(text)
    tokens = re.findall(r"[A-Za-z0-9']+|[^A-Za-z0-9'\s]|\s+", text)
    words = [i for i, tok in enumerate(tokens) if re.match(r"[A-Za-z0-9]", tok)]
    # Each choice replaces tokens first..last: {first: (last, key, Chinese, before, after)}
    chosen, by_word = {}, {}
    known_phrases = phrases()
    longest = max((len(p.split()) for p in known_phrases), default=0)
    i = 0
    while i < len(tokens):
        # A phrase from stream chat, longest first: "zywoo play" -> 载物玩耍
        if i in words and longest > 1:
            found = None
            position = words.index(i)
            for n in range(min(longest, len(words) - position), 1, -1):
                span = words[position:position + n]
                key = " ".join(tokens[j].lower() for j in span)
                if key in known_phrases and (forced is None or forced.get(key)):
                    found = (span[-1], key)
                    break
            if found:
                end, key = found
                zh = forced[key] if forced is not None else known_phrases[key]
                chosen[i] = (end, key, zh, "", "")
                i = end + 1
                continue
        # A word from the tables (names, memes, nicknames, acronyms, everyday meanings...)
        if i in words:
            w = tokens[i].lower()
            if w not in by_word:
                by_word[w] = (forced.get(w) if forced is not None
                              else stupid_word(tokens[i], proper))
            if by_word[w]:
                chosen[i] = (i, w, by_word[w], "", "")
        i += 1
    taken = {j for first, (last, *_) in chosen.items() for j in range(first, last + 1)}
    if use_rules:
        # The rules (rules.py) for the words the tables left alone
        for first, (last, key, zh, before, after) in rules.plan(tokens, words, proper,
                                                                 taken).items():
            if forced is not None:
                zh = forced.get(key)  # a person's choice, or normal if they turned it off
            if zh and not taken & set(range(first, last + 1)):
                chosen[first] = (last, key, zh, before, after)
                taken.update(range(first, last + 1))
        if forced is None:
            # One near-synonym in a few words; options() offers the others as versions
            for j, choices in rules.near_synonym_choices(tokens, words, proper, taken).items():
                chosen[j] = (j, tokens[j].lower(), choices[0], "", "")
    picks, out, i = {}, [], 0
    while i < len(tokens):
        if i in chosen:
            last, key, zh, before, after = chosen[i]
            picks[key] = zh
            out.append(before + wrap[0] + zh + wrap[1] + after)
            i = last + 1
        else:
            out.append(tokens[i])
            i += 1
    return proper, "".join(out), picks


def translate_injected(text, details=False, forced=None, proper=None, use_rules=True):
    """The stupid translation of text (see the top of this file).

    With details=True, returns a dict with the proper translation, the injected English,
    the stupid words and the ones missing from the result, for check.py. forced, proper and
    use_rules are passed on to inject().
    """
    proper, injected, picks = inject(text, forced=forced, proper=proper, use_rules=use_rules)
    wanted = list(dict.fromkeys(picks.values()))
    result = _repair(t.translate(injected), wanted) if picks else proper
    missing = [w for w in wanted if w not in result]
    if missing:
        # Google sometimes rewrites an injected word (often a verb); try other brackets once
        retry_injected = injected.replace("【", "「").replace("】", "」")
        retry = _repair(t.translate(retry_injected).replace("「", "【").replace("」", "】"), wanted)
        retry_missing = [w for w in wanted if w not in retry]
        if len(retry_missing) < len(missing):
            result, missing = retry, retry_missing
    if missing and use_rules:
        # Put a lost word where its English word's translation is: 太无聊了 -> 太钻孔了
        lost = {key: zh for key, zh in picks.items() if zh in missing}
        fixed = _swapped(result, lost)
        if _defects(fixed, wanted, text, proper) < _defects(result, wanted, text, proper):
            result = fixed
        missing = [w for w in wanted if w not in result]
        garbled = {key for key, zh in picks.items()
                   if zh in missing and zh in rules.chosen_near.get(key, [])}
        if garbled and forced is None:
            # Google garbles some near-synonyms (患病伊利亚 -> 脓伊利亚): leave those normal
            kept = {key: zh for key, zh in picks.items() if key not in garbled}
            return translate_injected(text, details, kept, proper, use_rules)
    if use_rules and _defects(result, wanted, text, proper):
        # Still garbled: the normal sentence with the stupid words swapped in may read better
        swapped = _swapped(proper, picks)
        if _defects(swapped, wanted, text, proper) < _defects(result, wanted, text, proper):
            result = swapped
            missing = [w for w in wanted if w not in result]
    if use_rules:
        # Google puts quotes around words it finds odd (“生病”), and writes curses formally
        for word in wanted:
            result = result.replace("“" + word + "”", word)
        result = rules.spell(result)
        picks = {key: rules.spell(zh) for key, zh in picks.items()}
        missing = [rules.spell(w) for w in missing]
    if details:
        return {"english": text, "proper": proper, "injected": injected, "words": picks,
                "result": result, "missing": missing}
    return result


# -- more options, for people who want to pick --------------------------------------------
#
# Like Google Translate's alternatives: after translating, every stupid word can be switched
# to another stupid meaning (or back to normal), and a few whole different versions are
# offered. options() makes them; adjust() rebuilds the sentence from a person's choices.

MAX_OPTIONS = 6  # stupid meanings offered per word
VERSIONS = 4  # whole sentences offered, the first one being the usual translation


def word_options(english, chosen, proper):
    """The stupid meanings one word can switch to: the chosen one first, then others.

    Others are its other plural forms (滔搏们 / 一些滔搏 / 滔搏搏), its other near-synonyms
    (房子 / 宿舍 / 地址, see rules.py) and the dictionary meanings that aren't in the normal
    translation, so each one really is a wrong meaning.
    """
    found = [chosen]
    if " " in english:
        return found  # a phrase from stream chat or a rule for several words
    name = plural_name(english)
    if name and chosen in plural_forms(name):
        return found + [form for form in plural_forms(name) if form != chosen]
    found += [zh for zh in rules.chosen_near.get(english, []) if zh not in found]
    try:
        meanings = sorted(t.dictionary_meanings(english))
    except Exception:
        meanings = []  # Google's dictionary didn't answer; keep what we have
    plain = _plain(english)
    for rarity, meaning in meanings:
        alone = t.STANDALONE_FORMS.get(meaning, meaning)
        if (rarity <= t.MAX_RARITY and alone and alone not in proper and alone != plain
                and alone not in found):
            found.append(alone)
        if len(found) >= MAX_OPTIONS:
            break
    return found


def options(text, versions=VERSIONS, check=False):
    """Translate text and offer choices. Returns a dict:

        translation  the stupid translation (written by the local model with check=True)
        versions     up to `versions` different whole sentences, translation first
        words        [{"english": word, "chosen": stupid Chinese, "options": [...]}, ...]
        proper       the normal translation (pass it to adjust() to save a request)
        checked      True when the local model was asked (check=True, see check.py)
        check_error  why the local model couldn't be asked, or None
    """
    details = translate_injected(text, details=True)
    proper, picks = details["proper"], details["words"]
    translation = details["result"]
    checked, check_error = False, None
    if check and picks:
        from .check import CheckUnavailable, build_injected
        try:
            translation = build_injected(details)
            checked = True
        except CheckUnavailable as error:
            check_error = str(error)  # no local model: keep Google's sentence
    with ThreadPoolExecutor(max_workers=4) as pool:
        choices = dict(zip(picks, pool.map(lambda w: word_options(w, picks[w], proper), picks)))
    # Other versions: each one switches some of the words to another of their options, and
    # words with near-synonyms to the next one (sick: 患病, then 不适, 恶心 ...)
    found, tried = [translation], [picks]
    for attempt in range(versions * 3):
        if len(found) >= versions:
            break
        variant = {w: o[(attempt + 1) % len(o)] if w in rules.chosen_near
                   else random.choice(o[1:]) if len(o) > 1 and random.random() < 0.6 else o[0]
                   for w, o in choices.items()}
        if variant in tried:
            continue
        tried.append(variant)
        sentence = translate_injected(text, forced=variant, proper=proper)
        if sentence not in found:
            found.append(sentence)
    words = [{"english": w, "chosen": picks[w], "options": choices[w]} for w in picks]
    return {"translation": translation, "versions": found, "words": words, "proper": proper,
            "checked": checked, "check_error": check_error}


def adjust(text, chosen, proper=None):
    """Rebuild the stupid sentence from a person's choices.

    chosen is {English word: stupid Chinese, or None to translate that word normally}, as
    picked from the options() words. Words not in it stay normal too.
    """
    forced = {w: zh for w, zh in chosen.items() if zh}
    return translate_injected(text, forced=forced, proper=proper)
