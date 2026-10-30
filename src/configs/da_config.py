"""Developer Assistant settings, read from the .env file and the environment."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"

ALLOWED_PROVIDERS = ("fake", "claude", "onprem")
DEFAULT_PROVIDER = "fake"
DEFAULT_DB_PATH = "data/devassist.db"
# Stands in for the logged-in developer until CodeVision's login is connected (spec Q5).
DEFAULT_DEVELOPER_ID = "dev-home-01"

# The work LLM connector (Phase 2C, spec 2.2). Defaults follow the standard chat-completions
# format; the Friday photos may change them (spec section 6).
DEFAULT_ONPREM_AUTH_HEADER = "Authorization"
DEFAULT_ONPREM_AUTH_PREFIX = "Bearer "
DEFAULT_ONPREM_TIMEOUT_SECONDS = 120


class ConfigError(Exception):
    """A setup problem the developer can fix. The message says how."""


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    claude_generator_model: str
    claude_reviewer_model: str
    db_path: Path
    developer_id: str = DEFAULT_DEVELOPER_ID
    # repr=False keeps the key out of print() and log output (rule R2).
    anthropic_api_key: str = field(default="", repr=False)
    # The onprem (Qwen/Llama) settings. URL and model are required only when onprem is chosen,
    # which get_llm_client checks. The key is hidden from printouts, like the Claude key.
    onprem_url: str = ""
    onprem_model: str = ""
    onprem_api_key: str = field(default="", repr=False)
    onprem_auth_header: str = DEFAULT_ONPREM_AUTH_HEADER
    onprem_auth_prefix: str = DEFAULT_ONPREM_AUTH_PREFIX
    # True = check certificates, False = do not (prototype only), a string = path to a
    # certificate file.
    onprem_verify: bool | str = True
    onprem_timeout_seconds: int = DEFAULT_ONPREM_TIMEOUT_SECONDS
    # None = do not send max_tokens (CodeVision does not). A number = send it (spec P13 2.1).
    onprem_max_tokens: int | None = None


def load_settings(
    env_file: Path | None = DEFAULT_ENV_FILE,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Read settings, apply defaults, and stop with a plain message if a value is not allowed.

    Values in the real environment win over values in the .env file.
    Tests pass env_file=None and their own environ, so they never read a real .env.
    """
    values: dict[str, str | None] = {}
    if env_file is not None and Path(env_file).exists():
        values.update(dotenv_values(env_file))
    values.update(os.environ if environ is None else environ)

    def read(name: str, default: str = "") -> str:
        return (values.get(name) or default).strip()

    provider = read("DA_LLM_PROVIDER", DEFAULT_PROVIDER).lower()
    if provider not in ALLOWED_PROVIDERS:
        raise ConfigError(
            f"DA_LLM_PROVIDER is '{provider}', which is not allowed. "
            f"Use one of: {', '.join(ALLOWED_PROVIDERS)}. Set it in your .env file."
        )

    return Settings(
        llm_provider=provider,
        claude_generator_model=read("DA_CLAUDE_GENERATOR_MODEL"),
        claude_reviewer_model=read("DA_CLAUDE_REVIEWER_MODEL"),
        db_path=_resolve_db_path(read("DA_DB_PATH", DEFAULT_DB_PATH)),
        developer_id=read("DA_DEVELOPER_ID", DEFAULT_DEVELOPER_ID),
        anthropic_api_key=read("ANTHROPIC_API_KEY"),
        onprem_url=read("DA_ONPREM_URL"),
        onprem_model=read("DA_ONPREM_MODEL"),
        onprem_api_key=read("DA_ONPREM_API_KEY"),
        onprem_auth_header=read("DA_ONPREM_AUTH_HEADER", DEFAULT_ONPREM_AUTH_HEADER),
        onprem_auth_prefix=_read_auth_prefix(values),
        onprem_verify=_parse_verify(read("DA_ONPREM_VERIFY")),
        onprem_timeout_seconds=_parse_timeout(read("DA_ONPREM_TIMEOUT_SECONDS")),
        onprem_max_tokens=_parse_max_tokens(read("DA_ONPREM_MAX_TOKENS")),
    )


def _read_auth_prefix(values: Mapping[str, str | None]) -> str:
    # Not stripped: the default "Bearer " needs its trailing space. Set but empty means "no
    # prefix", which a custom key header (for example x-api-key) needs.
    raw = values.get("DA_ONPREM_AUTH_PREFIX")
    return DEFAULT_ONPREM_AUTH_PREFIX if raw is None else raw


def _parse_verify(raw: str) -> bool | str:
    if raw.lower() in ("", "true"):
        return True
    if raw.lower() == "false":
        return False
    return raw  # a certificate file path; whether it exists is checked when the client is made


def _parse_timeout(raw: str) -> int:
    if not raw:
        return DEFAULT_ONPREM_TIMEOUT_SECONDS
    if not raw.isdigit() or int(raw) < 1:
        raise ConfigError(
            f"DA_ONPREM_TIMEOUT_SECONDS is '{raw}', which is not allowed. "
            "Use a whole number of seconds, 1 or more. Set it in your .env file."
        )
    return int(raw)


def _parse_max_tokens(raw: str) -> int | None:
    if not raw:
        return None
    if not raw.isdigit() or int(raw) < 1:
        raise ConfigError(
            f"DA_ONPREM_MAX_TOKENS is '{raw}', which is not allowed. "
            "Leave it empty, or use a whole number, 1 or more. Set it in your .env file."
        )
    return int(raw)


def _resolve_db_path(raw_path: str) -> Path:
    # A relative path means "inside the project folder", whichever folder the app is started from.
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path
