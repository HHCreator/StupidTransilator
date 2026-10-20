"""Learn memes and names for the stupid translator by crawling Wikipedia.

For each page it learns the Chinese name (from the page's Chinese Wikipedia link) and the
English short names that point to it: the title, one-word redirects (LoL), abbreviations
from the Chinese intro (简称TES) and a person's surname (Kerrigan). Results are saved to
data/memes_learned.json, which translator.py reads. Hand-written entries in data/memes.json
always win over learned ones.

Usage:
    py learn.py "Top Esports" "Frozen (2013 film)"   # learn these pages
    py learn.py                                      # learn the pages in data/meme_seeds.txt
    py learn.py --links 50 "League of Legends"       # also learn up to 50 pages each one links to
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SEEDS_FILE = os.path.join(HERE, "data", "meme_seeds.txt")
LEARNED_FILE = os.path.join(HERE, "data", "memes_learned.json")
WORDS_FILE = os.path.join(HERE, "data", "words", "common_english.txt")

# Wikipedia asks API clients to identify themselves and not hammer the servers
HEADERS = {"User-Agent": "SBtranslator/0.1 (https://github.com/HHCreator/StupidTransilator)"}
REQUEST_DELAY = 0.5  # seconds between requests

# Suffixes dropped from Chinese names so 滔搏电子竞技俱乐部 is learned as 滔搏
ZH_SUFFIXES = ["电子竞技俱乐部", "电竞俱乐部", "电子竞技", "俱乐部", "战队"]


def api(lang, params):
    params = {"format": "json", "formatversion": "2", "maxlag": "5", **params}
    url = f"https://{lang}.wikipedia.org/w/api.php?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    time.sleep(REQUEST_DELAY)
    return data


def query_all(lang, params):
    """Run a query, following 'continue' until every result is in. Yields each response."""
    params = {"action": "query", **params}
    while True:
        data = api(lang, params)
        yield data
        if "continue" not in data:
            break
        params = {**params, **data["continue"]}


def batches(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def linked_pages(title, limit):
    links = []
    for data in query_all("en", {"titles": title, "prop": "links", "plnamespace": 0,
                                 "pllimit": "max", "redirects": 1}):
        for page in data["query"]["pages"]:
            links += [link["title"] for link in page.get("links", [])]
        if len(links) >= limit:
            break
    return links[:limit]


def english_pages(titles):
    """Return {title: {"zh": zh title, "redirects": [...]}} for pages with a Chinese version."""
    pages = {}
    for batch in batches(titles, 50):
        for data in query_all("en", {"titles": "|".join(batch), "redirects": 1,
                                     "prop": "langlinks|redirects", "lllang": "zh",
                                     "rdnamespace": 0, "rdlimit": "max"}):
            for page in data["query"]["pages"]:
                entry = pages.setdefault(page["title"], {"zh": None, "redirects": []})
                for link in page.get("langlinks", []):
                    entry["zh"] = link["title"]
                entry["redirects"] += [r["title"] for r in page.get("redirects", [])]
    return {t: p for t, p in pages.items() if p["zh"]}


def chinese_pages(zh_titles):
    """Return {zh title: (simplified title, intro text)}."""
    result = {}
    for batch in batches(zh_titles, 20):  # extracts are limited to 20 pages per request
        for data in query_all("zh", {"titles": "|".join(batch), "prop": "info|extracts",
                                     "inprop": "varianttitles", "exintro": 1,
                                     "explaintext": 1, "exchars": 400, "variant": "zh-cn"}):
            for page in data["query"]["pages"]:
                simplified = page.get("varianttitles", {}).get("zh-cn", page["title"])
                old = result.get(page["title"], (simplified, ""))
                result[page["title"]] = (simplified, page.get("extract") or old[1])
    return result


def clean_zh(name):
    name = re.sub(r"[（(].*?[)）]", "", name).strip("《》 ")
    for suffix in ZH_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def single_word(name):
    """Return the lowercase key for a one-word English name, or None."""
    name = re.sub(r"\s*\(.*?\)", "", name).strip()
    return name.lower() if re.fullmatch(r"[A-Za-z0-9']+", name) else None


def learn(titles, seeds, common_words):
    learned = {}
    english = english_pages(titles)
    chinese = chinese_pages(sorted({p["zh"] for p in english.values()}))
    for title, page in english.items():
        zh_title, intro = chinese.get(page["zh"], (page["zh"], ""))
        zh_name = clean_zh(zh_title)
        # Short names: redirects that are the title's initials (League of Legends -> LoL)
        # and abbreviations from the Chinese intro (简称TES). Other redirects are usually
        # sub-topics (a champion's name redirecting to League of Legends), so skip them.
        base = re.sub(r"\s*\(.*?\)", "", title)
        initials = "".join(word[0] for word in re.findall(r"[A-Za-z0-9]+", base)).lower()
        aliases = [single_word(r) for r in page["redirects"]]
        aliases = [a for a in aliases if a and len(a) > 2 and a == initials]
        aliases += [a.lower() for a in re.findall(r"简称([A-Za-z0-9]{3,})", intro)]
        # A person: learn the surname too (Sarah Kerrigan -> 凯莉根)
        en_parts = re.sub(r"\s*\(.*?\)", "", title).split()
        if "·" in zh_name and len(en_parts) == len(zh_name.split("·")):
            learned.setdefault(en_parts[-1].lower(), zh_name.split("·")[-1])
        # A one-word title is learned as is when you asked for the page (Frozen -> 冰雪奇缘)
        if title in seeds and single_word(title):
            learned.setdefault(single_word(title), zh_name)
        for alias in aliases:
            if alias not in common_words:  # don't take over everyday words like "top"
                learned.setdefault(alias, zh_name)
    return learned


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    links = 0
    if "--links" in args:
        i = args.index("--links")
        links = int(args[i + 1])
        del args[i:i + 2]
    seeds = args
    if not seeds:
        with open(SEEDS_FILE, encoding="utf-8") as f:
            seeds = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    with open(WORDS_FILE, encoding="utf-8") as f:
        common_words = {line.strip().lower() for _, line in zip(range(3000), f)}

    titles = list(seeds)
    for seed in seeds if links else []:
        print(f"Collecting links from {seed}...")
        titles += [t for t in linked_pages(seed, links) if t not in titles]

    print(f"Learning from {len(titles)} pages...")
    found = learn(titles, set(seeds), common_words)

    try:
        with open(LEARNED_FILE, encoding="utf-8") as f:
            learned = json.load(f)
    except (OSError, ValueError):
        learned = {}
    new = {k: v for k, v in found.items() if learned.get(k) != v}
    learned.update(found)
    with open(LEARNED_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(learned.items())), f, ensure_ascii=False, indent=1)

    for key, value in sorted(new.items()):
        print(f"  {key} -> {value}")
    print(f"Learned {len(new)} new entries, {len(learned)} in total ({LEARNED_FILE}).")


if __name__ == "__main__":
    main()
