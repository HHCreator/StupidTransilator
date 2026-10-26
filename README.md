# StupidTransilator
This translator mean to generate stupid translation from English to Chinese for meme purpose

## Usage

Needs Python 3 and an internet connection (it calls Google Translate, and Bing Translator for Classical Chinese). No extra packages.

```
py translator.py "Hello world"            # stupid: a normal sentence with stupid words injected
py translator.py --wordy "Hello world"    # stupid word by word, wrong-but-real meanings
py translator.py --wordy --rarity 1.5 "Hi"  # same, rarer on average (0 = natural, 3 = obscure, default 0.8)
py translator.py --plain "Hello world"    # word by word, usual meanings
py translator.py --proper "Hello world"   # normal whole-sentence translation
py translator.py --classical "Hello"      # correct Classical Chinese (文言文) in traditional characters, via Bing
py translator.py                          # interactive mode, blank line to quit
```

## The stupid mode: a normal sentence with stupid words in it

Word-by-word translation reads like gibberish. The memes this is made for read like fluent
Chinese that means nothing: only a few words are stupid. So the stupid mode translates the
sentence normally and swaps a few words for stupid Chinese:

```
@frozen: teses, your HLTV top is 0, lol   ->   @冰雪奇缘：滔搏们，你的一半生活电视顶部是0，英雄联盟
```

The stupid words are written into the English inside 【】 ("your 【主要】 champion") and the
whole sentence goes to Google, which builds normal Chinese around them. They come from:

- phrases from stream chat (`sbtranslator/data/phrases.json`): life game -> 生命游戏, zywoo play -> 载物玩耍
- names and memes (the meme files below, and `names` in `sbtranslator/data/stupid_words.json`):
  frozen -> 冰雪奇缘, NaVi -> 导航, lol -> 英雄联盟, wow -> 魔兽世界; plurals: teses -> 滔搏们 or 一些滔搏
- players' Chinese nicknames (`sbtranslator/data/nicknames.json`): zywoo -> 载物, s1mple -> 森破
- acronyms, expanded and then translated word by word (`acronyms`): HLTV -> half life tv -> 一半生活电视
- player handles read as the nearest English word: m0NESY -> money -> 钱, ropz -> rope -> 绳索
- everyday meanings of jargon (`everyday`), only when the sentence means something else:
  major -> 主要, top -> 顶部, clutch -> 离合器
- compound words (butterfly -> 黄油飞) and unique words read as a typo of a famous name
  (karrigan -> 刀锋女王)

Google sometimes rewrites an injected word, usually a verb (clutch, play). With `--check` the
local AI model writes the sentence instead and must use every stupid word word for word; the
program checks and asks again (see below).

The old word-by-word stupid mode is still there as `--wordy`; the rules below are about it.

In the word-by-word modes, a past tense form that is also a word on its own uses that
word's meaning: "saw" becomes 锯 (the tool), "left" becomes 左, "rose" becomes 玫瑰.
The list of these forms is `IRREGULAR_PAST_FORMS` in `sbtranslator/translator.py`.

Compound words are split into the common words they are made of and each part is
translated on its own: "butterfly" becomes butter + fly, "pineapple" becomes pine + apple,
"carpet" becomes car + pet. Parts come from `sbtranslator/data/words/common_english.txt` and must also
be in Google's dictionary.

In the wordy mode the rarity is spread unevenly: each run, some words keep the
meaning that fits the sentence so it still reads fluently, while others get far-off
meanings. The average rarity over the sentence matches `TARGET_RARITY` (or `--rarity`).
Rarity is -log10 of how often Google says a meaning is used: 0 = natural, 1 = 10%,
2 = 1%, 3 = 0.1%. Results change from run to run.

Single characters that can't stand alone as a word, like 次 (a measure word), are swapped
for their standalone word, so "time" can come out as 次数. The table is `STANDALONE_FORMS`
in `sbtranslator/translator.py`, and `EXTRA_MEANINGS` adds meanings Google's dictionary leaves out.

For the 3,000 most common English words, the wordy mode also finds extra meanings with a
round trip: English -> Chinese -> English -> Chinese, keeping Chinese words whose default
English translation is the original word ("list" -> 单子, "life" -> 辈子). The first time
a word is seen this takes about 10 requests; results are cached in `sbtranslator/.cache/round_trip.json`.

## Overlay window (standalone exe)

**Download: [SBtranslator-windows.zip](https://github.com/HHCreator/StupidTransilator/releases/latest/download/SBtranslator-windows.zip)** (Windows, no install, no Python needed). Unzip it and run `SBtranslator.exe` inside the `SBtranslator` folder (keep the `_internal` folder next to it). The exe is not code signed, so Windows may warn about an unknown publisher; choose More info > Run anyway. GitHub builds it from this branch on every change, see the [Build exe workflow](.github/workflows/build-exe.yml).

A small always-on-top window to translate while you are in another app or a game:
type an English sentence, press Enter, and the Chinese shows below. Pick the mode with the
buttons at the top (Stupid, Plain, Proper, 文言文); in Stupid mode a slider sets the rarity.

```
py overlay.py                 # run it from source, no extra packages
py -m pip install pyinstaller
py build_exe.py               # builds dist/SBtranslator-windows.zip
```

The zip holds a folder with `SBtranslator.exe`, Python and the data, so it runs on a PC without
Python (it still needs an internet connection). It is a folder and not a single exe on purpose:
a single-file PyInstaller exe unpacks itself to a temp folder when it starts, and antivirus
programs often flag that as a virus. Controls:

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
py listen.py --review                   # approve the phrase candidates it found
```

**Phrases (used by the stupid mode).** Short danmu that a crowd spams often read as a word-by-word
translation: 生命游戏 is "life game", 载物玩耍 is "ZywOo play" (载物 is ZywOo's nickname),
设备玩耍 is "device play". So short danmu (8 characters or fewer, sent by at least 3 people)
are split into words and each word gets its English: a nickname from
`sbtranslator/data/nicknames.json`, else a player handle among its English meanings (the
players are in `sbtranslator/data/players.txt`), else its most common meaning. That gives
phrase candidates like zywoo play -> 载物玩耍. `py listen.py --review` asks about each one; the
ones you approve go into `sbtranslator/data/phrases.json`, and the stupid mode uses them,
longest first. You can also write phrases and nicknames there yourself.

**Memes (used by the wordy mode).** Something counts as a meme when at least 3 different people type it (`--people N` changes
that): a short danmu like 恶龙呢, or a word in English chat that isn't an English word, like
LULW. Chinese memes are translated to English, and the last real word of that English gets
the meme as a possible stupid meaning: 恶龙呢 is "Where's the dragon?", so "dragon" can come
out as 恶龙呢 (`sbtranslator/data/chat_meanings.json`). English memes that Google can
translate become memes like the Wikipedia ones: LULW -> 卢尔夫
(`sbtranslator/data/memes_chat.json`). The rest are printed so you can add them to
`memes.json` yourself. The room has to be live while you listen.

Other wordy-mode rules: contractions are expanded first (can't -> can not), "the" is dropped
(Chinese has no articles), compound parts keep their natural meaning (firepower -> 火 + 力量),
and words of 4 letters or fewer are never split (into stays 进入).

## Proofreading with a local AI model

`--check` lets a local AI model help.

- In the stupid mode it writes the sentence: it gets the English, the real meaning and the
  stupid words, and must use every stupid word word for word. The program checks, asks again
  up to 3 times, and falls back to Google's sentence if the model never gets it right. This
  fixes the verbs Google rewrites: "he can clutch any round" -> 他可以用离合器抓住任何圆形.
- In the wordy and plain modes it proofreads: the wordy mode makes 4 different versions, the
  model picks the funniest one that still reads like a Chinese sentence and may add or remove
  a few function words (的, 了, 在 ...). If it changes more than that, its edit is thrown away.

```
py translator.py --check "s1mple is the goat, he can clutch any round with a deagle"
py translator.py --wordy --check "The cat is sitting on the table"
```

It needs [Ollama](https://ollama.com) running on this computer with the model downloaded
(`ollama pull deepseek-r1:14b`, 9 GB; set `SBTRANSLATOR_MODEL` to use another model). Without
it, `--check` gives the unchecked translation and prints why. From Python use
`sbtranslator.translate(text, check=True)`, over HTTP add `check=1`, and the overlay has an
"AI 校对" box.

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
