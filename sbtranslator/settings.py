"""Your own settings: word table entries and the rarity, changed in the overlay's ⚙ window.

The word tables the program comes with are files in data/ (stupid_words.json, memes.json,
phrases.json, nicknames.json and the learned meme files). What you add, change or delete in
the ⚙ window goes into a file of your own instead, outside the program folder, so a new
download of the exe keeps it:

    %LOCALAPPDATA%\\SBtranslator\\settings.json    on Windows, for the exe and the source alike
    ~/.config/sbtranslator/settings.json          on other systems
    SBTRANSLATOR_SETTINGS=<file>                  to use another file

It looks like this (every part is optional):

    {"rarity": 1.2,
     "words": {"memes": {"g2": "鸡兔"}, "everyday": {"sick": "病态"}},
     "removed": {"everyday": ["good"]}}

"words" holds your entries, {English: Chinese}, and they win over the built-in ones;
"removed" lists the built-in entries you deleted. The code that uses a table passes its
built-in entries through merged() (translator._load_memes(), inject.tables(),
inject.phrases(), phrases.nicknames()), and every change here makes it read the tables
again, so a change is used from the next translation on, without restarting. A change
another program made to the file (the overlay, while the HTTP server runs) is picked up
the same way: sbtranslator.translate() first checks whether the file changed (refresh()).

export_file() writes your settings to a file to keep or to give to a friend; import_file()
adds such a file to yours (an old data/*.json table works too).
"""

import json
import os
import re
import time

from .translator import LETTERS, MAX_RARITY, TARGET_RARITY

# The tables you can change. Each one is {English: Chinese}:
#   memes      always replace the word, in every stupid mode         frozen -> 冰雪奇缘
#   everyday   the everyday meaning of a word, used when the sentence  major -> 主要
#              means something else (the stupid and 中文 modes)
#   acronyms   expanded to English, then translated word by word     hltv -> half life tv
#   phrases    several words replaced together                       zywoo play -> 载物玩耍
#   nicknames  a player's Chinese nickname                           zywoo -> 载物
TABLES = ("memes", "everyday", "acronyms", "phrases", "nicknames")

# Where each table's built-in entries come from, for rows(): (file in data/, the part of the
# file or None for all of it, label). Later files win, as in the code that reads them: in
# the stupid mode the names in stupid_words.json are looked up before the memes.
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
BUILT_IN, LEARNED, MINE, CHANGED = "内置", "学到的", "我加的", "我改的"
BUILT_IN_FILES = {
    "memes": [("memes_learned.json", None, LEARNED), ("memes_chat.json", None, LEARNED),
              ("memes.json", None, BUILT_IN), ("stupid_words.json", "names", BUILT_IN)],
    "everyday": [("stupid_words.json", "everyday", BUILT_IN)],
    "acronyms": [("stupid_words.json", "acronyms", BUILT_IN)],
    "phrases": [("phrases.json", None, BUILT_IN)],
    "nicknames": [("nicknames.json", None, BUILT_IN)],  # {nickname: player}, turned around
}

# The note at the top of an exported file, for people who open it
EXPORT_NOTE = ("SBtranslator settings. Import them in the overlay: ⚙ > 导入设置. words: your "
               "own entries {English: Chinese} per table (memes, everyday, acronyms, phrases, "
               "nicknames); removed: built-in entries you deleted; rarity: for the 逐词 mode.")

CHINESE = re.compile(r"[一-鿿]")
WORD = re.compile(f"[{LETTERS}0-9][{LETTERS}0-9']*")  # a word as the translator splits text

_data = None  # the settings file's content once loaded, see _load()
_unreadable = False  # the file exists but isn't valid JSON: keep a copy before replacing it
_loaded_version = None  # the file's modification time when it was read, see refresh()


def settings_file():
    """Where your settings are saved (see the top of this file)."""
    custom = os.environ.get("SBTRANSLATOR_SETTINGS")
    if custom:
        return custom
    if os.name == "nt":
        home = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(home, "SBtranslator", "settings.json")
    home = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(home, "sbtranslator", "settings.json")


# -- reading and saving the file ----------------------------------------------------------

def _clean(data):
    """The parts of a loaded settings file that make sense, in the shape the code expects:
    {"rarity": float or None, "words": {table: {English: Chinese}}, "removed": {table:
    [English, ...]}, "state": {...}}. Anything else is dropped."""
    rarity = data.get("rarity")
    words, removed = {}, {}
    for table in TABLES:
        found = (data.get("words") or {}).get(table)
        if isinstance(found, dict):
            words[table] = {clean_english(k): v.strip() for k, v in found.items()
                            if isinstance(k, str) and isinstance(v, str) and v.strip()}
        gone = (data.get("removed") or {}).get(table)
        if isinstance(gone, list):
            removed[table] = sorted({clean_english(k) for k in gone if isinstance(k, str)})
    state = data.get("state")
    return {"rarity": _rarity_value(rarity) if _is_number(rarity) else None,
            "words": words, "removed": removed,
            "state": state if isinstance(state, dict) else {}}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _rarity_value(value):
    """A rarity kept between 0 and MAX_RARITY, to one decimal like the slider."""
    return round(min(max(float(value), 0.0), MAX_RARITY), 1)


def _version():
    """When the settings file was last changed (None if there is no file)."""
    try:
        return os.stat(settings_file()).st_mtime_ns
    except OSError:
        return None


def _load():
    """The settings, read from the file the first time (an empty set if there is none)."""
    global _data, _unreadable, _loaded_version
    if _data is None:
        path = settings_file()
        _loaded_version = _version()
        try:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
            _unreadable = False
        except FileNotFoundError:
            data, _unreadable = {}, False
        except (OSError, ValueError):
            # Broken, maybe by hand: run without it, and keep a copy when saving (_store)
            data, _unreadable = {}, True
        _data = _clean(data)
    return _data


def _copy():
    """A copy of the settings to change: they are only replaced as a whole (_store), so a
    translation running in another thread never sees half a change."""
    return json.loads(json.dumps(_load(), ensure_ascii=False))


def _store(data):
    """Save data as the settings file and use it from now on. Raises OSError when the file
    can't be written (then nothing changes)."""
    global _data, _unreadable, _loaded_version
    path = settings_file()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if _unreadable and os.path.exists(path):
        os.replace(path, path + ".broken")  # the file we couldn't read, kept for its owner
        _unreadable = False
    content = {"rarity": data["rarity"],
               "words": {table: dict(sorted(found.items()))
                         for table, found in data["words"].items() if found},
               "removed": {table: gone for table, gone in data["removed"].items() if gone},
               "state": data["state"]}
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in content.items() if v not in (None, {})}, f,
                  ensure_ascii=False, indent=1)
    for attempt in range(5):  # all at once, so a crash never leaves half a file
        try:
            os.replace(temporary, path)
            break
        except PermissionError:  # Windows: another program is reading it right now
            if attempt == 4:
                raise
            time.sleep(0.05)
    _data, _loaded_version = data, _version()
    _changed()


def _changed():
    """Make the code that keeps a table in memory read it again (it goes through merged())."""
    from . import inject, translator
    inject._tables = inject._phrases = None
    translator._memes = translator._known_names = None
    translator._languages = {}  # its guesses count meme names as English words


def reload():
    """Read the settings file again."""
    global _data
    _data = None
    _changed()


def refresh():
    """Read the settings file again if it changed since it was read: by another program
    (the overlay while the HTTP server runs) or by hand. sbtranslator.translate() calls
    this first; it only costs a look at the file's date."""
    if _data is not None and _version() != _loaded_version:
        reload()


# -- what the rest of the code asks -------------------------------------------------------

def rarity():
    """The rarity for the 逐词 (wordy) mode: yours, or TARGET_RARITY."""
    value = _load()["rarity"]
    return TARGET_RARITY if value is None else value


def set_rarity(value):
    """Save a new rarity (0 to MAX_RARITY); returns it as saved. The default rarity isn't
    written down, so after 恢复默认 a future version's default is used."""
    value = _rarity_value(value)
    if rarity() != value:
        data = _copy()
        data["rarity"] = value
        _store(data)
    return value


def words(table):
    """Your own entries in a table: {English: Chinese}."""
    return dict(_load()["words"].get(table, {}))


def removed(table):
    """The built-in entries of a table you deleted: a set of English words."""
    return set(_load()["removed"].get(table, ()))


def merged(table, built_in):
    """A table as the translator uses it: built_in ({English: Chinese}, the entries it
    comes with) without the ones you deleted, plus yours, which win."""
    gone = removed(table)
    found = {k: v for k, v in built_in.items() if k not in gone}
    found.update(words(table))
    return found


def state(name, default=None):
    """Something the overlay remembers that isn't a setting (asked about the shortcut)."""
    return _load()["state"].get(name, default)


def set_state(name, value):
    data = _copy()
    data["state"][name] = value
    _store(data)


# -- the ⚙ window: showing and changing entries -------------------------------------------

def clean_english(english):
    """The form tables keep English in: lowercase, single spaces (Zywoo  Play -> zywoo play)."""
    return " ".join(english.replace("’", "'").lower().split())


def built_in(table):
    """The entries a table comes with: {English: (Chinese, label)}, label being 内置 (in
    the program's files) or 学到的 (learned from Wikipedia or stream chat)."""
    found = {}
    for name, part, label in BUILT_IN_FILES[table]:
        try:
            with open(os.path.join(DATA, name), encoding="utf-8") as f:
                entries = json.load(f)
        except (OSError, ValueError):
            continue
        if part:
            entries = entries.get(part) or {}
        for english, chinese in entries.items():
            if english.startswith("_") or not isinstance(chinese, str):
                continue  # notes for people, like "_comment"
            if table == "nicknames":
                english, chinese = chinese, english  # the file is {nickname: player}
            found[clean_english(english)] = (chinese, label)
    return found


def rows(table):
    """A table as the translator uses it, A to Z: [(English, Chinese, label)], label being
    内置, 学到的, 我加的 (your own entry) or 我改的 (yours, instead of a built-in one)."""
    original = built_in(table)
    gone = removed(table)
    found = {k: v for k, v in original.items() if k not in gone}
    for english, chinese in words(table).items():
        found[english] = (chinese, CHANGED if english in original else MINE)
    return [(english, chinese, label) for english, (chinese, label) in sorted(found.items())]


def check_entry(table, english, chinese):
    """Why an entry can't go into a table, as a sentence to show, or None when it can.
    english should be cleaned first (clean_english)."""
    if not english:
        return "英文那一格是空的"
    if not chinese:
        return "右边那一格是空的"
    parts = english.split()
    if not all(WORD.fullmatch(part) for part in parts):
        return "英文只能有字母、数字和 '，几个词用空格隔开"
    if table == "phrases" and len(parts) < 2:
        return "短语至少要两个词；一个词的放到「梗和名字」或「日常意思」"
    if table != "phrases" and len(parts) > 1:
        return "这里只能放一个词；几个词一起换的放到「短语」"
    if table == "acronyms" and not re.fullmatch(r"[A-Za-z' ]+", chinese):
        return "缩写的右边写它展开后的英文，比如 hltv → half life tv"
    if table == "nicknames" and not CHINESE.search(chinese):
        return "外号要写中文的，比如 zywoo → 载物"
    return None


def _put(data, table, english, chinese, original=None):
    """Put one entry into data (a _copy()); returns why it can't go in, or None. original
    is built_in(table), when the caller has it already."""
    english, chinese = clean_english(english), " ".join(chinese.split())
    if table == "acronyms":
        chinese = chinese.lower()  # the words it is expanded to
    problem = check_entry(table, english, chinese)
    if problem:
        return problem
    yours = data["words"].setdefault(table, {})
    original = (built_in(table) if original is None else original).get(english)
    if original and original[0] == chinese:
        yours.pop(english, None)  # the same as the built-in entry: nothing of yours to keep
    else:
        yours[english] = chinese
    gone = data["removed"].get(table, [])
    if english in gone:
        gone.remove(english)
    return None


def set_entry(table, english, chinese):
    """Add or change an entry; returns its English as saved. Raises ValueError (with a
    sentence to show) when it can't go into the table, OSError when it can't be saved."""
    data = _copy()
    problem = _put(data, table, english, chinese)
    if problem:
        raise ValueError(problem)
    _store(data)
    return clean_english(english)


def delete_entry(table, english):
    """Delete an entry: yours is removed, and a built-in one is listed as removed (so it is
    gone too, also when you had changed it; restore_entry() brings a built-in one back)."""
    english = clean_english(english)
    data = _copy()
    data["words"].get(table, {}).pop(english, None)
    if english in built_in(table):
        gone = data["removed"].setdefault(table, [])
        if english not in gone:
            gone.append(english)
            gone.sort()
    _store(data)


def restore_entry(table, english):
    """Undo your change to a built-in entry (or your deletion of it): it is used again."""
    english = clean_english(english)
    data = _copy()
    data["words"].get(table, {}).pop(english, None)
    gone = data["removed"].get(table, [])
    if english in gone:
        gone.remove(english)
    _store(data)


def reset():
    """Back to the built-in tables and the default rarity (what the overlay remembers stays)."""
    data = _copy()
    data.update(rarity=None, words={}, removed={})
    _store(data)


# -- import and export ----------------------------------------------------------------------

def export_file(path):
    """Write your settings (not what the overlay remembers) to path, to keep or share.
    A rarity you never changed isn't written, so importing keeps the other side's."""
    data = _load()
    content = {"_comment": EXPORT_NOTE, "app": "SBtranslator", "version": 1,
               "words": {table: dict(sorted(found.items()))
                         for table, found in data["words"].items() if found},
               "removed": {table: gone for table, gone in data["removed"].items() if gone}}
    if data["rarity"] is not None:
        content["rarity"] = data["rarity"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=1)


def _read_import(content):
    """What a file to import holds: ([(table, English, Chinese)], [(table, English)],
    rarity or None). It can be a file from export_file(), or one of the old tables people
    used to edit by hand: data/stupid_words.json, or a flat {English: Chinese} file like
    data/memes.json (entries with spaces are phrases) or data/nicknames.json ({中文: player})."""
    entries, removals = [], []
    if isinstance(content.get("words"), dict) or _is_number(content.get("rarity")):
        for table, found in (content.get("words") or {}).items():
            if table in TABLES and isinstance(found, dict):
                entries += [(table, k, v) for k, v in found.items() if isinstance(v, str)]
        for table, gone in (content.get("removed") or {}).items():
            if table in TABLES and isinstance(gone, list):
                removals += [(table, k) for k in gone if isinstance(k, str)]
        rarity_found = content.get("rarity")
        return entries, removals, rarity_found if _is_number(rarity_found) else None
    parts = {"names": "memes", "everyday": "everyday", "acronyms": "acronyms"}
    if any(isinstance(content.get(part), dict) for part in parts):
        for part, table in parts.items():  # an old data/stupid_words.json
            found = content.get(part)
            if isinstance(found, dict):
                entries += [(table, k, v) for k, v in found.items()
                            if not k.startswith("_") and isinstance(v, str)]
        return entries, removals, None
    for english, chinese in content.items():  # an old flat table
        if english.startswith("_") or not isinstance(chinese, str):
            continue
        if CHINESE.search(english) and not CHINESE.search(chinese):
            entries.append(("nicknames", chinese, english))  # data/nicknames.json
        elif len(english.split()) > 1:
            entries.append(("phrases", english, chinese))
        else:
            entries.append(("memes", english, chinese))
    return entries, removals, None


def import_file(path):
    """Add the settings in path to yours (its entries win when both have a word). Returns
    {"words": entries taken, "removed": built-in entries it deletes, "rarity": its rarity or
    None, "skipped": entries that didn't fit a table}. Raises ValueError for a file that
    isn't JSON or holds no settings, OSError when it can't be read or saved."""
    with open(path, encoding="utf-8-sig") as f:  # -sig: Notepad may start the file with a BOM
        content = json.load(f)
    if not isinstance(content, dict):
        raise ValueError("这不是设置文件：里面应该是一个 {…}")
    entries, removals, new_rarity = _read_import(content)
    if not (entries or removals or new_rarity is not None):
        raise ValueError("文件里没有能导入的词条或稀有度")
    data = _copy()
    original = {table: built_in(table) for table in TABLES}
    taken = skipped = 0
    for table, english, chinese in entries:
        if _put(data, table, english, chinese, original[table]):
            skipped += 1
        else:
            taken += 1
    deleted = 0
    for table, english in removals:
        english = clean_english(english)
        if english in original[table] and english not in data["words"].get(table, {}):
            gone = data["removed"].setdefault(table, [])
            if english not in gone:
                gone.append(english)
                deleted += 1
    for gone in data["removed"].values():
        gone.sort()
    if new_rarity is not None:
        data["rarity"] = _rarity_value(new_rarity)
    _store(data)
    return {"words": taken, "removed": deleted, "skipped": skipped,
            "rarity": data["rarity"] if new_rarity is not None else None}
