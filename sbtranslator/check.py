"""Let a local AI model (DeepSeek through Ollama) help with stupid translations.

    py translator.py --check "@frozen: teses, your HLTV top is 0, lol"
    sbtranslator.translate("...", check=True)

In the stupid mode (inject.py) the model writes the sentence: it gets the English, its real
meaning and the stupid words, and writes fluent Chinese that uses every stupid word word
for word. The program checks that every stupid word is really there and asks again if not
(BUILD_ATTEMPTS times); if the model never gets it right, Google's version is used.

In the wordy and plain modes it proofreads instead: the wordy mode makes several versions
of the sentence (VARIANTS). A local model picks the
funniest one that still reads like a Chinese sentence, and may add or remove a few small
function words (的, 了, 在 ...) so it reads better. It may not fix the wrong words: they are
the joke. If the model changes more than function words, its edit is thrown away and the
version it picked is used as it was.

Needs Ollama (https://ollama.com) running on this computer, with the model downloaded:

    ollama pull deepseek-r1:14b

Without it, a checked translation falls back to the first version and warns why.
Set SBTRANSLATOR_MODEL to use another Ollama model (for example deepseek-r1:8b).
"""

import json
import os
import re
import urllib.error
import urllib.request
import warnings

from .inject import translate_injected
from .translator import TARGET_RARITY, translate, translate_word_by_word

OLLAMA_URL = "http://127.0.0.1:11434"  # where Ollama listens on this computer
MODEL = os.environ.get("SBTRANSLATOR_MODEL", "deepseek-r1:14b")
VARIANTS = 4  # how many stupid versions the model chooses from
TIMEOUT = 180  # seconds; the first request also loads the model into the graphics card

# The small words the model may add or remove; every other character must stay as it was
FUNCTION_WORDS = set("的了在是把被着过吗呢吧啊得地和就也都给对")

INSTRUCTIONS = """你是「傻瓜翻译」的校对员。傻瓜翻译故意逐词翻译英文，把一部分词换成错误但真实存在的意思，目的是搞笑。

你的任务：
1. 从候选里选出最好笑、但读起来仍然勉强像一句中文的那一个。
2. 可以在选中的句子里加上或删掉少量虚词（的、了、在、是、把、被、着、过、吗、呢、吧、啊、得、地、和、就、也、都、给、对），让它读起来更顺。
3. 不能把故意用错的词改对，不能换词，不能加新的实词，不能调换词的顺序。

只输出 JSON：{"choice": 候选编号, "text": "校对后的句子"}"""


BUILD_INSTRUCTIONS = """你在帮一个搞笑翻译器造句。你会拿到一句英文、它的正确中文意思，和几个故意翻错的中文词（笑点）。

写一句通顺自然的中文：意思跟着英文走，但英文里对应的那几个词，必须换成给你的中文词，一字不差地用上，不能改字、不能换成同义词、不能加引号。其他部分像正常翻译一样通顺。

只输出 JSON：{"text": "句子"}"""
BUILD_ATTEMPTS = 3  # how many times the model may try to use every stupid word


class CheckUnavailable(Exception):
    """The local model can't be reached (Ollama not running, model not downloaded)."""


def _ask(messages, model, timeout):
    """Send a chat to Ollama and return the reply text."""
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",  # Ollama makes the model answer with valid JSON
        "think": False,  # DeepSeek-R1 would otherwise "think" out loud first, which is slow
        "options": {"temperature": 0.6},
    }
    for attempt in range(2):
        request = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                reply = json.loads(response.read().decode("utf-8"))["message"]["content"]
            # Older Ollama versions ignore "think" and send the thinking inside the reply
            return re.sub(r"<think>.*?</think>", "", reply, flags=re.S).strip()
        except urllib.error.HTTPError as error:
            message = error.read().decode("utf-8", "replace")
            if "think" in message and "think" in body:
                del body["think"]  # this model can't switch thinking off; ask again without
                continue
            if error.code == 404:
                raise CheckUnavailable(f"model {model} isn't downloaded (ollama pull {model})")
            raise CheckUnavailable(f"Ollama answered {error.code}: {message[:200]}")
        except (urllib.error.URLError, OSError) as error:
            raise CheckUnavailable(f"can't reach Ollama at {OLLAMA_URL} ({error})")
    raise CheckUnavailable("Ollama refused the request")


def _skeleton(text):
    """What may not change: the text without function words, punctuation and spaces."""
    return "".join(c for c in text if c.isalnum() and c not in FUNCTION_WORDS)


def proofread(english, candidates, proper, model=MODEL, timeout=TIMEOUT):
    """Have the local model pick and polish the best stupid version; return that sentence.

    english: the original sentence; candidates: the stupid versions; proper: the correct
    translation, which tells the model what the sentence means. Raises CheckUnavailable when
    the model can't be reached.
    """
    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(candidates, 1))
    question = (f"英文原文：{english}\n"
                f"正确的意思（只用来理解句子，不要照它改）：{proper}\n"
                f"候选：\n{numbered}")
    reply = _ask([{"role": "system", "content": INSTRUCTIONS},
                  {"role": "user", "content": question}], model, timeout)
    try:
        answer = json.loads(reply)
        choice = int(answer.get("choice", 1))
    except (ValueError, TypeError, AttributeError):
        return candidates[0]  # not the JSON we asked for: keep the first version
    picked = candidates[choice - 1] if 1 <= choice <= len(candidates) else candidates[0]
    text = str(answer.get("text") or picked).strip()
    # The model may only touch function words; if it changed real words, undo its edit
    return text if _skeleton(text) == _skeleton(picked) else picked


def checked_translation(text, rarity=TARGET_RARITY, rare=True, model=MODEL):
    """A stupid (or, with rare=False, plain) translation proofread by the local model.

    Falls back to the unchecked translation, with a warning, if the model isn't available.
    """
    candidates = translate_word_by_word(text, rare=rare, target_rarity=rarity,
                                        variants=VARIANTS if rare else 1)
    try:
        return proofread(text, candidates, translate(text), model)
    except CheckUnavailable as error:
        warnings.warn(f"Translation not checked: {error}")
        return candidates[0]


def build_injected(details, model=MODEL, timeout=TIMEOUT):
    """Have the local model write the stupid sentence around the stupid words.

    details comes from inject.translate_injected(details=True). Returns the model's sentence
    once it contains every stupid word, or Google's version after BUILD_ATTEMPTS tries.
    """
    required = list(dict.fromkeys(details["words"].values()))
    pairs = "\n".join(f"{english} -> {chinese}" for english, chinese in details["words"].items())
    question = (f"英文：{details['english']}\n"
                f"正确的意思：{details['proper']}\n"
                f"必须一字不差用上的词（英文 -> 中文）：\n{pairs}")
    messages = [{"role": "system", "content": BUILD_INSTRUCTIONS},
                {"role": "user", "content": question}]
    for attempt in range(BUILD_ATTEMPTS):
        reply = _ask(messages, model, timeout)
        try:
            text = str(json.loads(reply).get("text", "")).strip()
        except (ValueError, AttributeError):
            text = ""
        # The model sometimes puts spaces between Chinese words; Chinese has none
        text = re.sub(r"(?<=[^\x00-\x7f]) +| +(?=[^\x00-\x7f])", "", text)
        missing = [w for w in required if w not in text]
        if text and not missing:
            return text
        # Tell the model what went wrong and let it try again
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": "这些词没有一字不差地出现：" + "、".join(missing or required)
                      + "。请重写，必须原样用上它们。"}]
    return details["result"]


def checked_injected(text, model=MODEL):
    """The stupid translation, with the sentence written by the local model.

    Falls back to Google's version, with a warning, if the model isn't available.
    """
    details = translate_injected(text, details=True)
    if not details["words"]:
        return details["result"]  # nothing stupid to place: the normal translation
    try:
        return build_injected(details, model)
    except CheckUnavailable as error:
        warnings.warn(f"Sentence not written by the model: {error}")
        return details["result"]
