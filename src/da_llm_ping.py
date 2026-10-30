"""Checks that the AI can be reached, in seconds (Phase 2C, spec 2.4).

Like a PING or a quick CALL test before the real screen is used. Works with any provider.
It prints the server's host name only, never the full address and never the key.

Run: .venv\\Scripts\\python src\\da_llm_ping.py
"""

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from agents.da_llm_client import LLMClientError, get_llm_client
from configs.da_config import DEFAULT_ENV_FILE, ConfigError, Settings, load_settings

PING_SYSTEM = "Reply with the single word OK."
PING_PROMPT = "ping"
REPLY_PREVIEW_LENGTH = 200


@dataclass(frozen=True)
class PingResult:
    ok: bool
    provider: str
    model: str
    host: str
    seconds: float
    text: str = ""
    error: str = ""


def ping(settings: Settings) -> PingResult:
    """Send one tiny prompt with the generator client and time it. Never raises."""
    provider = settings.llm_provider
    host = _host_of(settings) if provider == "onprem" else "(none)"
    started = time.perf_counter()
    try:
        client = get_llm_client("generator", settings)
        reply = client.complete(PING_PROMPT, system=PING_SYSTEM)
    except (ConfigError, LLMClientError) as error:
        seconds = time.perf_counter() - started
        return PingResult(False, provider, "", host, seconds, error=str(error))
    return PingResult(
        True, reply.provider, reply.model, host, time.perf_counter() - started, text=reply.text
    )


def format_result(result: PingResult) -> list[str]:
    lines = [
        f"Provider: {result.provider}",
        f"Model: {result.model or '(not known)'}",
        f"Server: {result.host}",
        f"Time taken: {result.seconds:.2f} seconds",
    ]
    if result.ok:
        lines.append(f"Reply: {result.text[:REPLY_PREVIEW_LENGTH]}")
        lines.append("Ping OK.")
    else:
        lines.append(f"Ping failed: {result.error}")
    return lines


def _host_of(settings: Settings) -> str:
    # Host name only: the full address may hold an internal path.
    return urlparse(settings.onprem_url).hostname or "(unknown)"


def main(env_file: Path | None = DEFAULT_ENV_FILE) -> int:
    try:
        settings = load_settings(env_file=env_file)
    except ConfigError as error:
        print(f"Ping failed: {error}")
        return 1
    result = ping(settings)
    print("\n".join(format_result(result)))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
