# Kit de montage JILANI MONEY

Outil pour les membres de **JILANI MONEY** : faire monter une vidéo TikTok par **son propre abonnement Claude** (Pro ou Max), sans clé API ni crédits à acheter.

## Comment ça marche
1. Sur le site JILANI MONEY → **Machine à vidéos** → **Montage automatique**, choisis « Avec mon abonnement Claude », colle le lien de ta vidéo et choisis tes critères.
2. Clique sur **« Lancer dans mon Claude »** : Claude Code s'ouvre avec ce dépôt et la consigne déjà écrite. Appuie sur Envoyer.
3. Ton Claude fait le montage. Sur le site, la barre de progression avance, puis tu télécharges la vidéo.

## Réglage à faire une seule fois
1. Ouvre https://claude.ai/code et connecte ton compte GitHub (gratuit) quand c'est demandé.
2. Crée un environnement nommé **JILANI MONEY** : menu de l'environnement → **Add environment** (ou Edit sur l'environnement par défaut) → nom « JILANI MONEY » → **Network access : Full** → Save.
   (Plus prudent : « Custom » avec ces domaines + la case « Also include default list » cochée : `jilani-money.netlify.app`, `*.tiktok.com`, `tiktok.com`, `*.tiktokcdn.com`, `*.tiktokcdn-us.com`, `*.tiktokv.com`, `*.ibyteimg.com`, `*.byteoversea.com`, `huggingface.co`, `*.huggingface.co`, `*.hf.co`, `*.wikipedia.org`, `upload.wikimedia.org`, `commons.wikimedia.org`, `image.tmdb.org`, `images.pexels.com`, `videos.pexels.com`, `cdn.pixabay.com`, `*.youtube.com`, `*.googlevideo.com`, `*.instagram.com`, `*.cdninstagram.com`, `x.com`, `*.twimg.com`.)

## Ce que contient ce dépôt
- `CLAUDE.md` : le mode d'emploi lu par Claude.
- `outils/jm_job.py` : envoie l'avancement et la vidéo finie au site.
- `outils/installer.sh` : installe FFmpeg et les outils de montage au démarrage (lancé automatiquement).
Le moteur de montage (pack JILANI MONEY) est téléchargé depuis le site à chaque montage, toujours à jour.

Les montages comptent dans les limites d'utilisation de ton abonnement Claude.
