"""Fix G5 part 1 (P1): the plain-code safety check for a new request.

It looks for two things in the request text and the answers: broad destruction (drop all tables)
and harmful intent (revenge on a boss). No AI here: the same text always gives the same answer,
like a CL program checking a value before it calls the real work.
"""

import re
from dataclasses import dataclass

KIND_NONE = "none"
KIND_DESTRUCTIVE = "destructive"
KIND_INTENT = "intent"
KIND_BOTH = "both"

# All the word lists live here, in one place.
DESTRUCTIVE_VERBS = ("drop", "truncate", "delete", "erase", "purge")
DESTRUCTIVE_SCOPE = ("all", "every", "entire", "whole", "schema", "database")
DESTRUCTIVE_PHRASES = (
    "wipe",
    "disable logging",
    "disable audit",
    "disable the audit",
    "disable controls",
    "turn off logging",
    "turn off the audit",
)
INTENT_PHRASES = (
    "hate",
    "revenge",
    "get back at",
    "punish",
    "sabotage",
    "angry at",
)
PEOPLE_WORDS = ("boss", "manager", "colleague", "coworker", "co-worker")
NEGATIVE_WORDS = ("hate", "stupid", "idiot", "useless", "ruin", "hurt", "revenge", "angry")
# Distance (in words) inside which a person word and a negative word count as one thought.
PERSON_NEAR_WORDS = 6


@dataclass(frozen=True)
class GateScan:
    kind: str
    words: tuple[str, ...]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_'-]+", text.lower())


def _has_phrase(text_lower: str, phrase: str) -> bool:
    # Whole words only, so "hate" does not match "whatever" and "all" does not match "small".
    return re.search(rf"\b{re.escape(phrase)}\b", text_lower) is not None


def _destructive_words(text: str) -> list[str]:
    words = _words(text)
    found = [p for p in DESTRUCTIVE_PHRASES if _has_phrase(text.lower(), p)]
    verbs = [w for w in words if w in DESTRUCTIVE_VERBS]
    scopes = [w for w in words if w in DESTRUCTIVE_SCOPE]
    if verbs and scopes:
        found += list(dict.fromkeys(verbs)) + list(dict.fromkeys(scopes))
    return found


def _intent_words(text: str) -> list[str]:
    lower = text.lower()
    found = [p for p in INTENT_PHRASES if _has_phrase(lower, p)]
    words = _words(text)
    for index, word in enumerate(words):
        if word not in PEOPLE_WORDS:
            continue
        near = words[max(0, index - PERSON_NEAR_WORDS): index + PERSON_NEAR_WORDS + 1]
        negatives = [n for n in NEGATIVE_WORDS if n in near]
        if negatives:
            found += [word, *negatives]
    return list(dict.fromkeys(found))


def scan(text: str) -> GateScan:
    """Return none, destructive, intent or both, with the words that matched."""
    destructive = _destructive_words(text)
    intent = _intent_words(text)
    if destructive and intent:
        kind = KIND_BOTH
    elif intent:
        kind = KIND_INTENT
    elif destructive:
        kind = KIND_DESTRUCTIVE
    else:
        kind = KIND_NONE
    return GateScan(kind, tuple(dict.fromkeys(destructive + intent)))
