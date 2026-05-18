#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from typing import Any


WORD = "crop"
MAX_WRONG = 7
APP_SERVICE = "hangman.service"


class HangmanState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> dict[str, Any]:
        self.guesses: set[str] = set()
        self.wrong_guesses: list[str] = []
        self.done = False
        return self.snapshot(["New game started. Guess the word."])

    def display_word(self) -> str:
        return " ".join(letter if letter in self.guesses else "_" for letter in WORD)

    def snapshot(self, messages: list[str]) -> dict[str, Any]:
        won = all(letter in self.guesses for letter in WORD)
        lost = len(self.wrong_guesses) >= MAX_WRONG
        self.done = won or lost
        return {
            "word": self.display_word(),
            "wrong": self.wrong_guesses,
            "remaining": max(MAX_WRONG - len(self.wrong_guesses), 0),
            "done": self.done,
            "won": won,
            "messages": messages,
        }

    def guess(self, raw_guess: str) -> dict[str, Any]:
        guess = raw_guess.strip().lower()
        messages: list[str] = []

        if self.done:
            return self.snapshot(["The game is already done. Start a new game to play again."])

        if len(guess) != 1 or not guess.isalpha():
            return self.snapshot(["Enter one letter."])

        if guess in self.guesses or guess in self.wrong_guesses:
            return self.snapshot([f"You already guessed '{guess}'."])

        if guess in WORD:
            self.guesses.add(guess)
            messages.append(f"'{guess}' is in the word.")
        else:
            self.wrong_guesses.append(guess)
            messages.append(f"'{guess}' is not in the word.")

        won = all(letter in self.guesses for letter in WORD)
        lost = len(self.wrong_guesses) >= MAX_WRONG
        if won:
            messages.append("You got it. The word was crop.")
        elif lost:
            messages.append("No guesses left. The word was crop.")
        else:
            messages.append("Guess another letter.")

        print("hangman:", " ".join(messages), flush=True)
        return self.snapshot(messages)


STATE = HangmanState()


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hangman</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f1ea;
      --panel: #ffffff;
      --ink: #20242a;
      --muted: #68707a;
      --accent: #276f45;
      --accent-dark: #174b2d;
      --line: #d8d2c6;
      --bad: #9d3329;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Trebuchet MS", Verdana, sans-serif;
      color: var(--ink);
      background:
        linear-gradient(135deg, rgba(39,111,69,0.13), transparent 42%),
        linear-gradient(315deg, rgba(157,51,41,0.10), transparent 38%),
        var(--bg);
      display: grid;
      place-items: center;
      padding: 24px;
    }
    main {
      width: min(760px, 100%);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 16px 50px rgba(32,36,42,0.12);
      padding: 28px;
    }
    h1 {
      margin: 0 0 20px;
      font-size: 34px;
      letter-spacing: 0;
    }
    .word {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 46px;
      letter-spacing: 8px;
      padding: 20px;
      border: 1px solid var(--line);
      border-radius: 8px;
      text-align: center;
      background: #fbfaf7;
      min-height: 96px;
    }
    form {
      display: flex;
      gap: 10px;
      margin: 20px 0;
    }
    input {
      flex: 1;
      min-width: 0;
      font-size: 22px;
      padding: 14px 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    button {
      border: 0;
      border-radius: 8px;
      background: var(--accent);
      color: white;
      font-size: 18px;
      padding: 0 22px;
      cursor: pointer;
    }
    button:hover { background: var(--accent-dark); }
    .secondary { background: #4f5964; }
    .secondary:hover { background: #323940; }
    .status {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      color: var(--muted);
      margin-bottom: 16px;
      flex-wrap: wrap;
    }
    pre {
      min-height: 180px;
      max-height: 280px;
      overflow: auto;
      margin: 0;
      padding: 16px;
      border-radius: 8px;
      background: #20242a;
      color: #f4f1ea;
      white-space: pre-wrap;
      font-size: 15px;
      line-height: 1.45;
    }
    .bad { color: var(--bad); }
    @media (max-width: 560px) {
      main { padding: 20px; }
      .word { font-size: 36px; letter-spacing: 5px; }
      form { flex-direction: column; }
      button { min-height: 48px; }
    }
  </style>
</head>
<body>
  <main>
    <h1>Hangman</h1>
    <div id="word" class="word">_ _ _ _</div>
    <form id="guess-form">
      <input id="guess" maxlength="1" autocomplete="off" autofocus placeholder="Guess a letter">
      <button type="submit">Guess</button>
      <button type="button" id="reset" class="secondary">Reset</button>
      <button type="button" id="exit" class="secondary">Exit to Home</button>
    </form>
    <div class="status">
      <span>Wrong guesses: <strong id="wrong">none</strong></span>
      <span>Remaining: <strong id="remaining">6</strong></span>
    </div>
    <pre id="output">New game started. Guess the word.</pre>
  </main>
  <script>
    const wordEl = document.getElementById("word");
    const wrongEl = document.getElementById("wrong");
    const remainingEl = document.getElementById("remaining");
    const outputEl = document.getElementById("output");
    const guessEl = document.getElementById("guess");

    function appendOutput(messages) {
      outputEl.textContent += "\\n" + messages.join("\\n");
      outputEl.scrollTop = outputEl.scrollHeight;
    }

    function render(data) {
      wordEl.textContent = data.word;
      wrongEl.textContent = data.wrong.length ? data.wrong.join(", ") : "none";
      remainingEl.textContent = data.remaining;
      appendOutput(data.messages);
      guessEl.disabled = data.done;
      document.querySelector("button[type=submit]").disabled = data.done;
    }

    async function postJson(path, body) {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {})
      });
      return response.json();
    }

    document.getElementById("guess-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const guess = guessEl.value;
      guessEl.value = "";
      render(await postJson("/api/guess", { guess }));
      guessEl.focus();
    });

    document.getElementById("reset").addEventListener("click", async () => {
      outputEl.textContent = "";
      guessEl.disabled = false;
      document.querySelector("button[type=submit]").disabled = false;
      render(await postJson("/api/reset"));
      guessEl.focus();
    });

    document.getElementById("exit").addEventListener("click", async () => {
      try {
        await postJson("/api/exit");
      } catch (error) {
      }
      window.location.href = `${window.location.protocol}//${window.location.hostname}/apps/launcher`;
    });
  </script>
</body>
</html>
"""


def request_app_shutdown() -> None:
    print("hangman: exit requested", flush=True)
    timer = threading.Timer(
        0.75,
        lambda: subprocess.run(
            ["systemctl", "--user", "stop", APP_SERVICE],
            check=False,
            capture_output=True,
            text=True,
        ),
    )
    timer.daemon = True
    timer.start()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return
        self._send(200, HTML, "text/html; charset=utf-8")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_common_headers("text/plain")
        self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/api/guess":
            data = self._read_json()
            self._send_json(STATE.guess(str(data.get("guess", ""))))
            return
        if self.path == "/api/reset":
            print("hangman: reset", flush=True)
            self._send_json(STATE.reset())
            return
        if self.path == "/api/exit":
            request_app_shutdown()
            self._send_json({"message": "Shutdown requested."})
            return
        self.send_error(404)

    def log_message(self, format: str, *args: Any) -> None:
        print("hangman-http:", format % args, flush=True)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, data: dict[str, Any]) -> None:
        self._send(200, json.dumps(data), "application/json")

    def _send(self, status: int, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self._send_common_headers(content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_common_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")


def main() -> None:
    parser = argparse.ArgumentParser(description="Small Hangman app for the Amiga launcher.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8055)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"hangman: serving on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
