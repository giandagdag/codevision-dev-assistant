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

# Discover (Phase 3, spec 3.10). "codevision" is a placeholder until the work adapter exists.
ALLOWED_SEARCH_PROVIDERS = ("fake", "codevision")
DEFAULT_SEARCH_PROVIDER = "fake"
DEFAULT_SEARCH_TOP_K = 5
DEFAULT_DISCOVERY_MAX_ROUNDS = 3

# Enhance (Phase 9, spec 13). "bitbucket" is a placeholder until the work adapter exists (WF-1).
ALLOWED_MAIN_SOURCES = ("fake", "bitbucket")
DEFAULT_MAIN_SOURCE = "fake"
DEFAULT_FAKE_MAIN_DIR = "src/data/da_fake_main"

# Admin console (Phase 11, spec section 3).
ALLOWED_ADMIN_SOURCES = ("env", "codevision")
DEFAULT_ADMIN_SOURCE = "env"

# Senior inbox (Phase 10, spec section 9). Same switch as the Admin one.
ALLOWED_SENIOR_SOURCES = ("env", "codevision")
DEFAULT_SENIOR_SOURCE = "env"


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
    # Discover settings (Phase 3).
    search_provider: str = DEFAULT_SEARCH_PROVIDER
    search_top_k: int = DEFAULT_SEARCH_TOP_K
    discovery_max_rounds: int = DEFAULT_DISCOVERY_MAX_ROUNDS
    # Phase 4: the Tester's model. Empty means use the generator's model until the bake-off
    # decides (redesign M1).
    claude_tester_model: str = ""
    onprem_tester_model: str = ""
    # Phase 6: the CodeVision folder (the one that holds src/) the sandbox copies from (D-A).
    # None = not set; with the fake provider the made-up test folder is used instead.
    sandbox_source_dir: Path | None = None
    # Phase 9: where the server reads a file as it is on Bitbucket main (home: a fake folder).
    main_source: str = DEFAULT_MAIN_SOURCE
    fake_main_dir: Path = PROJECT_ROOT / DEFAULT_FAKE_MAIN_DIR
    # Phase 11: who may open the Admin console (WF-2 is open). "env" = the list below (home);
    # "codevision" = a placeholder that lets nobody in until the work source is decided.
    admin_source: str = DEFAULT_ADMIN_SOURCE
    admin_ids: tuple[str, ...] = ()
    # Phase 10: who may open the senior inbox. "env" = the list below plus every named or backup
    # senior in the active catalog; "codevision" = placeholder until the work source (WF-1).
    senior_source: str = DEFAULT_SENIOR_SOURCE
    senior_ids: tuple[str, ...] = ()
    # Phase 11 fix 2: the AI program tagger's cap per run, and the read-only SonarQube link.
    # All SonarQube values are empty by default (work fact WF-4); the token never prints.
    tagger_max_modules: int = 500
    sonar_url: str = ""
    sonar_token: str = field(default="", repr=False)
    sonar_profile: str = ""
    sonar_language: str = "py"
    # Phase 11 fix 3: where CodeVision's code lives and the Python that runs it (D-A). The work
    # embedder starts a helper process with them. Empty python = the DA's own.
    codevision_src: str = ""
    codevision_python: str = ""


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
        search_provider=_parse_search_provider(read("DA_SEARCH_PROVIDER")),
        search_top_k=_parse_whole_number(
            "DA_SEARCH_TOP_K", read("DA_SEARCH_TOP_K"), DEFAULT_SEARCH_TOP_K, 1, 20
        ),
        discovery_max_rounds=_parse_whole_number(
            "DA_DISCOVERY_MAX_ROUNDS",
            read("DA_DISCOVERY_MAX_ROUNDS"),
            DEFAULT_DISCOVERY_MAX_ROUNDS,
            1,
            5,
        ),
        claude_tester_model=read("DA_CLAUDE_TESTER_MODEL"),
        onprem_tester_model=read("DA_ONPREM_TESTER_MODEL"),
        sandbox_source_dir=_parse_folder(read("DA_SANDBOX_SOURCE_DIR")),
        main_source=_parse_main_source(read("DA_MAIN_SOURCE")),
        fake_main_dir=_parse_folder(read("DA_FAKE_MAIN_DIR"))
        or PROJECT_ROOT / DEFAULT_FAKE_MAIN_DIR,
        admin_source=_parse_admin_source(read("DA_ADMIN_SOURCE")),
        admin_ids=tuple(item.strip() for item in read("DA_ADMIN_IDS").split(",") if item.strip()),
        senior_source=_parse_senior_source(read("DA_SENIOR_SOURCE")),
        senior_ids=tuple(item.strip() for item in read("DA_SENIOR_IDS").split(",") if item.strip()),
        tagger_max_modules=_parse_whole_number(
            "DA_TAGGER_MAX_MODULES", read("DA_TAGGER_MAX_MODULES"), 500, 1, 100000
        ),
        sonar_url=read("DA_SONAR_URL").rstrip("/"),
        sonar_token=read("DA_SONAR_TOKEN"),
        sonar_profile=read("DA_SONAR_PROFILE"),
        sonar_language=read("DA_SONAR_LANGUAGE", "py"),
        codevision_src=read("DA_CODEVISION_SRC"),
        codevision_python=read("DA_CODEVISION_PYTHON"),
    )


def _parse_senior_source(raw: str) -> str:
    source = raw.lower() or DEFAULT_SENIOR_SOURCE
    if source not in ALLOWED_SENIOR_SOURCES:
        raise ConfigError(
            f"DA_SENIOR_SOURCE is '{source}', which is not allowed. "
            f"Use one of: {', '.join(ALLOWED_SENIOR_SOURCES)}. Set it in your .env file."
        )
    return source


def _parse_admin_source(raw: str) -> str:
    source = raw.lower() or DEFAULT_ADMIN_SOURCE
    if source not in ALLOWED_ADMIN_SOURCES:
        raise ConfigError(
            f"DA_ADMIN_SOURCE is '{source}', which is not allowed. "
            f"Use one of: {', '.join(ALLOWED_ADMIN_SOURCES)}. Set it in your .env file."
        )
    return source


def _read_auth_prefix(values: Mapping[str, str | None]) -> str:
    # Not stripped: the default "Bearer " needs its trailing space. Set but empty means "no
    # prefix", which a custom key header (for example x-api-key) needs.
    raw = values.get("DA_ONPREM_AUTH_PREFIX")
    return DEFAULT_ONPREM_AUTH_PREFIX if raw is None else raw


def _parse_folder(raw: str) -> Path | None:
    """A folder setting. Empty means not set. A relative path is read from the project folder."""
    if not raw.strip():
        return None
    path = Path(raw.strip()).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


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


def _parse_search_provider(raw: str) -> str:
    provider = (raw or DEFAULT_SEARCH_PROVIDER).lower()
    if provider not in ALLOWED_SEARCH_PROVIDERS:
        raise ConfigError(
            f"DA_SEARCH_PROVIDER is '{provider}', which is not allowed. "
            f"Use one of: {', '.join(ALLOWED_SEARCH_PROVIDERS)}. Set it in your .env file."
        )
    return provider


def _parse_main_source(raw: str) -> str:
    source = (raw or DEFAULT_MAIN_SOURCE).lower()
    if source not in ALLOWED_MAIN_SOURCES:
        raise ConfigError(
            f"DA_MAIN_SOURCE is '{source}', which is not allowed. "
            f"Use one of: {', '.join(ALLOWED_MAIN_SOURCES)}. Set it in your .env file."
        )
    return source


def _parse_whole_number(name: str, raw: str, default: int, low: int, high: int) -> int:
    if not raw:
        return default
    if not raw.isdigit() or not low <= int(raw) <= high:
        raise ConfigError(
            f"{name} is '{raw}', which is not allowed. "
            f"Use a whole number from {low} to {high}. Set it in your .env file."
        )
    return int(raw)


def _resolve_db_path(raw_path: str) -> Path:
    # A relative path means "inside the project folder", whichever folder the app is started from.
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path
