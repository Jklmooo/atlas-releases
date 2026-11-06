# Contrat d'un module d'Atlas

Ce qu'il faut savoir pour écrire un module qu'Atlas installe et fait marcher : comment il est rangé, ce que le cœur
lit avant de l'installer, et comment il lui parle ensuite. Le cœur ne sait rien de ce que fait un module (voix,
caméra, bulle à l'écran, capteur…) : deux modules qui parlent pareil se remplacent l'un l'autre. N'importe quel
langage convient, du moment que le programme lit et écrit des lignes.

## 1. Les deux rôles

Un module apporte une ou plusieurs **fiches**, chacune d'un de ces deux rôles :

- **Entrée** : elle parle à Atlas sans qu'il le demande. Ce qu'elle dit est une demande de la personne (une écoute
  au micro), ou une simple notification (une sonnette, un capteur).
- **Sortie** : elle reçoit les réponses d'Atlas (une voix qui les lit, une bulle qui les affiche).

Au-delà de son rôle, une fiche peut **demander à voir** davantage (l'état d'Atlas, chaque demande) et **demander à
faire** quelques gestes (couper la voix, remettre la fenêtre devant). Le cœur ne lui envoie que ce qu'elle a demandé
et refuse tout autre geste. La personne lit tout cela en clair avant d'installer (section 4).

## 2. Ranger un module

Un dépôt de modules est un dossier (ou un dépôt git) avec un sous-dossier par module :

```
mon-module/
  module.toml          # la fiche du module
  fiches/ecoute.toml   # une fiche par entrée ou sortie
  programme…           # ce que les fiches lancent
```

Le nom du dossier est l'identifiant du module : lettres minuscules, chiffres et tirets. Rien de personnel ni de
secret dans un module : ni clé, ni jeton. Ce qui dépend de la personne se demande par un réglage.

### `module.toml`

| Champ | Sens |
|---|---|
| `nom`, `description` | ce que la personne voit dans le catalogue |
| `version` | la version du module ; une version plus récente au dépôt se propose en mise à jour |
| `socle` | la version d'Atlas demandée, sous la forme `">=0.0.1"` ; vide, n'importe laquelle |
| `plateformes` | `["macos"]`, `["linux"]`, `["windows"]` ; vide, partout |
| `programmes` | ce qu'il faut sur la machine (`"swiftc"`, `"uv"`…) ; `uv` se télécharge avec l'accord de la personne, les autres se signalent avec leur commande d'installation |
| `telechargements` | ce que l'installation télécharge en plus, dit avant de la lancer |
| `preparation` | une commande lancée une fois le module copié (`["uv", "sync"]`, une compilation) |
| `etapes` | d'autres commandes, lancées ensuite dans l'ordre |
| `[[fiches]]` | `fichier` (chemin dans le module) et `dossier` (`"entrees"` ou `"sorties"`) |

Dans les commandes, `{dossier}` est remplacé par le dossier où le module est installé. L'installation copie le
module dans `~/.atlas/modules/<id>/` (sans `.git`, `.venv`, `node_modules`…), pose ses fiches, puis lance la
préparation. Une installation coupée en route se reprend d'un clic. Une mise à jour remplace tout le module, et une
fiche que la nouvelle version n'a plus disparaît.

### Une fiche

| Champ | Sens |
|---|---|
| `nom`, `description` | ce que la personne voit ; la description dit ce qui arrive vraiment quand la fiche est allumée |
| `commande`, `arguments` | le programme à lancer ; `{dossier}` est le dossier du module |
| `genre` | entrée seulement : `"personne"` (ce qu'elle dit vaut une demande de la personne) ou `"signal"` (par défaut : une notification, sans modèle ni réponse) |
| `micro` | entrée qui prend le micro : le bouton micro du réacteur l'allume ou l'éteint |
| `vocabulaire` | entrée qui veut les noms qu'Atlas connaît, pour mieux les reconnaître |
| `parle` | sortie qui parle : le bouton haut-parleur du réacteur l'allume ou l'éteint |
| `recoit` | ce qu'elle demande à voir en plus de son rôle : `"etat"`, `"demande"` (section 5) |
| `peut` | les gestes qu'elle demande à faire : `"couper"`, `"montrer"` (section 6) |
| `[[reglages]]` | ses réglages (section 3) |

Une fiche qui demande à voir ou à faire ce que la version d'Atlas en service ne connaît pas est refusée à
l'installation : rien n'est posé, et le catalogue le dit.

Exemple, la fiche de la pastille :

```toml
nom = "Pastille"
description = "Quand la fenêtre d'Atlas est derrière une autre, un orbe montre qu'il écoute, réfléchit ou parle."
commande = "{dossier}/pastille"
recoit = ["etat", "demande"]
peut = ["couper", "montrer"]
```

## 3. Réglages

```toml
[[reglages]]
cle = "place"
libelle = "Place"
aide = "Où la pastille apparaît."
defaut = "haut-droite"
valeurs = [
  { valeur = "haut-droite", libelle = "En haut à droite" },
  { valeur = "bas-droite", libelle = "En bas à droite" },
]
```

- Chaque réglage arrive au programme en variable d'environnement : `ATLAS_REGLAGE_PLACE` pour la clé `place`
  (majuscules, et `_` à la place de ce qui n'est ni lettre ni chiffre). Changer un réglage relance le programme.
- `valeurs` est une liste fixe : des textes, ou des objets `{ valeur, libelle }` avec au choix `groupe` (pour ranger
  une longue liste), `detail` (quelques mots pour choisir), `taille` (ce que son installation télécharge), `installe`
  et `supprimable`.
- `commande_valeurs` : une commande qui écrit en JSON la liste des valeurs, quand elle dépend de la machine (les
  modèles déjà téléchargés).
- `commande_installer` : installe une valeur absente (`{valeur}` dans la commande) ; elle écrit
  `{"progression": 0.42}` de temps en temps, puis finit. Un code de sortie non nul est un échec, montré en clair.
- `commande_supprimer` : enlève de la machine une valeur installée ; elle écrit `{"erreur": "…"}` si elle échoue.

Un module qui n'a que des réglages, sans `commande`, est permis.

## 4. Ce que la personne lit avant d'installer

Le catalogue montre, pour chaque module, la liste de ce qu'il pourra faire, tirée de ses fiches :

| Déclaré | Ce que la personne lit |
|---|---|
| une entrée `personne` | parler à Atlas en ton nom |
| une entrée `signal` | t'envoyer des notifications |
| une sortie | recevoir chaque réponse d'Atlas |
| `micro = true` | utiliser le micro |
| `recoit = ["etat"]` | voir quand Atlas écoute, réfléchit ou parle, le volume de la voix, et si sa fenêtre est devant toi |
| `recoit = ["demande"]` | voir chacune de tes demandes |
| `peut = ["couper"]` | couper la voix d'Atlas |
| `peut = ["montrer"]` | remettre la fenêtre d'Atlas devant toi |

La fiche d'un module installé redit la même liste. Une mise à jour qui demande davantage le dit avant qu'on la lance
(« Avec elle, il pourra aussi : … »). Ne demande que ce dont le module a besoin.

## 5. Parler avec le cœur

Allumée, une fiche est un programme que le cœur lance et arrête. Ils se parlent par **lignes JSON, une par
message** : le module lit son entrée standard et écrit sur sa sortie standard. Sa sortie d'erreur va au journal
d'Atlas : jamais de texte dicté ni de secret. Une ligne fait au plus 64 Ko. **Quand son entrée se ferme**, le cœur
s'arrête ou éteint la fiche : le module s'arrête aussi.

**Un message inconnu s'ignore**, des deux côtés. Le contrat s'élargit ainsi sans casser les modules existants.
Pense à vider ton tampon après chaque ligne (`flush`) : sinon le cœur ne reçoit rien.

### Ce que le module écrit

| Message | Qui | Sens |
|---|---|---|
| `{"texte": "…"}` | entrée | une demande (ou une notification, pour un `signal`) |
| `{"capte": true, "niveau": 0.4}` / `{"capte": false}` | entrée | elle capte, d'où l'état « écoute » ; une entrée `personne` qui capte fait taire les sorties. `niveau` de 0 à 1, facultatif |
| `{"emet": true}` / `{"emet": false}` | sortie | elle émet, d'où l'état « parole » ; les entrées le reçoivent |
| `{"emet": true, "niveau": 0.6}` | sortie | le volume de ce qu'elle joue, de 0 à 1, quelques fois par seconde |
| `{"geste": "couper"}` | fiche avec `peut = ["couper"]` | la voix d'Atlas se tait, comme quand une demande arrive |
| `{"geste": "montrer"}` | fiche avec `peut = ["montrer"]` | la fenêtre d'Atlas revient devant la personne |
| `{"erreur": "…"}` | toutes | pourquoi le module s'arrête, montré dans Réglages, Modules |

Un geste que la fiche n'a pas déclaré est refusé, et le refus est noté au journal.

### Ce que le module reçoit

| Message | Qui | Sens |
|---|---|---|
| `{"phrase": "…"}` | sortie | une phrase de la réponse, dès que le modèle l'a écrite : une voix parle avant la fin. Une réponse qui ne s'écrit pas au fil de l'eau (un outil, un accord) arrive en une seule phrase. Une erreur ne se dit pas |
| `{"fin": true}` | sortie | la réponse est complète |
| `{"couper": true}` | sortie | une demande arrive, ou une entrée capte : se taire, et oublier les phrases en attente |
| `{"texte": "…", "erreur": false}` | entrée | la réponse entière à la demande que cette entrée a faite |
| `{"sortie": true}` / `{"sortie": false}` | entrée | une sortie émet ou s'arrête (une écoute peut devenir plus exigeante pendant qu'Atlas parle) |
| `{"vocabulaire": ["…"]}` | entrée avec `vocabulaire` | les noms d'outils et de proches qu'Atlas connaît |
| `{"demande": "…"}` | fiche avec `recoit = ["demande"]` | la demande qui arrive, telle qu'Atlas l'a comprise (500 caractères au plus), avant la réponse ; pas pour une demande dite au micro du téléphone |
| `{"etat": {"etat": "parole", "niveau": 0.62, "fenetre": false}}` | fiche avec `recoit = ["etat"]` | l'état d'Atlas, envoyé dès le lancement puis à chaque changement, jusqu'à dix fois par seconde tant qu'Atlas n'est pas en veille |

Dans `{"etat"}` :
- `etat` vaut `veille`, `ecoute`, `reflexion`, `parole` ou `erreur` ;
- `niveau` est le volume de la voix entendue pendant l'écoute, ou de celle d'Atlas pendant la parole quand sa voix le
  donne, de 0 à 1 ;
- `fenetre` est vrai quand la fenêtre d'Atlas est vraiment devant la personne : visible, au premier plan, et sur le
  bureau affiché.

## 6. Un module minimal

Une sortie qui écrit chaque réponse dans un fichier, en Python :

```python
import json, sys

with open("/tmp/reponses.txt", "a") as journal:
    for ligne in sys.stdin:                      # s'arrête quand le cœur ferme l'entrée
        message = json.loads(ligne)
        if "phrase" in message:
            journal.write(message["phrase"] + "\n")
            journal.flush()
```

Sa fiche, posée dans `sorties` :

```toml
nom = "Journal des réponses"
description = "Chaque réponse d'Atlas s'ajoute à /tmp/reponses.txt."
commande = "python3"
arguments = ["{dossier}/journal.py"]
```

## 7. Essayer

- Pendant le développement, Atlas lit le dossier `atlas-modules` posé à côté de son dépôt. Sinon, la personne donne
  un dossier ou une adresse git dans Réglages, Modules, Catalogue.
- Installer, puis allumer la fiche dans la page du module. Ce que le module dit de son arrêt (`{"erreur"}`)
  s'affiche sur cette page.
- À la main, sans le cœur, on peut jouer son rôle : lancer le programme, puis taper les lignes JSON sur son entrée.

Les interfaces (un morceau du réacteur, en JavaScript) ne font pas encore partie de ce contrat : elles ne
s'installent pas depuis un dépôt.
