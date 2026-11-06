"""Petits outils de texte partagés par l'écoute et la voix."""
from __future__ import annotations

import re
import unicodedata


def plat(texte: str) -> str:
    """Minuscules, sans accents ni ponctuation superflue."""
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")
_CODE = re.compile(r"```.*?```", re.S)


def a_dire(texte: str, maximum: int = 600) -> str:
    """Réponse écrite -> phrase à dire : ni markdown, ni émoji, ni liste, ni lien, `maximum` caractères au plus
    (coupé à la fin d'une phrase quand c'est possible). Le ton « à dire » se demande aussi au modèle ; ceci garantit
    qu'une réponse mise en forme ne soit pas lue symbole par symbole."""
    t = _CODE.sub(" ", texte or "")
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"^\s{0,3}(?:#{1,6}|[-*+>]|\d+[.)])\s+", "", t, flags=re.M)
    t = re.sub(r"[*_`~|]+", "", t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= maximum:
        return t
    coupe = t[:maximum]
    fin = max(coupe.rfind(". "), coupe.rfind("! "), coupe.rfind("? "))
    return coupe[:fin + 1] if fin > maximum // 2 else coupe
