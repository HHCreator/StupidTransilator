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
The list of these forms is `IRREGULAR_PAST_FORMS` in `translator.py`.

Compound words are split into the common words they are made of and each part is
translated on its own: "butterfly" becomes butter + fly, "pineapple" becomes pine + apple,
"carpet" becomes car + pet. Parts come from `data/words/common_english.txt` and must also
be in Google's dictionary.

In the default stupid mode the rarity is spread unevenly: each run, some words keep the
meaning that fits the sentence so it still reads fluently, while others get far-off
meanings. The average rarity over the sentence matches `TARGET_RARITY` (or `--rarity`).
Rarity is -log10 of how often Google says a meaning is used: 0 = natural, 1 = 10%,
2 = 1%, 3 = 0.1%. Results change from run to run.

Single characters that can't stand alone as a word, like 次 (a measure word), are swapped
for their standalone word, so "time" can come out as 次数. The table is `STANDALONE_FORMS`
in `translator.py`, and `EXTRA_MEANINGS` adds meanings Google's dictionary leaves out.

For the 3,000 most common English words, the stupid mode also finds extra meanings with a
round trip: English -> Chinese -> English -> Chinese, keeping Chinese words whose default
English translation is the original word ("list" -> 单子, "life" -> 辈子). The first time
a word is seen this takes about 10 requests; results are cached in `.cache/round_trip.json`.

## Learning memes

The stupid modes replace memes and names with their Chinese names: "lol" -> 英雄联盟,
"frozen" -> 冰雪奇缘, "teses" -> 滔搏们 (plural of TES), "karrigan" -> 凯莉根 (close to Kerrigan).
These are learned from Wikipedia: for each page it takes the Chinese title and the English
short names (one-word title, initials like LoL, 简称 abbreviations like TES, surnames).

```
py learn.py                                   # learn the pages listed in data/meme_seeds.txt
py learn.py "Top Esports" "Sarah Kerrigan"    # learn specific pages
py learn.py --links 50 "League of Legends"    # also learn up to 50 pages each one links to
```

Learned entries go to `data/memes_learned.json`. Put your own in `data/memes.json`; they win.
