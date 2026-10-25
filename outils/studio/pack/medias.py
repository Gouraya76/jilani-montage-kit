#!/usr/bin/env python3
"""Trouve et télécharge des visuels pour enrichir le montage (affiches, photos, plans de coupe).

    python3 medias.py affiche "The Walking Dead" medias/          affiche officielle d'un film, d'une série, photo d'un acteur (IMDb en grand, sinon TMDB, sinon Wikipédia)
    python3 medias.py scene "The Walking Dead" medias/ --n 4      images officielles de scènes (TMDB via le site), en grand
    python3 medias.py photo "Rick Grimes" medias/                  photo libre (Wikimedia Commons, puis la banque du site)
    python3 medias.py video "zombie apocalypse city" medias/       plan de coupe vidéo libre (Pexels / Pixabay via le site)
Options : --n 3 (nombre de fichiers), --paysage (sinon vertical de préférence).
Affiche le chemin de chaque fichier téléchargé + sa source (à citer dans infos.json « credits »).
L'adresse de la banque du site et le jeton du montage sont lus dans les variables JM_BANQUE et JM_JETON.
"""
import json, os, re, sys, urllib.error, urllib.parse, urllib.request

UA = {'User-Agent': 'JilaniMoneyMontage/1.0 (montage TikTok ; contact via jilani-money.netlify.app)'}


def get(url, binaire=False):
    import time
    for essai in range(3):                      # Wikimédia limite les rafales : on patiente un peu et on réessaie
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                b = r.read()
            return b if binaire else json.loads(b.decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code != 429 or essai == 2: raise
            time.sleep(3 + 4 * essai)


def nom_fichier(dossier, base, ext):
    base = re.sub(r'[^\w\-]+', '-', base.lower()).strip('-')[:50] or 'media'
    p = os.path.join(dossier, f'{base}{ext}'); k = 2
    while os.path.exists(p): p = os.path.join(dossier, f'{base}-{k}{ext}'); k += 1
    return p


def telecharger(url, dossier, base):
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or '.jpg'
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.mp4'): ext = '.jpg'
    data = get(url, True)
    p = nom_fichier(dossier, base, ext)
    open(p, 'wb').write(data)
    return p


def affiche(q, dossier, n):
    """Image principale de la page Wikipédia (affiche du film / de la série, photo de la personne).
    Donne le titre exact si tu le connais (ex. « The Walking Dead (TV series) ») : la page exacte passe avant la recherche."""
    out, vus = [], set()
    def essayer(langue, titre):
        if (langue, titre) in vus: return
        vus.add((langue, titre))
        try:
            s = get(f'https://{langue}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(titre.replace(" ", "_"))}')
        except Exception:
            return
        img = (s.get('originalimage') or s.get('thumbnail') or {}).get('source')
        if img and s.get('type') != 'disambiguation':
            out.append((telecharger(img, dossier, s.get('title', titre)), f'Wikipédia ({langue}) — {s.get("title", titre)}'))
    for langue in ('en', 'fr'):
        essayer(langue, q)
        if len(out) >= n: return out
    for langue in ('en', 'fr'):
        try:
            r = get(f'https://{langue}.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=4&srsearch={urllib.parse.quote(q)}')
            for res in r['query']['search']:
                essayer(langue, res['title'])
                if len(out) >= n: return out
        except Exception as e:
            print('  wikipédia', langue, ':', e, file=sys.stderr)
    return out


def affiche_imdb(q, dossier, n):
    """Affiche officielle en grand depuis IMDb (recherche publique, sans clé). Donne « Titre année » pour viser juste."""
    out = []
    try:
        cle = re.sub(r'\s+', '_', q.strip().lower())
        d = get(f'https://v3.sg.media-imdb.com/suggestion/{urllib.parse.quote(cle[0])}/{urllib.parse.quote(cle)}.json')
        for x in d.get('d', []):
            img = (x.get('i') or {}).get('imageUrl')
            if not img or not x.get('id', '').startswith(('tt', 'nm')): continue
            img = re.sub(r'\._V1_.*\.jpg$', '._V1_SX1200.jpg', img) if '._V1_' in img else img
            p = telecharger(img, dossier, f'{x.get("l", q)} {x.get("y", "")}'.strip()); out.append((p, f'IMDb — {x.get("l")} ({x.get("y", "")})'))
            if len(out) >= n: break
    except Exception as e:
        print('  imdb :', e, file=sys.stderr)
    return out


def photo_commons(q, dossier, n):
    out = []
    try:
        r = get('https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6&gsrlimit=8'
                f'&prop=imageinfo&iiprop=url|size|extmetadata&iiurlwidth=1280&gsrsearch={urllib.parse.quote(q)}')
        for page in sorted((r.get('query') or {}).get('pages', {}).values(), key=lambda p: p.get('index', 99)):
            ii = (page.get('imageinfo') or [{}])[0]
            url = ii.get('thumburl') or ii.get('url')
            if not url or not re.search(r'\.(jpe?g|png|webp)$', urllib.parse.urlparse(url).path, re.I): continue
            lic = ((ii.get('extmetadata') or {}).get('LicenseShortName') or {}).get('value', '')
            p = telecharger(url, dossier, q); out.append((p, f'Wikimedia Commons — {page.get("title")} ({lic})'))
            if len(out) >= n: break
    except Exception as e:
        print('  commons :', e, file=sys.stderr)
    return out


def banque(type_, q, dossier, n, paysage):
    base, jeton = os.environ.get('JM_BANQUE'), os.environ.get('JM_JETON')
    if not base or not jeton: print('  banque du site : adresse ou jeton absent', file=sys.stderr); return []
    try:
        r = get(f'{base}?jeton={jeton}&type={type_}&orientation={"paysage" if paysage else "portrait"}&q={urllib.parse.quote(q)}')
    except Exception as e:
        print('  banque du site :', e, file=sys.stderr); return []
    out = []
    for res in r.get('resultats', [])[:n]:
        try:
            p = telecharger(res['url'], dossier, q); out.append((p, f'{res["source"]} — {res.get("auteur", "")} — {res.get("page", "")}'))
        except Exception as e:
            print('  téléchargement :', e, file=sys.stderr)
    return out


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) < 3: sys.exit(__doc__)
    type_, q, dossier = a[0], a[1], a[2]
    n = int(a[a.index('--n') + 1]) if '--n' in a else (1 if type_ == 'affiche' else 2)
    paysage = '--paysage' in a
    os.makedirs(dossier, exist_ok=True)
    if type_ == 'affiche': res = affiche_imdb(q, dossier, n) or banque('affiche', q, dossier, n, paysage) or affiche(q, dossier, n)
    elif type_ == 'scene': res = banque('scene', q, dossier, n, True)
    elif type_ == 'photo': res = photo_commons(q, dossier, n) or banque('photo', q, dossier, n, paysage)
    else: res = banque('video', q, dossier, n, paysage)
    for p, src in res: print(f'{p}\t{src}')
    if not res: print('aucun résultat', file=sys.stderr); sys.exit(1)
