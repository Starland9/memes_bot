"""Topic filter: never meme a tragedy or a violent story."""

from __future__ import annotations

import re

BLOCKED_TERMS: tuple[str, ...] = (
    # French
    "accident",
    "agress",
    "attentat",
    "blessé",
    "catastrophe",
    "corps",
    "crime",
    "décès",
    "deces",
    "drame",
    "émeute",
    "emeute",
    "épidémie",
    "epidemie",
    "famine",
    "fusillade",
    "génocide",
    "genocide",
    "guerre",
    "harcèlement",
    "harcelement",
    "inondation",
    "incendie",
    "manifestation",
    "massacre",
    "meurtre",
    "mort",
    "morte",
    "naufrage",
    "otage",
    "pandémie",
    "pandemie",
    "pédophil",
    "pedophil",
    "suicid",
    "séisme",
    "seisme",
    "terroris",
    "tremblement",
    "tuer",
    "tué",
    "tuée",
    "tueur",
    "victime",
    "viol",
    "violence",
    # English
    "attack",
    "bomb",
    "casualties",
    "crash",
    "dead",
    "death",
    "earthquake",
    "emergency",
    "famine",
    "flood",
    "genocide",
    "hostage",
    "hurricane",
    "killed",
    "kills",
    "murder",
    "outbreak",
    "rape",
    "shooting",
    "shooter",
    "suicide",
    "tragedy",
    "victim",
    "war",
)


def _pattern(term: str) -> re.Pattern[str]:
    """Match a term at the start of a word, never inside another word.

    Short ASCII terms ("war", "dead", "viol") only match the word itself or its
    plural, so "software" and "deadline" are not flagged.
    """
    escaped = re.escape(term)
    if term.isascii() and len(term) <= 4:
        return re.compile(rf"\b{escaped}(?:s|es)?\b", re.IGNORECASE)
    return re.compile(rf"\b{escaped}\w*", re.IGNORECASE)


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (term, _pattern(term)) for term in BLOCKED_TERMS
)


def blocked_term(title: str) -> str | None:
    """Return the first blocked term found in *title*, if any."""
    for term, pattern in _PATTERNS:
        if pattern.search(title):
            return term
    return None
