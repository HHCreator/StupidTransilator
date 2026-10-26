"""Read live stream chat (Douyu, Twitch) so the stupid translator can learn memes from it.

    py listen.py douyu 6657                 # listen to Douyu room 6657 for 10 minutes
    py listen.py twitch xqc --minutes 30    # listen to twitch.tv/xqc for 30 minutes

Both connections are read-only and anonymous: nothing is ever sent to the chat, and no
account is needed. Each message comes back as (user, text); the user is only used to count
how many different people said something, and is never saved as is (see learn_chat.py).

This file only does the connections; finding the memes in the messages is learn_chat.py.

    Twitch   IRC over a plain socket (irc.chat.twitch.tv), logged in as an anonymous
             "justinfan" reader, which Twitch allows for read-only chat clients
    Douyu    a WebSocket to Douyu's danmu (弹幕) server, speaking Douyu's own "STT"
             message format; the WebSocket part is written here with the standard
             library, so the package still needs no extra installs
"""

import base64
import os
import random
import socket
import ssl
import struct
import time


# -- Twitch -------------------------------------------------------------------------------

TWITCH_HOST, TWITCH_PORT = "irc.chat.twitch.tv", 6667


def twitch_messages(channel, seconds):
    """Yield (user, text) for every chat message in a Twitch channel for the given time."""
    sock = socket.create_connection((TWITCH_HOST, TWITCH_PORT), timeout=10)
    # "justinfanNNNN" with any password is Twitch's anonymous, read-only login
    nick = f"justinfan{random.randint(10000, 99999)}"
    sock.sendall(f"PASS SCHMOOPIIE\r\nNICK {nick}\r\nJOIN #{channel.lower()}\r\n".encode())
    end = time.time() + seconds
    buffer = b""
    try:
        while time.time() < end:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            if not data:
                break  # the server closed the connection
            buffer += data
            *lines, buffer = buffer.split(b"\r\n")
            for raw in lines:
                line = raw.decode("utf-8", "replace")
                if line.startswith("PING"):
                    sock.sendall(b"PONG :tmi.twitch.tv\r\n")  # keep the connection alive
                # :user!user@user.tmi.twitch.tv PRIVMSG #channel :message text
                elif " PRIVMSG " in line and line.startswith(":"):
                    user = line[1:line.index("!")] if "!" in line else "?"
                    text = line.split(" :", 1)[1] if " :" in line else ""
                    yield user, text
    finally:
        sock.close()


# -- Douyu --------------------------------------------------------------------------------

DOUYU_HOST, DOUYU_PORT = "danmuproxy.douyu.com", 8506
HEARTBEAT_SECONDS = 45  # Douyu drops connections that stay quiet for longer


def _stt_encode(fields):
    """Douyu's STT format: key@=value/key@=value/, with / written as @S and @ as @A."""
    def escape(s):
        return str(s).replace("@", "@A").replace("/", "@S")
    return "".join(f"{escape(k)}@={escape(v)}/" for k, v in fields.items())


def _stt_decode(text):
    """Turn an STT string back into a dict (nested values stay as strings)."""
    fields = {}
    for item in text.split("/"):
        if "@=" in item:
            key, value = item.split("@=", 1)
            fields[key.replace("@S", "/").replace("@A", "@")] = (
                value.replace("@S", "/").replace("@A", "@"))
    return fields


def _douyu_packet(fields):
    """Wrap an STT message in Douyu's packet header (length twice, type 689, two zeros)."""
    body = _stt_encode(fields).encode("utf-8") + b"\0"
    length = len(body) + 8
    return struct.pack("<IIHBB", length, length, 689, 0, 0) + body


class _WebSocket:
    """The smallest WebSocket client that Douyu's danmu server accepts (binary frames)."""

    def __init__(self, host, port, timeout=10):
        raw = socket.create_connection((host, port), timeout=timeout)
        # Douyu's server only offers old TLS ciphers, which Python refuses by default
        context = ssl.create_default_context()
        context.set_ciphers("DEFAULT:@SECLEVEL=0")
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self.sock = context.wrap_socket(raw, server_hostname=host)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\nOrigin: https://www.douyu.com\r\n\r\n").encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise ConnectionError("Douyu closed the connection during the handshake")
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise ConnectionError("Douyu refused the WebSocket connection")
        self.buffer = response.split(b"\r\n\r\n", 1)[1]

    def send(self, payload):
        """Send one binary frame. Frames from a client must be masked with a random key."""
        mask = os.urandom(4)
        header = bytes([0x82])  # final frame, binary
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def _read(self, n):
        while len(self.buffer) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("Douyu closed the connection")
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def receive(self):
        """Return the payload of the next data frame (answers pings along the way)."""
        while True:
            first, second = self._read(2)
            opcode, n = first & 0x0F, second & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if second & 0x80 else None
            payload = self._read(n)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:
                raise ConnectionError("Douyu closed the connection")
            if opcode == 0x9:  # ping: answer with a pong carrying the same data
                self.sock.sendall(bytes([0x8A, 0x80 | len(payload)]) + b"\0\0\0\0" + payload)
                continue
            if opcode in (0x1, 0x2):
                return payload

    def close(self):
        self.sock.close()


def douyu_messages(room, seconds):
    """Yield (user id, text) for every danmu (弹幕) in a Douyu room for the given time."""
    ws = _WebSocket(DOUYU_HOST, DOUYU_PORT)
    ws.sock.settimeout(5)
    ws.send(_douyu_packet({"type": "loginreq", "roomid": room}))
    # Group -9999 is the "everyone" group, which receives all danmu of the room
    ws.send(_douyu_packet({"type": "joingroup", "rid": room, "gid": -9999}))
    end = time.time() + seconds
    last_beat = time.time()
    pending = b""  # Douyu packets can be split over frames, or several share one frame
    try:
        while time.time() < end:
            if time.time() - last_beat > HEARTBEAT_SECONDS:
                ws.send(_douyu_packet({"type": "mrkl"}))
                last_beat = time.time()
            try:
                pending += ws.receive()
            except socket.timeout:
                continue
            while len(pending) >= 12:
                length = struct.unpack("<I", pending[:4])[0]
                if len(pending) < length + 4:
                    break  # the rest of this packet is in the next frame
                body, pending = pending[12:length + 4], pending[length + 4:]
                message = _stt_decode(body.rstrip(b"\0").decode("utf-8", "replace"))
                if message.get("type") == "chatmsg" and message.get("txt"):
                    yield message.get("uid", "?"), message["txt"]
    finally:
        ws.close()


def messages(source, room, seconds):
    """Yield (user, text) from "douyu" or "twitch" for the given number of seconds."""
    if source == "douyu":
        return douyu_messages(room, seconds)
    if source == "twitch":
        return twitch_messages(room, seconds)
    raise ValueError(f"Unknown source {source!r}, expected douyu or twitch")
