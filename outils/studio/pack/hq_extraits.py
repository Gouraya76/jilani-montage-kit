#!/usr/bin/env python3
"""Remplace les extraits de la vidéo source par les MÊMES scènes en haute qualité trouvées sur YouTube (best-effort).

    python3 hq_extraits.py source.mp4 "Twilight Carlisle Cullen|Twilight 2008 Cullen family scene" hq.mp4 [--n 3] [--max 1080]
        (plusieurs recherches séparées par « | » ; Dailymotion et Archive.org, puis YouTube s'il n'est pas bloqué)
    python3 hq_extraits.py source.mp4 - hq.mp4 --urls https://ok.ru/video/…,https://www.dailymotion.com/video/…
        (liens trouvés avec la recherche web sur les plateformes : OK.ru, Dailymotion, VK, Archive.org, Bilibili, Vimeo…)
    python3 hq_extraits.py source.mp4 - hq.mp4 --candidats film-hd.mp4,extrait2.mp4     (vidéos HD envoyées par le membre)

1. Cherche N vidéos par recherche (Dailymotion, puis YouTube) et les télécharge (≤ --max pixels de haut), les plus nettes d'abord.
2. Découpe la source en plans, et pour chaque plan cherche la même image dans les vidéos trouvées
   (points caractéristiques ORB + géométrie RANSAC : marche même si la source est recadrée ou zoomée).
3. Recale le plan au bon instant, recadre la version HD exactement comme la source, et fabrique hq.mp4
   (même durée, même son que la source ; les plans sans équivalent sont simplement agrandis).
Écrit hq.json (plans remplacés, score) et « PROGRESSION nn ». Si YouTube refuse le téléchargement, le dit et s'arrête
(code 2) : continue alors avec la source normale.
"""
import json, math, os, re, subprocess, sys, tempfile
import numpy as np, cv2

a = sys.argv[1:]
SRC, Q, OUT = a[0], a[1], a[2]
N = int(a[a.index('--n') + 1]) if '--n' in a else 3
HMAX = int(a[a.index('--max') + 1]) if '--max' in a else 1080
TMP = tempfile.mkdtemp(prefix='hq-', dir=os.path.dirname(os.path.abspath(OUT)))
FPS = 30


def sonde(p):
    d = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=width,height:format=duration', '-of', 'json', p],
                                  capture_output=True, text=True).stdout)
    return float(d['format']['duration']), d['streams'][0]['width'], d['streams'][0]['height']


def images(p, fps, largeur):
    w0 = largeur
    _, w, h = sonde(p); hh = int(h * w0 / w) // 2 * 2
    pr = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-i', p, '-vf', f'fps={fps},scale={w0}:{hh}', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], stdout=subprocess.PIPE)
    out = []
    while True:
        b = pr.stdout.read(w0 * hh)
        if len(b) < w0 * hh: break
        out.append(np.frombuffer(b, np.uint8).reshape(hh, w0))
    pr.wait(); return out


# ---------- 1. recherche et téléchargement (ou vidéos HD fournies)
# YouTube bloque presque toujours les serveurs ; Dailymotion répond (recherche publique + téléchargement).
import shutil, urllib.parse, urllib.request
FOURNIS = [x for x in (a[a.index('--candidats') + 1].split(',') if '--candidats' in a else []) if os.path.exists(x)]
URLS = [x for x in (a[a.index('--urls') + 1].split(',') if '--urls' in a else []) if x.startswith('http')]
REQUETES = [q.strip() for q in Q.split('|') if q.strip() and q.strip() != '-']
JS = ['--js-runtimes', 'node'] if shutil.which('node') and not shutil.which('deno') else []
# jeton anti-robot YouTube (installé par installer.sh dans /opt/bgutil, ou à la main : voir LISEZMOI-CLAUDE.md)
POT = next((f for f in ('/opt/bgutil/server/build/generate_once.js', os.path.expanduser('~/bgutil-ytdlp-pot-provider/server/build/generate_once.js')) if os.path.exists(f)), None)
if POT: JS += ['--extractor-args', f'youtubepot-bgutilscript:script_path={POT}']
SOURCES = {}
VUS = set()
def dl(url, nom):
    # durée d'abord : un film entier se télécharge en 720p (assez net, 2 fois moins lourd), un extrait jusqu'à --max
    r0 = subprocess.run(['yt-dlp', *JS, '--no-playlist', '--no-warnings', '--print', 'duration', url], capture_output=True, text=True, timeout=120)
    try: duree = float(r0.stdout.strip().splitlines()[-1])
    except Exception: duree = 0
    h = min(HMAX, 720) if duree > 900 else HMAX
    # YouTube : les flux HLS (m3u8) passent depuis un serveur, les flux DASH répondent souvent 403 → HLS d'abord
    hls = f'b[protocol^=m3u8][height<={h}]/bv*[protocol^=m3u8][height<={h}]+ba/' if 'youtu' in url or url.startswith('ytsearch') else ''
    r = subprocess.run(['yt-dlp', *JS, '--no-playlist', '--no-warnings', '-f', hls + f'bv*[height<={h}][ext=mp4]+ba/b[height<={h}]/bv*[height<={h}]+ba/b',
                        '--max-filesize', '3500M', '-o', f'{TMP}/{nom}.%(ext)s', url], capture_output=True, text=True, timeout=3000)
    if r.returncode and 'youtu' in url + nom:                        # autre essai : client « web_safari » (HLS jusqu'en 1080p)
        r = subprocess.run(['yt-dlp', *JS, '--no-playlist', '--no-warnings', '--extractor-args', 'youtube:player_client=web_safari,mweb',
                            '-f', f'b[height<={h}]/b', '-o', f'{TMP}/{nom}.%(ext)s', url], capture_output=True, text=True, timeout=3000)
    f = [os.path.join(TMP, x) for x in os.listdir(TMP) if x.startswith(nom + '.') and x.endswith(('.mp4', '.webm', '.mkv'))]
    return f[0] if f else None, (r.stderr or '')[-300:]
def dailymotion(q, n):
    url = ('https://api.dailymotion.com/videos?fields=id,title,duration,available_formats&limit=12&sort=relevance&search=' + urllib.parse.quote(q))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as r: lst = json.load(r).get('list', [])
    except Exception as e:
        print('dailymotion :', e, file=sys.stderr); return []
    rang = {'hd1080': 3, 'hd720': 2, 'hq': 1}
    mots = [m for m in re.findall(r'\w+', q.lower()) if len(m) > 3 and m not in ('scene', 'scène', 'film', 'movie', 'clip', 'extrait')]
    lst = [v for v in lst if 20 < v.get('duration', 0) < 1500 and v['id'] not in VUS
           and sum(m in v.get('title', '').lower() for m in mots) >= max(1, len(mots) // 2)]   # titre pertinent (pas de foot pour « Twilight »)
    lst.sort(key=lambda v: -max([rang.get(f, 0) for f in v.get('available_formats') or []] or [0]))   # les plus nettes d'abord
    return lst[:n]
def archive(q, n):
    url = 'https://archive.org/advancedsearch.php?fl[]=identifier&fl[]=title&rows=8&output=json&q=' + urllib.parse.quote(f'({q}) AND mediatype:movies')
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as r: docs = json.load(r)['response']['docs']
    except Exception as e:
        print('archive.org :', e, file=sys.stderr); return []
    return docs[:n]
cands = list(FOURNIS)
for k, u in enumerate(URLS):                                          # liens trouvés par Claude (recherche web sur les plateformes)
    f, err = dl(u, f'url{k}')
    if f: cands.append(f); SOURCES[f] = u
    else: print('  échec', u, err, file=sys.stderr)
if not cands:
    for k, q in enumerate(REQUETES):
        for v in dailymotion(q, N):
            if len(cands) >= N * max(1, len(REQUETES)): break
            VUS.add(v['id'])
            f, err = dl(f'https://www.dailymotion.com/video/{v["id"]}', f'dm{len(cands)}')
            if f: cands.append(f); SOURCES[f] = f'Dailymotion — {v["title"]} — https://www.dailymotion.com/video/{v["id"]}'
            else: print('  échec', v['id'], err, file=sys.stderr)
        for d_ in archive(q, 2):
            f, err = dl(f'https://archive.org/details/{d_["identifier"]}', f'ar{len(cands)}')
            if f: cands.append(f); SOURCES[f] = f'Archive.org — {d_.get("title", "")} — https://archive.org/details/{d_["identifier"]}'
        f, err = dl(f'ytsearch1:{q}', f'yt{k}')                     # YouTube (flux HLS)
        if f: cands.append(f); SOURCES[f] = f'YouTube — {q}'
if not cands:
    print('Aucune vidéo HD trouvée ou téléchargée (rien de téléchargeable sur YouTube, Dailymotion et Archive.org).', file=sys.stderr); sys.exit(2)
print('PROGRESSION 20\ncandidats :', len(cands), flush=True)

# ---------- 2. plans de la source et correspondances
DS, SW, SH = sonde(SRC)
out = subprocess.run(['ffmpeg', '-hide_banner', '-nostdin', '-i', SRC, '-vf', "scale=240:-2,select='gt(scene,0.30)',showinfo", '-an', '-f', 'null', '-'], capture_output=True, text=True).stderr
bornes = [0.0] + [float(x) for x in re.findall(r'pts_time:([0-9.]+)', out)] + [DS]
plans = [(x, y) for x, y in zip(bornes, bornes[1:]) if y - x > 0.4]
orb = cv2.ORB_create(1500); bf = cv2.BFMatcher(cv2.NORM_HAMMING)
src2 = images(SRC, 2, 480)
def desc(g): return orb.detectAndCompute(g, None)
def histo(g):
    h = cv2.calcHist([g], [0], None, [32], [0, 256]); return cv2.normalize(h, h).flatten()
cand_imgs = {p: images(p, 2 if sonde(p)[0] < 600 else 1, 640) for p in cands}      # film entier : 1 image par seconde
cand_hist = {p: np.array([histo(g) for g in v]) for p, v in cand_imgs.items()}
_desc = {}
def desc_c(p, j):
    if (p, j) not in _desc: _desc[(p, j)] = desc(cand_imgs[p][j])
    return _desc[(p, j)]
pas_c = {p: (0.5 if sonde(p)[0] < 600 else 1.0) for p in cands}
print('PROGRESSION 45', flush=True)
corr = []
for k, (x, y) in enumerate(plans):
    i = min(len(src2) - 1, int((x + y) / 2 * 2))
    meilleur = None
    for miroir in (False, True):                                  # les montages TikTok retournent souvent l'image
        g0 = cv2.flip(src2[i], 1) if miroir else src2[i]
        ks, ds = desc(g0)
        if ds is None or len(ks) < 30: continue
        for p in cands:
            for j in range(len(cand_imgs[p])):
                kc, dc = desc_c(p, j)
                if dc is None or len(kc) < 30: continue
                m = [p2[0] for p2 in bf.knnMatch(ds, dc, k=2) if len(p2) == 2 and p2[0].distance < 0.8 * p2[1].distance]
                if len(m) < 18: continue
                A, inl = cv2.estimateAffinePartial2D(np.float32([kc[u.trainIdx].pt for u in m]), np.float32([ks[u.queryIdx].pt for u in m]), method=cv2.RANSAC, ransacReprojThreshold=5)
                n_in = int(inl.sum()) if inl is not None else 0
                if A is None or n_in < 18: continue
                ech = math.hypot(A[0, 0], A[1, 0])
                if not 0.25 < ech < 6 or abs(math.atan2(A[1, 0], A[0, 0])) > 0.2: continue        # zoom plausible, image droite
                if meilleur is None or n_in > meilleur[0]: meilleur = (n_in, p, j * pas_c[p], A, miroir)
        if meilleur and meilleur[0] >= 30: break
    if meilleur:
        n_in, p, tc, A, miroir = meilleur
        corr.append({'plan': k, 'src': [x, y], 'video': os.path.basename(p), 'chemin': p, 't_candidat': tc - ((x + y) / 2 - x), 'points': n_in, 'A': A.tolist(), 'miroir': miroir})
    print(f'  plan {k + 1}/{len(plans)} : ' + (f'retrouvé ({meilleur[0]} points)' if meilleur else 'pas trouvé'), flush=True)
# recalage fin de l'instant (les vidéos ont été comparées à 2 images/s) : ±0,6 s par pas de 1/30 s
def gris_a(p, t, w):
    b = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', f'{max(0, t):.3f}', '-i', p, '-frames:v', '1', '-vf', f'scale={w}:-2', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True).stdout
    _, w0, h0 = sonde(p); h = len(b) // w if w else 0
    return np.frombuffer(b, np.uint8).reshape(h, w).astype(np.float32) if h else None
def lot(p, t0, dur, w):
    _, w0, h0 = sonde(p); hh = int(h0 * w / w0) // 2 * 2
    b = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', f'{max(0, t0):.3f}', '-t', f'{dur:.3f}', '-i', p, '-vf', f'fps={FPS},scale={w}:{hh}', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True).stdout
    return [np.frombuffer(b[k:k + w * hh], np.uint8).reshape(hh, w).astype(np.float32) for k in range(0, len(b) - w * hh + 1, w * hh)]
for c in corr:
    x, y = c['src']; tm = (x + y) / 2
    ref = gris_a(SRC, tm, 480)
    if ref is None: continue
    if c.get('miroir'): ref = cv2.flip(ref, 1)
    _, cw, ch = sonde(c['chemin'])
    A = np.vstack([np.array(c['A']), [0, 0, 1]]) @ np.diag([640 / 640, 640 / 640, 1])
    t_c = c['t_candidat'] + (tm - x)
    serie = lot(c['chemin'], t_c - 1.1, 2.2, 640)
    best, bt = -2, t_c
    for k, g in enumerate(serie):
        wv = cv2.warpAffine(g, A[:2], (ref.shape[1], ref.shape[0]))
        a_, b_ = wv - wv.mean(), ref - ref.mean(); sc = float((a_ * b_).sum() / (np.sqrt((a_ ** 2).sum() * (b_ ** 2).sum()) + 1e-6))
        if sc > best: best, bt = sc, t_c - 1.1 + k / FPS
    c['t_candidat'] = bt - (tm - x); c['ressemblance'] = round(best, 3)
corr = [c for c in corr if c.get('ressemblance', 1) > 0.35]
print('PROGRESSION 60\nplans remplacés :', len(corr), '/', len(plans), flush=True)
json.dump([dict({k: v for k, v in c.items() if k != 'chemin'}, source=SOURCES.get(c['chemin'], os.path.basename(c['chemin']))) for c in corr], open(os.path.splitext(OUT)[0] + '.json', 'w'), indent=1, ensure_ascii=False)

# ---------- 3. fabrication : plans HD recadrés comme la source (taille de sortie : source agrandie jusqu'à 1080 de large)
E = max(1.0, min(1080 / SW, 1920 / SH)); OW, OH = int(SW * E) // 2 * 2, int(SH * E) // 2 * 2
def lecteur(p, t0, w, h):
    return subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'quiet', '-ss', f'{max(0, t0):.3f}', '-i', p, '-vf', f'fps={FPS}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
src = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'quiet', '-i', SRC, '-vf', f'fps={FPS}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
enc = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{OW}x{OH}', '-r', str(FPS), '-i', '-', '-i', SRC,
                        '-map', '0:v', '-map', '1:a?', '-c:a', 'copy', '-c:v', 'libx264', '-preset', 'fast', '-crf', '16', '-pix_fmt', 'yuv420p', '-shortest', OUT], stdin=subprocess.PIPE)
par_plan = {c['plan']: c for c in corr}
NT = int(DS * FPS); i = 0; actif = None; lec = None
while i < NT:
    b = src.stdout.read(SW * SH * 3)
    if len(b) < SW * SH * 3: break
    f = np.frombuffer(b, np.uint8).reshape(SH, SW, 3); t = i / FPS
    k = next((n for n, (x, y) in enumerate(plans) if x <= t < y), None)
    c = par_plan.get(k)
    img = None
    if c is not None:
        if actif != k:
            if lec: lec.kill()
            _, cw, ch = sonde(c['chemin']); lec = lecteur(c['chemin'], c['t_candidat'], cw, ch); actif = k; dims = (cw, ch)
        cw, ch = dims; bb = lec.stdout.read(cw * ch * 3)
        if len(bb) == cw * ch * 3:
            hd = np.frombuffer(bb, np.uint8).reshape(ch, cw, 3)
            A = np.array(c['A'], np.float64)                       # candidat (640 de large) -> source (480 de large)
            s_c, s_s = 640 / cw, 480 / SW
            M = np.vstack([A, [0, 0, 1]]) @ np.diag([s_c, s_c, 1]); M = np.diag([E / s_s, E / s_s, 1]) @ M
            img = cv2.warpAffine(hd, M[:2], (OW, OH), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            if c.get('miroir'): img = cv2.flip(img, 1)
    if img is None: img = cv2.resize(f, (OW, OH), interpolation=cv2.INTER_CUBIC)
    enc.stdin.write(img.tobytes()); i += 1
    if i % 90 == 0: print(f'PROGRESSION {60 + int(39 * i / NT)}', flush=True)
enc.stdin.close(); enc.wait()
print('PROGRESSION 100\nok', OUT)
