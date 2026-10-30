"""The AI provider switch. The rest of the app only calls get_llm_client(role)."""

import warnings
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Any, Literal, Protocol

import requests
import urllib3

from configs.da_config import ConfigError, Settings, load_settings
from da_logging import get_logger

logger = get_logger(__name__)

Role = Literal["generator", "reviewer"]
ROLES = ("generator", "reviewer")

# Room for a full request record in one reply (Phase 2), so it is not cut off.
CLAUDE_MAX_TOKENS = 2048

# The on-prem request body (spec 2.1). temperature and top_p are the same as CodeVision's
# llm_config.py. If Friday's photos show different names or numbers, change them here.
ONPREM_TEMPERATURE = 0.2
ONPREM_TOP_P = 0.2
ONPREM_MAX_TOKENS = 2048
# Network retries (spec 2.1): 3 tries in total, waiting 2 then 4 seconds between them.
ONPREM_MAX_TRIES = 3
ONPREM_RETRY_WAITS = (2, 4)
# How much of a server's answer may appear in an error message.
ERROR_TEXT_LIMIT = 300


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


class _RetryableCallError(Exception):
    """A failure worth trying again (network trouble, 429, 5xx). Never leaves this file."""


class OnPremLLMClient:
    """Calls the work Qwen or Llama through the standard chat-completions format.

    Like a CALL to a remote program through its published parameter list: we send the agreed
    body, and read the answer from the agreed place. The three small functions below
    (_build_body, _build_headers, _read_reply) are the only places that know that format, so a
    difference found at work is a one-function change.
    """

    def __init__(self, settings: Settings):
        self.model = settings.onprem_model
        self._url = settings.onprem_url
        self._verify = settings.onprem_verify
        self._timeout = settings.onprem_timeout_seconds
        self._api_key = settings.onprem_api_key
        self._headers = _build_headers(
            settings.onprem_api_key, settings.onprem_auth_header, settings.onprem_auth_prefix
        )

    def complete(self, prompt: str, system: str | None = None) -> LLMReply:
        body = _build_body(self.model, prompt, system)
        for attempt in range(1, ONPREM_MAX_TRIES + 1):
            try:
                return self._send_once(body)
            except _RetryableCallError as error:
                if attempt == ONPREM_MAX_TRIES:
                    raise LLMClientError(
                        f"{error} It was tried {ONPREM_MAX_TRIES} times."
                    ) from None
                wait = ONPREM_RETRY_WAITS[attempt - 1]
                logger.warning(
                    "On-prem call failed (try %d of %d), trying again in %d seconds",
                    attempt,
                    ONPREM_MAX_TRIES,
                    wait,
                )
                sleep(wait)
        raise AssertionError("unreachable: the loop returns or raises")  # pragma: no cover

    def _send_once(self, body: dict[str, Any]) -> LLMReply:
        try:
            with warnings.catch_warnings():
                if self._verify is False:
                    # Our own WARNING at start-up says it; skip the library's repeat of it.
                    warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
                response = requests.post(
                    self._url,
                    json=body,
                    headers=self._headers,
                    timeout=self._timeout,
                    verify=self._verify,
                )
        # Order matters: SSLError and Timeout are also kinds of ConnectionError.
        except requests.exceptions.SSLError as error:
            raise LLMClientError(
                "The certificate check failed. Check DA_ONPREM_VERIFY "
                "(the bank's certificate file, or false for the prototype)."
            ) from error
        except requests.exceptions.Timeout:
            raise _RetryableCallError(
                f"The AI server did not answer within {self._timeout} seconds (timed out). "
                "Check the network, or raise DA_ONPREM_TIMEOUT_SECONDS."
            ) from None
        except requests.exceptions.ConnectionError:
            raise _RetryableCallError(
                "Cannot connect to the AI server. Check DA_ONPREM_URL and the network."
            ) from None
        except requests.exceptions.RequestException as error:
            raise LLMClientError(
                f"The AI call could not be made ({type(error).__name__}). "
                "Check that DA_ONPREM_URL is a full address starting with http:// or https://."
            ) from error
        return self._handle_response(response)

    def _handle_response(self, response: requests.Response) -> LLMReply:
        status = response.status_code
        if 200 <= status < 300:
            return _read_reply(response, self.model)
        if status in (401, 403):
            raise LLMClientError(
                f"The AI server refused the request (HTTP {status}). Check DA_ONPREM_API_KEY, "
                "DA_ONPREM_AUTH_HEADER and DA_ONPREM_AUTH_PREFIX."
            )
        if status == 404:
            raise LLMClientError(
                "The AI server says the address was not found (HTTP 404). "
                "Check the path at the end of DA_ONPREM_URL."
            )
        message = f"The AI server answered HTTP {status}: {self._safe_text(response.text)}"
        if status == 429 or status >= 500:
            raise _RetryableCallError(message)
        raise LLMClientError(message)

    def _safe_text(self, text: str) -> str:
        # Remove the key first, then cut, so a half-cut key can never be left behind (rule R1).
        if self._api_key:
            text = text.replace(self._api_key, "***")
        return text[:ERROR_TEXT_LIMIT]


def _build_body(model: str, prompt: str, system: str | None) -> dict[str, Any]:
    """The JSON body. A system message only when given, then the user message."""
    messages = [{"role": "system", "content": system}] if system else []
    messages.append({"role": "user", "content": prompt})
    return {
        "model": model,
        "messages": messages,
        "temperature": ONPREM_TEMPERATURE,
        "top_p": ONPREM_TOP_P,
        "max_tokens": ONPREM_MAX_TOKENS,
        "stream": False,
    }


def _build_headers(api_key: str, auth_header: str, auth_prefix: str) -> dict[str, str]:
    """Content type, plus one auth header when there is a key."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers[auth_header] = f"{auth_prefix}{api_key}"
    return headers


def _read_reply(response: requests.Response, fallback_model: str) -> LLMReply:
    """Read the text from choices[0].message.content, and the model name if the reply has one."""
    try:
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        model = data.get("model")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        text = None
    if not isinstance(text, str):
        raise LLMClientError(
            "The AI server answered, but not in the expected chat-completions shape "
            "(no choices[0].message.content). Check DA_ONPREM_URL points at the chat endpoint."
        )
    return LLMReply(
        text=text,
        provider="onprem",
        model=model if isinstance(model, str) and model else fallback_model,
    )


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
        client = _make_onprem_client(settings)
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


def _make_onprem_client(settings: Settings) -> OnPremLLMClient:
    # One model for both roles for now (decision D-B).
    required = (("DA_ONPREM_URL", settings.onprem_url), ("DA_ONPREM_MODEL", settings.onprem_model))
    for name, value in required:
        if not value:
            raise ConfigError(
                f"{name} is missing. Add it to your .env file, "
                "or set DA_LLM_PROVIDER=fake to work without the work LLM."
            )
    verify = settings.onprem_verify
    if isinstance(verify, str) and not Path(verify).is_file():
        raise ConfigError(
            f"DA_ONPREM_VERIFY points to '{verify}', which does not exist. "
            "Use true, false, or the path to the certificate file."
        )
    if verify is False:
        logger.warning("Certificate check is OFF. Use only for the prototype.")
    return OnPremLLMClient(settings)


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
