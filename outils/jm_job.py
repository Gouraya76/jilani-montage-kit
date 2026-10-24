#!/usr/bin/env python3
"""Liaison avec le site JILANI MONEY pour un montage lancé avec l'abonnement Claude du membre.

    python3 outils/jm_job.py demarrer "https://jilani-money.netlify.app/api/montage-job?job=…&t=…"
        -> affiche les consignes complètes et les critères du membre (à suivre à la lettre)
    python3 outils/jm_job.py etape 3 "Je transcris la voix."      (barre de progression sur le site, étapes 1 à 6)
    python3 outils/jm_job.py livrer /workspace/montage.mp4 /workspace/infos.json
        -> envoie la vidéo finie au site (morceaux de 4 Mo) : le membre la télécharge sur la page
    python3 outils/jm_job.py echec "raison en une phrase simple"
Uniquement la bibliothèque standard de Python.
"""
import json, math, os, sys, time, urllib.error, urllib.request

ETAT = os.path.expanduser('~/.jm_job.json')
UA = {'User-Agent': 'jilani-montage-kit/1.0'}
MORCEAU = 4_000_000


def url_job():
    try:
        return json.load(open(ETAT))['url']
    except Exception:
        sys.exit('Lance d’abord : python3 outils/jm_job.py demarrer "ADRESSE_DU_JOB"')


def appel(methode, url, corps=None, binaire=False, essais=4):
    data = corps if binaire else (json.dumps(corps).encode() if corps is not None else None)
    entetes = {**UA, 'Content-Type': 'application/octet-stream' if binaire else 'application/json'}
    for e in range(essais):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, method=methode, headers=entetes), timeout=120) as r:
                txt = r.read().decode('utf-8', 'replace')
                return json.loads(txt) if txt.strip().startswith('{') else txt
        except urllib.error.HTTPError as err:
            msg = err.read().decode('utf-8', 'replace')[:300]
            if err.code in (400, 401, 403, 404, 409, 413) or e == essais - 1:
                sys.exit(f'Erreur du site ({err.code}) : {msg}\nSi c’est « 403 » ou « blocked » : ajoute jilani-money.netlify.app à l’accès réseau de l’environnement (ou choisis « Full »).')
        except Exception as err:
            if e == essais - 1:
                sys.exit(f'Site injoignable : {err}\nVérifie l’accès réseau de l’environnement Claude Code (« Full », ou jilani-money.netlify.app autorisé).')
        time.sleep(2 * (e + 1))


def avec(url, **params):
    return url + ''.join(f'&{k}={v}' for k, v in params.items())


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == 'demarrer':
        url = sys.argv[2].strip().strip('"\'')
        if '/api/montage-job?' not in url:
            sys.exit('Adresse de job invalide.')
        json.dump({'url': url}, open(ETAT, 'w'))
        d = appel('GET', url)
        appel('POST', avec(url, action='etape'), {'n': 1, 'texte': 'Ton Claude a reçu la vidéo et prépare sa machine de montage.'})
        print(d.get('consignes', ''))
        print('\n===== CE QUE LE MEMBRE DEMANDE =====\n' + d.get('message', ''))
    elif cmd == 'etape':
        appel('POST', avec(url_job(), action='etape'), {'n': int(sys.argv[2]), 'texte': ' '.join(sys.argv[3:])[:300]})
        print('ok')
    elif cmd == 'echec':
        appel('POST', avec(url_job(), action='echec'), {'texte': ' '.join(sys.argv[2:])[:500]})
        print('échec signalé au site')
    elif cmd == 'livrer':
        video = sys.argv[2]
        infos = {}
        if len(sys.argv) > 3 and os.path.exists(sys.argv[3]):
            try:
                infos = json.load(open(sys.argv[3], encoding='utf-8'))
            except Exception:
                infos = {}
        taille = os.path.getsize(video)
        n = math.ceil(taille / MORCEAU)
        if n > 60:
            sys.exit('Vidéo trop lourde (240 Mo maximum) : réencode-la plus légère (ex. crf 23) puis relance.')
        url = url_job()
        with open(video, 'rb') as f:
            for i in range(n):
                appel('POST', avec(url, action='morceau', i=i), f.read(MORCEAU), binaire=True)
                print(f'envoi {i + 1}/{n}', flush=True)
        appel('POST', avec(url, action='fin'), {'parts': n, 'taille': taille, 'infos': infos})
        print('Vidéo livrée : le membre peut la télécharger sur le site.')
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
