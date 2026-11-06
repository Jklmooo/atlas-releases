"""Seulement ce qu'une erreur coûterait cher : téléchargement non voulu, texte lu symbole par symbole."""
import pytest

from atlas_voix import modeles
from atlas_voix.ecoute import est_question
from atlas_voix.texte import a_dire


def test_modele_absent_sans_accord_ne_telecharge_pas(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    with pytest.raises(modeles.ModeleAbsent):
        modeles.resoudre("small", telechargement=False)


def test_modele_present_sert_depuis_le_cache(tmp_path, monkeypatch):
    snap = tmp_path / "models--Systran--faster-whisper-small" / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (snap / "model.bin").write_bytes(b"x")
    (snap / "config.json").write_text("{}")
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    chemin, local = modeles.resoudre("small", telechargement=False)
    assert local and chemin == str(snap)
    assert modeles.propositions()["propose_present"]


def test_a_dire_nettoie_et_coupe():
    assert a_dire("## Titre\n- **un** point 😀\n- [lien](http://x.fr)") == "Titre un point lien"
    long = ("Phrase courte. " * 100).strip()
    assert len(a_dire(long, 600)) <= 600 and a_dire(long, 600).endswith(".")


def test_un_modele_ne_se_telecharge_jamais_par_les_reglages():
    from atlas_voix.reglages import Reglages
    assert Reglages({})["telechargement"] is False
    assert Reglages({"ATLAS_REGLAGE_TELECHARGEMENT": "oui", "ATLAS_REGLAGE_MODELE": "base"})["telechargement"] is False


def test_la_liste_des_modeles_dit_ce_qui_est_installe(tmp_path, monkeypatch):
    snap = tmp_path / "models--Systran--faster-whisper-small" / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (snap / "model.bin").write_bytes(b"x")
    (snap / "config.json").write_text("{}")
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    liste = {v["valeur"]: v for v in modeles.liste_valeurs()}
    assert liste["small"]["installe"] is True and liste["base"]["installe"] is False
    assert liste["base"]["taille"].startswith("≈")


def test_le_scan_trouve_whisper_et_parakeet_comme_ollama(tmp_path, monkeypatch):
    for dossier, fichiers in (("models--Systran--faster-whisper-small", ["model.bin", "config.json"]),
                              ("models--mlx-community--parakeet-tdt-0.6b-v3", ["model.safetensors", "config.json"]),
                              ("models--mlx-community--parakeet-tdt-1.1b", ["config.json"])):   # incomplet : ignoré
        snap = tmp_path / dossier / "snapshots" / "abc"
        snap.mkdir(parents=True)
        for f in fichiers:
            (snap / f).write_text("{}")
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    monkeypatch.setattr(modeles, "parakeet_possible", lambda: True)
    trouves = {m["id"]: m["moteur"] for m in modeles.presents()}
    assert trouves == {"small": "whisper", "parakeet-v3": "parakeet"}
    chemin, local = modeles.resoudre("parakeet-v3", telechargement=False)
    assert local and chemin.endswith("abc") and modeles.moteur_de("parakeet-v3") == modeles.PARAKEET
    assert {v["valeur"]: v for v in modeles.liste_valeurs()}["parakeet-v3"]["installe"] is True
    # Ailleurs que sur un Mac à puce Apple, Parakeet n'est ni trouvé ni proposé.
    monkeypatch.setattr(modeles, "parakeet_possible", lambda: False)
    assert [m["id"] for m in modeles.presents()] == ["small"]
    assert "parakeet-v3" not in {v["valeur"] for v in modeles.liste_valeurs()}


def test_un_modele_installe_s_enleve_seul_et_un_absent_est_refuse(tmp_path, monkeypatch):
    import pytest
    for dossier in ("models--Systran--faster-whisper-small", "models--Systran--faster-whisper-base"):
        snap = tmp_path / dossier / "snapshots" / "abc"
        snap.mkdir(parents=True)
        for f in ("model.bin", "config.json"):
            (snap / f).write_text("{}")
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    valeurs = {v["valeur"]: v for v in modeles.liste_valeurs()}
    assert valeurs["base"]["supprimable"] and valeurs["base"]["groupe"] == "Whisper" and not valeurs["medium"]["supprimable"]
    modeles.supprimer("base")
    assert [m["id"] for m in modeles.presents()] == ["small"]
    with pytest.raises(ValueError):
        modeles.supprimer("medium")


def test_arret_met_au_repos_mais_une_demande_reste_une_demande():
    from atlas_voix.ecoute import est_arret
    for dit in ("Arrête.", "Stop", "Hey Jarvis, arrête", "D'accord, merci", "Mets-toi au repos", "Tais-toi", "Très bien merci", "All right.", "Alright"):
        assert est_arret(dit), dit
    for dit in ("Arrête la musique", "Quel temps fait-il ?", "Ok mets la playlist", "Ok"):
        assert not est_arret(dit), dit


def test_un_arret_dit_a_la_voix_arrete_aussi_le_coeur(monkeypatch):
    import time
    from atlas_voix.ecoute import MOT_ARRET, Ecoute
    from atlas_voix.reglages import Reglages
    envoyes = []
    e = Ecoute(Reglages({}), demander=envoyes.append, capte=lambda *x: None)
    monkeypatch.setattr(e, "_transcrire", lambda audio: "Stop.")

    class Phrase:
        def audio(self):
            return None
    e._terminer(Phrase(), "parole")
    time.sleep(0.1)
    assert envoyes == [MOT_ARRET] and e._repos   # le cœur coupe le tour, l'écoute retourne au mot d'éveil


def test_l_amorce_de_whisper_porte_les_noms_d_outils():
    from atlas_voix.ecoute import prompt
    assert prompt([]).endswith("Jarvis.")
    assert "MySeedbox, Seedbox" in prompt(["MySeedbox", "Seedbox"])


def test_sans_say_la_voix_prend_piper(monkeypatch):
    from atlas_voix import voix
    monkeypatch.setattr(voix.MOTEURS["say"], "disponible", lambda: False)
    monkeypatch.setattr(voix.MOTEURS["piper"], "disponible", lambda: True)
    assert voix.choisir_moteur("say") is voix.MOTEURS["piper"]
    monkeypatch.setattr(voix.MOTEURS["piper"], "disponible", lambda: False)
    assert voix.choisir_moteur("say") is None


def test_fenetre_longue_seulement_si_la_reponse_pose_une_question():
    assert est_question("Tu veux que je lance la playlist ?")
    assert est_question("Lequel : « Dune » ?  ")
    assert not est_question("C'est fait.")
    assert not est_question("")


def test_un_mot_bref_au_dessus_de_la_voix_d_atlas_est_rendu_mais_pas_sa_voix():
    import numpy as np
    from atlas_voix.ecoute import TRANCHE, Rafale
    trame = lambda niveau: np.full(TRANCHE, niveau, dtype=np.int16)
    r = Rafale()
    for _ in range(20):   # sa voix dans le micro
        assert r.ajouter(trame(400), 400.0) is None
    rendu = [r.ajouter(trame(2000), 2000.0) for _ in range(6)] + [r.ajouter(trame(400), 400.0) for _ in range(6)]
    assert sum(x is not None for x in rendu) == 1, "un « arrête » de 0,5 s"
    r = Rafale()
    for _ in range(20):
        r.ajouter(trame(400), 400.0)
    assert all(r.ajouter(trame(2000), 2000.0) is None for _ in range(40)), "plus de 1,8 s : une phrase, pas un arrêt"


def test_les_phrases_se_disent_a_la_suite_et_atlas_parle_jusqu_a_la_fin(monkeypatch):
    """Une réponse par phrases : la première part seule, les suivantes attendent puis partent ensemble ; entre deux,
    Atlas « parle » encore (sinon l'Écoute ouvrirait sa fenêtre de suite au milieu de la réponse)."""
    from atlas_voix import voix as v
    dits = []

    class Faux:
        nom = "say"
        def __init__(self): self.fini = False
        def poll(self): return 0 if self.fini else None
        def terminate(self): self.fini = True

    class Moteur:
        nom = "say"
        def disponible(self): return True
        def dire(self, texte, voix):
            dits.append(texte)
            p = Faux(); procs.append(p); return p

    procs: list = []
    voix = v.Voix(v.Reglages({}))
    monkeypatch.setattr(voix, "moteur", lambda: Moteur())
    assert voix.phrase("Bonjour Paul.") and dits == ["Bonjour Paul."]
    voix.phrase("Il fait **beau**.")
    voix.phrase("Et demain ?")
    assert dits == ["Bonjour Paul."]          # la première se dit encore
    procs[-1].fini = True
    assert voix.parle()                       # rien ne sort, mais deux phrases attendent
    voix.enchainer()
    assert dits[-1] == "Il fait beau. Et demain ?"
    procs[-1].fini = True
    assert voix.parle()                       # la réponse n'est pas finie : le modèle écrit peut-être la suite
    voix.fin_de_reponse()
    assert not voix.parle()
    voix.phrase("Encore une.")
    voix.couper()
    assert not voix.parle()


def test_la_purge_rend_les_fichiers_partages_d_un_modele_enleve_et_garde_ceux_d_un_modele_present(tmp_path):
    from atlas_voix import cachehf
    partage = tmp_path / "blobs" / "ab"
    partage.mkdir(parents=True)
    for nom, taille in (("ab1", 10), ("ab2", 20)):
        (partage / nom).write_bytes(b"x" * taille)
        (partage / f"{nom}.lock").write_text("")
    for depot, nom in (("models--a--vivant", "ab1"), ("models--a--parti", "ab2")):
        blobs = tmp_path / depot / "blobs"
        blobs.mkdir(parents=True)
        (blobs / "h").symlink_to(partage / nom)
        (partage / f"{nom}.refs").write_text(f"{depot}/blobs/h\n")
    import shutil
    shutil.rmtree(tmp_path / "models--a--parti")
    assert cachehf.purger(tmp_path) == 20
    assert (partage / "ab1").exists() and (partage / "ab1.refs").exists()
    assert not (partage / "ab2").exists() and not (partage / "ab2.refs").exists() and not (partage / "ab2.lock").exists()
