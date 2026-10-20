# StupidTransilator
This translator mean to generate stupid translation from English to Chinese for meme purpose

## Usage

Needs Python 3 and an internet connection (it calls Google Translate, and Bing Translator for Classical Chinese). No extra packages.

```
py translator.py "Hello world"            # stupid: word by word, wrong-but-real meanings
py translator.py --rarity 2.5 "Hello"     # same, rarer meanings (0 = common, 3 = obscure, default 1.5)
py translator.py --plain "Hello world"    # word by word, usual meanings
py translator.py --proper "Hello world"   # normal whole-sentence translation
py translator.py --classical "Hello"      # correct Classical Chinese (文言文) in traditional characters, via Bing
py translator.py                          # interactive mode, blank line to quit
```
