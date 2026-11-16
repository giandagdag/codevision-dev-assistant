"""Read-only SonarQube client (fix 11-2, section 4). GET only, two calls, no AI.

The token is the user name with an empty password (how SonarQube expects it). It is never put in
a message or a log line.
"""

import requests

from configs.da_config import Settings

TIMEOUT_SECONDS = 15
MAX_PAGES = 20
PAGE_SIZE = 500
NOT_CONNECTED = "Not connected yet (#61)"


class SonarError(Exception):
    """Carries a plain message that is safe to show."""


def sonar_configured(settings: Settings) -> bool:
    return bool(settings.sonar_url and settings.sonar_token)


def _get(session, settings: Settings, path: str, params: dict) -> dict:
    try:
        reply = session.get(
            settings.sonar_url + path,
            params=params,
            auth=(settings.sonar_token, ""),
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        raise SonarError("SonarQube did not answer") from error  # error text may hold the URL
    if reply.status_code in (401, 403):
        raise SonarError("The token was refused")
    if reply.status_code != 200:
        raise SonarError("SonarQube did not answer")
    return reply.json()


def _profile_key(session, settings: Settings) -> tuple[str, str]:
    found = _get(
        session, settings, "/api/qualityprofiles/search", {"language": settings.sonar_language}
    )["profiles"]
    for profile in found:
        if settings.sonar_profile and profile.get("name") == settings.sonar_profile:
            return profile["key"], profile["name"]
        if not settings.sonar_profile and profile.get("isDefault"):
            return profile["key"], profile["name"]
    raise SonarError("Profile not found")


def fetch_active_rules(settings: Settings, session=None) -> tuple[str, list[dict]]:
    """(profile name, rules as key / name / severity). Raises SonarError with a plain message."""
    if not sonar_configured(settings):
        raise SonarError(NOT_CONNECTED)
    session = session or requests.Session()
    key, name = _profile_key(session, settings)
    rules: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        data = _get(
            session,
            settings,
            "/api/rules/search",
            {
                "activation": "true",
                "qprofile": key,
                "f": "name,severity,actives",
                "ps": PAGE_SIZE,
                "p": page,
            },
        )
        rules += [
            {"key": r["key"], "name": r.get("name", ""), "severity": r.get("severity", "")}
            for r in data.get("rules", [])
        ]
        if page * PAGE_SIZE >= data.get("total", 0):
            break
    return name, rules
