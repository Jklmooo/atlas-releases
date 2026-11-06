"""Réglages du module : le cœur les garde (fenêtre Réglages > Modules) et les passe en variables `ATLAS_REGLAGE_<CLE>`.
Changer un réglage relance le programme : il les lit donc une fois, au démarrage. Sans cœur, les valeurs par défaut."""
from __future__ import annotations

import os
from typing import Any

DEFAUT: dict[str, Any] = {
    # écoute
    "modele": "small", "calcul": "int8", "langue": "fr", "micro": "",
    # voix
    "moteur": "say", "voix": "Aurélie (Enhanced)",
}


class Reglages:
    def __init__(self, environnement: dict[str, str] | None = None) -> None:
        env = os.environ if environnement is None else environnement
        self._valeurs = {cle: env.get(f"ATLAS_REGLAGE_{cle.upper()}", defaut) for cle, defaut in DEFAUT.items()}
        self._valeurs["telechargement"] = False   # un modèle ne se télécharge que par le bouton « Installer »
        self._valeurs["micro"] = self._valeurs["micro"] or None

    def lire(self) -> dict[str, Any]:
        return self._valeurs

    def __getitem__(self, cle: str) -> Any:
        return self._valeurs[cle]
