"""A pretend work LLM server, for trying the onprem provider at home (Phase 2C, spec 2.5).

It answers the standard chat-completions POST in the same shape as the real server, using the
scripted Understand replies, so the whole screen runs with DA_LLM_PROVIDER=onprem and no real AI.
Like a dummy remote program on a test LPAR that answers the same way as the real one.

Standard library only for the server itself. Listens on 127.0.0.1 only (rule R13).

Run: .venv\\Scripts\\python src\\web\\da_fake_onprem_server.py [--mode normal|bad-json|error]
Then in .env: DA_LLM_PROVIDER=onprem, DA_ONPREM_URL=http://127.0.0.1:8070/v1/chat/completions,
DA_ONPREM_MODEL=fake-qwen
"""

import argparse
import json
import os
import re
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Started as a script from src/web, Python only sees this folder. Add src so the imports work.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import dotenv_values  # noqa: E402

from agents.da_approach_agent import TASK_MARKERS, ScriptedApproachClient  # noqa: E402
from agents.da_build_agent import (  # noqa: E402
    CODE_MARKER,
    CONTRACT_MARKER,
    TESTS_MARKER,
    scripted_build_reply,
)
from agents.da_code_tests import CODE_TESTS_MARKER  # noqa: E402
from agents.da_discover_agent import TASK_MARKER, ScriptedDiscoverClient  # noqa: E402
from agents.da_enhance_agent import (  # noqa: E402
    CORRECT_MARKER,
    FIX_MARKER,
    NET_MARKER,
    TODAY_MARKER,
)
from agents.da_refine_agent import (  # noqa: E402
    LANE_MARKER,
    OWN_TEST_MARKER,
    REPRO_MARKER,
    REVISION_MARKER,
)
from agents.da_tester_agent import (  # noqa: E402
    CASE_MARKER,
    CASE_STEP,
    PLAN_MARKER,
    PLAN_STEP,
    ScriptedTesterClient,
)
from agents.da_tester_review import REVIEW_MARKER  # noqa: E402
from agents.da_understand_agent import FAKE_SCRIPT_FILE, ScriptedUnderstandClient  # noqa: E402
from agents.da_understand_flow import (  # noqa: E402
    CORRECTION_QUESTION,
    FORM_QUESTION,
    OPENING_QUESTION,
    OPTIONAL_QUESTION,
    QUESTIONS,
)
from configs.da_config import DEFAULT_ENV_FILE  # noqa: E402

HOST = "127.0.0.1"
PORT = 8070
CHAT_PATH = "/v1/chat/completions"
MODES = ("normal", "bad-json", "error")
KEY_SETTING = "DA_FAKE_ONPREM_KEY"


# The scripted entry for each question the engine can ask. Picking by the question in the
# prompt (not by counting calls) keeps the server in step through retries and restarts.
def _decision_questions() -> dict[str, str]:
    """The material question the script raises at question 4. After the developer decides it, the
    engine asks again with that question, and the script answers with its "decision" entry."""
    script = json.loads(FAKE_SCRIPT_FILE.read_text(encoding="utf-8"))
    return {a["text"]: "decision" for a in script["question_4"]["ambiguities"] if a["material"]}


SCRIPT_STEPS: dict[str, str] = {
    OPENING_QUESTION: "opening",
    FORM_QUESTION: "form",
    **{text: f"question_{number}" for number, text in QUESTIONS.items()},
    OPTIONAL_QUESTION: "optional",
    CORRECTION_QUESTION: "correction",
    **_decision_questions(),
}
_QUESTION_LINE = re.compile(r"^The question being answered: (.*)$", re.MULTILINE)
# The engine adds this to the prompt when it asks again after a rejected reply.
RETRY_MARKER = "Your previous reply was not accepted"
NOT_JSON_REPLY = "Sorry, here is my answer in words and not in JSON."


# Phase 4: the three Generator calls and the two Tester calls, told apart by the task line each
# prompt carries. The Generator and the Tester replies come from the same scripted Excel example
# as the fake provider, so they cite the Discover hit numbers and criterion IDs in the prompt.
_APPROACH_CALLS = {marker: call for call, marker in TASK_MARKERS.items()}


# Phase 6: the three Build calls (contract, tests, one code file), and the Phase 7 Tester review of
# the code, told apart by the task line each
# prompt carries on a line of its own. The same scripted replies as the fake provider answer them,
# so a build through the onprem connector follows the same path as the fake one.
_BUILD_LINES = tuple(
    re.compile(rf"^{re.escape(marker)}$", re.MULTILINE)
    for marker in (
        CONTRACT_MARKER,
        TESTS_MARKER,
        CODE_MARKER,
        REVIEW_MARKER,
        CODE_TESTS_MARKER,  # Fix D1: the code tests written after the code passes
        # Phase 8: the Refine calls are answered by the same scripted code.
        LANE_MARKER,
        REVISION_MARKER,
        REPRO_MARKER,
        OWN_TEST_MARKER,
        # Phase 9: the today-draft and safety-net calls of Enhance.
        TODAY_MARKER,
        NET_MARKER,
        FIX_MARKER,
        CORRECT_MARKER,
    )
)


def _build_reply(prompt: str, mode: str) -> str | None:
    """The reply for a Build prompt, or None if the prompt is not one."""
    if not any(line.search(prompt) for line in _BUILD_LINES):
        return None
    return NOT_JSON_REPLY if mode == "bad-json" else scripted_build_reply(prompt)


def _approach_reply(prompt: str, mode: str) -> str | None:
    """The reply for an Approach or Tester prompt, or None if the prompt is neither."""
    for marker, call in _APPROACH_CALLS.items():
        if marker in prompt:
            return (
                NOT_JSON_REPLY
                if mode == "bad-json"
                else (ScriptedApproachClient(call).complete(prompt).text)
            )
    for marker, step in ((CASE_MARKER, CASE_STEP), (PLAN_MARKER, PLAN_STEP)):
        if marker in prompt:
            return (
                NOT_JSON_REPLY
                if mode == "bad-json"
                else (ScriptedTesterClient(step).complete(prompt).text)
            )
    return None


def reply_text(prompt: str, mode: str) -> str:
    """The text the pretend model sends back for this prompt."""
    build = _build_reply(prompt, mode)
    if build is not None:
        return build
    approach = _approach_reply(prompt, mode)
    if approach is not None:
        # bad-json is bad on every try here, as in Discover, so the failure paths can be seen.
        return approach
    if TASK_MARKER in prompt:
        # A Discover prompt (Phase 3). bad-json is bad on every try here, so the app's fallback
        # to plain search results can be seen (unlike Understand, whose retry then passes).
        if mode == "bad-json":
            return NOT_JSON_REPLY
        return ScriptedDiscoverClient("good").complete(prompt).text
    match = _QUESTION_LINE.search(prompt)
    if match is None:
        return "OK"  # not an Understand prompt, for example the ping
    if mode == "bad-json" and RETRY_MARKER not in prompt:
        # The first try of each turn is bad; the engine's retry carries the marker, so it passes.
        return NOT_JSON_REPLY
    step = SCRIPT_STEPS.get(match.group(1).strip(), "unknown")
    return ScriptedUnderstandClient(step).complete(prompt).text


class FakeOnPremServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, mode: str, key: str):
        super().__init__((HOST, port), _Handler)
        self.mode = mode
        self.key = key
        # What came in, so tests can check the request the client really sent.
        self.seen: list[dict] = []

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.server_port}{CHAT_PATH}"


class _Handler(BaseHTTPRequestHandler):
    server: FakeOnPremServer

    def do_POST(self) -> None:  # the name http.server looks for
        if not self.path.split("?")[0].endswith("/chat/completions"):
            return self._send(404, {"error": {"message": "Not found"}})
        if self.server.key and self.headers.get("Authorization") != f"Bearer {self.server.key}":
            return self._send(401, {"error": {"message": "Invalid or missing key"}})
        if self.server.mode == "error":
            return self._send(500, {"error": {"message": "Pretend server error"}})
        body = self._read_body()
        if body is None:
            return self._send(400, {"error": {"message": "Body must be JSON with messages"}})
        self.server.seen.append(
            {"path": self.path, "headers": dict(self.headers.items()), "body": body}
        )
        prompt = next(
            (m.get("content", "") for m in reversed(body["messages"]) if m.get("role") == "user"),
            "",
        )
        self._send(
            200,
            {
                "id": "fake-completion",
                "object": "chat.completion",
                "model": body.get("model", "fake-qwen"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": reply_text(prompt, self.server.mode),
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    def _read_body(self) -> dict | None:
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except ValueError:
            return None
        if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
            return None
        return body

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@contextmanager
def running_fake_onprem_server(
    mode: str = "normal", key: str = "", port: int = 0
) -> Iterator[FakeOnPremServer]:
    """Run the pretend server in a background thread. Port 0 picks a free port (tests, smoke)."""
    server = FakeOnPremServer(port, mode, key)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _read_key() -> str:
    # Same rule as load_settings: the real environment wins over the .env file.
    value = os.environ.get(KEY_SETTING)
    if value is None and Path(DEFAULT_ENV_FILE).exists():
        value = dotenv_values(DEFAULT_ENV_FILE).get(KEY_SETTING)
    return (value or "").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pretend work LLM server (home testing only).")
    parser.add_argument("--mode", choices=MODES, default="normal")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args(argv)
    key = _read_key()

    with running_fake_onprem_server(args.mode, key, args.port) as server:
        print(f"Pretend work LLM running at {server.url} (mode {args.mode}).")
        print(f"Requests need the key from {KEY_SETTING}." if key else "No key needed.")
        print("Press Ctrl+C to stop.")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            print("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
