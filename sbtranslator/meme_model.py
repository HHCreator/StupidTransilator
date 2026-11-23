"""Asking a model about the bot's memes: DeepSeek's flash model online, or qwen3:14b on this
computer through Ollama when DeepSeek can't be reached.

meme_cues.py asks it to write each meme's English cues, and meme_pick.py whether a meme fits
a sentence. MemeLearnerBot judges memes with the same two models, and on Hao's marks flash
did far better (49 points against 22.5, and 44 against 13 on live chat), so it goes first:

    1. DeepSeek flash, when your key is in the DEEPSEEK_API_KEY environment variable (the
       bot uses the same one). The translator never saves, shows or logs the key.
    2. qwen3:14b through Ollama (the overlay starts Ollama only when you agree; this doesn't),
       when DeepSeek has no key, refuses it, has no balance left or can't be reached. After
       that DeepSeek is left alone for DOWN_MINUTES, so each sentence doesn't wait on it.

Every answer is JSON. ask() raises Unavailable when neither model can answer in time.
SBTRANSLATOR_MEME_MODEL and SBTRANSLATOR_MEME_LOCAL_MODEL choose other models.
"""

import collections
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request

DEEPSEEK_URL = "https://api.deepseek.com"
KEY_VARIABLE = "DEEPSEEK_API_KEY"
ONLINE_MODEL = os.environ.get("SBTRANSLATOR_MEME_MODEL", "deepseek-flash")
LOCAL_MODEL = os.environ.get("SBTRANSLATOR_MEME_LOCAL_MODEL", "qwen3:14b")
DOWN_MINUTES = 5  # after DeepSeek couldn't be reached, ask only the local model this long
ANSWER_TOKENS = 800  # the longest answer: a meme's cues, or the memes for one sentence
LOCAL_CONTEXT = 8192  # tokens Ollama keeps for a question (the list of every meme fits)

# How many questions each model answered, and the tokens it read and wrote, for the
# meme-test report: {model: Counter(calls, input, cached, output, seconds)}
usage = collections.defaultdict(collections.Counter)
_down_until = 0.0  # DeepSeek is left alone until then (time.time())
_lock = threading.Lock()


class Unavailable(Exception):
    """No model could answer: why, in a sentence to show."""


class _Unreachable(Exception):
    """DeepSeek can't be asked now (no key, refused key, no balance, no internet)."""


def online_ready():
    """Whether DeepSeek will be asked first: a key is set and it wasn't down just now."""
    return bool(os.environ.get(KEY_VARIABLE, "").strip()) and time.time() >= _down_until


def ask(instructions, question, timeout):
    """Ask the first model that can answer (see the top of this file) and return (its JSON
    answer as a dict, the model's name). question is any JSON-able value. Raises Unavailable
    when no model answered within timeout seconds."""
    global _down_until
    deadline = time.monotonic() + timeout
    messages = [{"role": "system", "content": instructions},
                {"role": "user", "content": json.dumps(question, ensure_ascii=False)}]
    problems = []
    if online_ready():
        try:
            return _json(_ask_deepseek(messages, deadline)), ONLINE_MODEL
        except _Unreachable as error:
            with _lock:
                _down_until = time.time() + DOWN_MINUTES * 60
            problems.append(str(error))
        except Unavailable as error:
            raise Unavailable(f"DeepSeek: {error}")  # too slow: no time left for another
    elif os.environ.get(KEY_VARIABLE, "").strip():
        problems.append("DeepSeek couldn't be reached a moment ago")
    else:
        problems.append(f"no DeepSeek key in {KEY_VARIABLE}")
    try:
        return _json(_ask_ollama(messages, deadline)), LOCAL_MODEL
    except Unavailable as error:
        problems.append(str(error))
    raise Unavailable("; ".join(problems))


def _json(reply):
    """The JSON object in a reply ({} when there is none)."""
    found = re.search(r"\{.*\}", reply or "", re.S)
    try:
        answer = json.loads(found.group(0) if found else reply)
    except (ValueError, TypeError):
        return {}
    return answer if isinstance(answer, dict) else {}


def _left(deadline):
    """Seconds until the deadline; Unavailable when it has passed."""
    left = deadline - time.monotonic()
    if left <= 0.05:
        raise Unavailable("no answer in time")
    return left


def _ask_deepseek(messages, deadline):
    """Send a chat to DeepSeek and return the reply text. Tests replace this."""
    key = os.environ.get(KEY_VARIABLE, "").strip()
    body = {"model": ONLINE_MODEL, "messages": messages, "stream": False,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},  # thinking out loud first is slower and costs more
            "temperature": 0.2, "max_tokens": ANSWER_TOKENS}
    request = urllib.request.Request(
        f"{DEEPSEEK_URL}/chat/completions", data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=_left(deadline)) as response:
            answer = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code in (401, 402):
            raise _Unreachable("DeepSeek refused the key in DEEPSEEK_API_KEY" if error.code == 401
                               else "DeepSeek: the balance has run out")
        raise Unavailable(f"DeepSeek answered {error.code}")
    except (socket.timeout, TimeoutError):
        raise Unavailable("no answer in time")
    except (urllib.error.URLError, OSError) as error:
        if isinstance(getattr(error, "reason", None), (socket.timeout, TimeoutError)):
            raise Unavailable("no answer in time")
        raise _Unreachable(f"can't reach DeepSeek ({getattr(error, 'reason', error)})")
    except ValueError:
        raise Unavailable("DeepSeek answered something that isn't JSON")
    spent = answer.get("usage") or {}
    usage[ONLINE_MODEL].update(calls=1, input=spent.get("prompt_tokens") or 0,
                               cached=spent.get("prompt_cache_hit_tokens") or 0,
                               output=spent.get("completion_tokens") or 0,
                               seconds=time.monotonic() - started)
    try:
        return answer["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


def _ollama_url():
    from .check import OLLAMA_URL  # imported here: check.py imports the stupid mode
    return OLLAMA_URL


def _ask_ollama(messages, deadline):
    """Send a chat to the local model through Ollama and return the reply text. Tests
    replace this."""
    body = {"model": LOCAL_MODEL, "messages": messages, "stream": False, "format": "json",
            "think": False,  # qwen3 would otherwise think out loud first, which is slow
            "options": {"temperature": 0.2, "num_ctx": LOCAL_CONTEXT}}
    started = time.monotonic()
    for attempt in range(2):
        request = urllib.request.Request(
            f"{_ollama_url()}/api/chat", data=json.dumps(body, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=_left(deadline)) as response:
                answer = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            said = error.read().decode("utf-8", "replace")
            if "think" in said and "think" in body:
                del body["think"]  # a model that can't switch thinking off: ask without
                continue
            if error.code == 404:
                raise Unavailable(f"{LOCAL_MODEL} isn't downloaded (ollama pull {LOCAL_MODEL})")
            raise Unavailable(f"Ollama answered {error.code}")
        except (socket.timeout, TimeoutError):
            raise Unavailable("no answer in time")
        except (urllib.error.URLError, OSError) as error:
            if isinstance(getattr(error, "reason", None), (socket.timeout, TimeoutError)):
                raise Unavailable("no answer in time")
            from . import check
            raise Unavailable(check.NOT_RUNNING if check.ollama_program() else check.NOT_INSTALLED)
        except ValueError:
            raise Unavailable("Ollama answered something that isn't JSON")
        usage[LOCAL_MODEL].update(calls=1, input=answer.get("prompt_eval_count") or 0,
                                  output=answer.get("eval_count") or 0,
                                  seconds=time.monotonic() - started)
        reply = (answer.get("message") or {}).get("content") or ""
        return re.sub(r"<think>.*?</think>", "", reply, flags=re.S).strip()
    raise Unavailable("Ollama refused the request")
