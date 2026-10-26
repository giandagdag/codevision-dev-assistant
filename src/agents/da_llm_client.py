"""The AI provider switch. The rest of the app only calls get_llm_client(role)."""

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from configs.da_config import ConfigError, Settings, load_settings
from da_logging import get_logger

logger = get_logger(__name__)

Role = Literal["generator", "reviewer"]
ROLES = ("generator", "reviewer")

# Room for a full request record in one reply (Phase 2), so it is not cut off.
CLAUDE_MAX_TOKENS = 2048


class LLMClientError(Exception):
    """The AI call itself failed. The message says what to check."""


@dataclass(frozen=True)
class LLMReply:
    text: str
    provider: str
    model: str


class LLMClient(Protocol):
    """What every provider offers, so callers never care which one is active."""

    def complete(self, prompt: str, system: str | None = None) -> LLMReply: ...


class FakeLLMClient:
    """Fixed, predictable replies. Never touches the network. Used by all tests."""

    def __init__(self, role: Role):
        self.model = f"fake-{role}"

    def complete(self, prompt: str, system: str | None = None) -> LLMReply:
        return LLMReply(text=f"[fake reply] {prompt[:40]}", provider="fake", model=self.model)


class ClaudeLLMClient:
    """Calls Claude through the official Anthropic library (home only, never installed at work)."""

    def __init__(self, model: str, api_key: str):
        anthropic = _import_anthropic()
        self.model = model
        self._api_error = anthropic.APIError
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, prompt: str, system: str | None = None) -> LLMReply:
        # The keyword arguments for messages.create, built up so "system" is only sent when given.
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": CLAUDE_MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            request["system"] = system
        try:
            response = self._client.messages.create(**request)
        except self._api_error as error:
            raise LLMClientError(
                f"The Claude call failed ({type(error).__name__}). "
                "Check the model name, your API key, and your network, then try again."
            ) from error
        # A reply can hold several parts; keep only the text parts.
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMReply(text=text, provider="claude", model=self.model)


def get_llm_client(role: Role, settings: Settings | None = None) -> LLMClient:
    """Return the client for the active provider, set up for this role."""
    if role not in ROLES:
        raise ValueError(f"Role '{role}' is not known. Use one of: {', '.join(ROLES)}.")
    settings = settings or load_settings()
    provider = settings.llm_provider

    if provider == "fake":
        client = FakeLLMClient(role)
    elif provider == "claude":
        client = _make_claude_client(role, settings)
    elif provider == "onprem":
        # Placeholder until we know how CodeVision calls Qwen and Llama (spec open question Q1).
        raise ConfigError(
            "The on-prem provider (Qwen/Llama) is not configured yet. "
            "Set DA_LLM_PROVIDER=fake or claude in your .env file for now."
        )
    else:
        # load_settings already blocks this; kept so a hand-built Settings cannot slip through.
        raise ConfigError(f"DA_LLM_PROVIDER '{provider}' is not supported.")

    logger.info("Using %s provider, model %s, for role %s", provider, client.model, role)
    return client


def _make_claude_client(role: Role, settings: Settings) -> ClaudeLLMClient:
    if not settings.anthropic_api_key:
        raise ConfigError(
            "ANTHROPIC_API_KEY is missing. Add it to your .env file, "
            "or set DA_LLM_PROVIDER=fake to work without Claude."
        )
    model_setting = f"DA_CLAUDE_{role.upper()}_MODEL"
    model = (
        settings.claude_generator_model if role == "generator" else settings.claude_reviewer_model
    )
    if not model:
        raise ConfigError(
            f"{model_setting} is missing. Add the Claude model name for the {role} role "
            "to your .env file."
        )
    return ClaudeLLMClient(model=model, api_key=settings.anthropic_api_key)


def _import_anthropic():
    # Imported here, not at the top of the file: the library is not installed at work, and the
    # app must still start there with the fake or onprem provider.
    try:
        import anthropic
    except ImportError as error:
        raise ConfigError(
            "The Claude provider needs the anthropic library, which is installed at home only "
            "(requirements-home.txt). Set DA_LLM_PROVIDER=fake or onprem in your .env file."
        ) from error
    return anthropic
