#!/usr/bin/env python3
"""Fabrique une voix off (Fish Audio ou ElevenLabs) avec la clé du membre, sans jamais la voir.

    python3 voix_off.py verifier fish            (la clé est-elle là ? crédit restant)
    python3 voix_off.py fish texte.txt voix-off.mp3 [--voix ID_DU_MODELE]
    python3 voix_off.py elevenlabs texte.txt voix-off.mp3 [--voix ID_DE_LA_VOIX]

La clé n'est jamais visible ici :
- montage avec clé API : la variable FISH_API_KEY / ELEVENLABS_API_KEY contient un repère que le coffre Anthropic
  remplace par la vraie clé au moment où la demande sort vers api.fish.audio / api.elevenlabs.io ;
- montage avec l'abonnement (Claude Code) : aucune variable, la clé est un « secret réseau » de l'environnement
  que le proxy de Claude Code ajoute lui-même aux demandes vers ces sites.
Le texte est découpé en paragraphes (≤ 900 caractères) puis recollé. Ensuite : transcrire.py voix-off.mp3 mots.json
pour avoir les mots minutés, et "voix_off": {"fichier": ..., "mots": ...} dans le plan de jm_pro.py.
"""
import json, os, re, subprocess, sys, tempfile, urllib.error, urllib.request

ABSENTE = ('CLÉ ABSENTE : la clé {nom} n’est pas rangée (Claude Code : environnement → Secrets réseau → site {hote} ; '
           'clé API : « Ranger ma clé » sur le site). Garde la voix d’origine et explique-le au membre.')


def entetes(service):
    """En-tête d'authentification seulement si la variable existe (sinon le secret réseau de Claude Code s'en charge)."""
    if service == 'fish':
        cle = os.environ.get('FISH_API_KEY')
        return {'Authorization': f'Bearer {cle}'} if cle else {}
    cle = os.environ.get('ELEVENLABS_API_KEY')
    return {'xi-api-key': cle} if cle else {}


def appel(req, service):
    try:
        with urllib.request.urlopen(req, timeout=180) as r: return r.read()
    except urllib.error.HTTPError as e:
        nom, hote = ('Fish Audio', 'api.fish.audio') if service == 'fish' else ('ElevenLabs', 'api.elevenlabs.io')
        if e.code in (401, 403): sys.exit(ABSENTE.format(nom=nom, hote=hote))
        if e.code == 402: sys.exit(f'CRÉDIT ÉPUISÉ : plus de crédit API {nom}. Garde la voix d’origine et dis au membre d’en ajouter.')
        sys.exit(f'ERREUR {nom} {e.code} : {e.read()[:300].decode("utf-8", "replace")}')


def morceaux(texte, n=900):
    phrases = re.split(r'(?<=[.!?…])\s+', texte.strip()); out, cur = [], ''
    for p in phrases:
        if len(cur) + len(p) + 1 > n and cur: out.append(cur); cur = p
        else: cur = (cur + ' ' + p).strip()
    return out + ([cur] if cur else [])


def fish(texte, voix):
    corps = {'text': texte, 'format': 'mp3', 'mp3_bitrate': 192, 'normalize': True, 'latency': 'normal'}
    if voix: corps['reference_id'] = voix
    req = urllib.request.Request('https://api.fish.audio/v1/tts', data=json.dumps(corps).encode(), method='POST',
                                 headers={**entetes('fish'), 'Content-Type': 'application/json', 'model': 's2.1-pro-free'})   # modèle gratuit et illimité (usage raisonnable) de Fish Audio
    return appel(req, 'fish')


def elevenlabs(texte, voix):
    if not voix:
        req = urllib.request.Request('https://api.elevenlabs.io/v1/voices', headers=entetes('elevenlabs'))
        voix = json.loads(appel(req, 'elevenlabs'))['voices'][0]['voice_id']
    req = urllib.request.Request(f'https://api.elevenlabs.io/v1/text-to-speech/{voix}?output_format=mp3_44100_192', method='POST',
                                 data=json.dumps({'text': texte, 'model_id': 'eleven_multilingual_v2'}).encode(),
                                 headers={**entetes('elevenlabs'), 'Content-Type': 'application/json', 'Accept': 'audio/mpeg'})
    return appel(req, 'elevenlabs')


def verifier(service):
    """Demande sans frais : la clé est-elle bien ajoutée (variable ou secret réseau) ?"""
    url = 'https://api.fish.audio/wallet/self/api-credit' if service == 'fish' else 'https://api.elevenlabs.io/v1/user'
    d = json.loads(appel(urllib.request.Request(url, headers={**entetes(service), 'Accept': 'application/json'}), service) or b'{}')
    credit = d.get('credit') if service == 'fish' else (d.get('subscription') or {}).get('character_count')
    print('CLÉ OK', service, '(modèle gratuit s2.1-pro-free : le crédit ne compte pas)' if service == 'fish' else (f'(crédit : {credit})' if credit is not None else ''))


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == 'verifier': verifier(a[1]); sys.exit(0)
    if len(a) < 3: sys.exit(__doc__)
    service, fichier_texte, sortie = a[0], a[1], a[2]
    voix = a[a.index('--voix') + 1] if '--voix' in a else os.environ.get('JM_VOIX_ID', '')
    texte = open(fichier_texte, encoding='utf-8').read()
    fab = fish if service == 'fish' else elevenlabs
    tmp = tempfile.mkdtemp(); parts = []
    for k, m in enumerate(morceaux(texte)):
        p = os.path.join(tmp, f'{k:03d}.mp3'); open(p, 'wb').write(fab(m, voix)); parts.append(p); print('morceau', k + 1, 'ok', flush=True)
    open(os.path.join(tmp, 'liste.txt'), 'w').write(''.join(f"file '{p}'\n" for p in parts))
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', os.path.join(tmp, 'liste.txt'), '-c:a', 'libmp3lame', '-b:a', '192k', sortie], check=True)
    print('ok', sortie)
