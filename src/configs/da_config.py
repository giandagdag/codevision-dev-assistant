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


class ConfigError(Exception):
    """A setup problem the developer can fix. The message says how."""


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    claude_generator_model: str
    claude_reviewer_model: str
    db_path: Path
    # repr=False keeps the key out of print() and log output (rule R2).
    anthropic_api_key: str = field(default="", repr=False)


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
        anthropic_api_key=read("ANTHROPIC_API_KEY"),
    )


def _resolve_db_path(raw_path: str) -> Path:
    # A relative path means "inside the project folder", whichever folder the app is started from.
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path
