#!/usr/bin/env python3
"""Efface proprement (sans flou) les sous-titres incrustés, pseudos, filigranes et logos d'une vidéo.

Trois sources de masque, réunies image par image :
  1. le texte incrusté détecté automatiquement (lettres claires cernées de sombre, n'importe où dans l'image) ;
  2. les filigranes fixes (logo, pseudo, « @compte ») : ce qui ne bouge pas alors que l'image bouge ;
  3. les zones que tu indiques toi-même après avoir regardé les images (--zones).
Reconstruction : on reprend d'abord le vrai décor vu dans les images voisines (plan fixe ou peu mobile),
sinon on reconstruit par diffusion (OpenCV, Navier-Stokes) avec une texture fine ; jamais de flou.

Utilisation :
    python3 effacer.py source.mp4 propre.mp4 [--zones zones.json] [--sans-auto] [--apercu dossier/]
zones.json : [{"x":0.62,"y":0.03,"l":0.35,"h":0.06,"debut":0,"fin":999}, ...]  (fractions de l'image SOURCE, heures en s)
--decor : plan fixe (caméra immobile) : reprend le vrai décor des images voisines au lieu de le reconstruire.
--apercu : écrit 6 paires avant/après (JPG) pour contrôler le résultat avant de monter.
Écrit « PROGRESSION nn » et propre.json : {"sous_titres_y": hauteur des anciens sous-titres (fraction) ou null}.
"""
import json, os, subprocess, sys
import numpy as np, cv2

args = sys.argv[1:]
SRC, OUT = args[0], args[1]
ZONES = json.load(open(args[args.index('--zones') + 1])) if '--zones' in args else []
AUTO = '--sans-auto' not in args
DECOR = '--decor' in args          # reprise du décor des images voisines : seulement pour un plan fixe (trépied)
APERCU = args[args.index('--apercu') + 1] if '--apercu' in args else None

p = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=width,height,r_frame_rate:format=duration',
                               '-of', 'json', SRC], capture_output=True, text=True, check=True).stdout)
W0, H0 = p['streams'][0]['width'], p['streams'][0]['height']
num, den = map(int, p['streams'][0]['r_frame_rate'].split('/'))
FPS = min(60.0, num / den if den else 30.0)
DUREE = float(p['format']['duration'])
N = int(DUREE * FPS)
k3, k5 = np.ones((3, 3), np.uint8), np.ones((5, 5), np.uint8)


def lecteur(fps=None):
    vf = ['-vf', f'fps={fps}'] if fps else []
    return subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-i', SRC, *vf, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)


def lire(proc):
    b = proc.stdout.read(W0 * H0 * 3)
    return None if len(b) < W0 * H0 * 3 else np.frombuffer(b, np.uint8).reshape(H0, W0, 3)


# ---------- 2. filigranes fixes : bords présents au même endroit dans presque toutes les images, alors que l'image change
def masque_fixe():
    pr = lecteur(fps=2); bords, images = [], []
    while True:
        f = lire(pr)
        if f is None: break
        g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)
        bords.append(cv2.Canny(g, 80, 200) > 0); images.append(cv2.resize(g, (W0 // 4, H0 // 4)).astype(np.int16))
    pr.wait()
    if len(bords) < 6: return np.zeros((H0, W0), np.uint8)
    freq = np.mean(bords, axis=0)
    mouvement = np.mean([np.abs(a - b) for a, b in zip(images, images[1:])], axis=0)
    mouvement = cv2.resize(mouvement.astype(np.float32), (W0, H0))
    m = ((freq > 0.7) & (cv2.blur(mouvement, (31, 31)) > 6)).astype(np.uint8)   # bord fixe sur une image qui bouge = incrustation
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    out = np.zeros_like(m)
    for j in range(1, n):
        x, y, w, h, a = st[j]
        if a > 40 and w < 0.6 * W0 and h < 0.25 * H0: out[lab == j] = 1      # pas les grands bords (cadre noir, barres)
    return cv2.dilate(out, k5, iterations=2)


# ---------- 1. texte incrusté : lettres claires (blanc ou jaune) qui ressortent du décor, alignées en ligne
LIGNES_Y = []                                              # hauteur des sous-titres trouvés (pour y poser les nouveaux)
ECH = min(1.0, 720 / W0)                                   # détection sur une image réduite (rapide), masque remis à la taille
def masque_texte(f):
    g = cv2.resize(f, (int(W0 * ECH), int(H0 * ECH)), interpolation=cv2.INTER_AREA) if ECH < 1 else f
    h0, w0 = g.shape[:2]
    mx, mn = g.max(2).astype(np.int16), g.min(2).astype(np.int16)
    clair = ((mn > 165) & (mx - mn < 80)) | ((g[..., 0] > 200) & (g[..., 1] > 170) & (g[..., 2] < 120))
    sombre = (mx < 80).astype(np.uint8)
    # lettre incrustée = clair collé à un contour sombre ; ou clair qui ressort nettement du décor (ombre douce)
    gris = g.mean(2).astype(np.float32)
    ressort = (gris - cv2.blur(gris, (max(9, w0 // 25),) * 2)) > 45
    texte = (clair & (cv2.dilate(sombre, k3, iterations=2).astype(bool) | ressort)).astype(np.uint8)
    bords = cv2.Canny(cv2.cvtColor(g, cv2.COLOR_RGB2GRAY), 60, 160) > 0
    ligne = cv2.morphologyEx(texte, cv2.MORPH_CLOSE, np.ones((3, max(11, w0 // 20)), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(ligne, 8)
    m = np.zeros((h0, w0), np.uint8)
    for j in range(1, n):
        x, y, w, h, a = st[j]
        if not (0.010 * h0 < h < 0.09 * h0) or w < 2.2 * h or w < 0.04 * w0: continue
        boite = (slice(y, y + h), slice(x, x + w))
        dens = texte[boite].mean(); arete = bords[boite].mean()
        if dens < 0.12 or arete < 0.10: continue                          # pas assez « texte » (aplat clair, ciel, mur)
        my, mxx = int(0.35 * h) + 2, int(0.2 * h) + 2
        m[max(0, y - my):min(h0, y + h + my), max(0, x - mxx):min(w0, x + w + mxx)] = 1   # toute la ligne
        LIGNES_Y.append((y + h / 2) / h0)
    return cv2.resize(m, (W0, H0), interpolation=cv2.INTER_NEAREST) if ECH < 1 else m


def masque_zones(t):
    m = np.zeros((H0, W0), np.uint8)
    for z in ZONES:
        if z.get('debut', 0) <= t <= z.get('fin', 1e9):
            x0, y0 = int(z['x'] * W0), int(z['y'] * H0)
            m[max(0, y0):y0 + int(z['h'] * H0), max(0, x0):x0 + int(z['l'] * W0)] = 1
    return m


rng = np.random.default_rng(7)
def reconstruire(f, m, decor, age):
    if not m.any(): return f
    m8 = m.astype(np.uint8)
    out = f.copy()
    # a) vrai décor vu récemment (images voisines) si le pourtour colle : rien d'inventé, image nette
    anneau = (cv2.dilate(m8, k5, iterations=3) > 0) & (m8 == 0)
    if decor is not None and anneau.any():
        ecart = np.abs(f[anneau].astype(np.int16) - decor[anneau].astype(np.int16)).mean()
        frais = (age < FPS * 4) & (m8 > 0)
        if DECOR and ecart < 4 and frais.any():
            out[frais] = decor[frais]
            m8 = (m8 > 0) & ~frais
            m8 = m8.astype(np.uint8)
            if not m8.any(): return out
    # b) reconstruction par diffusion + texture fine (évite l'aspect « tache lisse »)
    rep = cv2.inpaint(out, m8 * 255, 5, cv2.INPAINT_NS).astype(np.float32)
    bruit = rng.normal(0, 2.2, rep.shape).astype(np.float32)
    rep = np.clip(rep + bruit, 0, 255)
    mm = cv2.GaussianBlur(m8.astype(np.float32), (0, 0), 1.2)[..., None]
    return (out * (1 - mm) + rep * mm).astype(np.uint8)


FIXE = masque_fixe() if AUTO else np.zeros((H0, W0), np.uint8)
print(f'filigranes fixes : {int(FIXE.sum())} pixels', flush=True)
pr = lecteur()
enc = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W0}x{H0}', '-r', f'{FPS:.3f}', '-i', '-',
                        '-i', SRC, '-map', '0:v', '-map', '1:a?', '-c:a', 'copy', '-c:v', 'libx264', '-preset', 'fast', '-crf', '15', '-pix_fmt', 'yuv420p', OUT],
                       stdin=subprocess.PIPE)
decor, age = None, np.full((H0, W0), 1e9, np.float32)
hist = []                                                # masques des 2 images précédentes (évite le clignotement)
apercus = set(int(N * k / 7) for k in range(1, 7)) if APERCU else set()
if APERCU: os.makedirs(APERCU, exist_ok=True)
i = 0
while True:
    f = lire(pr)
    if f is None: break
    t = i / FPS
    m = masque_zones(t) | FIXE
    if AUTO: mt = masque_texte(f); m = m | mt; hist = (hist + [mt])[-2:]; m = m | np.bitwise_or.reduce(hist)
    g = reconstruire(f, m > 0, decor, age)
    libre = m == 0                                       # mise à jour du décor connu avec les pixels non masqués
    if decor is None: decor = f.copy()
    decor[libre] = f[libre]; age[libre] = 0; age[~libre] += 1
    if i in apercus: cv2.imwrite(os.path.join(APERCU, f'avant-apres-{t:06.2f}.jpg'), cv2.cvtColor(np.hstack([f, g]), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 82])
    enc.stdin.write(g.tobytes()); i += 1
    if i % int(FPS * 3) == 0: print(f'PROGRESSION {min(99, int(100 * i / max(N, 1)))}', flush=True)
enc.stdin.close(); enc.wait(); pr.wait()
infos = {'images': i, 'sous_titres_y': None}
if len(LIGNES_Y) > FPS:                                   # sous-titres incrustés trouvés : leur hauteur la plus fréquente
    h_, b_ = np.histogram(LIGNES_Y, bins=40, range=(0, 1)); k = int(np.argmax(h_)); infos['sous_titres_y'] = round(float((b_[k] + b_[k + 1]) / 2), 3)
json.dump(infos, open(os.path.splitext(OUT)[0] + '.json', 'w'))
print('PROGRESSION 100\nok', i, 'images ->', OUT, json.dumps(infos))
print('conseil : dans le plan de jm_pro.py, mets "sous_titres_y":', infos['sous_titres_y'], '(les nouveaux sous-titres couvrent la zone reconstruite)' if infos['sous_titres_y'] else '')
