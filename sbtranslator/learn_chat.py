"""Learn memes from live stream chat (Douyu, Twitch), where meme culture actually lives.

    py listen.py douyu 6657                 # listen to Douyu room 6657 for 10 minutes, then learn
    py listen.py twitch xqc --minutes 30    # same for twitch.tv/xqc
    py listen.py douyu 6657 --minutes 0     # learn again from what was already recorded

How it works:

    1. Record     chat.py reads the chat; every message is appended to a log in the cache
                  folder as "user hash<TAB>text" (the real user name or id is never saved)
    2. Find memes A meme is something many different people type: the same short danmu
                  sent by at least MIN_PEOPLE people (典, 绷不住了, 666), or, in English chat,
                  a word that isn't an English word typed by at least MIN_PEOPLE (KEKW, Pog)
    3. Translate  Chinese memes go Chinese -> English with Google. When that gives a short
                  English phrase, its last ordinary word gets the meme as a possible stupid
                  meaning (恶龙呢 -> "Where's the dragon?" -> dragon -> 恶龙呢, 香 ->
                  "fragrant" -> fragrant -> 香): data/chat_meanings.json
                  English memes go English -> Chinese. When Google knows them, they become
                  memes like the Wikipedia ones: data/memes_chat.json. The ones Google
                  doesn't know are listed so you can add them to data/memes.json yourself.

Logs from earlier runs are used again every time, so the more you listen, the more it knows.
"""

import collections
import hashlib
import json
import os
import re
import sys

from . import chat
from .translator import CACHE_FILE, WORDS_FILE, _get_json

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(os.path.dirname(CACHE_FILE), "chat")  # raw chat, never committed
MEANINGS_FILE = os.path.join(HERE, "data", "chat_meanings.json")
MEMES_FILE = os.path.join(HERE, "data", "memes_chat.json")

MIN_PEOPLE = 3  # how many different people must type something before it counts as a meme
MAX_DANMU_LENGTH = 8  # longer danmu are sentences, not memes
MAX_WORD_LENGTH = 15  # longer "words" in English chat are pasted junk, not memes
MAX_PHRASE_WORDS = 3  # a Chinese meme whose English is longer is a sentence: skip it
# Words that say nothing on their own, so they never get a meme meaning
STOPWORDS = set("a an the is are am was be been it its i you he she we they me my your his "
                "her our their of to in on at for and or but so too very not no yes this that "
                "what where who how why there here do does did".split())
CJK = re.compile(r"[一-鿿]")


# -- 1. recording -------------------------------------------------------------------------

def log_path(source, room):
    return os.path.join(LOG_DIR, f"{source}-{room}.tsv")


def record(source, room, minutes):
    """Listen to the chat for some minutes and append every message to its log file."""
    os.makedirs(LOG_DIR, exist_ok=True)
    count = 0
    with open(log_path(source, room), "a", encoding="utf-8") as log:
        for user, text in chat.messages(source, room, minutes * 60):
            # Only a short hash of the user is kept, enough to count different people
            who = hashlib.sha1(f"{source}:{user}".encode()).hexdigest()[:10]
            log.write(f"{who}\t{' '.join(text.split())}\n")
            count += 1
            if count % 100 == 0:
                print(f"  {count} messages so far...")
    return count


def read_logs(source=None):
    """Yield (user hash, text, source) from every log, or only from one source's logs."""
    if not os.path.isdir(LOG_DIR):
        return
    for name in sorted(os.listdir(LOG_DIR)):
        log_source = name.split("-", 1)[0]
        if source and log_source != source:
            continue
        with open(os.path.join(LOG_DIR, name), encoding="utf-8") as f:
            for line in f:
                if "\t" in line:
                    who, text = line.rstrip("\n").split("\t", 1)
                    yield who, text, log_source


# -- 2. finding memes ---------------------------------------------------------------------

def normalize_danmu(text):
    """哈哈哈哈哈哈 -> 哈哈哈, and drop spaces, so spam variations count as the same danmu."""
    text = "".join(text.split())
    return re.sub(r"(.)\1{3,}", r"\1\1\1", text)


def find_memes(min_people=MIN_PEOPLE):
    """Return (chinese, english): {meme: number of different people who typed it}."""
    with open(WORDS_FILE, encoding="utf-8") as f:
        english_words = {line.strip().lower() for line in f if line.strip()}
    chinese, english = collections.defaultdict(set), collections.defaultdict(set)
    for who, text, _ in read_logs():
        danmu = normalize_danmu(text)
        # Chinese: the whole short message is the meme (danmu spam: 典, 绷不住了, 666)
        if 0 < len(danmu) <= MAX_DANMU_LENGTH and (CJK.search(danmu) or danmu.isdigit()):
            chinese[danmu].add(who)
        # English: single words that aren't English words (KEKW, Pog, copium)
        text = re.sub(r"@\w+", " ", text)  # @mentions are user names, not memes
        for word in set(re.findall(r"[A-Za-z][A-Za-z0-9']+", text)):
            if word.lower() not in english_words and len(word) <= MAX_WORD_LENGTH:
                english[word.lower()].add(who)
    keep = lambda found: {m: len(p) for m, p in found.items() if len(p) >= min_people}
    return keep(chinese), keep(english)


# -- 3. translating -----------------------------------------------------------------------

def _translate_many(texts, source, target):
    """Translate a list of short texts with Google, 50 at a time; returns one per text."""
    results = []
    for i in range(0, len(texts), 50):
        batch = texts[i:i + 50]
        params = [("client", "dict-chrome-ex"), ("sl", source), ("tl", target)]
        params += [("q", t) for t in batch]
        data = _get_json("https://clients5.google.com/translate_a/t", params, 10)
        results += [d[0] if isinstance(d, list) else d for d in data]
    return results


def learn(chinese, english):
    """Turn the memes found into (meanings, memes, unknown) as described at the top."""
    with open(WORDS_FILE, encoding="utf-8") as f:
        english_words = {line.strip().lower() for line in f if line.strip()}
    meanings = collections.defaultdict(list)
    phrases = sorted(chinese, key=lambda m: -chinese[m])
    for phrase, meaning in zip(phrases, _translate_many(phrases, "zh-CN", "en") if phrases else []):
        words = re.findall(r"[a-z]+(?:'[a-z]+)?", meaning.lower())
        if not 0 < len(words) <= MAX_PHRASE_WORDS:
            continue
        # The last ordinary, meaningful word carries the meme: "Where's the dragon?" -> dragon
        useful = [w for w in words if w in english_words and w not in STOPWORDS]
        if useful:
            meanings[useful[-1]].append(phrase)
    memes, unknown = {}, []
    words = sorted(english, key=lambda m: -english[m])
    for word, chinese_text in zip(words, _translate_many(words, "en", "zh-CN") if words else []):
        if CJK.search(chinese_text) and chinese_text.lower() != word:
            memes[word] = chinese_text
        else:
            unknown.append(word)
    return dict(meanings), memes, unknown


def save(meanings, memes):
    """Write the results; translator.py reads them the next time it starts."""
    with open(MEANINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(meanings.items())), f, ensure_ascii=False, indent=1)
    with open(MEMES_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(memes.items())), f, ensure_ascii=False, indent=1)


# -- command line -------------------------------------------------------------------------

def main():
    """py listen.py douyu|twitch ROOM [--minutes N] [--people N]"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    minutes, people = 10.0, MIN_PEOPLE
    if "--minutes" in args:
        i = args.index("--minutes")
        minutes = float(args[i + 1])
        del args[i:i + 2]
    if "--people" in args:
        i = args.index("--people")
        people = int(args[i + 1])
        del args[i:i + 2]
    if len(args) != 2 or args[0] not in ("douyu", "twitch"):
        sys.exit(__doc__.split("How it works")[0].strip())
    source, room = args

    if minutes > 0:
        print(f"Listening to {source} {room} for {minutes:g} minutes (read only)...")
        try:
            count = record(source, room, minutes)
        except KeyboardInterrupt:
            count = None  # Ctrl+C stops listening early; learn from what was recorded
        print(f"Recorded {'some' if count is None else count} messages.")

    chinese, english = find_memes(people)
    print(f"Found {len(chinese)} Chinese and {len(english)} English memes "
          f"(typed by at least {people} people, in all recorded chat).")
    meanings, memes, unknown = learn(chinese, english)
    save(meanings, memes)

    for word, phrases in sorted(meanings.items()):
        print(f"  {word} -> {' / '.join(phrases)}")
    for word, text in sorted(memes.items()):
        print(f"  {word} -> {text}")
    if unknown:
        print("Google doesn't know these; add the good ones to data/memes.json yourself:")
        print("  " + ", ".join(unknown[:40]))
    print(f"Saved {len(meanings)} stupid meanings and {len(memes)} memes.")


if __name__ == "__main__":
    main()
