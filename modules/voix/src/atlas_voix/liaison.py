"""Ce que le module échange avec Atlas : des lignes JSON, une par message, sur sa sortie et son entrée.

Sortie : {"texte": "…"} est une demande (voir `src/modules.rs`). Entrée : {"texte", "erreur"} est la réponse d'Atlas.
Les états du réacteur, le muet et les réglages passeront par la même liaison une fois le protocole fixé avec le socle ;
le reste du module ne parle qu'à cette classe, pour que ce changement reste ici."""
from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable, Iterator
from typing import Any

_VERROU = threading.Lock()


def ecrire(message: dict[str, Any]) -> None:
    with _VERROU:
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def demander(texte: str) -> None:
    ecrire({"texte": texte})


def recus() -> Iterator[dict[str, Any]]:
    for ligne in sys.stdin:
        try:
            message = json.loads(ligne)
        except ValueError:
            continue
        if isinstance(message, dict):
            yield message


def journal(*morceaux: Any) -> None:
    """Sur la sortie d'erreur, jamais sur la sortie : elle est réservée aux messages. Jamais de texte dicté."""
    print(*morceaux, file=sys.stderr, flush=True)
