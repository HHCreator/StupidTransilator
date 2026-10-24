# StupidTransilator
This translator mean to generate stupid translation from English to Chinese for meme purpose

## Usage

Needs Python 3 and an internet connection (it calls Google Translate, and Bing Translator for Classical Chinese). No extra packages.

```
py translator.py "Hello world"            # stupid: word by word, wrong-but-real meanings
py translator.py --rarity 1.5 "Hello"     # same, rarer on average (0 = natural, 3 = obscure, default 0.8)
py translator.py --plain "Hello world"    # word by word, usual meanings
py translator.py --proper "Hello world"   # normal whole-sentence translation
py translator.py --classical "Hello"      # correct Classical Chinese (文言文) in traditional characters, via Bing
py translator.py                          # interactive mode, blank line to quit
```

In both word-by-word modes, a past tense form that is also a word on its own uses that
word's meaning: "saw" becomes 锯 (the tool), "left" becomes 左, "rose" becomes 玫瑰.
The list of these forms is `IRREGULAR_PAST_FORMS` in `sbtranslator/translator.py`.

Compound words are split into the common words they are made of and each part is
translated on its own: "butterfly" becomes butter + fly, "pineapple" becomes pine + apple,
"carpet" becomes car + pet. Parts come from `sbtranslator/data/words/common_english.txt` and must also
be in Google's dictionary.

In the default stupid mode the rarity is spread unevenly: each run, some words keep the
meaning that fits the sentence so it still reads fluently, while others get far-off
meanings. The average rarity over the sentence matches `TARGET_RARITY` (or `--rarity`).
Rarity is -log10 of how often Google says a meaning is used: 0 = natural, 1 = 10%,
2 = 1%, 3 = 0.1%. Results change from run to run.

Single characters that can't stand alone as a word, like 次 (a measure word), are swapped
for their standalone word, so "time" can come out as 次数. The table is `STANDALONE_FORMS`
in `sbtranslator/translator.py`, and `EXTRA_MEANINGS` adds meanings Google's dictionary leaves out.

For the 3,000 most common English words, the stupid mode also finds extra meanings with a
round trip: English -> Chinese -> English -> Chinese, keeping Chinese words whose default
English translation is the original word ("list" -> 单子, "life" -> 辈子). The first time
a word is seen this takes about 10 requests; results are cached in `sbtranslator/.cache/round_trip.json`.

## Overlay window (standalone exe)

**Download: [SBtranslator.exe](https://github.com/HHCreator/StupidTransilator/raw/standalone/dist/SBtranslator.exe)** (Windows, no install, no Python needed). Windows may warn about an unknown publisher because the exe is not code signed; choose More info > Run anyway.

A small always-on-top window to translate while you are in another app or a game:
type an English sentence, press Enter, and the Chinese shows below. Pick the mode with the
buttons at the top (Stupid, Plain, Proper, 文言文); in Stupid mode a slider sets the rarity.

```
py overlay.py                 # run it from source, no extra packages
py -m pip install pyinstaller
py build_exe.py               # builds dist/SBtranslator.exe
```

`dist/SBtranslator.exe` is a single file with Python and the data inside, so it runs on a PC
without Python (it still needs an internet connection). Controls:

- Enter translates, Shift+Enter adds a new line, Copy puts the result on the clipboard
- Drag the title bar to move it, ✕ to quit
- Ctrl+Alt+T hides and shows it from any app (if another app already uses that key, the hint
  in the title bar disappears and the hotkey is off)

It stays above normal windows, but a game in exclusive fullscreen can hide it (use windowed
or borderless mode). The exe keeps the round trip cache in `%LOCALAPPDATA%\SBtranslator`.
Without building, `pip install` also adds a `sbtranslator-overlay` command.

## Learning memes

The stupid modes replace memes and names with their Chinese names: "lol" -> 英雄联盟,
"frozen" -> 冰雪奇缘, "teses" -> 滔搏们 (plural of TES).
These are learned from Wikipedia: for each page it takes the Chinese title and the English
short names (one-word title, initials like LoL, 简称 abbreviations like TES, surnames).
When the Chinese article gives a famous nickname or title, that wins over the name:
Sarah Kerrigan calls herself the Queen of Blades, so "kerrigan" -> 刀锋女王.

Unique words that aren't English words, like player names, are read as a typo of the most
similar famous name, the way Google guesses what a typo meant: "karrigan" is one letter away
from "kerrigan", so it also becomes 刀锋女王. A word may be 1 typo away from the name, or 2
when it has 7 letters or more (`NEAR_NAME_MIN_LETTERS` and `NEAR_NAME_LONG` in
`sbtranslator/translator.py`).

```
py learn.py                                   # learn the pages listed in sbtranslator/data/meme_seeds.txt
py learn.py "Top Esports" "Sarah Kerrigan"    # learn specific pages
py learn.py --links 50 "League of Legends"    # also learn up to 50 pages each one links to
```

Learned entries go to `sbtranslator/data/memes_learned.json`. Put your own in `sbtranslator/data/memes.json`; they win.

## Learning memes from live stream chat

Meme culture lives in stream chat more than on Wikipedia, so the translator can also learn
from a live Douyu room or Twitch channel. It only reads the chat (anonymously, nothing is
ever sent), keeps the messages in `sbtranslator/.cache/chat/` (with user names replaced by a
short hash), and learns from everything recorded so far:

```
py listen.py douyu 6657                 # listen to Douyu room 6657 for 10 minutes, then learn
py listen.py twitch xqc --minutes 30    # listen to twitch.tv/xqc for 30 minutes
py listen.py douyu 6657 --minutes 0     # learn again from what was already recorded
```

Something counts as a meme when at least 3 different people type it (`--people N` changes
that): a short danmu like 恶龙呢, or a word in English chat that isn't an English word, like
LULW. Chinese memes are translated to English, and the last real word of that English gets
the meme as a possible stupid meaning: 恶龙呢 is "Where's the dragon?", so "dragon" can come
out as 恶龙呢 (`sbtranslator/data/chat_meanings.json`). English memes that Google can
translate become memes like the Wikipedia ones: LULW -> 卢尔夫
(`sbtranslator/data/memes_chat.json`). The rest are printed so you can add them to
`memes.json` yourself. The room has to be live while you listen.

Other stupid-mode rules: contractions are expanded first (can't -> can not), "the" is dropped
(Chinese has no articles), compound parts keep their natural meaning (firepower -> 火 + 力量),
and words of 4 letters or fewer are never split (into stays 进入).

## Using it in other apps (add-on)

Install it as a Python package (no extra dependencies):

```
pip install git+https://github.com/HHCreator/StupidTransilator
```

From Python:

```python
import sbtranslator

sbtranslator.translate("The butterfly is eating a pineapple.")        # stupid (default)
sbtranslator.translate("Hello world", mode="plain")                    # word by word
sbtranslator.translate("Hello world", mode="proper")                   # correct
sbtranslator.translate("Long time no see", mode="classical")           # 文言文
sbtranslator.translate("Long time no see", rarity=1.5)                 # stupider
```

From any other language (a bot, a browser extension, a game mod), run the local HTTP API:

```
sbtranslator-server                      # or: python -m sbtranslator.server --port 8765
```

```
GET  http://127.0.0.1:8765/translate?text=Hello%20world&mode=stupid
POST http://127.0.0.1:8765/translate   {"text": "Hello world", "mode": "stupid", "rarity": 0.8}
GET  http://127.0.0.1:8765/modes
```

Responses are JSON: `{"text": ..., "mode": ..., "translation": ...}`, or `{"error": ...}` with
status 400 for bad input and 502 when the online translator can't be reached. The API allows
cross-origin requests so browser extensions and web pages can call it.

Installing also adds the commands `sbtranslator` (same as `py translator.py`) and
`sbtranslator-learn` (same as `py learn.py`).
