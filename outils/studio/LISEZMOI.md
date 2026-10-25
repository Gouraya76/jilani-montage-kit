# Studio JILANI MONEY — outils de montage sauvegardés

Tous les outils construits pendant les montages, rangés pour être réutilisés d'une session à l'autre.

## Installation dans une nouvelle session
```bash
mkdir -p /workspace && cp -r outils/studio/pack /workspace/pack      # les scripts cherchent le pack dans /workspace/pack
mkdir -p /workspace/scripts && ln -sf /workspace/pack/polices /workspace/scripts/polices && ln -sf /workspace/pack/sons /workspace/scripts/sons
apt-get install -y blender                                         # facultatif : vraie 3D (titres en relief, globe…)
```

## `pack/` — pack de montage JILANI MONEY (copie du site)
`jm_pro.py` (moteur pro), `effacer.py`, `separer_voix.py`, `transcrire.py`, `medias.py`, `hq_extraits.py`, `voix_off.py`,
`sons/` (41 bruitages, `sons.txt`), `polices/` (Montserrat, OFL). Mode d'emploi : `pack/LISEZMOI-CLAUDE.md`.

## `actu/` — vidéos d'actualité « C1 News »
- `actu_pro.py` : **le montage complet** (modèle validé par le membre).
  Plein écran 9:16, en-tête discret (point rouge qui pulse, date, lieu en gris) + petit logo C1 News en haut à droite,
  barre de progression rouge, titre unique 3D de 0 à 6 s (étiquettes blanches à barre rouge), **pas de sous-titres pendant le titre**,
  sous-titres en grandes majuscules blanches, transitions 3D/2D à chaque coupe (cube, flip, whip, zoom, glitch),
  jauge de vitesse animée, compteurs 3D qui défilent avec icônes (alerte, éclair, sirène, pluie), pluie/vent en particules,
  tremblement caméra sur les impacts, vignette, bruitages synchronisés, -14 LUFS.
  `python3 actu_pro.py plan.json sortie.mp4` ; aperçu de quelques instants : `python3 actu_pro.py plan.json x.mp4 1.5,10,20`
  (écrit des `ap-*.jpg` — chemin à adapter en fin de script).
- `plan_exemple.json` : exemple de plan (durée, coupes, voix, musique, mots minutés, logo, date, lieu, titre, chiffres).
- `fond_exemple.py` : fabrique le fond (plans recadrés en 9:16, enchaînés) + `coupes.json`.
- `actu_simple.py` / `actu_bandeau.py` : anciennes variantes (habillage simple, gros bandeau TV).
- `logo-c1news.png` : logo C1 News détouré (fond transparent).

## `films/` — vidéos films / séries
- `jm_pro_transitions.py` : `jm_pro.py` + clé de plan `"transitions": [{"t": 10.5, "type": "cube"}, …]` pour choisir
  les transitions à la main (les autres coupes restent franches, comme dans une bande-annonce).
- `vertical_916.py` : recadre une vidéo paysage en 9:16 plein écran en suivant la zone la plus détaillée, plan par plan.
- `fond_extraits.py` : exemple de découpe d'extraits.

## Ce que le membre veut (à respecter)
- **Plein écran 9:16**, jamais un petit carré ou une vidéo paysage au milieu du noir.
- Vraiment monté : transitions 3D/2D, motion design, animations, bruitages — jamais minimaliste.
- Plus d'**1 minute** (monétisation TikTok).
- Voix Fish Audio du membre (demander l'identifiant ; « fdsfsd » de Tao Leneuro = `f4dd1fa4d97b41068a795a2619ecd437`).
- Infos vérifiées (avec « selon »/« estimé » quand ce n'est pas officiel) ; provocations seulement sur la forme.
- Sources vidéo : liens TikTok du membre (HD) > Dailymotion (souvent 288p depuis le serveur) ; YouTube bloqué sans jeton anti-robot.

## `blender/` — vraie 3D (Blender 4, sans écran)
`apt-get install -y blender`, puis `blender -b -P script.py`. Sur ce serveur : moteur **CYCLES sur CPU** (EEVEE demande une carte graphique),
`s.cycles.use_denoising=False` (débruiteur absent), 32 échantillons ≈ quelques secondes par image en 540x960.
`texte3d_exemple.py` : texte en relief métal rouge, caméra, lumière, rendu PNG (base pour logo/titres 3D animés).
