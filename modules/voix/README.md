# Voix

Deux modules d'Atlas, un seul dossier, un seul environnement Python (`uv`) :

- **Écoute** (entrée, `fiches/ecoute.toml`) : mot d'éveil « Hey Jarvis » (openWakeWord), parole détectée, transcription locale
  faster-whisper, ou Parakeet (MLX) sur un Mac à puce Apple. Ce qu'elle dit vaut une demande de la personne. Le bouton micro du réacteur l'arrête vraiment.
- **Voix** (sortie, `fiches/voix.toml`) : Atlas lit ses réponses à voix haute (`say` sur Mac ; Piper, voix locales portables ; Voxtral de Mistral sur un Mac à puce Apple, plus naturelle mais lente sur 8 Go). Le bouton voix du réacteur la coupe.

Installation : Réglages, Modules, Catalogue, « Installer ». Si `uv` manque, Atlas propose de le télécharger (≈35 Mo, site officiel,
empreinte vérifiée). L'installation télécharge aussi le modèle du mot d'éveil (≈ 10 Mo). Le module s'installe sans rien allumer :
sa fiche (clic sur « Voix » dans Modules) a un bouton par entrée et par sortie, qui suit les boutons micro et haut-parleur du réacteur.
Les modèles de transcription déjà dans le cache Hugging Face sont trouvés seuls, comme Ollama liste les siens ; chacun dit son
moteur (Whisper partout, Parakeet seulement sur un Mac à puce Apple). Un modèle ou une voix Piper absents se choisissent, puis s'installent d'un clic, avec leur taille et leur avancement ;
rien ne se télécharge sans ce clic.

Mac et Windows pour l'instant ; Linux au J12 (openWakeWord y demande `tflite-runtime`).
