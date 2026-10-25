#!/usr/bin/env python3
"""Moteur de montage PRO JILANI MONEY (1080x1920, 30 i/s) — niveau monteur professionnel, jamais basique.

Prend une vidéo source (déjà nettoyée par effacer.py) + un plan JSON écrit par Claude, et fabrique :
- cadrage 9:16 : plein écran qui dérive (vidéo verticale) ou panneau flottant 3D sur fond flouté, avec un plan sur trois
  en plein écran recadré (vidéo horizontale) ;
- une transition à chaque coupe (zoom, whip gauche/droite/haut, glitch, flash, punch, flip 3D, cube 3D) ;
- titre 3D avec émoji, mots-clés 3D, badges « N°1 », tampons, compteurs animés, flèches et cercles animés,
  images (affiches, photos) qui entrent par la gauche / la droite en 3D, plans de coupe (b-roll) en plein écran ou
  en incrustation, arrêts sur image, zooms « punch » ;
- sous-titres mot à mot (mots forts en couleur), particules, grain, vignette, barre de progression, fin
  « DIS-LE EN COMMENTAIRE » + « ABONNE-TOI » ;
- son : voix (d'origine, séparée de sa musique, ou voix off), musique baissée sous la voix, bruitages synchronisés
  avec CHAQUE effet, volume final -14 LUFS.

Utilisation :
    python3 jm_pro.py --exemple > plan.json          (plan commenté)
    python3 jm_pro.py plan.json --apercu 1,5,12      (images de contrôle dans apercus/, rapide)
    python3 jm_pro.py plan.json montage.mp4          (rendu complet, en parallèle sur tous les processeurs)
Toutes les heures du plan sont en secondes DANS LA SOURCE (comme la transcription) ; le moteur les recale après les coupes.
Écrit « PROGRESSION nn » au fil du rendu.
"""
import json, math, os, re, subprocess, sys, tempfile, time
import multiprocessing as mp
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ICI = os.path.dirname(os.path.abspath(__file__))
W, H, FPS, SR = 1080, 1920, 30, 48000

EXEMPLE = {
    "source": "/workspace/propre.mp4",
    "voix": {"fichier": "/workspace/sep/voix.wav", "volume": 1.0},     # null = son de la source ; voix.wav = voix séparée de sa musique
    "voix_off": None,                  # {"fichier": "voix-off.mp3", "mots": [...]} : la voix off remplace la voix d'origine (images calées dessus)
    "segments": [[0.0, 12.4], [14.1, 31.0]],    # parties gardées, dans l'ordre ([] = toute la vidéo)
    "vitesse": 1.0,                    # 1.0 à 1.15
    "mots": [{"m": "Regarde", "debut": 0.31, "fin": 0.72}],             # transcription mot par mot (transcrire.py)
    "titre": {"lignes": ["CE DÉTAIL QUE", "PERSONNE N'A VU"], "emoji": "👀", "duree": 3.2},
    "couleur": "#FFD60A",
    "rythme": "explosif",              # sobre | dynamique | explosif (choix et fréquence des transitions)
    "sous_titres": "mot_cle",          # mot_cle | karaoke | classique | aucun
    "sous_titres_y": 0.5,              # hauteur des sous-titres (fraction de l'image finale) ; mets celle donnée par effacer.py pour couvrir les anciens
    "mots_forts": ["jamais", "secret"],
    "moments": [
        {"t": 4.2, "type": "image", "fichier": "/workspace/medias/affiche.jpg", "cote": "droite", "legende": "THE WALKING DEAD", "duree": 2.6},
        {"t": 7.0, "type": "badge", "texte": "SECRET N°1"},
        {"t": 9.5, "type": "mot", "texte": "IMPOSSIBLE"},
        {"t": 11.0, "type": "fleche", "x": 0.62, "y": 0.40, "depuis": "gauche", "duree": 1.6},
        {"t": 11.0, "type": "cercle", "x": 0.62, "y": 0.40, "r": 0.12, "duree": 1.6},
        {"t": 15.0, "type": "broll", "fichier": "/workspace/medias/pexels-123.mp4", "mode": "incrustation", "duree": 2.5, "legende": "EN VRAI"},
        {"t": 18.0, "type": "compteur", "valeur": 1500000, "legende": "DE DOLLARS"},
        {"t": 21.0, "type": "tampon", "texte": "CONFIRMÉ"},
        {"t": 24.0, "type": "arret", "duree": 1.2, "texte": "REGARDE BIEN"},
        {"t": 26.0, "type": "zoom", "x": 0.5, "y": 0.35, "echelle": 1.35, "duree": 1.4},
        {"t": 28.0, "type": "emoji", "texte": "😱"},
    ],
    "question": "ET TOI, TU L'AVAIS VU ?",     # fin : question + « DIS-LE EN COMMENTAIRE » + « ABONNE-TOI »
    "musique": {"fichier": "/workspace/musique.mp3", "volume": 0.20},       # null = aucune ; "/workspace/sep/musique.wav" = musique d'origine seule
    "ambiance": "poussiere",           # poussiere | braises | etincelles | neige | aucune
    "bruitages": [],                   # en plus des bruitages automatiques : [{"t": 3.2, "son": "impact-cinema", "volume": 0.8}]
}

# ===================================================================================== outils
def clamp(x, a=0.0, b=1.0): return a if x < a else b if x > b else x
def ease(p): p = clamp(p); return p * p * (3 - 2 * p)
def eout(p): p = clamp(p); return 1 - (1 - p) ** 3
def ein(p): p = clamp(p); return p ** 3
def back(p, s=1.9): p = clamp(p) - 1; return p * p * ((s + 1) * p + s) + 1
def hexrgb(h): h = h.lstrip('#'); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def police(taille, poids=900):
    for p in (f'{ICI}/polices/Montserrat-{poids}.ttf', f'{ICI}/polices/Montserrat-900.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'):
        if os.path.exists(p): return ImageFont.truetype(p, taille)
    return ImageFont.load_default()

_txt = {}
def texte_img(txt, taille, couleur=(255, 255, 255), contour=9, relief=0, coul_relief=(60, 40, 10), ombre=True, poids=900):
    """Texte RGBA : contour, extrusion 3D, reflet, ombre portée."""
    k = (txt, taille, couleur, contour, relief, coul_relief, ombre, poids)
    if k in _txt: return _txt[k]
    f = police(taille, poids)
    l, t, r, b = f.getbbox(txt, stroke_width=contour)
    w, h = r - l + relief + 70, b - t + relief + 70
    im = Image.new('RGBA', (w, h)); ox, oy = 35 - l, 35 - t
    if ombre:
        sh = Image.new('RGBA', (w, h))
        ImageDraw.Draw(sh).text((ox + relief + 8, oy + relief + 14), txt, font=f, fill=(0, 0, 0, 180), stroke_width=contour, stroke_fill=(0, 0, 0, 180))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(im)
    for i in range(relief, 0, -1):
        c = tuple(int(v * (0.5 + 0.5 * (1 - i / max(relief, 1)))) for v in coul_relief)
        d.text((ox + i, oy + i), txt, font=f, fill=c + (255,), stroke_width=contour, stroke_fill=(6, 4, 8, 255))
    d.text((ox, oy), txt, font=f, fill=tuple(couleur) + (255,), stroke_width=contour, stroke_fill=(6, 4, 8, 255))
    if relief:
        m = Image.new('L', (w, h)); ImageDraw.Draw(m).text((ox, oy), txt, font=f, fill=255)
        ys = np.arange(h)[:, None]; g = np.clip(1 - (ys - oy) / (0.5 * (b - t)), 0, 1) * 85 * np.ones((1, w))
        lum = Image.new('RGBA', (w, h), (255, 255, 255, 0)); lum.putalpha(Image.fromarray(np.minimum(np.array(m), g).astype(np.uint8)))
        im = Image.alpha_composite(im, lum)
    _txt[k] = im
    return im

def largeur_max(im, wmax=1000):
    return im.resize((wmax, int(im.height * wmax / im.width)), Image.LANCZOS) if im.width > wmax else im

def coller(fond, img, cx, cy, echelle=1.0, alpha=1.0, angle=0.0):
    if img is None or alpha <= 0.01 or echelle <= 0.01: return
    a = img if isinstance(img, np.ndarray) else np.asarray(img)
    a = a.astype(np.float32)
    if echelle != 1.0 or angle:
        h, w = a.shape[:2]; M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, echelle)
        c, s = abs(M[0, 0]), abs(M[0, 1]); nw, nh = int(h * s + w * c) + 2, int(h * c + w * s) + 2
        M[0, 2] += nw / 2 - w / 2; M[1, 2] += nh / 2 - h / 2
        a = cv2.warpAffine(a, M, (nw, nh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    h, w = a.shape[:2]; x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if xa >= xb or ya >= yb: return
    sub = a[ya - y0:yb - y0, xa - x0:xb - x0]; al = sub[..., 3:4] / 255.0 * alpha
    fond[ya:yb, xa:xb] = fond[ya:yb, xa:xb] * (1 - al) + sub[..., :3] * al

def lueur(im, rayon=12, force=1.6):
    g = np.asarray(im.filter(ImageFilter.GaussianBlur(rayon))).astype(np.float32); g[..., 3] = np.minimum(255, g[..., 3] * force)
    return Image.alpha_composite(Image.fromarray(g.astype(np.uint8)), im)

def perspective(img, ax=0.0, ay=0.0, f=1600.0):
    """Rotation 3D (degrés autour de X puis Y) d'une image RGBA (np) autour de son centre."""
    h, w = img.shape[:2]; ax, ay = math.radians(ax), math.radians(ay); pts = []
    for (x, y) in [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]:
        y2, z2 = y * math.cos(ax), y * math.sin(ax)
        x3, z3 = x * math.cos(ay) + z2 * math.sin(ay), -x * math.sin(ay) + z2 * math.cos(ay)
        s = f / (f + z3); pts.append((x3 * s, y2 * s))
    ow, oh = int(w * 1.5), int(h * 1.5)
    M = cv2.getPerspectiveTransform(np.float32([(0, 0), (w, 0), (w, h), (0, h)]), np.float32([(ow / 2 + x, oh / 2 + y) for x, y in pts]))
    return cv2.warpPerspective(img, M, (ow, oh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))

def carte(rgb, bord=10, coul=(255, 255, 255), rayon=26):
    """Image RGB -> carte RGBA à coins arrondis, bord blanc et ombre (pour panneaux, affiches, incrustations)."""
    h, w = rgb.shape[:2]; m = 40
    c = np.zeros((h + 2 * bord + 2 * m, w + 2 * bord + 2 * m, 4), np.float32)
    masque = Image.new('L', (w + 2 * bord, h + 2 * bord)); ImageDraw.Draw(masque).rounded_rectangle([0, 0, w + 2 * bord - 1, h + 2 * bord - 1], rayon, fill=255)
    mk = np.asarray(masque).astype(np.float32)
    om = np.zeros(c.shape[:2], np.float32); om[m + 14:m + 14 + mk.shape[0], m + 6:m + 6 + mk.shape[1]] = mk
    c[..., 3] = cv2.GaussianBlur(om, (0, 0), 16) * 0.6
    ins = np.zeros((h + 2 * bord, w + 2 * bord, 3), np.float32); ins[:] = coul; ins[bord:bord + h, bord:bord + w] = rgb
    al = mk[..., None] / 255
    zone = c[m:m + h + 2 * bord, m:m + w + 2 * bord]
    zone[..., :3] = zone[..., :3] * (1 - al) + ins * al; zone[..., 3:4] = np.maximum(zone[..., 3:4], mk[..., None])
    return c

def sonde(p):
    d = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,width,height', '-of', 'json', p],
                                  capture_output=True, text=True, check=True).stdout)
    v = next((s for s in d['streams'] if s.get('codec_type') == 'video'), {})
    return float(d['format']['duration']), v.get('width', 0), v.get('height', 0), any(s.get('codec_type') == 'audio' for s in d['streams'])

# ===================================================================================== plan
if len(sys.argv) < 2 or sys.argv[1] == '--exemple':
    print(json.dumps(EXEMPLE, ensure_ascii=False, indent=2)); sys.exit()
PLAN = json.load(open(sys.argv[1], encoding='utf-8'))
SRC = PLAN['source']
DUR_SRC, SW, SH, A_AUDIO = sonde(SRC)
VERTICAL = SH > SW * 1.2
ACC = hexrgb(PLAN.get('couleur', '#FFD60A')); ACC_F = tuple(int(c * 0.45) for c in ACC)
RYTHME = PLAN.get('rythme', 'dynamique')
VIT = clamp(float(PLAN.get('vitesse', 1.0)), 0.8, 1.25)
SEGS = [(clamp(a, 0, DUR_SRC), clamp(b, 0, DUR_SRC)) for a, b in (PLAN.get('segments') or [[0, DUR_SRC]]) if b - a > 0.2]
VOIX_OFF = PLAN.get('voix_off')

# ---- correspondance temps de sortie <-> temps source
O = [0.0]
for a, b in SEGS: O.append(O[-1] + (b - a) / VIT)
DUREE_IMG = O[-1]
if VOIX_OFF:                         # voix off : les images (segments enchaînés) s'étirent sur la durée de la voix
    DUREE_VOIX = sonde(VOIX_OFF['fichier'])[0]
    ETIRE = DUREE_IMG / max(DUREE_VOIX, 0.1)
else:
    DUREE_VOIX = DUREE_IMG; ETIRE = 1.0
def t_src(t):
    u = clamp(t * ETIRE, 0, DUREE_IMG - 1e-3)
    k = min(len(SEGS) - 1, max(0, int(np.searchsorted(O, u, side='right')) - 1))
    return SEGS[k][0] + (u - O[k]) * VIT
def t_sortie(s):
    for k, (a, b) in enumerate(SEGS):
        if a - 0.05 <= s <= b + 0.05: return (O[k] + (clamp(s, a, b) - a) / VIT) / ETIRE
    return None
FIN_VOIX = DUREE_VOIX
DUREE = round(FIN_VOIX + 2.4, 2)
NTOT = int(round(DUREE * FPS))

# ---- mots (heures de sortie)
if VOIX_OFF: MOTS = [(m['m'], m['debut'], m['fin']) for m in VOIX_OFF.get('mots', [])]
else:
    MOTS = []
    for m in PLAN.get('mots', []):
        a, b = t_sortie(m['debut']), t_sortie(m['fin'])
        if a is not None and b is not None and b >= a: MOTS.append((m['m'], a, b))
def _n(m): return re.sub(r"[^\w\-]", '', re.sub(r"^(?:l|d|j|qu|n|s|c|t|m)'", '', m.lower().replace('’', "'")))
FORTS = {_n(x) for x in PLAN.get('mots_forts', [])}

# ---- moments (heures de sortie)
def heure(m):
    return float(m['t']) if VOIX_OFF else t_sortie(float(m['t']))
MOMENTS = sorted([dict(m, T=heure(m)) for m in PLAN.get('moments', []) if heure(m) is not None and heure(m) < FIN_VOIX], key=lambda m: m['T'])
TITRE = PLAN.get('titre') or {}
D_TITRE = float(TITRE.get('duree', 3.2)) if TITRE.get('lignes') else 0.0
T_Q = FIN_VOIX - 2.2 if PLAN.get('question') else FIN_VOIX + 9
HAUT = ('mot', 'badge', 'tampon', 'compteur', 'arret')       # éléments qui partagent la place en haut de l'image : un seul à la fois
_h = [m for m in MOMENTS if m['type'] in HAUT]
for a_, b_ in zip(_h, _h[1:]):
    d0 = a_.get('duree', {'mot': 1.35, 'badge': 1.7, 'tampon': 1.5, 'compteur': 1.8, 'arret': 1.2}[a_['type']])
    if a_['T'] + d0 > b_['T'] - 0.05: a_['duree'] = max(0.5, b_['T'] - 0.05 - a_['T'])
MOMENTS = [m for m in MOMENTS if (m['T'] >= D_TITRE - 0.2 or m['type'] in ('broll', 'zoom')) and m['T'] < T_Q - 0.4]
for m in MOMENTS:                                       # rien ne déborde sur la question de fin
    d0 = m.get('duree', {'mot': 1.35, 'badge': 1.7, 'tampon': 1.5, 'compteur': 1.8, 'emoji': 1.2}.get(m['type'], 2.0))
    m['duree'] = max(0.6, min(d0, T_Q - 0.1 - m['T']))

# ---- coupes : bords des segments + coupes de plan de la source
def coupes_source():
    out = subprocess.run(['ffmpeg', '-hide_banner', '-nostdin', '-i', SRC, '-vf', "scale=240:-2,select='gt(scene,0.30)',showinfo", '-an', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    return [float(x) for x in re.findall(r'pts_time:([0-9.]+)', out)]
COUPES = sorted(set(round(o / ETIRE, 3) for o in O[1:-1]) | {round(x, 3) for x in (t_sortie(c) for c in coupes_source()) if x is not None})
COUPES = [c for k, c in enumerate(COUPES) if 0.6 < c < FIN_VOIX - 0.3 and (k == 0 or c - COUPES[k - 1] > 0.7)]
CYCLES = {'sobre': ['flash', 'zoom', 'whipG', 'zoom'],
          'dynamique': ['zoom', 'whipG', 'glitch', 'flash', 'punch', 'whipD', 'flip', 'whipH'],
          'explosif': ['zoom', 'whipG', 'glitch', 'cube', 'punch', 'whipD', 'flip', 'glitch', 'whipH', 'flash', 'cube', 'punch']}
CYC = CYCLES.get(RYTHME, CYCLES['dynamique'])
TRANS = {c: CYC[k % len(CYC)] for k, c in enumerate(COUPES)}
if PLAN.get('transitions') is not None: TRANS = {float(x['t']): x['type'] for x in PLAN['transitions']}   # transitions choisies à la main (les autres coupes restent franches)
DUREE_T = {'cube': 0.42, 'flip': 0.42, 'zoom': 0.34}

# ===================================================================================== lecture vidéo
class Lecteur:
    def __init__(self, chemin, duree, w, h):
        self.p, self.d = chemin, duree
        e = min(1.0, 1280 / max(w, h)); self.w, self.h = int(w * e) // 2 * 2, int(h * e) // 2 * 2
        self.proc = None; self.base = 0; self.lu = -1; self.mem = {}
    def _ouvrir(self, i):
        if self.proc: self.proc.kill()
        self.base = max(0, i - 10)
        self.proc = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-ss', f'{self.base / FPS:.3f}', '-i', self.p, '-vf', f'fps={FPS},scale={self.w}:{self.h}',
                                      '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.lu = self.base - 1; self.mem = {}
    def image(self, ts):
        i = int(round(clamp(ts, 0, self.d - 0.07) * FPS))
        if i in self.mem: return self.mem[i]
        if self.proc is None or i < self.base or i > self.lu + 90: self._ouvrir(i)
        n = self.w * self.h * 3
        while self.lu < i:
            b = self.proc.stdout.read(n)
            if len(b) < n: break
            self.lu += 1; self.mem[self.lu] = np.frombuffer(b, np.uint8).reshape(self.h, self.w, 3)
            if len(self.mem) > 100: self.mem.pop(min(self.mem))
        if not self.mem: return np.zeros((self.h, self.w, 3), np.uint8)
        return self.mem.get(i, self.mem[max(self.mem)])
_lec = {}
def lecteur(chemin):
    if chemin not in _lec:
        d, w, h, _ = sonde(chemin) if chemin != SRC else (DUR_SRC, SW, SH, A_AUDIO)
        _lec[chemin] = Lecteur(chemin, d, w, h)
    return _lec[chemin]

def net(a, k=1.3):
    a = a.astype(np.float32); return np.clip(a * k - cv2.GaussianBlur(a, (0, 0), 2.0) * (k - 1), 0, 255)

def couvrir(a, fx=0.5):
    """Recadre une image pour remplir 1080x1920 (garde la zone fx horizontalement)."""
    h, w = a.shape[:2]
    if w / h > W / H:
        cw = int(h * W / H); x0 = int(clamp((w - cw) * fx, 0, w - cw)); a = a[:, x0:x0 + cw]
    else:
        ch = int(w * H / W); y0 = int((h - ch) * 0.45); a = a[y0:y0 + ch]
    return cv2.resize(a, (W, H), interpolation=cv2.INTER_CUBIC)

def fond_flou(a, k=0.42):
    f = couvrir(a); f = cv2.GaussianBlur(cv2.resize(f, (W // 8, H // 8)), (0, 0), 3).astype(np.float32)
    return cv2.resize(f, (W, H)) * k

# ===================================================================================== image de base d'un plan
def num_plan(t): return sum(1 for c in COUPES if t >= c)
def zoom_moments(t):
    z, cx, cy = 0.0, 0.5, 0.45
    for m in MOMENTS:
        u = t - m['T']
        if m['type'] == 'zoom' and 0 <= u < m.get('duree', 1.4):
            q = eout(u / 0.25) * (1 - ein(clamp((u - m.get('duree', 1.4) + 0.35) / 0.35)))
            return (m.get('echelle', 1.3) - 1) * q, m.get('x', 0.5), m.get('y', 0.45)
        if m['type'] in ('mot', 'badge', 'tampon', 'compteur') and 0 <= u < 1.4:
            z = max(z, 0.08 * eout(u / 0.18) * (1 - ein(clamp((u - 0.9) / 0.5))))
    return z, cx, cy

def plan_base(t):
    for m in MOMENTS:                                    # plan de coupe en plein écran
        if m['type'] == 'broll' and m.get('mode', 'plein') == 'plein' and m['T'] <= t < m['T'] + m.get('duree', 2.5):
            L = lecteur(m['fichier']); u = t - m['T']
            img = net(couvrir(L.image(m.get('debut', 0) + u)), 1.2)
            M = cv2.getRotationMatrix2D((540, 960), 0, 1.04 + 0.06 * u / m.get('duree', 2.5))
            return cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    gel = next((m for m in MOMENTS if m['type'] == 'arret' and m['T'] <= t < m['T'] + m.get('duree', 1.2)), None)
    ts = t_src(gel['T'] if gel else t)
    a = lecteur(SRC).image(ts)
    k = num_plan(t); debut = COUPES[k - 1] if k else 0.0; u = t - debut
    zm, zx, zy = zoom_moments(t)
    derive = 1.04 + 0.05 * ease(min(u, 4.0) / 4.0) + zm
    if VERTICAL:
        img = net(couvrir(a))
        M = cv2.getRotationMatrix2D((W * zx + 30 * math.sin(k * 1.7), H * zy + 40 * math.cos(k * 1.3)), 0.6 * math.sin(t * 0.4), derive)
        out = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    elif k % 3 == 2 or zm > 0.15:                        # un plan sur trois en plein écran recadré
        img = net(couvrir(a, 0.5 + 0.18 * math.sin(k * 2.1)), 1.25)
        M = cv2.getRotationMatrix2D((W * zx, H * zy), 0, derive); out = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    else:                                                # panneau flottant 3D sur fond flouté
        fond = fond_flou(a)
        h, w = a.shape[:2]; pw = 1000; ph = int(pw * h / w)
        cw, chh = w / derive, h / derive; x0 = (w - cw) / 2 * (1 + 0.6 * math.sin(k * 1.9 + t * 0.15)); y0 = (h - chh) / 2
        Mz = np.float32([[pw / cw, 0, -x0 * pw / cw], [0, ph / chh, -y0 * ph / chh]])
        pan = net(cv2.warpAffine(a, Mz, (pw, ph), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT))
        c = carte(pan, 8, ACC, 22)
        cp = perspective(c, 3.5 * math.sin(t * 0.7 + k), 5.0 * math.sin(t * 0.5 + k * 0.7), 2200)
        coller(fond, cp, 540, 905); out = fond
    if gel:                                              # arrêt sur image : légère désaturation + cadre
        u = t - gel['T']; g = out.mean(2, keepdims=True); out = out * 0.55 + g * 0.45
        if u < 0.12: out = out * (1 - (1 - u / 0.12)) + 255 * (1 - u / 0.12)
    return out

# ===================================================================================== transitions
def flou_dir(img, L, horizontal=True):
    L = int(L)
    if L < 3: return img
    k = np.zeros((L, L), np.float32)
    if horizontal: k[L // 2, :] = 1
    else: k[:, L // 2] = 1
    return cv2.resize(cv2.filter2D(cv2.resize(img, (W // 2, H // 2)), -1, k / k.sum()), (W, H))
def flou_radial(img, force):
    acc = np.zeros_like(img)
    for j in range(6):
        M = cv2.getRotationMatrix2D((540, 960), 0, 1 + force * j / 6); acc += cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    return acc / 6
def glitch(img, t, force):
    rr = np.random.default_rng(int(t * 1000)); out = img.copy()
    for _ in range(int(14 * force)):
        y = rr.integers(0, H - 60); h = rr.integers(8, 90); out[y:y + h] = np.roll(out[y:y + h], int(rr.integers(-120, 120) * force), axis=1)
    s = int(18 * force); out[..., 0] = np.roll(out[..., 0], s, axis=1); out[..., 2] = np.roll(out[..., 2], -s, axis=1)
    return out
def sombre(img): return cv2.resize(cv2.GaussianBlur(cv2.resize(img, (W // 8, H // 8)), (0, 0), 6), (W, H)) * 0.35
def cube(A, B, e, sc):
    phi = -math.radians(90 * e); fz = 1800.0
    def proj(p3):
        o = []
        for (x, y, z) in p3:
            xr, zr = x * math.cos(phi) - z * math.sin(phi), x * math.sin(phi) + z * math.cos(phi)
            s = fz / (fz + zr + W / 2) * sc; o.append((W / 2 + xr * s, H / 2 + y * s))
        return o
    out = sombre(A if e < .5 else B)
    for img, c3 in [(A, [(-W/2, -H/2, -W/2), (W/2, -H/2, -W/2), (W/2, H/2, -W/2), (-W/2, H/2, -W/2)]), (B, [(W/2, -H/2, -W/2), (W/2, -H/2, W/2), (W/2, H/2, W/2), (W/2, H/2, -W/2)])]:
        c2 = proj(c3)
        if sum(c2[k][0] * c2[(k + 1) % 4][1] - c2[(k + 1) % 4][0] * c2[k][1] for k in range(4)) <= 0: continue
        Mp = cv2.getPerspectiveTransform(np.float32([(0, 0), (W, 0), (W, H), (0, H)]), np.float32(c2))
        im = cv2.warpPerspective(img, Mp, (W, H)); m = cv2.warpPerspective(np.ones((H, W), np.float32), Mp, (W, H))[..., None]
        out = out * (1 - m) + im * m * (0.5 + 0.5 * min(1, abs(c2[1][0] - c2[0][0]) / W / sc))
    return out
def flip(A, B, p):
    fond = sombre(B)
    def pers(img, ang):
        a = math.radians(ang); pts = []
        for (x, y) in [(-W / 2, -H / 2), (W / 2, -H / 2), (W / 2, H / 2), (-W / 2, H / 2)]:
            s = 1800 / (1800 + x * math.sin(a)) * (1 - 0.12 * math.sin(math.pi * p)); pts.append((W / 2 + x * math.cos(a) * s, H / 2 + y * s))
        Mp = cv2.getPerspectiveTransform(np.float32([(0, 0), (W, 0), (W, H), (0, H)]), np.float32(pts))
        return cv2.warpPerspective(img, Mp, (W, H)) * (1 - 0.5 * abs(math.sin(a))), cv2.warpPerspective(np.ones((H, W), np.float32), Mp, (W, H))[..., None]
    im, m = pers(A, 90 * ease(p * 2)) if p < .5 else pers(B, -90 * (1 - ease((p - .5) * 2)))
    return fond * (1 - m) + im * m
def composer(t):
    for c, k in TRANS.items():
        D = DUREE_T.get(k, 0.28)
        if c - D / 2 <= t < c + D / 2:
            p = (t - (c - D / 2)) / D
            A = plan_base(min(t, c - 1 / FPS)); B = plan_base(max(t, c + 0.5 / FPS))
            if k.startswith('whip'):
                e = ease(p); v = math.sin(math.pi * p); out = np.zeros_like(A)
                if k == 'whipH':
                    off = int(e * H); out[:H - off] = A[off:]; out[H - off:] = B[:off]; return flou_dir(out, 160 * v, False)
                off = int(e * W)
                if k == 'whipG': out[:, :W - off] = A[:, off:]; out[:, W - off:] = B[:, :off]
                else: out[:, off:] = A[:, :W - off]; out[:, :off] = B[:, W - off:]
                return flou_dir(out, 200 * v)
            if k in ('punch', 'zoom'):
                fz = 0.45 if k == 'punch' else 0.8
                if p < 0.5: return flou_radial(A, fz * ease(p * 2)) * (1 + 0.45 * ease(p * 2))
                return flou_radial(B, fz * 0.9 * (1 - ease((p - .5) * 2))) * (1 + 0.45 * (1 - ease((p - .5) * 2)))
            if k == 'glitch': return glitch(A if p < 0.5 else B, t, 1.3 * math.sin(math.pi * p) + 0.2)
            if k == 'flash': w_ = math.exp(-abs(p - 0.5) * 9); return (A if p < 0.5 else B) * (1 - w_) + 255 * w_
            if k == 'cube': return cube(A, B, ease(p), 1 - 0.2 * math.sin(math.pi * p))
            if k == 'flip': return flip(A, B, p)
    return plan_base(t)

# ===================================================================================== éléments graphiques
CACHE = {}
def cache(cle, fn):
    if cle not in CACHE: CACHE[cle] = fn()
    return CACHE[cle]
def emoji(e, taille):
    try:
        f = ImageFont.truetype('/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf', 109)
        im = Image.new('RGBA', (180, 180)); ImageDraw.Draw(im).text((10, 10), e, font=f, embedded_color=True)
        bb = im.getbbox()
        if not bb: return None
        im = im.crop(bb); return np.asarray(im.resize((int(im.width * taille / im.height), taille), Image.LANCZOS)).astype(np.float32)
    except Exception:
        return None
def badge(txt):
    f = police(150 if len(txt) <= 4 else 92); l, tt, r, b = f.getbbox(txt); w, h = r - l + 110, b - tt + 64
    im = Image.new('RGBA', (w + 40, h + 40)); sh = Image.new('RGBA', im.size)
    ImageDraw.Draw(sh).rounded_rectangle([26, 30, 20 + w, 24 + h], 30, fill=(0, 0, 0, 170)); im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(im); d.rounded_rectangle([20, 20, 20 + w, 20 + h], 30, fill=ACC + (255,), outline=(255, 255, 255, 255), width=7)
    d.rounded_rectangle([34, 30, 6 + w, 20 + h // 2], 22, fill=(255, 255, 255, 60)); d.text((20 + 55 - l, 20 + 32 - tt), txt, font=f, fill=(12, 10, 20, 255))
    return np.asarray(largeur_max(im, 1000)).astype(np.float32)
def tampon(txt, angle):
    f = police(70); l, t, r, b = f.getbbox(txt); w, h = r - l + 70, b - t + 46
    im = Image.new('RGBA', (w + 20, h + 20)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([10, 10, 10 + w, 10 + h], 10, outline=ACC + (255,), width=9); d.text((10 + 35 - l, 10 + 23 - t), txt, font=f, fill=ACC + (255,))
    a = np.array(im); msk = np.random.default_rng(len(txt)).random(a.shape[:2]) < 0.12; a[msk, 3] = (a[msk, 3] * 0.3).astype(np.uint8)
    return largeur_max(Image.fromarray(a).rotate(angle, expand=True, resample=Image.BICUBIC), 980)
def image_carte(chemin, legende, largeur=640):
    try: a = np.asarray(Image.open(chemin).convert('RGB'))
    except Exception: return None
    h, w = a.shape[:2]; hmax = 560; e = min(largeur / w, hmax / h, 2.2)       # pas trop haute (sous-titres), pas trop agrandie (netteté)
    a = cv2.resize(a, (int(w * e), int(h * e)), interpolation=cv2.INTER_AREA).astype(np.float32)
    c = carte(a, 10, (255, 255, 255), 24)
    if legende:
        lb = np.asarray(texte_img(legende.upper(), 54, ACC, 7, 6, ACC_F)).astype(np.float32)
        if lb.shape[1] > c.shape[1] + 120: lb = cv2.resize(lb, (c.shape[1] + 120, int(lb.shape[0] * (c.shape[1] + 120) / lb.shape[1])))
        out = np.zeros((c.shape[0] + lb.shape[0] - 40, max(c.shape[1], lb.shape[1]), 4), np.float32)
        ox = (out.shape[1] - c.shape[1]) // 2; out[:c.shape[0], ox:ox + c.shape[1]] = c
        y = c.shape[0] - 80; lx = (out.shape[1] - lb.shape[1]) // 2
        sub = out[y:y + lb.shape[0], lx:lx + lb.shape[1]]; al = lb[..., 3:4] / 255
        sub[..., :3] = sub[..., :3] * (1 - al) + lb[..., :3] * al; sub[..., 3:4] = np.maximum(sub[..., 3:4], lb[..., 3:4])
        return out
    return c

Y_HAUT = 330 if not VERTICAL else 520
def dessiner_titre(f, t):
    if not TITRE.get('lignes') or t > D_TITRE + 0.2: return
    y = 330 if not VERTICAL else 420
    for k, ligne in enumerate(TITRE['lignes'][:2]):
        im = cache(('titre', k), lambda: largeur_max(texte_img(ligne.upper(), 82 if k == 0 else 92, (255, 255, 255) if k == 0 else ACC, 9 if k == 0 else 10, 12 if k == 0 else 16, (40, 40, 60) if k == 0 else ACC_F)))
        t0 = 0.05 + 0.28 * k
        if t < t0: continue
        p = (t - t0) / 0.25; s = 2.2 - 1.2 * eout(p) if p < 1 else 1 + 0.015 * math.sin((t - t0) * 5)
        coller(f, im, 540, y + k * 118, s, min(1, p * 2) * (1 - clamp((t - D_TITRE + 0.15) / 0.3)))
    e = cache('titre-emoji', lambda: emoji(TITRE.get('emoji', ''), 120) if TITRE.get('emoji') else None)
    if e is not None and t > 0.75:
        coller(f, e, 540, y - 125, back(min((t - 0.75) / 0.35, 1), 2.4), 1 - clamp((t - D_TITRE + 0.15) / 0.3), 12 * math.sin(t * 4))

DUREES = {'mot': 1.35, 'badge': 1.7, 'tampon': 1.5, 'compteur': 1.8, 'emoji': 1.2}
def dessiner_moments(f, t):
    cal = None
    for k, m in enumerate(MOMENTS):
        u = t - m['T']; ty = m['type']
        if u < 0: continue
        dur = m.get('duree', DUREES.get(ty, 2.0))
        if u > dur: continue
        sortie = 1 - clamp((u - dur + 0.22) / 0.22)
        if ty == 'badge':
            im = cache(('b', m['texte']), lambda: badge(m['texte'])); p = eout(u / 0.4)
            coller(f, perspective(im, 0, (1 - p) * 95 + 4 * math.sin(u * 3), 1400), 540, Y_HAUT, 0.85 + 0.15 * p, min(1, p * 2) * sortie)
        elif ty == 'mot':
            im = cache(('m', m['texte']), lambda: largeur_max(texte_img(m['texte'].upper(), 104, (255, 255, 255), 10, 16, ACC_F)))
            p = u / 0.2; coller(f, im, 540, Y_HAUT, 2.3 - 1.3 * eout(p) if p < 1 else 1 + 0.02 * math.sin(u * 6), min(1, p * 2) * sortie)
        elif ty == 'tampon':
            im = cache(('t', m['texte']), lambda: tampon(m['texte'].upper(), -8 if k % 2 else 7))
            p = u / 0.16; coller(f, im, 540, Y_HAUT, 1.9 - 0.9 * eout(p) if p < 1 else 1, min(1, p * 2) * sortie)
        elif ty == 'compteur':
            q = eout(clamp(u / 0.75)); v = int(round(float(m['valeur']) * q))
            im = largeur_max(texte_img(f'{v:,}'.replace(',', ' '), 170, ACC, 12, 22, ACC_F))
            coller(f, im, 540, Y_HAUT - 30, 1 + 0.1 * (1 - q), sortie)
            if m.get('legende'):
                lb = cache(('l', m['legende']), lambda: largeur_max(texte_img(m['legende'].upper(), 72, (255, 255, 255), 8, 10, (40, 40, 60))))
                coller(f, lb, 540, Y_HAUT + 120, back(clamp((u - 0.2) / 0.3), 2.0), sortie)
        elif ty == 'emoji':
            e = cache(('e', m['texte']), lambda: emoji(m['texte'], 210))
            if e is not None: coller(f, e, 540 + 260 * (1 if k % 2 else -1), Y_HAUT + 60, back(clamp(u / 0.3), 2.6), sortie, 14 * math.sin(u * 5))
        elif ty == 'image':
            c = cache(('i', m['fichier'], m.get('legende')), lambda: image_carte(m['fichier'], m.get('legende')))
            if c is None: continue
            cote = m.get('cote', 'droite'); sgn = {'gauche': -1, 'droite': 1}.get(cote, 0)
            ent = eout(clamp(u / 0.45)); sor = ein(clamp((u - dur + 0.4) / 0.4))
            cx = 540 + sgn * (170 + (1 - ent) * 900 + sor * 900) if sgn else 540
            hc = c.shape[0] * 0.72                              # hauteur visible de la carte (sans l'ombre)
            base_y = Y_SOUS + 140 + hc / 2 if Y_SOUS < 1150 else 720   # jamais sur les sous-titres
            base_y = min(base_y, 1640 - hc / 2)
            cy = base_y + (0 if sgn else (1 - ent) * 900 - sor * 1200)
            ang_y = sgn * (-28 * (1 - ent) + 10 + 3 * math.sin(u * 2)) if sgn else 8 * math.sin(u * 2)
            coller(f, perspective(c, 4 * math.sin(u * 1.6), ang_y, 1800), cx, cy, 0.95 + 0.05 * ent, 1.0, -sgn * 4 * (1 - ent))
        elif ty == 'broll' and m.get('mode', 'plein') == 'incrustation':
            L = lecteur(m['fichier']); fr = L.image(m.get('debut', 0) + u)
            h, w = fr.shape[:2]; e = min(620 / w, 760 / h); fr = cv2.resize(fr, (int(w * e), int(h * e))).astype(np.float32)
            c = carte(fr, 9, ACC, 22); ent = back(clamp(u / 0.35), 1.6); sor = ein(clamp((u - dur + 0.3) / 0.3))
            coller(f, perspective(c, 0, -12 + 4 * math.sin(u * 2), 1800), 700, 760 + sor * 1500, ent, 1.0, -3)
            if m.get('legende'):
                lb = cache(('l', m['legende']), lambda: largeur_max(texte_img(m['legende'].upper(), 60, ACC, 7, 8, ACC_F), 700))
                coller(f, lb, 700, 760 + c.shape[0] / 2 - 30 + sor * 1500, ent, 1.0)
        elif ty in ('fleche', 'cercle'):
            if cal is None: cal = Image.new('RGBA', (W, H)); d = ImageDraw.Draw(cal)
            x, y = m.get('x', 0.5) * W, m.get('y', 0.4) * H; p = eout(clamp(u / 0.45)); al = int(255 * sortie)
            if ty == 'cercle':
                r = m.get('r', 0.12) * W; d.arc([x - r, y - r * 0.9, x + r, y + r * 0.9], -100, -100 + 370 * p, fill=ACC + (al,), width=14)
            else:
                dep = {'gauche': (-1, 0.3), 'droite': (1, 0.3), 'haut': (0.2, -1), 'bas': (0.2, 1)}.get(m.get('depuis', 'gauche'), (-1, 0.3))
                x0, y0 = x + dep[0] * 330, y + dep[1] * 330; xe, ye = x + dep[0] * 70, y + dep[1] * 70
                mx_, my_ = (x0 + xe) / 2 - (ye - y0) * 0.25, (y0 + ye) / 2 + (xe - x0) * 0.25
                pts = [((1 - s) ** 2 * x0 + 2 * (1 - s) * s * mx_ + s * s * xe, (1 - s) ** 2 * y0 + 2 * (1 - s) * s * my_ + s * s * ye) for s in np.linspace(0, max(p, 0.02), 40)]
                d.line(pts, fill=ACC + (al,), width=16, joint='curve')
                if p > 0.8:
                    (xa, ya), (xb, yb) = pts[-4], pts[-1]; a = math.atan2(yb - ya, xb - xa); Lg = 52
                    d.polygon([(xb + math.cos(a) * Lg * .6, yb + math.sin(a) * Lg * .6), (xb + math.cos(a + 2.5) * Lg, yb + math.sin(a + 2.5) * Lg), (xb + math.cos(a - 2.5) * Lg, yb + math.sin(a - 2.5) * Lg)], fill=ACC + (al,))
        elif ty == 'arret' and m.get('texte'):
            im = cache(('a', m['texte']), lambda: largeur_max(texte_img(m['texte'].upper(), 88, ACC, 9, 12, ACC_F)))
            coller(f, im, 540, Y_HAUT, back(clamp(u / 0.25), 2.2), sortie)
    if cal is not None: coller(f, np.asarray(lueur(cal, 10, 1.5)).astype(np.float32), W / 2, H / 2)

# ---- sous-titres mot à mot
STYLE = PLAN.get('sous_titres', 'mot_cle')
GROUPES, cur = [], []
for i, (m, a, b) in enumerate(MOTS):
    cur.append(i)
    if len(cur) >= 3 or len(' '.join(MOTS[j][0] for j in cur)) >= 16 or m.endswith((',', '.', ':', '?', '!', '…')): GROUPES.append(cur); cur = []
if cur: GROUPES.append(cur)
GR = [(MOTS[g[0]][1] - 0.04, (MOTS[GROUPES[k + 1][0]][1] - 0.04) if k + 1 < len(GROUPES) else MOTS[g[-1]][2] + 0.4, g) for k, g in enumerate(GROUPES)]
Y_SOUS = int(clamp(float(PLAN['sous_titres_y']), 0.3, 0.8) * H) if PLAN.get('sous_titres_y') else (1450 if not VERTICAL else 1180)
BANDE = (1 - 0.6 * np.sin(np.linspace(0, math.pi, 240)) ** 1.2).astype(np.float32)[:, None, None]
def img_groupe(g, actif):
    def fab():
        parts = []
        for j in g:
            mm = MOTS[j][0].strip(',.:;«»"').upper()
            fort = _n(MOTS[j][0]) in FORTS
            coul = ACC if (STYLE == 'mot_cle' and fort) else (ACC if STYLE == 'karaoke' and j == actif else (255, 255, 255))
            parts.append(texte_img(mm, 80, coul, 9, 0))
        wt = sum(p.width for p in parts) - 50 * (len(parts) - 1); hm = max(p.height for p in parts)
        im = Image.new('RGBA', (wt, hm)); x = 0
        for p in parts: im.alpha_composite(p, (x, (hm - p.height) // 2)); x += p.width - 50
        return np.asarray(largeur_max(im, 1010)).astype(np.float32)
    return cache(('g', tuple(g), actif if STYLE == 'karaoke' else -1), fab)
def dessiner_sous(f, t):
    if STYLE == 'aucun': return
    for a, b, g in GR:
        if a <= t < b:
            actif = max([j for j in g if MOTS[j][1] - 0.04 <= t] or [g[0]])
            p = (t - a) / 0.11; s = 0.78 + 0.22 * back(min(p, 1), 2.4) if p < 1 else 1.0
            f[Y_SOUS - 120:Y_SOUS + 120] *= BANDE
            coller(f, img_groupe(g, actif), 540, Y_SOUS, s, 1.0); return

def dessiner_fin(f, t):
    q_txt = PLAN.get('question')
    if q_txt and t >= T_Q:
        u = t - T_Q
        q = cache('q', lambda: np.asarray(largeur_max(texte_img(q_txt.upper(), 96, ACC, 10, 14, ACC_F))).astype(np.float32))
        p = u / 0.25; coller(f, q, 540, 400, (2.0 - eout(p)) if p < 1 else 1 + 0.02 * math.sin(u * 5), min(1, p * 2))
        if u > 0.5:
            cal = Image.new('RGBA', (W, H)); d = ImageDraw.Draw(cal); s = 1 + 0.07 * math.sin(u * 7); cy = 610
            d.rounded_rectangle([540 - 120 * s, cy - 72 * s, 540 + 120 * s, cy + 62 * s], radius=48, fill=(255, 255, 255, 255))
            d.polygon([(495, cy + 56 * s), (455, cy + 140), (575, cy + 56 * s)], fill=(255, 255, 255, 255))
            for j in range(3): d.ellipse([478 + j * 62 - 15, cy - 25, 478 + j * 62 + 15, cy + 5], fill=ACC + (255,))
            coller(f, np.asarray(lueur(cal, 10, 1.3)).astype(np.float32), W / 2, H / 2, 1.0, clamp((u - 0.5) / 0.3))
            im = cache('dis', lambda: texte_img('DIS-LE EN COMMENTAIRE', 62, (255, 255, 255), 8, 8, (40, 40, 60)))
            coller(f, im, 540, cy + 175, back(clamp((u - 0.7) / 0.3), 2.0), 1.0)
    if t > FIN_VOIX + 0.2:
        def fab():
            fo = police(50); l, tt, r, b = fo.getbbox('ABONNE-TOI POUR LA SUITE'); im = Image.new('RGBA', (r - l + 72, b - tt + 44), ACC + (255,))
            ImageDraw.Draw(im).text((36 - l, 22 - tt), 'ABONNE-TOI POUR LA SUITE', font=fo, fill=(12, 10, 20, 255)); return im
        coller(f, cache('abo', fab), 540, 1640, back(clamp((t - FIN_VOIX - 0.2) / 0.35), 2.0), 1.0)

# ---- ambiance
AMB = PLAN.get('ambiance', 'poussiere')
rng0 = np.random.default_rng(3)
PART = [(rng0.uniform(0, W), rng0.uniform(20, 120), rng0.uniform(0, 40), rng0.uniform(1.5, 5)) for _ in range(55)]
COUL_P = {'braises': (255, 120, 50), 'etincelles': (255, 230, 150), 'neige': (255, 255, 255), 'poussiere': (230, 230, 255)}.get(AMB)
def particules(f, t):
    if not COUL_P: return
    cal = Image.new('RGBA', (W, H)); d = ImageDraw.Draw(cal); sens = -1 if AMB == 'neige' else 1
    for x0, v, ph, r in PART:
        y = (H - ((t + ph) * v) % (H + 80)) if sens > 0 else ((t + ph) * v) % (H + 80); x = x0 + 25 * math.sin((t + ph) * 1.1)
        d.ellipse([x - r, y - r, x + r, y + r], fill=COUL_P + (int(150 * (0.5 + 0.5 * math.sin((t + ph) * 2.7))),))
    coller(f, np.asarray(lueur(cal, 5, 1.6)).astype(np.float32), W / 2, H / 2)
GRAIN = [np.random.default_rng(s).normal(0, 5, (H // 2, W // 2)).astype(np.float32) for s in range(6)]
yy, xx = np.ogrid[:H, :W]
VIGN = (1 - 0.38 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 1.6)) ** 2)).clip(0.42, 1).astype(np.float32)[..., None]

# ===================================================================================== impacts, flashs, bruitages
IMPACTS, FLASHS, EVENTS = [], [], []
def sfx(t, nom, vol=1.0): EVENTS.append((round(max(0.0, t), 3), nom, vol))
if TITRE.get('lignes'):
    sfx(0.0, 'boom-bande-annonce', 0.7); sfx(0.33, 'coup-poing', 0.6); IMPACTS += [(0.05, 22, 0.35), (0.35, 14, 0.25)]; FLASHS.append((0.0, (255, 255, 255), 0.2, 0.7))
    if TITRE.get('emoji'): sfx(0.75, 'pop-bulle', 0.5)
SON_MOMENT = {
    'badge': [(-0.35, 'riser-court', 0.35), (0, 'impact-cinema', 0.6), (0, 'sub-drop-court', 0.5)],
    'mot': [(0, 'whoosh-court', 0.6), (0.02, 'coup-poing', 0.45)],
    'tampon': [(0, 'impact-metal', 0.6), (0, 'sub-drop-court', 0.4)],
    'emoji': [(0, 'pop-bulle', 0.6)],
    'image': [(0, 'whoosh-passage', 0.55), (0.4, 'pop', 0.35)],
    'broll': [(0, 'whoosh-long', 0.45)],
    'fleche': [(0, 'swish', 0.5)], 'cercle': [(0.05, 'clic-doux', 0.5)],
    'arret': [(0, 'arret-bande', 0.6)], 'zoom': [(0, 'whoosh-grave', 0.55)],
}
for m in MOMENTS:
    ty, tm = m['type'], m['T']
    for dt, nom, vol in SON_MOMENT.get(ty, []): sfx(tm + dt, nom, vol)
    if ty == 'badge': IMPACTS.append((tm, 24, 0.4)); FLASHS.append((tm, ACC, 0.22, 0.45))
    elif ty == 'mot': IMPACTS.append((tm, 14, 0.28))
    elif ty == 'tampon': IMPACTS.append((tm, 18, 0.3))
    elif ty == 'arret': FLASHS.append((tm, (255, 255, 255), 0.15, 0.8))
    elif ty == 'compteur':
        for j in range(8): sfx(tm + j * 0.09, 'clic-sec', 0.3)
        sfx(tm + 0.75, 'validation', 0.5)
SON_T = {'glitch': 'glitch-court', 'cube': 'whoosh-grave', 'zoom': 'whoosh-inverse', 'flip': 'swish', 'whipH': 'whoosh-court', 'whipG': 'whoosh-court', 'whipD': 'whoosh-court', 'flash': 'whoosh-court', 'punch': 'coup-poing'}
for c, k in TRANS.items(): sfx(c - DUREE_T.get(k, 0.28) / 2, SON_T[k], 0.4)
if PLAN.get('question'): sfx(FIN_VOIX - 2.2, 'pop-bulle', 0.6); sfx(FIN_VOIX - 1.7, 'notification', 0.5)
sfx(FIN_VOIX + 0.2, 'validation', 0.5)
for b in PLAN.get('bruitages', []):
    tt = float(b['t']) if VOIX_OFF else t_sortie(float(b['t']))
    if tt is not None: sfx(tt, b['son'], float(b.get('volume', 0.7)))
def secousse(t):
    return max([amp * (1 - (t - s) / dur) for s, amp, dur in IMPACTS if s <= t < s + dur] or [0.0])

def rendre(i):
    t = i / FPS
    f = composer(t).astype(np.float32)
    if t > FIN_VOIX + 0.1:
        q = clamp((t - FIN_VOIX - 0.1) / 0.6); f = f * (1 - 0.45 * q) + cv2.GaussianBlur(f, (0, 0), 8) * 0.25 * q
    tr = secousse(t)
    if tr > 0.5:
        M = cv2.getRotationMatrix2D((540, 960), tr * 0.05 * math.sin(t * 53), 1 + tr / 900); M[0, 2] += tr * 0.9 * math.sin(t * 91); M[1, 2] += tr * math.cos(t * 77)
        f = cv2.warpAffine(f, M, (W, H), borderMode=cv2.BORDER_REFLECT)
        if tr > 12: s = int(tr / 3); f[..., 0] = np.roll(f[..., 0], s, 1); f[..., 2] = np.roll(f[..., 2], -s, 1)
    for s, coul, dur, force in FLASHS:
        if s <= t < s + dur: w_ = force * (1 - (t - s) / dur); f = f * (1 - w_) + np.array(coul, np.float32) * w_
    particules(f, t)
    f *= VIGN; f += cv2.resize(GRAIN[i % 6], (W, H))[..., None]
    dessiner_titre(f, t); dessiner_moments(f, t); dessiner_sous(f, t); dessiner_fin(f, t)
    f[0:8, :int(W * t / DUREE)] = ACC
    return np.clip(f, 0, 255).astype(np.uint8)

# ===================================================================================== son
def lire_audio(p, af=None):
    cmd = ['ffmpeg', '-nostdin', '-v', 'error', '-i', p] + (['-af', af] if af else []) + ['-ac', '2', '-ar', str(SR), '-f', 'f32le', '-']
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.float32).reshape(-1, 2).copy()
def moyenne(x, k):
    c = np.cumsum(np.concatenate([np.zeros(k // 2 + 1), x, np.zeros(k)])); return ((c[k:] - c[:-k]) / k)[:len(x)]
def bande_son(chemin):
    n = int(DUREE * SR); piste = lambda: np.zeros((n, 2), np.float32)
    def poser(dst, src, t, g=1.0):
        i = int(t * SR); j = min(n, i + len(src))
        if j > i and i >= 0: dst[i:j] += src[:j - i] * g
    voix = piste()
    if VOIX_OFF:
        poser(voix, lire_audio(VOIX_OFF['fichier'], 'highpass=f=70,acompressor=threshold=-20dB:ratio=3:makeup=3dB,loudnorm=I=-16:TP=-1.5'), 0)
    else:
        vf = (PLAN.get('voix') or {}).get('fichier') or (SRC if A_AUDIO else None)
        if vf:
            brut = lire_audio(vf, 'loudnorm=I=-16:TP=-1.5:LRA=9'); g = float((PLAN.get('voix') or {}).get('volume', 1.0))
            for k, (a, b) in enumerate(SEGS):          # chaque segment, recalé, avec micro-fondus (pas de clic aux coupes)
                s = brut[int(a * SR):int(b * SR)]
                if VIT != 1.0:
                    s = np.frombuffer(subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', '-', '-af', f'atempo={VIT}', '-f', 'f32le', '-'],
                                                     input=s.tobytes(), capture_output=True).stdout, np.float32).reshape(-1, 2).copy()
                f_ = min(len(s) // 2, int(0.012 * SR))
                if f_: s[:f_] *= np.linspace(0, 1, f_)[:, None]; s[-f_:] *= np.linspace(1, 0, f_)[:, None]
                poser(voix, s, O[k], g)
    e = moyenne(np.sqrt(moyenne(voix.mean(1) ** 2, int(0.05 * SR))), int(0.3 * SR))
    seuil = np.percentile(e[e > 1e-4], 35) if (e > 1e-4).any() else 1.0
    parle = np.clip((e - seuil * 0.4) / (seuil * 1.2), 0, 1)
    mus = piste(); mu = PLAN.get('musique')
    if mu and mu.get('fichier'):
        mf = mu['fichier'] if os.path.isabs(mu['fichier']) else os.path.join(ICI, mu['fichier'])
        if os.path.exists(mf):
            m = lire_audio(mf, 'loudnorm=I=-16:TP=-2:LRA=11')
            while 0 < len(m) < n: m = np.concatenate([m, m])
            m = m[:n]; k = int(2.0 * SR); m[-k:] *= np.linspace(1, 0, k)[:, None]
            base = 20 * math.log10(max(float(mu.get('volume', 0.2)), 0.02))      # 0.2 -> -14 dB seule, ~-25 dB sous la voix
            poser(mus, m * (10 ** ((base - 11 * parle) / 20))[:len(m), None], 0)
    sons = piste()
    for t, nom, vol in EVENTS:
        p = next((x for x in (f'{ICI}/sons/{nom}.mp3', f'{ICI}/sons/{nom}.wav') if os.path.exists(x)), None)
        if not p: continue
        s = cache(('son', p), lambda: lire_audio(p))[:int(SR * 2.5)].copy()
        if not len(s): continue
        k = min(len(s), int(0.3 * SR)); s[-k:] *= np.linspace(1, 0, k)[:, None]
        poser(sons, s / (np.abs(s).max() + 1e-6) * 0.5, t, vol * 0.45)
    sons *= (10 ** ((-5 * parle) / 20))[:, None]
    tmp = chemin + '.brut.wav'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', '-', tmp], input=(voix + mus + sons).astype(np.float32).tobytes(), check=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', tmp, '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.84:level=false', '-ar', str(SR), chemin], check=True)
    os.remove(tmp)

# ===================================================================================== rendu parallèle
def travail(args):
    de, a, sortie, idx, total = args
    enc = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19', '-pix_fmt', 'yuv420p', sortie], stdin=subprocess.PIPE)
    for i in range(de, a):
        enc.stdin.write(rendre(i).tobytes())
        if idx == 0 and (i - de) % 30 == 0: print(f'PROGRESSION {min(95, int(100 * (i - de) / max(1, a - de)))}', flush=True)
    enc.stdin.close(); enc.wait(); return sortie

if __name__ == '__main__':
    print(f'durée {DUREE:.1f} s · {len(COUPES)} coupes · {len(MOMENTS)} moments · {len(EVENTS)} bruitages · {"vertical" if VERTICAL else "horizontal"}', flush=True)
    if '--apercu' in sys.argv:
        os.makedirs('apercus', exist_ok=True)
        for ts in [float(x) for x in sys.argv[sys.argv.index('--apercu') + 1].split(',')]:
            Image.fromarray(rendre(int(round(ts * FPS)))).save(f'apercus/a-{ts:06.2f}.jpg', quality=85); print('apercus/a-%06.2f.jpg' % ts)
        sys.exit()
    sortie = sys.argv[2]
    tmpd = tempfile.mkdtemp(prefix='jmpro-')
    n = max(1, min(mp.cpu_count(), 8)); pas = math.ceil(NTOT / n)
    t0 = time.time()
    with mp.get_context('fork').Pool(n) as pool:
        parts = pool.map(travail, [(k * pas, min(NTOT, (k + 1) * pas), f'{tmpd}/p{k}.mp4', k, n) for k in range(n) if k * pas < NTOT])
    open(f'{tmpd}/liste.txt', 'w').write(''.join(f"file '{p}'\n" for p in parts))
    bande_son(f'{tmpd}/son.wav')
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', f'{tmpd}/liste.txt', '-i', f'{tmpd}/son.wav',
                    '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
                    '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-shortest', sortie], check=True)
    print('PROGRESSION 100', flush=True)
    print(f'ok {sortie} · {DUREE:.1f} s · rendu en {time.time() - t0:.0f} s', flush=True)
