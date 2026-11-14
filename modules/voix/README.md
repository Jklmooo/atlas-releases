# Voix

Le module Voix d'Atlas propose deux fiches exclusives.

- **Conversation** (`fiches/conversation.toml`) utilise Pipecat pour écouter, envoyer la demande au socle et dire
  sa réponse phrase par phrase.
- **Agent vocal** (`fiches/agent_vocal.toml`) utilise l'agent vocal de Mistral avec les outils d'Atlas par la porte
  MCP. Il s'utilise avec le micro du Mac. L'appel du téléphone reste à faire pour cette fiche.

## Conversation

- Mot d'éveil « Hey Jarvis » (openWakeWord), mots d'arrêt, filtre des phrases que Whisper invente sur du silence.
- Transcription (STT) au choix : Whisper (dans la base), Whisper MLX ou Parakeet sur un Mac à puce Apple, ou Voxtral 3 en direct
  (en ligne, Mistral). Voix (TTS) au choix : voix d'Apple, Piper, Kokoro, Voxtral local (puce Apple, 16 Go de mémoire au moins) ou Voxtral 3 en direct, dont le réglage Ton (chaleureux, enjoué…) passe par les balises d’émotion de Mistral.
- Une voix qui parle coupe Atlas aussitôt, et le cœur ne garde que ce qui a été dit.
- Sur le Mac, le micro passe par l'annuleur d'écho de WebRTC (la voix d'Atlas en est retirée) ; le téléphone l'appelle
  depuis la page d'Atlas (bouton micro, WebRTC, adresse en https de Tailscale).

Les clés des moteurs en ligne (Mistral) viennent du cœur, qui les garde pour le modèle du même service : le module ne lit
jamais `secrets.toml`.

Installation : Réglages, Modules, Catalogue, « Installer ». Si `uv` manque, Atlas propose de le télécharger (35 Mo, site
officiel, empreinte vérifiée). La base prend 580 Mo (mot d'éveil, Whisper, Pipecat), plus le modèle du mot d'éveil
(10 Mo). Le module s'installe avec ses deux fiches éteintes. Dans Modules, ouvre « Voix » pour choisir celle à utiliser.

Rien ne se coche à l'installation : chaque liste (transcription, voix, locuteur) montre tout ce qui peut marcher sur cet
ordinateur. Ce qui est déjà là est trouvé seul (les modèles du cache Hugging Face, comme Ollama liste les siens) ; le
reste s'installe d'un clic depuis « Gérer », avec sa taille, moteur compris (Parakeet : 390 Mo, plus son modèle de
1,2 Go), et son avancement. Un modèle ou une voix Piper à soi s'ajoute aussi, par son dépôt Hugging Face (champ « Autre »), ou se trouve seul s'il est déjà dans le cache. Rien ne se télécharge sans ce clic. Un moteur installé ainsi est gardé par le cœur
(`.options.toml`, options cachées de `module.toml`) et revient aux mises à jour.

Publié, le module n'a pas son code : un paquet compilé (`construire.sh`) est joint à la version d'Atlas.

Le module a été essayé sur Mac. La capture du micro sous Windows reste à porter.
