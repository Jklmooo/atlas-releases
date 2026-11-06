"""Voix d'Atlas : texte vers parole. Le moteur est un choix des réglages ; `say` (Mac) vient en premier.

Un moteur sait dire un texte sans bloquer, se couper, lister ses voix et produire un fichier audio pour le téléphone.
La place d'un moteur portable (piper, par exemple) est prévue : une classe de plus dans MOTEURS, rien d'autre à changer."""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import threading
from collections import deque
from pathlib import Path
from typing import Protocol

from atlas_voix import cachehf, liaison
from atlas_voix.reglages import Reglages
from atlas_voix.texte import a_dire

CARACTERES_MAX = 600


class Moteur(Protocol):
    nom: str

    def disponible(self) -> bool: ...
    def voix(self) -> list[str]: ...
    def dire(self, texte: str, voix: str) -> "subprocess.Popen | Lecture | None": ...
    def audio(self, texte: str, voix: str) -> bytes | None: ...


class Say:
    """Voix d'Apple, installée avec macOS."""
    nom = "say"

    def disponible(self) -> bool:
        return shutil.which("say") is not None

    def voix(self) -> list[str]:
        """Voix françaises (France) installées, d'après `say -v ?`."""
        noms: list[str] = []
        try:
            sortie = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return noms
        for ligne in sortie.splitlines():
            m = re.match(r"^(.+?)\s+fr_FR\s+#", ligne)
            if m and m.group(1).strip() not in noms:
                noms.append(m.group(1).strip())
        return noms

    def dire(self, texte: str, voix: str) -> subprocess.Popen | None:
        try:
            return subprocess.Popen(["say", "-v", voix, texte[:CARACTERES_MAX]],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc:
            liaison.journal("voix indisponible :", type(exc).__name__)
            return None

    def audio(self, texte: str, voix: str) -> bytes | None:
        """Réponse en fichier audio (AAC, .m4a), pour la lire sur le téléphone : Safari iOS bloque souvent sa propre
        synthèse vocale après l'usage du micro. Fichiers temporaires privés, effacés aussitôt."""
        if not texte.strip():
            return None
        with tempfile.TemporaryDirectory(prefix="atlas-voix-") as d:
            brut, m4a = os.path.join(d, "r.aiff"), os.path.join(d, "r.m4a")
            try:
                subprocess.run(["say", "-v", voix, "-o", brut, texte[:CARACTERES_MAX]], check=True, timeout=30,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", brut, m4a], check=True, timeout=30,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                with open(m4a, "rb") as f:
                    return f.read()
            except (OSError, subprocess.SubprocessError) as exc:
                liaison.journal("audio de la réponse impossible :", type(exc).__name__)
                return None


# Voix Piper : (dépôt, dossier dans le dépôt, taille). Le modèle se télécharge par le bouton « Installer » des réglages.
PIPER_DEPOT = "rhasspy/piper-voices"
PIPER_VOIX = {
    "fr_FR-siwis-medium": ("fr/fr_FR/siwis/medium", "≈ 65 Mo"),
    "fr_FR-siwis-low": ("fr/fr_FR/siwis/low", "≈ 30 Mo"),
    "fr_FR-upmc-medium": ("fr/fr_FR/upmc/medium", "≈ 65 Mo"),
}


def _enveloppe(son, taux: int, pas: float) -> list[float]:
    """Le volume (RMS) d'un son par tranches de `pas` secondes, ramené au plus fort du morceau : quelques dizaines de
    valeurs, calculées d'un coup par numpy."""
    import numpy as np
    son = np.asarray(son, dtype=np.float32).reshape(-1)
    taille = max(1, int(taux * pas))
    n = len(son) // taille
    if n == 0:
        return []
    rms = np.sqrt(np.mean(np.square(son[: n * taille].reshape(n, taille)), axis=1))
    haut = float(rms.max())
    return [] if haut <= 0 else [round(float(v), 2) for v in np.minimum(1.0, rms / haut)]


class Lecture(threading.Thread):
    """Une phrase Piper en cours de lecture ; même interface qu'un processus (`poll`, `terminate`) pour pouvoir la couper."""

    PAS = 0.05   # l'enveloppe du son : un niveau toutes les 50 ms

    def __init__(self, voix, texte: str) -> None:
        super().__init__(daemon=True, name="piper")
        self.voix, self.texte, self._fini, self._arret = voix, texte, threading.Event(), threading.Event()
        self._enveloppe: list[float] = []   # le morceau qui se joue : son volume, calculé une fois avant de le jouer
        self._debut = 0.0

    def niveau(self) -> float:
        """Le volume de ce qui se joue maintenant, de 0 à 1 (relatif au morceau) : l'orbe de la pastille en bat."""
        enveloppe, debut = self._enveloppe, self._debut
        i = int((time.monotonic() - debut) / self.PAS)
        return enveloppe[i] if 0 <= i < len(enveloppe) else 0.0

    def poll(self) -> int | None:
        return 0 if self._fini.is_set() else None

    def terminate(self) -> None:
        self._arret.set()
        import sounddevice as sd
        sd.stop()

    def run(self) -> None:
        try:
            import sounddevice as sd
            for morceau in self.voix.synthesize(self.texte):
                if self._arret.is_set():
                    break
                son = morceau.audio_float_array
                self._enveloppe = _enveloppe(son, morceau.sample_rate, self.PAS)
                self._debut = time.monotonic()
                sd.play(son, morceau.sample_rate)
                sd.wait()
                self._enveloppe = []
        except Exception as exc:
            liaison.journal("lecture impossible :", type(exc).__name__)
        finally:
            self._fini.set()


class Piper:
    """Voix locales Piper : portables (Mac, Linux, Windows), sans rien d'Apple."""
    nom = "piper"

    def __init__(self) -> None:
        self._charges: dict[str, object] = {}

    def disponible(self) -> bool:
        try:
            import piper  # noqa: F401
            return True
        except ImportError:
            return False

    def _fichier(self, voix: str, suffixe: str, telecharger: bool = False) -> str | None:
        from huggingface_hub import hf_hub_download, try_to_load_from_cache
        dossier = PIPER_VOIX[voix][0]
        chemin = f"{dossier}/{voix}{suffixe}"
        if telecharger:
            return hf_hub_download(PIPER_DEPOT, chemin)
        trouve = try_to_load_from_cache(PIPER_DEPOT, chemin)
        return trouve if isinstance(trouve, str) else None

    def installee(self, voix: str) -> bool:
        return voix in PIPER_VOIX and all(self._fichier(voix, s) for s in (".onnx", ".onnx.json"))

    def liste(self) -> list[dict]:
        def libelle(v: str) -> str:
            _, nom, qualite = v.split("-")
            return f"{nom.capitalize()} ({ {'low': 'légère', 'medium': 'moyenne', 'high': 'haute'}.get(qualite, qualite)})"
        return [{"valeur": v, "libelle": libelle(v), "groupe": "Piper", "detail": v, "installe": (la := self.installee(v)),
                 "supprimable": la, "taille": PIPER_VOIX[v][1]} for v in PIPER_VOIX]

    def supprimer(self, voix: str) -> None:
        """Enlève une voix du cache, à la demande de la personne : ses deux fichiers seulement (le dépôt en a d'autres)."""
        if voix not in PIPER_VOIX:
            raise ValueError("voix inconnue")
        for suffixe in (".onnx", ".onnx.json"):
            lien = self._fichier(voix, suffixe)
            if lien is None:
                continue
            blob = os.path.realpath(lien)
            os.remove(lien)
            if blob != lien and os.path.exists(blob):
                os.remove(blob)
        cachehf.purger()
        self._charges.pop(voix, None)

    def installer(self, voix: str, avancement) -> None:
        if voix not in PIPER_VOIX:
            raise ValueError("voix inconnue")
        avancement(0.05)
        self._fichier(voix, ".onnx.json", telecharger=True)
        avancement(0.15)
        self._fichier(voix, ".onnx", telecharger=True)
        avancement(1.0)

    def voix(self) -> list[str]:
        return list(PIPER_VOIX)

    def dire(self, texte: str, voix: str) -> Lecture | None:
        if voix not in PIPER_VOIX:   # le choix de voix est celui d'un autre moteur : la première Piper installée
            voix = next((v for v in PIPER_VOIX if self.installee(v)), voix)
        if not self.installee(voix):
            liaison.journal("voix Piper non installée :", voix)
            return None
        if voix not in self._charges:
            from piper import PiperVoice
            self._charges[voix] = PiperVoice.load(self._fichier(voix, ".onnx"), self._fichier(voix, ".onnx.json"))
        lecture = Lecture(self._charges[voix], texte[:CARACTERES_MAX])
        lecture.start()
        return lecture

    def audio(self, texte: str, voix: str) -> bytes | None:
        return None   # le fichier pour le téléphone n'existe que pour `say`

# Voix de Mistral (Voxtral TTS, MLX) : un Mac à puce Apple seulement. Deux versions quantifiées (la bf16 pèse 8 Go) ;
# chaque voix existe dans chaque version, et les deux voix d'une version partagent le même modèle téléchargé.
VOXTRAL_MODELES = {
    "4bit": ("mlx-community/Voxtral-4B-TTS-2603-mlx-4bit", "≈ 2,5 Go"),
    "6bit": ("mlx-community/Voxtral-4B-TTS-2603-mlx-6bit", "≈ 3,5 Go"),
}
VOXTRAL_VOIX = {"fr_female": "féminine", "fr_male": "masculine"}
VOXTRAL_FICHIERS = ["*.json", "model*.safetensors", "model.safetensors.index.json", "tekken.json",
                    "voice_embedding/fr_*.safetensors"]
VOXTRAL_DEFAUT = "fr_female@4bit"


def _voxtral_cle(valeur: str) -> tuple[str, str]:
    voix, _, version = valeur.partition("@")
    if voix not in VOXTRAL_VOIX or version not in VOXTRAL_MODELES:
        raise ValueError("voix inconnue")
    return voix, version


class _Morceau:
    def __init__(self, audio, taux: int) -> None:
        self.audio_float_array, self.sample_rate = audio, taux


class _VoxtralChargee:
    """Le modèle Voxtral chargé une fois ; dit une voix, phrase par phrase pour que le son parte tôt."""
    _verrou = threading.Lock()   # un seul calcul à la fois : une phrase coupée finit son morceau pendant que la suivante part

    def __init__(self, depot: str, voix: str) -> None:
        self.depot, self.voix, self.modele = depot, voix, None

    def synthesize(self, texte: str):
        import numpy as np
        phrases = [p.strip() for p in re.split(r"(?<=[.!?…:;])\s+", texte) if p.strip()]
        with self._verrou:
            if self.modele is None:
                from mlx_audio.tts.utils import load
                self.modele = load(self.depot)
        for phrase in phrases:
            with self._verrou:
                audio = [np.array(r.audio, dtype=np.float32) for r in self.modele.generate(text=phrase, voice=self.voix)]
            if audio:
                yield _Morceau(np.concatenate(audio), 24000)


class Voxtral:
    """Voix de Mistral, locales, avec un rendu plus naturel que Piper. Lourdes : seulement sur un Mac à puce Apple."""
    nom = "voxtral"

    def __init__(self) -> None:
        self._charges: dict[str, _VoxtralChargee] = {}

    def disponible(self) -> bool:
        if sys.platform != "darwin" or platform.machine() != "arm64":
            return False
        try:
            import mlx_audio  # noqa: F401
            return True
        except ImportError:
            return False

    def _dossier(self, version: str):
        """Le dossier du modèle dans le cache, s'il est complet ; sinon None."""
        from huggingface_hub import snapshot_download
        try:
            d = Path(snapshot_download(VOXTRAL_MODELES[version][0], allow_patterns=VOXTRAL_FICHIERS, local_files_only=True))
        except Exception:
            return None
        pret = (d / "tekken.json").exists() and (d / "model.safetensors").exists() and all(
            (d / "voice_embedding" / f"{v}.safetensors").exists() for v in VOXTRAL_VOIX)
        return d if pret else None

    def installee(self, valeur: str) -> bool:
        try:
            return self._dossier(_voxtral_cle(valeur)[1]) is not None
        except ValueError:
            return False

    def liste(self) -> list[dict]:
        sorties = []
        for version, (_, taille) in VOXTRAL_MODELES.items():
            la = self._dossier(version) is not None
            for voix, genre in VOXTRAL_VOIX.items():
                sorties.append({"valeur": f"{voix}@{version}", "libelle": f"Voxtral, voix {genre} ({version.replace('bit', ' bits')})",
                                "groupe": "Voxtral (Mistral)", "installe": la, "supprimable": la, "taille": taille,
                                "detail": "plus lente que la parole sur un Mac de 8 Go" if version == "4bit" else "meilleure, plus lourde"})
        return sorties

    def installer(self, valeur: str, avancement) -> None:
        import fnmatch
        from huggingface_hub import HfApi, snapshot_download
        _, version = _voxtral_cle(valeur)
        depot = VOXTRAL_MODELES[version][0]
        info = HfApi().model_info(depot, files_metadata=True)
        total = sum(f.size or 0 for f in info.siblings if any(fnmatch.fnmatch(f.rfilename, m) for m in VOXTRAL_FICHIERS)) or 1
        blobs = Path(os.path.expanduser("~/.cache/huggingface/hub")) / f"models--{depot.replace('/', '--')}" / "blobs"
        fini = threading.Event()

        def suivre() -> None:
            while not fini.wait(0.5):
                recu = sum(f.stat().st_size for f in blobs.glob("*") if f.is_file()) if blobs.is_dir() else 0
                avancement(min(0.99, recu / total))

        threading.Thread(target=suivre, daemon=True).start()
        try:
            snapshot_download(depot, allow_patterns=VOXTRAL_FICHIERS)
        finally:
            fini.set()
        avancement(1.0)

    def supprimer(self, valeur: str) -> None:
        """Enlève la version du cache (ses deux voix s'en vont avec : elles n'ont qu'un modèle)."""
        import shutil
        from huggingface_hub import constants
        _, version = _voxtral_cle(valeur)
        dossier = Path(constants.HF_HUB_CACHE) / f"models--{VOXTRAL_MODELES[version][0].replace('/', '--')}"
        if dossier.parent != Path(constants.HF_HUB_CACHE) or not dossier.is_dir():
            raise ValueError("modèle absent de la machine")
        shutil.rmtree(dossier)
        cachehf.purger(Path(constants.HF_HUB_CACHE))
        self._charges = {k: v for k, v in self._charges.items() if not k.endswith("@" + version)}

    def voix(self) -> list[str]:
        return [f"{v}@{ver}" for ver in VOXTRAL_MODELES for v in VOXTRAL_VOIX]

    def dire(self, texte: str, voix: str) -> Lecture | None:
        if not self.installee(voix):   # le choix de voix est celui d'un autre moteur : la première Voxtral installée
            voix = next((v for v in self.voix() if self.installee(v)), voix)
        if not self.installee(voix):
            liaison.journal("voix Voxtral non installée :", voix)
            return None
        nom, version = _voxtral_cle(voix)
        if voix not in self._charges:
            self._charges[voix] = _VoxtralChargee(str(self._dossier(version)), nom)
        lecture = Lecture(self._charges[voix], texte[:CARACTERES_MAX])
        lecture.start()
        return lecture

    def audio(self, texte: str, voix: str) -> bytes | None:
        return None


MOTEURS: dict[str, Moteur] = {"say": Say(), "piper": Piper(), "voxtral": Voxtral()}


def choisir_moteur(nom: str) -> Moteur | None:
    """Le moteur choisi, s'il marche ici ; sinon Piper (`say` n'existe que sur le Mac) ; sinon rien."""
    choisi = MOTEURS.get(nom)
    if choisi is not None and choisi.disponible():
        return choisi
    return MOTEURS["piper"] if MOTEURS["piper"].disponible() else None


class Voix:
    """Dit les réponses. Le cœur envoie chaque phrase dès qu'elle est écrite (`phrase`) : la première se dit pendant que le
    modèle écrit la suite, les suivantes attendent leur tour ; `fin` dit que la réponse est complète."""

    def __init__(self, reglages: Reglages) -> None:
        self.reglages = reglages
        self.raison = ""   # pourquoi le dernier texte n'a rien dit, quand ce n'est pas faute de texte
        self._en_cours: "subprocess.Popen | Lecture | None" = None
        self._verrou = threading.Lock()
        self._file: deque[str] = deque()   # phrases reçues, pas encore dites
        self._en_reponse = False   # une réponse arrive par phrases : Atlas parle jusqu'à sa fin, même entre deux phrases
        self._enchaine = threading.Lock()   # un seul lancement à la fois : deux phrases ne se disent jamais en même temps
        self._dits = 0             # caractères de cette réponse déjà dits ou en attente : CARACTERES_MAX au plus, comme d'un bloc

    def phrase(self, texte: str) -> bool:
        """Une phrase de la réponse : dite tout de suite si rien ne se dit, sinon à la suite. Faux sans moteur."""
        if self.moteur() is None:
            return False
        reste = CARACTERES_MAX - self._dits
        phrase = a_dire(texte, reste) if reste > 0 else ""
        with self._verrou:
            if not self._en_reponse:
                self._en_reponse, self._dits = True, 0
            if phrase:
                self._file.append(phrase)
                self._dits += len(phrase) + 1
        return self.enchainer()

    def fin_de_reponse(self) -> None:
        """La réponse est finie : quand la file sera dite, Atlas aura fini de parler."""
        with self._verrou:
            self._en_reponse = False

    def enchainer(self) -> bool:
        """Rien ne se dit et des phrases attendent : elles partent ensemble (un seul `say`, sans blanc entre elles)."""
        with self._enchaine:
            return self._enchainer()

    def _enchainer(self) -> bool:
        with self._verrou:
            if not self._file or (self._en_cours is not None and self._en_cours.poll() is None):
                return True
            texte = " ".join(self._file)
            self._file.clear()
        r = self.reglages.lire()
        moteur = self.moteur()
        if moteur is None:
            return False
        proc = moteur.dire(texte, r["voix"] if moteur.nom == r["moteur"] else "")
        with self._verrou:
            self._en_cours = proc
        self.raison = "" if proc is not None else (
            f"aucune voix {moteur.nom.capitalize()} n'est installée : installe-en une dans Réglages, Modules, Voix" if moteur.nom in ("piper", "voxtral") else f"le moteur {moteur.nom} ne part pas")
        return proc is not None

    def moteur(self) -> Moteur | None:
        return choisir_moteur(self.reglages["moteur"])

    def niveau(self) -> float | None:
        """Le volume de la phrase qui se dit, si le moteur le connaît (Piper, Voxtral) ; `say` ne le donne pas."""
        with self._verrou:
            proc = self._en_cours
        return proc.niveau() if isinstance(proc, Lecture) and proc.poll() is None else None

    def parle(self) -> bool:
        with self._verrou:
            return bool(self._file) or self._en_reponse or (self._en_cours is not None and self._en_cours.poll() is None)

    def couper(self) -> bool:
        """Coupe la voix en cours (« Hey Jarvis » pendant qu'Atlas parle), et les phrases qui attendaient ; vrai s'il parlait."""
        with self._verrou:
            proc, self._en_cours = self._en_cours, None
            self._file.clear()
            self._en_reponse = False
        if proc is None or proc.poll() is not None:
            return False
        proc.terminate()
        return True


def _moteur_de_voix(valeur: str):
    """Le moteur à qui appartient une voix installable : « fr_female@4bit » est à Voxtral, « fr_FR-… » à Piper."""
    return MOTEURS["voxtral"] if "@" in valeur else MOTEURS["piper"]


def main() -> None:
    """Programme lancé par le cœur : chaque réponse d'Atlas arrive sur l'entrée phrase par phrase (`{"phrase"}`, puis
    `{"fin"}`) et se dit à voix haute ; `{"couper"}` la coupe (une entrée arrive). Il dit au cœur quand il émet, pour l'état « parole », et le volume de ce qu'il joue (`{"emet", "niveau"}`, Piper et Voxtral)."""
    import json
    moteur = os.environ.get("ATLAS_REGLAGE_MOTEUR", "say")
    effectif = choisir_moteur(moteur)
    if "--moteurs-liste" in sys.argv:     # liste du réglage « moteur » : ceux qui marchent sur cet ordinateur
        print(json.dumps([{"valeur": n, "libelle": {"say": "say (voix d'Apple)", "piper": "Piper (voix locales)", "voxtral": "Voxtral (voix de Mistral, plus naturelles)"}[n]}
                          for n, m in MOTEURS.items() if m.disponible()], ensure_ascii=False))
        return
    if "--voix-liste" in sys.argv:        # liste du réglage « voix » pour le moteur choisi, lue par les réglages d'Atlas
        if effectif in (MOTEURS["piper"], MOTEURS["voxtral"]):
            print(json.dumps(effectif.liste(), ensure_ascii=False))
        else:
            print(json.dumps([{"valeur": v, "libelle": v, "groupe": "Voix d'Apple", "installe": True} for v in Say().voix()], ensure_ascii=False))
        return
    if "--installer-voix" in sys.argv:    # bouton « Installer » des réglages : avancement en lignes JSON
        try:
            _moteur_de_voix(sys.argv[sys.argv.index("--installer-voix") + 1]).installer(sys.argv[sys.argv.index("--installer-voix") + 1],
                                       lambda p: print(json.dumps({"progression": round(p, 3)}), flush=True))
        except Exception as exc:
            print(json.dumps({"erreur": f"téléchargement impossible ({type(exc).__name__})"}), flush=True)
            sys.exit(1)
        return
    if "--supprimer-voix" in sys.argv:    # bouton « Supprimer » des réglages : les voix Piper et Voxtral s'enlèvent
        try:
            _moteur_de_voix(sys.argv[sys.argv.index("--supprimer-voix") + 1]).supprimer(sys.argv[sys.argv.index("--supprimer-voix") + 1])
        except Exception as exc:
            print(json.dumps({"erreur": f"suppression impossible ({exc})"}, ensure_ascii=False), flush=True)
            sys.exit(1)
        return
    voix = Voix(Reglages())
    emet = False

    def echouer(raison: str) -> None:   # rien à dire ici : le cœur l'affiche dans Modules, et il relancera le module quand on aura réglé
        liaison.ecrire({"erreur": raison})
        os._exit(1)

    if voix.moteur() is None:
        echouer("aucun moteur de voix ne marche sur cet ordinateur : installe Piper (voix locales) ou utilise un Mac pour la voix d'Apple")

    def surveiller() -> None:
        nonlocal emet
        dit, tour = None, 0   # le dernier niveau envoyé ; il part une fois sur deux (10 par seconde), s'il a bougé
        while True:
            if not voix.enchainer() and voix.raison:
                echouer(voix.raison)
            parle = voix.parle()
            if parle != emet:
                emet, dit = parle, None
                liaison.ecrire({"emet": parle})
            tour += 1
            if parle and tour % 2 == 0:
                niveau = voix.niveau()
                if niveau is not None and (dit is None or abs(niveau - dit) >= 0.05):
                    dit = niveau
                    liaison.ecrire({"emet": True, "niveau": niveau})
            time.sleep(0.05)

    threading.Thread(target=surveiller, daemon=True).start()
    for message in liaison.recus():
        if message.get("couper"):
            voix.couper()
        elif message.get("phrase"):
            if not voix.phrase(str(message["phrase"])) and voix.raison:
                echouer(voix.raison)
        elif message.get("fin"):
            voix.fin_de_reponse()
    voix.couper()


if __name__ == "__main__":
    main()
