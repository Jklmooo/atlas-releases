"""Écoute d'Atlas : mot d'éveil « Hey Jarvis » (openWakeWord), puis phrase transcrite par faster-whisper.
Repris de l'écoute de Jarvis (d'après la boucle de sosoj92, MIT), réglages inchangés.

- en veille, chaque tranche de 80 ms du micro passe au détecteur ; rien n'est enregistré ni transcrit ;
- au mot d'éveil : petit son, état « écoute », la phrase est gardée en mémoire jusqu'à un silence (ou 12 s) ;
- transcription locale (aucun audio ne quitte la machine), filtre des phrases inventées par Whisper sur du silence,
  puis la phrase part à Atlas comme une demande écrite ;
- pendant qu'Atlas parle, le détecteur reste actif mais plus exigeant : « Hey Jarvis » coupe sa voix et passe
  directement à l'écoute (sa propre voix, qui ne dit pas « Hey Jarvis », ne le réveille pas) ; un mot bref et net, bien
  au-dessus du niveau de sa voix dans le micro (« arrête », « stop »), est transcrit : s'il demande d'arrêter, la voix se
  coupe et l'écoute repasse en veille ;
- après chaque réponse, fenêtre de suite sans mot d'éveil : 5 s si la réponse se termine par une question, 2 s sinon ;
  rien dit, il repasse en veille sans bruit.
Le texte dicté n'est jamais journalisé. Débranché, le programme s'arrête : ni micro ni modèle ne restent en mémoire.
Micro coupé (bouton du réacteur, Atlas bloqué) : le cœur arrête ce programme, le micro est libéré pour de bon."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import numpy as np

from atlas_voix import liaison, modeles
from atlas_voix.reglages import Reglages
from atlas_voix.texte import plat

TAUX = 16_000
MOT_ARRET = "arrête"   # reconnu par le cœur sans modèle, quelle que soit l'entrée
TRANCHE = 1280              # 80 ms : taille attendue par openWakeWord
SEUIL_EVEIL = 0.4          # 0,5 ratait des « Hey Jarvis » à 0,46 ; rien entre 0,3 et 0,4 dans les journaux
SEUIL_COUPURE = 0.8         # « Hey Jarvis » pendant qu'il parle : plus exigeant, sa voix passe aussi par le micro
SEUIL_TRACE = 0.15          # pics journalisés (score seulement) pour régler le seuil
SILENCE_FIN_S = 1.4         # silence qui termine la phrase (0,9 s coupait Paul quand il cherchait ses mots)
ATTENTE_PAROLE_S = 4.0      # rien dit après « Hey Jarvis » : on abandonne
ATTENTE_SUITE_S = 2.0       # fenêtre de suite : après une réponse, on écoute encore sans mot d'éveil
ATTENTE_QUESTION_S = 5.0    # …plus longtemps quand la réponse d'Atlas se termine par une question
DUREE_MAX_S = 12.0          # durée maximale de la parole, attente non comprise
TRAMES_AVANT_PAROLE = 6     # ~0,5 s gardée avant la parole, pour ne pas perdre le début du premier mot
REPOS_APRES_PAROLE_S = 0.6  # écho de la voix d'Atlas dans la pièce
RAFALE_FACTEUR = 2.5        # pendant qu'Atlas parle : un son au-dessus de 2,5 fois le niveau de sa voix dans le micro
RAFALE_MIN_S = 0.25         # …assez long pour être un mot
RAFALE_MAX_S = 1.8          # …et assez court pour n'être qu'un « arrête » : au-delà, c'est une phrase (ou sa voix)
RAFALE_SILENCE_S = 0.35     # fin du mot
SON_EVEIL = "/System/Library/Sounds/Tink.aiff"   # Mac ; ailleurs, pas de son pour l'instant
# Des phrases types, pas seulement des noms : une simple liste faisait écrire « fera Thales » pour « fera-t-il ».
PROMPT = "Mets la playlist. Quel temps fera-t-il ? Quelles sont les dernières nouvelles ? Jarvis"


def prompt(vocabulaire: list[str]) -> str:
    """L'amorce de Whisper : les phrases types, puis les noms des outils branchés (donnés par Atlas) pour qu'il les
    reconnaisse (« Seedbox » et non « Cinebox »)."""
    return ", ".join([PROMPT, *[m for m in vocabulaire if m]]) + "."

# Phrases que Whisper invente sur du silence ou du bruit (liste de sosoj92, core/hallucinations.py).
HALLUCINATIONS = ("amara.org", "sous-titres", "sous titres", "merci d'avoir regarde", "abonnez-vous",
                  "abonnez vous", "a la prochaine video", "n'oubliez pas de vous abonner", "sous-titrage")
# Phrases courtes, avec ou sans « Jarvis », qui mettent fin à l'échange : atlas repasse au repos, sans fenêtre de suite.
# Comparées sur le texte aplati (sans accents). Les simples accusés de réception (« merci », « d'accord » ; pas « ok », que Paul dit en fin de demande) en font partie : ils ne
# sont pas une demande, et leur répondre relançait une écoute de 20 s.
ARRET = re.compile(r"(?:(?:hey |he )?jarvis )?(?:stop|arrete|arretez|arrete toi|arrete d'ecouter|arrete de parler|"
                   r"tais toi|taisez vous|silence|ca suffit|laisse tomber|annule|c'est bon|c'est tout|merci c'est tout|"
                   r"repos|au repos|mets toi au repos|repose toi|veille|en veille|mets toi en veille|"
                   r"ca ira|ca va aller|non merci|j'ai fini|c'est fini|"
                   r"d'accord|merci|tres bien|parfait|super|nickel|chut|arrete ca|stop stop|"
                   # « arrête » coupé par le début de la fenêtre de suite : Whisper l'a écrit « All right » (04/11/2026)
                   r"all right|alright|allright|all rights|arret)"
                   r"(?: jarvis)?(?: merci)?")


def transcrire_parakeet(modele: Any, audio: np.ndarray, vocabulaire: list[str]) -> str:
    """Parakeet lit le son du micro tel quel ; les noms d'outils d'Atlas sont favorisés, comme l'indice donné à Whisper."""
    import mlx.core as mx
    from parakeet_mlx import Beam, DecodingConfig, boost
    from parakeet_mlx.audio import get_logmel
    mel = get_logmel(mx.array(audio.astype(np.float32)), modele.preprocessor_config)
    mots = {m: 2.0 for m in vocabulaire if m and m.strip()}
    config = DecodingConfig(decoding=Beam(beam_size=4, booster=boost.lift(boost.words(mots), modele.vocabulary))) if mots else DecodingConfig()
    return modele.generate(mel, decoding_config=config)[0].text.strip()


def est_hallucination(texte: str) -> bool:
    t = plat(texte)
    return not t or any(h in t for h in HALLUCINATIONS)


def est_question(texte: str) -> bool:
    """La réponse se termine par une question : on la laisse le temps d'y répondre."""
    return texte.rstrip().rstrip("\"'»”)*_ \n").endswith("?")


def est_arret(texte: str) -> bool:
    """La phrase entière demande d'arrêter : « arrête la musique » reste une demande normale."""
    return bool(ARRET.fullmatch(" ".join(re.sub(r"[^a-z' ]+", " ", plat(texte)).split())))


def micros() -> list[str]:
    """Les noms des micros, sans doublon."""
    import sounddevice as sd
    noms: list[str] = []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0 and d["name"] not in noms:
            noms.append(d["name"])
    return noms


def trouver_micro(cible: str) -> int | None:
    import sounddevice as sd
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and cible.lower() in d["name"].lower():
            return i
    return None


def micro_donne_du_son(micro: int | None, duree: float = 2.0) -> bool:
    """Ouvre le micro et attend un son : un micro coupé (ou dont l'accès est refusé) ne donne que des zéros."""
    import sounddevice as sd
    try:
        with sd.InputStream(samplerate=TAUX, channels=1, dtype="int16", device=micro) as flux:
            for _ in range(int(duree / 0.1)):
                donnees, _ = flux.read(TAUX // 10)
                if donnees.any():
                    return True
    except sd.PortAudioError as exc:
        liaison.journal("micro impossible à ouvrir :", exc)
    return False


def message_micro_muet(nom: str) -> str:
    acces = {"darwin": "Réglages Système, Confidentialité et sécurité, Micro",
             "win32": "Paramètres, Confidentialité et sécurité, Micro"}.get(sys.platform, "les réglages de confidentialité du système")
    return (f"le micro « {nom} » ne donne aucun son : il est coupé, ou l'accès au micro est refusé. "
            f"Rallume-le dans les réglages du son, vérifie l'accès d'Atlas ({acces}), puis rallume l'écoute")


def choisir_micro(voulu: str | None) -> int | None:
    """Index du micro à ouvrir, vérifié (il donne du son) ; None : le micro par défaut du système. Le micro voulu d'abord
    (réglage « micro ») ; sinon celui par défaut ; on ne se replie sur celui du MacBook que si le défaut est muet (un casque
    Bluetooth ou l'iPhone le sont souvent). Sans aucun son, l'écoute s'arrête en le disant."""
    import sounddevice as sd
    trouve = trouver_micro(voulu) if voulu else None
    if voulu and trouve is None:
        liaison.journal("micro choisi introuvable : micro par défaut")
    candidats = [trouve]
    if trouve is None:
        repli = trouver_micro("MacBook")
        if repli is not None:
            candidats.append(repli)
    for micro in candidats:
        if micro_donne_du_son(micro):
            return micro
    raise RuntimeError(message_micro_muet(sd.query_devices(trouve, "input")["name"]))


def eveil_present() -> bool:
    import openwakeword
    dossier = os.path.dirname(openwakeword.MODELS["hey_jarvis"]["model_path"])
    return all(os.path.exists(os.path.join(dossier, f)) for f in
               ("hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx"))


def telecharger_eveil() -> None:
    """Quelques Mo depuis GitHub, annoncés à l'installation : lancé par elle, et repris par l'Écoute s'il n'est pas arrivé."""
    import openwakeword.utils
    openwakeword.utils.download_models(["hey_jarvis"])


def jouer_son() -> None:
    if sys.platform == "darwin" and shutil.which("afplay"):
        subprocess.Popen(["afplay", SON_EVEIL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Phrase:
    """Découpe d'une phrase à l'énergie : parole détectée au-dessus du bruit de fond, fin après un silence."""

    def __init__(self, fond: float, attente: float = ATTENTE_PAROLE_S) -> None:
        self.seuil = max(fond * 2.5, 180.0)
        self.attente = attente
        self.trames: list[np.ndarray] = []
        self.parle = False
        self.silence = 0.0
        self.duree = 0.0
        self.parole = 0.0

    def ajouter(self, trame: np.ndarray) -> str | None:
        """Renvoie « fin », « vide » (rien dit) ou None (continuer)."""
        self.trames.append(trame)
        d = len(trame) / TAUX
        self.duree += d
        fort = float(np.sqrt(np.mean(trame.astype(np.float32) ** 2))) > self.seuil
        if fort:
            self.parle, self.silence = True, 0.0
        elif self.parle:
            self.silence += d
        else:
            del self.trames[:-TRAMES_AVANT_PAROLE]
        if not self.parle:
            return "vide" if self.duree >= self.attente else None
        self.parole += d
        return "fin" if self.silence >= SILENCE_FIN_S or self.parole >= DUREE_MAX_S else None

    def audio(self) -> np.ndarray:
        return np.concatenate(self.trames).astype(np.float32) / 32768.0


class Rafale:
    """Pendant qu'Atlas parle : un mot bref de la personne, plus fort que la voix d'Atlas renvoyée par le micro.
    Le niveau de cette voix se mesure en continu ; seul ce qui le dépasse nettement compte."""

    def __init__(self) -> None:
        self.echo: deque[float] = deque(maxlen=40)   # ~3 s de niveaux de la voix d'Atlas
        self.avant: deque[np.ndarray] = deque(maxlen=3)
        self.trames: list[np.ndarray] = []
        self.silence = self.duree = 0.0

    def oublier(self) -> None:
        self.echo.clear(); self.avant.clear(); self.trames = []
        self.silence = self.duree = 0.0

    def ajouter(self, trame: np.ndarray, rms: float) -> np.ndarray | None:
        """Rend l'audio d'un mot bref quand il se termine ; None sinon."""
        d = len(trame) / TAUX
        seuil = max(float(np.median(self.echo)) * RAFALE_FACTEUR, 300.0) if len(self.echo) >= 10 else None
        fort = seuil is not None and rms > seuil
        if not self.trames:
            if fort:
                self.trames, self.duree, self.silence = [*self.avant, trame], d, 0.0
            else:
                self.echo.append(rms)
                self.avant.append(trame)
            return None
        self.trames.append(trame)
        self.duree += d
        self.silence = 0.0 if fort else self.silence + d
        if self.duree > RAFALE_MAX_S + RAFALE_SILENCE_S:   # trop long : une phrase, ou la voix d'Atlas elle-même
            self.oublier()
            return None
        if self.silence < RAFALE_SILENCE_S:
            return None
        audio, mot = np.concatenate(self.trames), self.duree - self.silence
        self.trames, self.duree, self.silence = [], 0.0, 0.0
        return audio.astype(np.float32) / 32768.0 if mot >= RAFALE_MIN_S else None


class Ecoute(threading.Thread):
    def __init__(self, reglages: Reglages, demander: Callable[[str], None],
                 capte: Callable[[bool, float], None]) -> None:
        super().__init__(daemon=True, name="ecoute")
        self.reglages = reglages
        self.demander, self.capte = demander, capte
        self.parle = threading.Event()      # une sortie d'Atlas émet : détecteur plus exigeant
        self._arret = threading.Event()
        self._interrompu = False   # la parole a été coupée par « Hey Jarvis » : pas de fenêtre de suite en plus
        self._fin_parole = 0.0
        self._suite = False        # une réponse vient d'être dite : ouvrir la fenêtre de suite
        self._question = False     # …et cette réponse se terminait par une question : fenêtre plus longue
        self.vocabulaire: list[str] = []   # les noms d'outils d'Atlas, donnés par le cœur
        self._repos = False        # « arrête » a été dit : plus de fenêtre de suite avant le prochain mot d'éveil
        self._modele_charge = ""   # (modèle, calcul, langue) du Whisper chargé, pour le changer à chaud
        self._whisper: Any = None
        self.erreur = ""

    # -- ce que le cœur dit : une sortie émet ou s'arrête, une réponse arrive
    def etat(self, e: str) -> None:
        """« ecoute » : une phrase se capte (le cœur coupe alors ce qui sortait) ; tout autre état : rien ne se capte."""
        self.capte(e == "ecoute", 0.0)

    def reponse(self, texte: str = "") -> None:
        """Atlas a répondu : si rien ne se dit à voix haute, la fenêtre de suite s'ouvre ; sinon à la fin de la parole."""
        self._question = est_question(texte)
        def ouvrir() -> None:
            if not self.parle.is_set() and not self._repos:
                self._fin_parole, self._suite = time.monotonic(), True
        threading.Timer(1.0, ouvrir).start()

    def atlas_parle(self, oui: bool) -> None:
        if oui:
            self.parle.set()
        else:
            self.parle.clear()
            self._fin_parole = time.monotonic()
            self._suite = not self._interrompu and not self._repos
            self._interrompu = False

    def arreter(self) -> None:
        self._arret.set()

    def _arreter_atlas(self) -> None:
        """« Arrête » vaut pour Atlas entier, comme d'une autre entrée : le cœur interrompt le tour du modèle en cours, sans
        rien dire. On lui envoie le mot tel qu'il le reconnaît, pas la phrase entendue."""
        threading.Thread(target=self.demander, args=(MOT_ARRET,), daemon=True).start()

    # -- modèle de transcription : chargé au premier besoin, rechargé si le réglage change ; son moteur vient du modèle
    def _transcripteur(self) -> Any:
        r = self.reglages.lire()
        cle = (r["modele"], r["calcul"], bool(r["telechargement"]))
        if self._whisper is None or cle != self._modele_charge:
            chemin, local = modeles.resoudre(r["modele"], bool(r["telechargement"]))
            self._whisper = None          # l'ancien est libéré avant que le nouveau ne se charge
            if modeles.moteur_de(r["modele"]) == modeles.PARAKEET:
                if not modeles.parakeet_possible():
                    raise RuntimeError("Parakeet ne marche que sur un Mac à puce Apple : choisis un modèle Whisper")
                from parakeet_mlx import from_pretrained
                self._whisper = from_pretrained(chemin)
            else:
                from faster_whisper import WhisperModel
                self._whisper = WhisperModel(chemin, device="cpu", compute_type=r["calcul"], cpu_threads=4,
                                             local_files_only=local)
            self._modele_charge = cle
            liaison.journal("modèle de transcription chargé :", r["modele"])
        return self._whisper

    # -- boucle
    def run(self) -> None:
        try:
            self._boucle()
        except Exception as exc:  # micro absent, modèle introuvable… : Atlas reste utilisable à l'écrit
            self.erreur = str(exc) if isinstance(exc, (modeles.ModeleAbsent, RuntimeError)) else type(exc).__name__
            liaison.journal("écoute arrêtée :", self.erreur)
            self.etat("veille")
            self._arret.set()

    def _boucle(self) -> None:
        import sounddevice as sd
        from openwakeword.model import Model

        # Le micro d'abord : un micro muet demande un geste de la personne, inutile de charger Whisper (et de se relancer) avant.
        micro = choisir_micro(self.reglages["micro"])
        self._transcripteur()   # un modèle absent échoue tout de suite, pas à la première phrase
        if not eveil_present():   # annoncé et accepté à l'installation : s'il n'est pas arrivé alors, on le reprend ici
            liaison.journal("modèle du mot d'éveil absent : téléchargement")
            try:
                telecharger_eveil()
            except Exception as exc:
                raise RuntimeError(f"le modèle du mot d'éveil n'a pas pu être téléchargé ({type(exc).__name__}) : "
                                   "vérifie la connexion à Internet, puis rallume l'Écoute") from exc
            if not eveil_present():
                raise RuntimeError("le modèle du mot d'éveil n'a pas pu être téléchargé : vérifie la connexion à Internet, puis rallume l'Écoute")
        eveil = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        file: deque[np.ndarray] = deque(maxlen=200)
        disponible = threading.Event()

        def rappel(donnees: Any, n: int, t: Any, statut: Any) -> None:
            file.append(donnees[:, 0].copy())
            disponible.set()

        rafale = Rafale()
        fond = deque(maxlen=60)   # ~5 s de niveaux de fond, pour le seuil de parole
        phrase: Phrase | None = None
        dernier_niveau = dernier_pic = 0.0
        nuls = 0
        flux: Any = None
        try:
            liaison.journal("écoute prête (Hey Jarvis)")
            while not self._arret.is_set():
                if flux is None:
                    flux = sd.InputStream(samplerate=TAUX, channels=1, dtype="int16", blocksize=TRANCHE,
                                          device=micro, callback=rappel)
                    flux.start()
                if not disponible.wait(0.5):
                    continue
                disponible.clear()
                while file:
                    trame = file.popleft()
                    rms = float(np.sqrt(np.mean(trame.astype(np.float32) ** 2)))
                    # Un micro dont chaque échantillon vaut 0 pendant 4 s n'est pas « calme » : il s'est coupé en route.
                    nuls = nuls + 1 if not trame.any() else 0
                    if nuls >= 50:
                        raise RuntimeError(message_micro_muet(self.reglages["micro"] or "du système"))
                    if phrase is not None:
                        if time.monotonic() - dernier_niveau > 0.1:
                            self.capte(True, min(1.0, rms / 3000.0))
                            dernier_niveau = time.monotonic()
                        fin = phrase.ajouter(trame)
                        if fin:
                            self._terminer(phrase, fin)
                            phrase = None
                            eveil.reset()
                        continue
                    if self.parle.is_set():   # Atlas parle : un « Hey Jarvis » net, ou un « arrête » bref, le coupe
                        mot = rafale.ajouter(trame, rms)
                        if mot is not None and est_arret(self._transcrire(mot)):
                            liaison.journal("parole coupée par un mot d'arrêt")
                            self._suite, self._repos, self._interrompu = False, True, True
                            self._arreter_atlas()
                            self.etat("ecoute")   # capter coupe la voix…
                            self.etat("veille")   # …et rien d'autre ne se capte : retour à « Hey Jarvis »
                            rafale.oublier()
                            eveil.reset()
                            continue
                        if max(eveil.predict(trame).values()) >= SEUIL_COUPURE:
                            self._repos = False
                            liaison.journal("parole coupée par le mot d'éveil")
                            self._interrompu = True   # capter coupe la voix : le cœur le fait pour toute entrée
                            jouer_son()
                            self.etat("ecoute")
                            phrase = Phrase(float(np.median(fond)) if fond else 100.0)
                            eveil.reset()
                        continue
                    rafale.oublier()
                    if time.monotonic() - self._fin_parole < REPOS_APRES_PAROLE_S:
                        continue
                    if self._suite:   # Atlas vient de répondre : on écoute la suite sans mot d'éveil
                        self._suite = False
                        self.etat("ecoute")
                        phrase = Phrase(float(np.median(fond)) if fond else 100.0, attente=ATTENTE_QUESTION_S if self._question else ATTENTE_SUITE_S)
                        eveil.reset()
                        continue
                    fond.append(rms)
                    score = max(eveil.predict(trame).values())
                    if SEUIL_TRACE <= score < SEUIL_EVEIL and time.monotonic() - dernier_pic > 1.5:
                        liaison.journal("pic sous le seuil (score %.2f)" % score)   # pour régler le seuil, sans audio
                        dernier_pic = time.monotonic()
                    if score >= SEUIL_EVEIL:
                        self._repos = False   # un mot d'éveil rouvre l'écoute
                        liaison.journal("mot d'éveil (score %.2f)" % score)
                        jouer_son()
                        self.etat("ecoute")
                        phrase = Phrase(float(np.median(fond)) if fond else 100.0)
                        eveil.reset()
        finally:
            if flux is not None:
                flux.stop(); flux.close()

    def _transcrire(self, audio: np.ndarray) -> str:
        r = self.reglages.lire()
        debut = time.monotonic()
        modele = self._transcripteur()
        if modeles.moteur_de(r["modele"]) == modeles.PARAKEET:
            texte = transcrire_parakeet(modele, audio, self.vocabulaire)
        else:
            segments, _ = modele.transcribe(
                audio, language=r["langue"], beam_size=1, vad_filter=True, initial_prompt=prompt(self.vocabulaire),
                without_timestamps=True, condition_on_previous_text=False)
            texte = " ".join(s.text.strip() for s in segments).strip()
        liaison.journal(f"transcrit en {time.monotonic() - debut:.2f} s ({len(audio) / TAUX:.1f} s de parole, {r['modele']})")
        return texte

    def _terminer(self, phrase: Phrase, fin: str) -> None:
        if fin == "vide":
            self.etat("veille")
            return
        self.etat("reflexion")
        texte = self._transcrire(phrase.audio())
        if est_hallucination(texte):
            self.etat("veille")
            return
        if est_arret(texte):   # sans modèle : voix coupée, fenêtre de suite fermée, retour à « Hey Jarvis »
            liaison.journal("arrêt demandé à la voix")
            self._suite, self._repos = False, True
            self._arreter_atlas()
            self.etat("veille")
            return
        threading.Thread(target=self.demander, args=(texte,), daemon=True).start()


def main() -> None:
    """Programme lancé par le cœur : demandes et « capte » sur la sortie, réponses et « sortie » sur l'entrée."""
    import json
    if "--modeles" in sys.argv:           # choix à l'installation : ce qui est déjà là, et notre proposition
        print(json.dumps({**modeles.propositions(), "eveil_present": eveil_present()}, ensure_ascii=False))
        return
    if "--modeles-liste" in sys.argv:     # liste du réglage « modèle », lue par les réglages d'Atlas
        print(json.dumps(modeles.liste_valeurs(), ensure_ascii=False))
        return
    if "--installer-modele" in sys.argv:  # bouton « Installer » des réglages : écrit son avancement, une ligne JSON par pas
        try:
            modeles.installer(sys.argv[sys.argv.index("--installer-modele") + 1],
                              lambda p: print(json.dumps({"progression": round(p, 3)}), flush=True))
        except Exception as exc:
            print(json.dumps({"erreur": f"téléchargement impossible ({type(exc).__name__})"}), flush=True)
            sys.exit(1)
        return
    if "--supprimer-modele" in sys.argv:  # bouton « Supprimer » des réglages : enlève un modèle du cache
        try:
            modeles.supprimer(sys.argv[sys.argv.index("--supprimer-modele") + 1])
        except Exception as exc:
            print(json.dumps({"erreur": f"suppression impossible ({exc})"}, ensure_ascii=False), flush=True)
            sys.exit(1)
        return
    if "--micros-liste" in sys.argv:      # liste du réglage « micro » : celui du système d'abord
        print(json.dumps([{"valeur": "", "libelle": "Micro par défaut du système"},
                          *[{"valeur": n, "libelle": n} for n in micros()]], ensure_ascii=False))
        return
    if "--telecharger-eveil" in sys.argv:
        telecharger_eveil()
        return
    ecoute = Ecoute(Reglages(), demander=liaison.demander,
                    capte=lambda oui, niveau: liaison.ecrire({"capte": oui, "niveau": round(niveau, 2)} if oui else {"capte": False}))
    ecoute.start()

    def surveiller() -> None:         # la boucle s'est arrêtée (modèle absent…) : on le dit, puis on s'arrête
        ecoute.join()
        if ecoute.erreur:
            liaison.ecrire({"erreur": ecoute.erreur})
        os._exit(1 if ecoute.erreur else 0)

    threading.Thread(target=surveiller, daemon=True).start()
    for message in liaison.recus():
        if "vocabulaire" in message:
            ecoute.vocabulaire = [str(m)[:40] for m in message["vocabulaire"] if isinstance(m, str)][:40]
        elif "sortie" in message:
            ecoute.atlas_parle(bool(message["sortie"]))
        elif "texte" in message:
            ecoute.reponse(str(message["texte"]))
    ecoute.arreter()   # l'entrée s'est fermée : le cœur a débranché le module, ou Atlas s'est fermé
    # La boucle ferme elle-même son micro, puis on sort sans la fin ordinaire de Python : celle-ci (Pa_Terminate de
    # sounddevice) arrêtait le même flux en même temps que la boucle, les deux restaient bloqués sur CoreAudio, et une
    # Écoute orpheline survivait à chaque fermeture d'Atlas (quatre le 04/11/2026).
    ecoute.join(timeout=3.0)
    os._exit(0)
