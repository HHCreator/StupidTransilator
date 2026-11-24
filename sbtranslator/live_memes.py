"""The overlay's 梗 panel: the danmu lines MemeLearnerBot says by itself as a live room goes on.

MemeLearnerBot (https://github.com/HHCreator/MemeLearnerBot) learns gaming memes from
Bilibili. Its `py -m memelearner live-say ROOM` (or 看直播出梗.bat) listens to a live room
and, every 30 seconds or so, says a few danmu lines with the memes it learned that fit what
is going on in the match. It serves them on this computer only:

    GET http://127.0.0.1:8766/lines?after=N
    {"room": {"name", "title", "link"}, "started", "every", "heard", "rounds": [{"id", "at",
     "situation", "when", "game", "names", "lines": [{"line", "meme", "meaning", "template",
     "name"}], "why", "model", "spent"}, ...]}

The overlay asks every POLL_SECONDS in a thread of its own (watch()), and shows the newest
lines; click one to copy it, then send it yourself. Nothing here sends a danmu. When nobody
answers, live-say isn't running and the panel stays hidden, so the overlay is the same as
before for anyone who doesn't use MemeLearnerBot. SBTRANSLATOR_MEMES_URL asks another
address (live-say --port).
"""

import json
import os
import urllib.request

URL = os.environ.get("SBTRANSLATOR_MEMES_URL") or "http://127.0.0.1:8766/lines"
POLL_SECONDS = 2  # how often the overlay asks
TIMEOUT = 2  # seconds to wait for an answer from this computer


def fetch(after=0, url=URL, timeout=TIMEOUT):
    """What live-say said after round after (its JSON, above). Raises OSError when nobody
    answers (live-say isn't running) and ValueError when the answer isn't live-say's."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never a proxy
    with opener.open(f"{url}?after={int(after)}", timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("rounds"), list):
        raise ValueError("not what live-say answers")
    data["rounds"] = [round_ for round_ in data["rounds"]
                      if isinstance(round_, dict) and isinstance(round_.get("id"), int)]
    return data


def watch(events, stop, url=URL, every=POLL_SECONDS, ask=fetch):
    """Ask live-say every every seconds until stop (a threading.Event) is set, and put in
    events ("memes", answer, new rounds) when it answers with rounds the overlay hasn't had
    (or answers at all for the first time), and ("memes off",) once when it stops answering.
    A live-say that started again counts its rounds from 1, so they are all asked for again."""
    started, after, on = None, 0, False
    while True:
        try:
            data = ask(after, url)
            if data.get("started") != started:  # another live-say: from its first round
                started, after = data.get("started"), 0
                data = ask(0, url)
            rounds = [round_ for round_ in data["rounds"] if round_["id"] > after]
            if rounds or not on:
                events.put(("memes", data, rounds))
            after = max([after] + [round_["id"] for round_ in rounds])
            on = True
        except (OSError, ValueError):
            if on:
                events.put(("memes off",))
            started, after, on = None, 0, False
        if stop.wait(every):
            return


def newest(rounds):
    """The newest round that has lines, or None."""
    said = [round_ for round_ in rounds if round_.get("lines")]
    return said[-1] if said else None
