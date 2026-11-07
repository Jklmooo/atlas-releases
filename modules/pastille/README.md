# Pastille

Une sortie d'Atlas pour macOS : un orbe rond qui scintille, dans un `NSPanel` qui ne prend jamais le focus, au-dessus
des fenêtres, sur tous les bureaux. Quand la fenêtre d'Atlas est fermée ou derrière une autre, il montre qu'Atlas
**écoute** (bleu, l'orbe grandit et brille avec ta voix), **réfléchit** (violet et rose) ou **parle** (doré, et l'orbe bat avec le volume de sa voix avec Piper ou Voxtral ; avec `say`, il respire), puis
s'efface en veille. En option, une bulle montre ta demande (`{"demande"}` reçu du cœur) et la réponse qui s'écrit
(`{"phrase"}`), et reste quatre secondes après la fin pour la lire.

- Un clic pendant qu'il parle coupe sa voix (`{"geste": "couper"}`) ; sinon il rouvre la fenêtre (`{"geste": "montrer"}`).
- Elle ne parle qu'avec le cœur, par son entrée et sa sortie ([`CONTRAT.md`](../CONTRAT.md)) : sa fiche demande à voir
  l'état (`recoit = ["etat", "demande"]`, poussé à chaque changement) et déclare ses deux gestes (`peut`).
- Réglage `place` : en haut à droite (par défaut), en haut au centre, en bas à droite.
- Réglage `transcription` : `oui` (par défaut, l'orbe et la bulle de texte) ou `non` (l'orbe seul).

Installation : Réglages, Modules, Catalogue, « Installer », puis l'allumer dans sa fiche. Elle se compile à
l'installation avec `swiftc` (outils de développement d'Apple : `xcode-select --install`).

Essai à la main, sans le cœur : `swiftc -O -swift-version 5 -o pastille Pastille.swift`, lancer `./pastille`, puis
taper par exemple `{"etat": {"etat": "parole", "niveau": 0.5, "fenetre": false}}` sur son entrée.
