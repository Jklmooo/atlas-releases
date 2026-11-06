"""Le cache Hugging Face range les gros fichiers dans `blobs/` (partagé entre modèles), chacun avec un `.refs` qui dit quels
modèles s'en servent. Effacer le dossier d'un modèle laisse donc ses fichiers : cette purge rend l'espace."""
from __future__ import annotations

from pathlib import Path


def cache() -> Path:
    from huggingface_hub import constants
    return Path(constants.HF_HUB_CACHE)


def purger(base: Path | None = None) -> int:
    """Retire du `blobs/` partagé tout fichier dont plus aucun modèle du cache ne se sert (et ses `.refs` et `.lock`).
    Rend le nombre d'octets libérés. Un modèle encore présent garde ses fichiers : seules ses références mortes s'enlèvent."""
    base = base or cache()
    partage = base / "blobs"
    if not partage.is_dir():
        return 0
    libres = 0
    for refs in list(partage.rglob("*.refs")):
        blob = refs.with_suffix("")
        vivantes = [l for l in refs.read_text().split() if (base / l).exists() and (base / l).resolve() == blob.resolve()]
        if vivantes:
            refs.write_text("\n".join(vivantes) + "\n")
            continue
        if blob.is_file():
            libres += blob.stat().st_size
            blob.chmod(0o644)
            blob.unlink()
        for annexe in (refs, blob.with_name(blob.name + ".lock")):
            annexe.unlink(missing_ok=True)
    return libres
