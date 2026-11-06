"""Les modèles de transcription déjà présents sur la machine (cache Hugging Face), proposés à l'installation, comme
Ollama liste ses modèles : faster-whisper partout, Parakeet (MLX) sur un Mac à puce Apple. Chaque modèle dit son moteur.

Rien ne se télécharge ici : on lit des dossiers. Un modèle absent ne se télécharge que si la personne l'a choisi
(réglage `telechargement`), jamais par défaut."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROPOSE = "small"          # notre proposition : bon compromis vitesse et qualité en français sur CPU
CALCUL = "int8"
LANGUE = "fr"
DEPOT = "Systran/faster-whisper-{}"
WHISPER, PARAKEET = "whisper", "parakeet"
# Les modèles proposés : (moteur, dépôt Hugging Face, ce que l'installation télécharge). Les tailles sont approximatives.
CONNUS = {
    "tiny": (WHISPER, "Systran/faster-whisper-tiny", "≈ 75 Mo"),
    "base": (WHISPER, "Systran/faster-whisper-base", "≈ 145 Mo"),
    "small": (WHISPER, "Systran/faster-whisper-small", "≈ 485 Mo"),
    "medium": (WHISPER, "Systran/faster-whisper-medium", "≈ 1,5 Go"),
    "large-v3-turbo": (WHISPER, "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "≈ 1,6 Go"),
    "large-v3": (WHISPER, "Systran/faster-whisper-large-v3", "≈ 3 Go"),
    "parakeet-v3": (PARAKEET, "mlx-community/parakeet-tdt-0.6b-v3", "≈ 1,2 Go"),   # 25 langues européennes, dont le français
}
# Ce qu'il faut savoir pour choisir, dit à côté du nom dans les réglages (mesuré sur un Mac M-série, voir docs/essais.md d'Atlas).
DETAILS = {
    "tiny": "le plus léger, se trompe souvent",
    "base": "léger, moins juste",
    "small": "juste et rapide, ≈ 1 s par phrase",
    "medium": "plus juste, plus lent",
    "large-v3-turbo": "très juste, ≈ 4 s par phrase",
    "large-v3": "le plus juste, lent",
    "parakeet-v3": "le plus rapide, ≈ 0,5 s ; noms propres moins sûrs",
}
NOMS = {WHISPER: "Whisper", PARAKEET: "Parakeet (puce Apple)"}
FICHIERS = {WHISPER: ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"],
            PARAKEET: ["config.json", "*.safetensors"]}
# Ce qui rend un instantané du cache complet, par moteur.
COMPLET = {WHISPER: ("model.bin", "config.json"), PARAKEET: ("model.safetensors", "config.json")}


def parakeet_possible() -> bool:
    """Parakeet passe par MLX : seulement un Mac à puce Apple."""
    import platform
    return sys.platform == "darwin" and platform.machine() == "arm64"


def possible(moteur: str) -> bool:
    return moteur != PARAKEET or parakeet_possible()


def moteur_de(modele: str) -> str:
    """Le moteur d'un modèle : par son nom connu, sinon par son dépôt ou son dossier."""
    if modele in CONNUS:
        return CONNUS[modele][0]
    return PARAKEET if "parakeet" in modele.lower() else WHISPER


def cache() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    base = os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
    return Path(base) / "hub"


def presents() -> list[dict[str, str]]:
    """Modèles complets du cache, des moteurs possibles ici :
    {"id": "small", "depot": "Systran/faster-whisper-small", "chemin": "<snapshot>", "moteur": "whisper"}."""
    par_depot = {depot: i for i, (_, depot, _) in CONNUS.items()}
    trouves = []
    for motif, moteur in (("models--*faster-whisper-*", WHISPER), ("models--*parakeet*", PARAKEET)):
        if not possible(moteur):
            continue
        for dossier in sorted(cache().glob(motif)):
            snapshots = sorted((dossier / "snapshots").glob("*")) if (dossier / "snapshots").is_dir() else []
            complet = [s for s in snapshots if all((s / f).exists() for f in COMPLET[moteur])]
            if not complet:
                continue
            auteur, _, nom = dossier.name.removeprefix("models--").partition("--")
            depot = f"{auteur}/{nom}"
            ident = par_depot.get(depot) or (nom.removeprefix("faster-whisper-") if moteur == WHISPER else nom)
            trouves.append({"id": ident, "depot": depot, "chemin": str(complet[-1]), "moteur": moteur})
    return trouves


def propositions() -> dict:
    """Ce qu'on montre à l'installation : les modèles déjà là, et notre choix par défaut (présent ou non)."""
    la = presents()
    return {"presents": la, "propose": PROPOSE, "propose_present": any(m["id"] == PROPOSE for m in la),
            "autres_connus": [m for m, (moteur, _, _) in CONNUS.items() if possible(moteur) and m not in {x["id"] for x in la}]}


def liste_valeurs() -> list[dict]:
    """Le réglage « modèle » : chaque modèle dit sa famille, ce qu'il vaut, s'il est sur la machine (il peut alors
    s'enlever), et sa taille s'il faut le télécharger."""
    la = {m["id"]: m for m in presents()}
    libelle = lambda i: ("Parakeet v3" if i == "parakeet-v3" else i) + (" (proposé)" if i == PROPOSE else "")
    valeurs = [{"valeur": i, "libelle": libelle(i), "groupe": NOMS[moteur], "detail": DETAILS.get(i, ""),
                "installe": i in la, "supprimable": i in la, "taille": taille}
               for i, (moteur, _, taille) in CONNUS.items() if possible(moteur)]
    valeurs += [{"valeur": i, "libelle": i, "groupe": NOMS[m["moteur"]], "detail": m["depot"], "installe": True, "supprimable": True}
                for i, m in sorted(la.items()) if i not in CONNUS]
    return valeurs


def supprimer(modele: str) -> None:
    """Enlève un modèle du cache Hugging Face, à la demande de la personne : tout son dossier (il ne sert qu'à lui)."""
    import shutil
    trouve = next((m for m in presents() if modele in (m["id"], m["depot"])), None)
    if trouve is None:
        raise ValueError("modèle absent de la machine")
    dossier = cache() / f"models--{trouve['depot'].replace('/', '--')}"
    if dossier.parent != cache() or not dossier.name.startswith("models--"):
        raise ValueError("dossier inattendu")
    shutil.rmtree(dossier)
    from atlas_voix import cachehf
    cachehf.purger(cache())   # ses gros fichiers vivent dans le dossier partagé : sans cela, l'espace n'est pas rendu


def installer(modele: str, avancement) -> None:
    """Télécharge un modèle choisi par la personne (jamais de lui-même). `avancement(0 à 1)` est appelé pendant le
    téléchargement : on mesure ce qui est arrivé dans le cache, sur le total annoncé par le dépôt."""
    import threading
    from huggingface_hub import HfApi, snapshot_download

    if modele not in CONNUS or not possible(CONNUS[modele][0]):
        raise ValueError("modèle inconnu")
    moteur, depot, _ = CONNUS[modele]
    info = HfApi().model_info(depot, files_metadata=True)
    import fnmatch
    total = sum(f.size or 0 for f in info.siblings if any(fnmatch.fnmatch(f.rfilename, m) for m in FICHIERS[moteur])) or 1
    blobs = cache() / f"models--{depot.replace('/', '--')}" / "blobs"
    fini = threading.Event()

    def suivre() -> None:
        while not fini.wait(0.5):
            recu = sum(f.stat().st_size for f in blobs.glob("*") if f.is_file()) if blobs.is_dir() else 0
            avancement(min(0.99, recu / total))

    fil = threading.Thread(target=suivre, daemon=True)
    fil.start()
    try:
        snapshot_download(depot, allow_patterns=FICHIERS[moteur])
    finally:
        fini.set()
    avancement(1.0)


def resoudre(modele: str, telechargement: bool) -> tuple[str, bool]:
    """Ce qu'il faut passer au moteur (WhisperModel, ou Parakeet), et si c'est un modèle local.

    Un dossier est pris tel quel. Un nom connu déjà en cache sert depuis le cache, sans réseau. Un nom absent
    n'est téléchargé que si `telechargement` est vrai ; sinon on lève une erreur claire."""
    if os.path.isdir(modele):
        return modele, True
    for m in presents():
        if modele in (m["id"], m["depot"]):
            return m["chemin"], True
    if not telechargement:
        raise ModeleAbsent(modele)
    if modele in CONNUS:
        return CONNUS[modele][1], False
    return (modele if "/" in modele else DEPOT.format(modele)), False


class ModeleAbsent(Exception):
    def __init__(self, modele: str) -> None:
        super().__init__(f"modèle « {modele} » absent de la machine : à installer depuis les réglages, avec ton accord")
        self.modele = modele
