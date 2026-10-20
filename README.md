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
