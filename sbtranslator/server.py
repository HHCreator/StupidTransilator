"""A small HTTP API so apps in any language can use SBtranslator as an add-on.

    python -m sbtranslator.server                 # listens on http://127.0.0.1:8765
    python -m sbtranslator.server --port 9000

Requests:
    GET  /translate?text=Hello%20world&mode=stupid&rarity=0.8&check=1
    POST /translate   with JSON {"text": "Hello world", "mode": "stupid", "rarity": 0.8, "check": true}
    GET  /modes

Responses are JSON: {"text": ..., "mode": ..., "translation": ...} or {"error": ...}.
Only "text" is required; mode defaults to "stupid" and rarity to the library default.
check turns on proofreading by a local AI model (see check.py); it is off by default.

Python's standard http.server does the HTTP work: ThreadingHTTPServer accepts connections
and runs each request in its own thread, calling the do_GET / do_POST / do_OPTIONS method
of a new Handler. Handler only turns requests into sbtranslator.translate() calls.
"""

import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import MODES, translate
from .translator import TARGET_RARITY

# 127.0.0.1 means only programs on this computer can connect
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class Handler(BaseHTTPRequestHandler):
    """Answers one HTTP request; http.server creates a new Handler for every request."""

    def _send(self, status, body):
        """Send body as a JSON response with the given HTTP status code."""
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        # Let browser extensions and web pages call the API too
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def _translate(self, params):
        """Translate params["text"] and answer with the result, for both GET and POST.

        Status codes: 400 for bad input (no text, unknown mode, rarity not a number) and
        502 when the online translator can't be reached.
        """
        text = params.get("text")
        if not text:
            return self._send(400, {"error": "Missing 'text'"})
        if not isinstance(text, str):
            return self._send(400, {"error": "'text' must be a string"})
        mode = params.get("mode") or "stupid"
        try:
            rarity = float(params.get("rarity", TARGET_RARITY))
            # check arrives as true/false in JSON, or as text ("1", "true") in a URL
            check = str(params.get("check", "")).lower() in ("1", "true", "yes")
            translation = translate(text, mode=mode, rarity=rarity, check=check)
        except ValueError as error:
            return self._send(400, {"error": str(error)})
        except Exception as error:
            return self._send(502, {"error": f"Translation failed: {error}"})
        self._send(200, {"text": text, "mode": mode, "translation": translation})

    def do_OPTIONS(self):
        """Answer the "preflight" check browsers send before a cross-site POST."""
        self._send(204, {})

    def do_GET(self):
        """GET /modes lists the modes; GET /translate?text=... translates."""
        url = urllib.parse.urlparse(self.path)
        if url.path == "/modes":
            return self._send(200, {"modes": list(MODES), "default_rarity": TARGET_RARITY})
        if url.path == "/translate":
            # parse_qs gives lists ({"text": ["Hello"]}), keep the first value of each
            params = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
            return self._translate(params)
        self._send(404, {"error": "Not found. Use /translate or /modes"})

    def do_POST(self):
        """POST /translate with a JSON body {"text": ..., "mode": ..., "rarity": ...}."""
        if urllib.parse.urlparse(self.path).path != "/translate":
            return self._send(404, {"error": "Not found. Use /translate"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            params = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except ValueError:
            return self._send(400, {"error": "Body must be JSON"})
        self._translate(params)


def main():
    """Start the server (sbtranslator-server [--host HOST] [--port PORT]) until Ctrl+C."""
    args = sys.argv[1:]
    host, port = DEFAULT_HOST, DEFAULT_PORT
    if "--host" in args:
        host = args[args.index("--host") + 1]
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"SBtranslator API on http://{host}:{port}/translate (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
