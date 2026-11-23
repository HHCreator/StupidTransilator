"""The memes MemeLearnerBot learned, read from the bot's own files.

MemeLearnerBot (https://github.com/HHCreator/MemeLearnerBot) learns memes from stream chat.
The ones Hao approves in its report go into its memelearner/data/memes.json:

    {"memes": {"野距": {"meaning": "两队打野水平差距大", "english": "jungle gap; ...",
                        "examples": [...], "variants": ["打野差距"], ...}, ...},
     "rejected": {...}}

and its players' nicknames into memelearner/data/nicknames.txt (Chovy = 超威, 大超). The
translator only reads these two files, never changes them, and takes them from the first of
these places that has them:

    1. the bot's folder on this computer: the one chosen in the ⚙ window, else the one in
       SBTRANSLATOR_BOT_FOLDER, else a MemeLearnerBot folder next to the translator's own
       when it runs from the source (G:\\SBtranslator -> G:\\MemeLearnerBot)
    2. a copy of the bot's files on GitHub (the repository is public), downloaded in the
       background at most every FETCH_HOURS hours into the settings folder
       (%LOCALAPPDATA%\\SBtranslator\\bot)
    3. the copy the exe comes with (data/bot/, written when the exe is built)

A file is read again when it changes, like settings.refresh(): a meme Hao adds in the bot's
report is used from the next sentence on, without restarting. A meme he turns down or
forgets is gone from memes.json, so the translator stops using it too.

How many memes a stupid sentence gets is the 玩梗程度: none, some (one a sentence, the
default) or max (one a clause, three at most). It is set in the ⚙ window, with
--memes none|some|max on the command line, or translate(text, memes="some") in Python.

    py -m sbtranslator.bot_memes      # where the memes come from, and how many there are
"""

import json
import os
import re
import sys
import threading
import time
import urllib.request

from . import settings

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_ROOT = os.path.dirname(HERE)  # G:\SBtranslator, when running from the source
BOT_FOLDER_NAMES = ("MemeLearnerBot", "memelearnerbot")  # what the bot's folder is called
MEMES_FILE = ("memelearner", "data", "memes.json")  # the bot's files, inside its folder
NICKNAMES_FILE = ("memelearner", "data", "nicknames.txt")
BUNDLED = os.path.join(HERE, "data", "bot")  # the copy the exe comes with
GITHUB = "https://raw.githubusercontent.com/HHCreator/MemeLearnerBot/main/"
FETCH_HOURS = 6  # how old the GitHub copy may get before it is downloaded again
RETRY_MINUTES = 10  # after a download failed, wait this long before trying again
FETCH_TIMEOUT = 15  # seconds

# Where the memes came from, as the ⚙ window and the test report say it
LOCAL, GITHUB_COPY, BUNDLED_COPY = "本机机器人的文件夹", "GitHub 上的", "exe 自带的"

LEVELS = settings.MEME_LEVELS
LEVEL_NAMES = {"none": "不用", "some": "适量", "max": "尽量多"}

_read_cache = {}  # {path: (modification time, what was read)}
_fetch_lock = threading.Lock()
_fetching = False
_last_try = 0.0  # when the last download from GitHub started (time.time())


def level_of(value=None):
    """A 玩梗程度 as one of LEVELS ("none", "some", "max"); 不用, 适量 and 尽量多 work too.
    None means the one set in the ⚙ window. Raises ValueError for anything else."""
    if value is None:
        return settings.meme_level()
    found = str(value).strip().lower()
    found = {name: level for level, name in LEVEL_NAMES.items()}.get(found, found)
    if found not in LEVELS:
        raise ValueError(f"Unknown 玩梗程度 {value!r}, expected one of {', '.join(LEVELS)}")
    return found


# -- where the files are ----------------------------------------------------------------------

def _has_memes(folder):
    return bool(folder) and os.path.isfile(os.path.join(folder, *MEMES_FILE))


def bot_folder():
    """The bot's folder on this computer, or None (see the top of this file). The exe has no
    folder of its own to look next to, so there it must be chosen in the ⚙ window."""
    for chosen in (settings.bot_folder(), os.environ.get("SBTRANSLATOR_BOT_FOLDER")):
        if chosen:
            return chosen if _has_memes(chosen) else None
    if getattr(sys, "frozen", False):
        return None
    parent = os.path.dirname(SOURCE_ROOT)
    return next((os.path.join(parent, name) for name in BOT_FOLDER_NAMES
                 if _has_memes(os.path.join(parent, name))), None)


def github_folder():
    """Where the copy from GitHub is kept: a "bot" folder next to the settings file."""
    return os.path.join(os.path.dirname(os.path.abspath(settings.settings_file())), "bot")


def files():
    """(where from, memes.json, nicknames.txt) of the first place that has the bot's memes
    (see the top of this file), or (None, None, None). Without the bot's folder, this also
    starts a download from GitHub when the copy there is missing or old."""
    folder = bot_folder()
    if folder:
        return LOCAL, os.path.join(folder, *MEMES_FILE), os.path.join(folder, *NICKNAMES_FILE)
    _fetch_if_old()
    for label, folder in ((GITHUB_COPY, github_folder()), (BUNDLED_COPY, BUNDLED)):
        memes_file = os.path.join(folder, MEMES_FILE[-1])
        if os.path.isfile(memes_file):
            return label, memes_file, os.path.join(folder, NICKNAMES_FILE[-1])
    return None, None, None


# -- reading them -------------------------------------------------------------------------------

def _read(path, parse):
    """parse(the text of path), read again only when the file changed; None without a file.
    A file that can't be read or parsed (the bot may be writing it right now) keeps what
    was read before."""
    try:
        version = os.stat(path).st_mtime_ns
    except (OSError, TypeError):
        return None
    cached = _read_cache.get(path)
    if cached and cached[0] == version:
        return cached[1]
    try:
        with open(path, encoding="utf-8-sig") as f:
            found = parse(f.read())
    except (OSError, ValueError, AttributeError, TypeError):
        found = cached[1] if cached else None
    _read_cache[path] = (version, found)
    return found


def _texts(value, limit=None):
    """The non-empty strings in a list from memes.json (a broken entry gives [])."""
    found = [v.strip() for v in value if isinstance(v, str) and v.strip()] \
        if isinstance(value, list) else []
    return found[:limit] if limit else found


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def parse_memes(text):
    """The memes in the text of a memes.json: {phrase: {"meaning", "english", "variants",
    "examples", "notes", "games"}}, every part there even when the file left it out."""
    data = json.loads(text)
    found = {}
    for phrase, meme in (data.get("memes") or {}).items():
        if not isinstance(meme, dict) or not isinstance(phrase, str) or not phrase.strip():
            continue
        found[phrase.strip()] = {
            "meaning": _text(meme.get("meaning")),
            "english": _text(meme.get("english")),
            "variants": [v for v in _texts(meme.get("variants")) if v != phrase.strip()],
            "examples": _texts(meme.get("examples"), 5),
            "notes": _texts(meme.get("notes")),
            "games": _texts(meme.get("games")),
        }
    return found


def squeezed(name):
    """A name as the bot compares names: lowercase, repeated letters as one (chooovy ->
    chovy), full-width letters as normal ones."""
    name = settings.clean_english(name.translate(
        {code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)}))
    return re.sub(r"(.)\1+", r"\1", name)


def parse_nicknames(text):
    """The bot's nickname table: {player as written (Chovy): [his nicknames]}. One player a
    line, "Chovy = 超威, 大超"; a player may have several lines; # starts a note."""
    found = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        player, equals, names = line.partition("=")
        player = player.strip()
        if not equals or not player:
            continue
        nicknames = found.setdefault(player, [])
        for name in re.split(r"[,，、\s]+", names):
            if name and name not in nicknames and squeezed(name) != squeezed(player):
                nicknames.append(name)
    return found


def memes():
    """The bot's memes, {phrase: meme} (see parse_memes()), or {} when none can be found."""
    return _read(files()[1], parse_memes) or {}


def nicknames():
    """The bot's nickname table, {player: [nicknames]} (see parse_nicknames())."""
    return _read(files()[2], parse_nicknames) or {}


def source():
    """Where the memes come from, to show: "本机机器人的文件夹 G:\\MemeLearnerBot", "GitHub
    上的", "exe 自带的", or None when there are none."""
    label = files()[0]
    if label == LOCAL:
        return f"{label} {bot_folder()}"
    return label


# -- the copy from GitHub -----------------------------------------------------------------------

def _download(url, timeout=FETCH_TIMEOUT):
    """The bytes at url. Tests replace this."""
    request = urllib.request.Request(url, headers={"User-Agent": "SBtranslator"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch():
    """Download the bot's files from GitHub into github_folder() now. Raises OSError (or
    ValueError for a memes.json that isn't one) when it fails; then nothing is replaced."""
    folder = github_folder()
    downloaded = {}
    for path in (MEMES_FILE, NICKNAMES_FILE):
        downloaded[path[-1]] = _download(GITHUB + "/".join(path))
    parse_memes(downloaded[MEMES_FILE[-1]].decode("utf-8"))  # a broken download isn't kept
    os.makedirs(folder, exist_ok=True)
    for name, data in downloaded.items():
        temporary = os.path.join(folder, name + ".tmp")
        with open(temporary, "wb") as f:
            f.write(data)
        os.replace(temporary, os.path.join(folder, name))  # all at once, never half a file


def _fetch_in_background():
    global _fetching
    try:
        fetch()
    except (OSError, ValueError):
        pass  # no internet or GitHub is down: the old copy (or the exe's) is used meanwhile
    finally:
        _fetching = False


def _fetch_if_old():
    """Start downloading the GitHub copy in the background when it is missing or older than
    FETCH_HOURS, at most once every RETRY_MINUTES."""
    global _fetching, _last_try
    try:
        age = time.time() - os.stat(os.path.join(github_folder(), MEMES_FILE[-1])).st_mtime
    except OSError:
        age = None
    if age is not None and age < FETCH_HOURS * 3600:
        return
    with _fetch_lock:
        if _fetching or time.time() - _last_try < RETRY_MINUTES * 60:
            return
        _fetching, _last_try = True, time.time()
    threading.Thread(target=_fetch_in_background, daemon=True).start()


def main():
    """Say where the memes come from and how many there are."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    found = memes()
    level = level_of()
    print(f"玩梗程度：{LEVEL_NAMES[level]} ({level})")
    if not found:
        print("没找到机器人的梗：没有机器人的文件夹，GitHub 上的也还没下载下来。")
        return
    print(f"{len(found)} 个梗，来自{source()}；外号表里 {len(nicknames())} 个选手")


if __name__ == "__main__":
    main()
