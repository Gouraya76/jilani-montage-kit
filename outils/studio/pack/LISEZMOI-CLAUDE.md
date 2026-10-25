# Pack montage JILANI MONEY — mode d'emploi pour Claude

But : un montage TikTok 9:16 digne d'un monteur professionnel (3D, 2D, transitions, motion design, affiches, plans de coupe, bruitages sur chaque effet). Jamais minimaliste.

## Outils
- `jm_pro.py` : moteur PRO. `python3 jm_pro.py --exemple` (plan commenté), `--apercu 1,5,9` (images de contrôle), puis `python3 jm_pro.py plan.json montage.mp4`. Panneau 3D flottant ou plein écran, transitions (zoom, whip, glitch, flash, punch, flip 3D, cube 3D), titre 3D + émoji, mots-clés 3D, badges, tampons, compteurs, flèches et cercles animés, images qui entrent à gauche / à droite en 3D, plans de coupe (plein écran ou incrustation), arrêts sur image, zooms punch, sous-titres mot à mot, particules, grain, fin « DIS-LE EN COMMENTAIRE » + « ABONNE-TOI ». Bruitages automatiques sur chaque effet, musique baissée sous la voix, -14 LUFS.
- `effacer.py` : efface sous-titres incrustés, pseudos, filigranes (reconstruction, sans flou). `--zones zones.json` pour les zones repérées à l'œil, `--apercu dossier/` pour vérifier.
- `separer_voix.py` : voix.wav + musique.wav + analyse.json (musique d'origine présente ?). Jamais deux musiques en même temps.
- `transcrire.py` : mots minutés (faster-whisper).
- `medias.py` : `affiche`, `scene`, `photo`, `video` (Wikipédia, Wikimedia Commons, banque du site : TMDB, Pexels, Pixabay). Variables JM_BANQUE et JM_JETON.
- `hq_extraits.py` : la même scène en HD (Dailymotion, Archive.org, YouTube en flux HLS, `--urls` trouvés par la recherche web, ou `--candidats` avec la vidéo HD du membre), recalée et recadrée comme la source.
- `voix_off.py` : voix off Fish Audio / ElevenLabs avec la clé du membre, sans jamais la voir (coffre Anthropic, ou secret réseau de Claude Code). `python3 voix_off.py verifier fish` d'abord : « CLÉ OK » ou « CLÉ ABSENTE » (alors voix d'origine).
- `jm_montage.py` : ancien moteur simple (à n'utiliser qu'en secours).
- `sons/` (41 bruitages, `sons.txt`), `polices/` (Montserrat, OFL).

## Ordre conseillé
1. Regarder (planche d'images), 2. séparer la voix, 3. transcrire, 4. HD si demandé puis effacer, 5. chercher les visuels, 6. plan + aperçus, 7. rendu, 8. contrôle (planche, durée, son).
