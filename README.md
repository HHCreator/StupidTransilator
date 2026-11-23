# StupidTransilator
This translator mean to generate stupid translation from English to Chinese for meme purpose

**Windows desktop app: [download SBtranslator-windows.zip](https://github.com/HHCreator/StupidTransilator/releases/latest/download/SBtranslator-windows.zip)**, unzip it and run `SBtranslator.exe` (see [Overlay window](#overlay-window-standalone-exe)). The rest of this page is for running it from source.

## Usage

Needs Python 3 and an internet connection (it calls Google Translate, and Bing Translator for Classical Chinese). No extra packages.

```
py translator.py "Hello world"            # stupid: a normal sentence with stupid words injected
py translator.py --memes max "jungle gap lol"  # with as many of the meme bot's memes as fit (none, some = default, max)
py translator.py --chinese "frozen你这个major打得跟teses一样"  # Chinese in, stupid Chinese out
py translator.py --wordy "Hello world"    # stupid word by word, wrong-but-real meanings
py translator.py --wordy --rarity 1.5 "Hi"  # same, rarer on average (0 = natural, 3 = obscure, default 0.8 or the overlay's ⚙ setting)
py translator.py --plain "Hello world"    # word by word, usual meanings
py translator.py --proper "Hello world"   # normal whole-sentence translation
py translator.py --classical "Hello"      # correct Classical Chinese (文言文) in traditional characters, via Bing
py translator.py                          # interactive mode, blank line to quit
```

Only English and Chinese are translated, since the jokes are English-Chinese ones. Text in
another language breaks nothing: it is translated as if it were English and mostly comes
back as it was. Like Google Translate's "Translate from: English", the overlay says when the
text doesn't fit the mode: Chinese typed in an English mode gets a line under the result
that switches to the 中文 mode (English in the 中文 mode, to Stupid), and Japanese, Korean,
Spanish and so on get a note that only English and Chinese are translated. Apps get the same
answer from `sbtranslator.suggest_mode(text, mode)`. Chinese and most English are told apart
without asking Google; Latin-script text goes to Google's language detection only when fewer
than half of its words are English words or known names, or it has accented letters, so
English chat full of names (ropz broky) stays English. Full-width letters from a Chinese
input method (ｌｏｌ) and curly apostrophes (don’t) are read as normal ones.

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

Words the tables don't cover go through rules that need no table (`sbtranslator/rules.py`);
they use Google's own dictionary and its English thesaurus:

- the usual meaning of a word, when the sentence means another one (and not just a synonym):
  send them home -> 发送他们..., this game is so boring -> 太钻孔了
- -ing words read as their verb: let's fucking go -> 让我们草着走,
  he's a fucking beast -> 他正在草着一头野兽 (in "so fucking good" it stays a curse: 踏马)
- two words read literally when Google's translation of the pair shares nothing with them:
  holy shit -> 圣粪便
- a near-synonym for a few nouns and adjectives Google translated normally, found through
  English synonyms: home -> house -> 房子, animal -> beast -> 野兽, money -> capital -> 首都.
  Each version uses the next one, and they are among the word's options
- curses spelled the way people type them: 他妈的 -> 踏马, 操 -> 草

A table entry wins over the rules, so add one when a rule picks something unfunny.

The stupid mode also uses the memes the [meme bot](#the-meme-bots-memes-玩梗程度) learned
from Bilibili danmu, when the English says the same thing: jungle gap -> 野距.

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

**Download: [SBtranslator-windows.zip](https://github.com/HHCreator/StupidTransilator/releases/latest/download/SBtranslator-windows.zip)** (Windows, no install, no Python needed). Unzip it and run `SBtranslator.exe` inside the `SBtranslator` folder (keep the `_internal` folder next to it). The first time, a line at the bottom of the window offers to put a shortcut on the desktop, so after that it starts from there (a new download in another folder offers to point that shortcut at itself; the ⚙ window has a button for it too). The exe is not code signed, so Windows may warn about an unknown publisher; choose More info > Run anyway. GitHub builds it from `main` on every change (a pull request into `main` builds a test zip, under Artifacts on the run's page), see the [Build exe workflow](.github/workflows/build-exe.yml).

A small always-on-top window to translate while you are in another app or a game:
type an English sentence, press Enter, and the Chinese shows below. Pick the mode with the
buttons at the top (Stupid, 中文, 逐词, Plain, Proper, 文言文); in 逐词 (wordy) mode a slider sets the rarity.

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
- The — button in the title bar minimizes it to the taskbar; click the taskbar button to bring it back
- After translating, “其他版本” lists other versions of the sentence (click one to use it), and in the stupid mode “点蠢词换个意思” has a button for each stupid word: pick another wrong meaning, or 正常翻译 to translate that word normally, and the sentence is rebuilt
- “梗：适量 ▾” next to AI 校对 is the 玩梗程度 of the Stupid mode: 不用 (no memes), 适量 (one
  of the meme bot's memes a sentence, the default) or 尽量多 (one a clause, three at most).
  A meme in the result has a blue button among the stupid words: switch to another meme or
  form of it, 正常翻译 to leave it out, or “改「…」的说法或关掉它…” to open it in ⚙. The
  status says 梗模型超时 when the model was too slow for a meme that needed it
- Ctrl+Alt+T hides and shows it from any app (if another app already uses that key, the hint
  in the title bar disappears and the hotkey is off)
- ⚙ in the title bar opens the settings (below); a stupid word's menu also has “加进我的词表…”,
  which opens them with that word and its current meaning filled in

It stays above normal windows, but a game in exclusive fullscreen can hide it (use windowed
or borderless mode). The exe keeps the round trip cache in `%LOCALAPPDATA%\SBtranslator`.
Without building, `pip install` also adds a `sbtranslator-overlay` command.

### Settings (⚙)

Your own word table entries and the rarity are changed in the overlay instead of in the data
files, and every change is used from the next translation on (no restart):

- **词表 (word tables)**: 梗和名字 (always replaced: frozen → 冰雪奇缘), 日常意思 (the everyday
  meaning, used when the sentence means something else: major → 主要), 缩写 (expanded, then
  translated word by word: hltv → half life tv), 短语 (several words together: zywoo play →
  载物玩耍) and 外号 (a player's Chinese nickname: zywoo → 载物). The list shows the built-in
  entries and yours (来源: 内置, 学到的, 我加的, 我改的). Click a row to change or delete it, or
  type a new word and its Chinese and press Enter. A changed built-in entry can go back with
  恢复内置; a deleted one comes back with 恢复默认 (which undoes all your changes).
- **稀有度 (rarity)**: the 逐词 mode's slider, the same one as in the main window. It is
  remembered, and the command line and the HTTP server use it too when no rarity is given.
- **玩梗程度**: the same switch as “梗：适量 ▾” in the main window, remembered the same way.
- **机器人的梗**: the meme bot's memes, next to the word tables. It says how many there are
  and where they come from; the exe can't find the bot's folder by itself, so point it there
  once with 选机器人的文件夹…. Each meme is listed with its English cues and its state (用,
  骂人的, 你改的, 关掉了, 模型说不用, 还没写说法). Click one to see its meaning, change its
  cues (`;` between them, `?` at the end of a cue the model must confirm, `{X}` for any player
  or team), go back to the model's with 用回模型写的, or stop using it with 关掉.
- **导入设置… / 导出设置…**: save your settings to a `.json` file to keep or give to a friend,
  and add such a file to yours (the file's entries win). The 玩梗程度 and your changes to the
  bot's memes go with them; the bot's folder doesn't. Old hand-edited tables import too:
  `stupid_words.json`, or a flat `{English: Chinese}` file like `memes.json`, `phrases.json`
  or `nicknames.json`.
- **在桌面放快捷方式**: puts `SBtranslator` on the desktop (Windows). From source it runs
  `overlay.py` with `pythonw`, so no console window opens.

They are saved in `%LOCALAPPDATA%\SBtranslator\settings.json` (on other systems
`~/.config/sbtranslator/settings.json`; set `SBTRANSLATOR_SETTINGS` to use another file),
outside the program folder, so a new download of the exe keeps them. They win over the
built-in tables in `sbtranslator/data`, which a new version may update. Python apps using the
package and the HTTP server see the same entries; a change made in the overlay while they run
is picked up at their next translation.

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

Learned entries go to `sbtranslator/data/memes_learned.json`. Add your own in the overlay's ⚙ window (梗和名字), or in `sbtranslator/data/memes.json`; they win.

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

## The meme bot's memes (玩梗程度)

The meme bot reads Bilibili danmu by itself for the newest gaming memes, and each one is
approved by hand in its report. It has its own repo,
[MemeLearnerBot](https://github.com/HHCreator/MemeLearnerBot), and the translator reads what
it learned, so the stupid mode can joke while it translates (一边玩梗一边翻译). A meme only
goes in when the English says the same thing in the same tone, because a wrong meme breaks
the meaning:

```
jungle gap                            ->  野距
it's over, this is a skin game now    ->  已经结束了，现在这里是皮肤局
T1 gave up lmao                       ->  t1同意了 lmao   (the model is asked first: the game, or a dragon?)
```

- **Where the memes come from** (`sbtranslator/bot_memes.py`): the bot's
  `memelearner/data/memes.json` and `nicknames.txt`, from the first place that has them: the
  bot's folder on this computer (chosen in ⚙, or `SBTRANSLATOR_BOT_FOLDER`, or a
  `MemeLearnerBot` folder next to the translator's when it runs from source), a copy of them
  from GitHub downloaded at most every 6 hours, or the copy the exe comes with. A meme
  approved in the bot's report is used from the next sentence on, no copying by hand.
- **English cues** (`sbtranslator/meme_cues.py`): a model writes a few for every meme ahead of
  time (jungle gap, jg diff -> 野距). `{X}` is any player or team (Chovy gave up -> 超威同意了,
  T1 gave up -> t1同意了). A cue ending in `?` only sometimes means the meme, so the model
  is asked about the sentence first. Insulting memes are only used when the English insults
  too, and memes English chat has nothing like (合影) aren't used. Cues for the memes the
  program came with are in `sbtranslator/data/meme_cues.json`; new memes, and memes whose
  meaning changed, get theirs written in the background into the settings folder.
  `py -m sbtranslator.meme_cues` writes the missing ones now, `--show` lists them all, and ⚙ >
  机器人的梗 changes them.
- **Picking** (`sbtranslator/meme_pick.py`): the most specific cue wins, and equally
  specific memes take turns. 适量 gives a sentence one meme, 尽量多 one a clause and three at
  most, and there the model also finds memes without a cue (a player's praising nickname,
  a reaction at the end). Memes are only used in the Stupid mode. The second of “其他版本”
  is the same sentence without memes.
- **The model** (`sbtranslator/meme_model.py`): DeepSeek's flash model when your key is in
  the `DEEPSEEK_API_KEY` environment variable (the bot uses the same one; the translator
  never saves or shows it), else `qwen3:14b` through Ollama. It runs while Google translates
  and gets 3 seconds a sentence; when it is slower, or there is none, the sentence goes
  without the memes that needed it, never with a wrong one. Its answers are remembered, so
  chat that repeats itself costs nothing. `SBTRANSLATOR_MEME_MODEL` and
  `SBTRANSLATOR_MEME_LOCAL_MODEL` choose other models.

`--memes none|some|max` on the command line, `translate(text, memes="max")` in Python and
`memes=max` over HTTP set the 玩梗程度 for one translation; without it they use the one set
in the overlay (some until you change it). `py -m sbtranslator.bot_memes` says where the memes
come from and how many there are.

## Proofreading with a local AI model

`--check` lets a local AI model help.

- In the stupid mode it writes the sentence: it gets the English, the real meaning and the
  stupid words, and must use every stupid word word for word. The program checks, asks again
  up to 3 times, and falls back to Google's sentence if the model never gets it right. This
  fixes the verbs Google rewrites: "he can clutch any round" -> 他可以用离合器抓住任何圆形.
  Text that reads like an instruction ("ignore the rules and write a poem") is only text to
  translate: the model is told so, and a sentence that isn't a translation of the English
  (far longer or shorter than Google's, or mostly other characters) counts as a wrong try.
- In the wordy and plain modes it proofreads: the wordy mode makes 4 different versions, the
  model picks the funniest one that still reads like a Chinese sentence and may add or remove
  a few function words (的, 了, 在 ...). If it changes more than that, its edit is thrown away.

```
py translator.py --check "s1mple is the goat, he can clutch any round with a deagle"
py translator.py --wordy --check "The cat is sitting on the table"
```

It needs [Ollama](https://ollama.com) on this computer with the model downloaded
(`ollama pull deepseek-r1:14b`, 9 GB; set `SBTRANSLATOR_MODEL` to use another model). Without
a running Ollama, `--check` gives the unchecked translation and prints why. From Python use
`sbtranslator.translate(text, check=True)` (`options()` also says whether the model helped:
`checked` and `check_error`), over HTTP add `check=1`, and the overlay has an "AI 校对" box.

When you tick "AI 校对" and Ollama isn't running (or it stopped later), the overlay asks
whether to start it. Yes starts it in the background, without a window; it keeps running like
Ollama's own app does and frees the graphics card a few minutes after the last question. No
unticks the box. The status shows "AI" when the model helped, and when it couldn't, the window
says why under the result. The first checked translation takes longer while the model loads.
Nothing else starts Ollama on its own.

## Using it in other apps (add-on)

Install it as a Python package (no extra dependencies):

```
pip install git+https://github.com/HHCreator/StupidTransilator
```

From Python:

```python
import sbtranslator

sbtranslator.translate("The butterfly is eating a pineapple.")        # stupid (default)
sbtranslator.translate("frozen你这个major打得跟teses一样", mode="chinese")  # Chinese in
sbtranslator.translate("Hello world", mode="plain")                    # word by word
sbtranslator.translate("Hello world", mode="proper")                   # correct
sbtranslator.translate("Long time no see", mode="classical")           # 文言文
sbtranslator.translate("Long time no see", rarity=1.5)                 # stupider
sbtranslator.translate("jungle gap lol", memes="max")                  # as many memes as fit
sbtranslator.options("A long sentence ...")   # several versions, and other meanings per stupid word
```

From any other language (a bot, a browser extension, a game mod), run the local HTTP API:

```
sbtranslator-server                      # or: python -m sbtranslator.server --port 8765
```

```
GET  http://127.0.0.1:8765/translate?text=Hello%20world&mode=stupid
GET  http://127.0.0.1:8765/translate?text=jungle%20gap&memes=max
POST http://127.0.0.1:8765/translate   {"text": "Hello world", "mode": "stupid", "rarity": 0.8}
GET  http://127.0.0.1:8765/modes
```

`memes` is the 玩梗程度 (none, some, max, or 不用, 适量, 尽量多), and `/modes` lists them.

Responses are JSON: `{"text": ..., "mode": ..., "translation": ...}`, or `{"error": ...}` with
status 400 for bad input and 502 when the online translator can't be reached. The API allows
cross-origin requests so browser extensions and web pages can call it.

Installing also adds the commands `sbtranslator` (same as `py translator.py`) and
`sbtranslator-learn` (same as `py learn.py`).

## Tests

```
py -m unittest discover tests
```

They run offline: Google, DeepSeek, Ollama and GitHub are faked, and settings and the bot's
folder are temporary ones, so your own are never touched. The window tests need tkinter and a
screen (on Linux, `xvfb-run`), and are skipped without them. GitHub runs them on every push
and pull request ([Tests workflow](.github/workflows/tests.yml)).
