#!/usr/bin/env python3
"""Moteur de montage TikTok JILANI MONEY.

Prend une vidéo source + un plan JSON (écrit par Claude) et fabrique une vidéo verticale 1080x1920, 30 i/s :
coupes, cadrage vertical (plein cadre ou fond flou), titre d'accroche, sous-titres animés mot par mot,
zooms, secousses, flashs de transition, bruitages de la banque JILANI MONEY, musique baissée sous la voix,
volume final -14 LUFS.

Utilisation :
    python3 jm_montage.py plan.json sortie.mp4
    python3 jm_montage.py --exemple > plan.json      (plan d'exemple commenté)

Toutes les heures du plan (mots, zooms, bruitages…) sont en secondes DANS LA VIDÉO SOURCE ;
le moteur les recale lui-même après les coupes (ce qui tombe dans une partie coupée est ignoré).
Le moteur écrit « PROGRESSION nn » au fil du rendu.
"""
import json, math, os, subprocess, sys, tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    import cv2
except ImportError:  # OpenCV accélère les zooms ; sans lui on passe par Pillow
    cv2 = None

ICI = os.path.dirname(os.path.abspath(__file__))
W, H, FPS, SR = 1080, 1920, 30, 48000

EXEMPLE = {
    "source": "/mnt/session/uploads/video.mp4",
    "cadrage": "auto",                # auto | plein | flou   (flou = vidéo entière sur fond flouté, pour les vidéos horizontales)
    "focus_x": 0.5,                   # 0 = garder la gauche, 1 = la droite (cadrage plein d'une vidéo horizontale)
    "segments": [[0.0, 12.4], [14.1, 31.0]],   # parties gardées, dans l'ordre ; [] = toute la vidéo
    "vitesse": 1.0,                   # 1.0 à 1.15 : accélère légèrement l'ensemble (voix comprise)
    "titre": {"texte": "IL A FAIT ÇA DEVANT TOUT LE MONDE", "duree": 3.0},
    "sous_titres": {"style": "mot_cle", "mots_par_groupe": 3},   # classique | mot_cle | karaoke | aucun
    "mots": [{"m": "Regardez", "debut": 0.31, "fin": 0.72}],     # transcription mot par mot (heures source)
    "mots_forts": ["jamais", "100", "police"],                    # mots mis en couleur (et zoom léger)
    "zooms": [{"t": 3.2, "duree": 1.2, "echelle": 1.18}],
    "secousses": [5.0],
    "flashs": [8.4],
    "bruitages": [{"t": 3.2, "son": "whoosh-court", "volume": 0.8}],
    "transitions_auto": True,         # flash + whoosh à chaque coupe
    "musique": {"fichier": "/workspace/musique.mp3", "volume": 0.18, "debut": 0},   # null = pas de musique
    "voix_volume": 1.0,
    "barre_progression": True,
    "couleur": "#FFD60A",             # couleur des mots forts et de la barre
    "flou_zones": [],                 # [{"x":0.70,"y":0.04,"l":0.28,"h":0.06,"debut":0,"fin":999}] : flouter un logo (fractions de l'image finale)
}


def log(p):
    print(f"PROGRESSION {int(p)}", flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def sonde(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,width,height,r_frame_rate',
                          '-of', 'json', path], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    v = next((s for s in d['streams'] if s.get('codec_type') == 'video'), None)
    a = any(s.get('codec_type') == 'audio' for s in d['streams'])
    return float(d['format']['duration']), (v['width'], v['height']) if v else (0, 0), a


def police(taille, poids=900):
    for nom in (f'polices/Montserrat-{poids}.ttf', 'polices/Montserrat-900.ttf', 'polices/Montserrat-800.ttf'):
        p = os.path.join(ICI, nom)
        if os.path.exists(p):
            return ImageFont.truetype(p, taille)
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',):
        if os.path.exists(p):
            return ImageFont.truetype(p, taille)
    return ImageFont.load_default()


def hex_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------- timeline ----------
class Chrono:
    """Correspondance heure source <-> heure de sortie après coupes et changement de vitesse."""

    def __init__(self, segments, vitesse):
        self.segs = segments
        self.v = vitesse
        self.debuts = []
        t = 0.0
        for a, b in segments:
            self.debuts.append(t)
            t += (b - a) / vitesse
        self.duree = t

    def sortie(self, ts):
        for (a, b), d in zip(self.segs, self.debuts):
            if a <= ts < b:
                return d + (ts - a) / self.v
        return None

    def coupes(self):
        return self.debuts[1:]


# ---------- sous-titres ----------
def groupes_mots(mots, chrono, n):
    """Regroupe les mots (heures de sortie) par 1 à n, en coupant aux pauses et à la ponctuation."""
    ms = []
    for m in mots:
        d = chrono.sortie(m['debut'])
        if d is None:
            continue
        f = chrono.sortie(max(m['debut'], m['fin'] - 1e-3))
        f = f if f is not None else d + 0.25
        texte = str(m['m']).strip()
        if texte:
            ms.append({'m': texte, 'd': d, 'f': max(f, d + 0.08)})
    gs, cur = [], []
    for i, m in enumerate(ms):
        cur.append(m)
        fin_phrase = m['m'][-1:] in '.!?,;:'
        pause = i + 1 < len(ms) and ms[i + 1]['d'] - m['f'] > 0.35
        if len(cur) >= n or fin_phrase or pause or i == len(ms) - 1:
            gs.append(cur)
            cur = []
    for k, g in enumerate(gs):  # le groupe reste affiché jusqu'au suivant (max 0,6 s de plus)
        nxt = gs[k + 1][0]['d'] if k + 1 < len(gs) else g[-1]['f'] + 0.6
        g_fin = min(nxt, g[-1]['f'] + 0.6)
        for m in g:
            m['gf'] = g_fin
    return gs


def nettoie(m):
    return ''.join(c for c in m.lower() if c.isalnum())


class SousTitres:
    def __init__(self, plan, chrono):
        st = plan.get('sous_titres') or {}
        self.style = st.get('style', 'mot_cle')
        self.groupes = [] if self.style == 'aucun' else groupes_mots(plan.get('mots') or [], chrono, int(st.get('mots_par_groupe', 3)))
        self.forts = {nettoie(m) for m in plan.get('mots_forts') or []}
        self.couleur = hex_rgb(plan.get('couleur', '#FFD60A'))
        self.f = police(92, 900)
        self.cache = {}

    def groupe_a(self, t):
        for g in self.groupes:
            if g[0]['d'] - 0.02 <= t < g[0]['gf']:
                return g
        return None

    def image(self, g, actif):
        cle = (id(g), actif)
        if cle in self.cache:
            return self.cache[cle]
        mots = [m['m'].upper() for m in g]
        esp = 26
        tailles = [self.f.getbbox(m) for m in mots]
        larg = [b[2] - b[0] for b in tailles]
        # retour à la ligne si trop large (zone sûre : 900 px)
        lignes, cur, lw = [], [], 0
        for i, w in enumerate(larg):
            if cur and lw + esp + w > 900:
                lignes.append(cur)
                cur, lw = [], 0
            cur.append(i)
            lw += (esp if len(cur) > 1 else 0) + w
        lignes.append(cur)
        hl = 118
        img = Image.new('RGBA', (1000, hl * len(lignes) + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for li, ligne in enumerate(lignes):
            total = sum(larg[i] for i in ligne) + esp * (len(ligne) - 1)
            x = (1000 - total) // 2
            y = 20 + li * hl
            for i in ligne:
                fort = nettoie(g[i]['m']) in self.forts
                coul = (255, 255, 255)
                if self.style == 'mot_cle' and fort:
                    coul = self.couleur
                if self.style == 'karaoke' and i == actif:
                    d.rounded_rectangle([x - 14, y - 6, x + larg[i] + 14, y + 104], 18, fill=self.couleur + (255,))
                    coul = (10, 10, 10)
                elif self.style == 'classique' and i == actif:
                    coul = self.couleur
                ox = -tailles[i][0]
                d.text((x + ox, y), mots[i], font=self.f, fill=coul, stroke_width=0 if (self.style == 'karaoke' and i == actif) else 9, stroke_fill=(0, 0, 0))
                x += larg[i] + esp
        ombre = img.filter(ImageFilter.GaussianBlur(10))
        a = np.array(ombre)[..., 3].astype(np.float32) * 0.55
        fond = Image.new('RGBA', img.size, (0, 0, 0, 0))
        fond.putalpha(Image.fromarray(a.astype(np.uint8)))
        fond.alpha_composite(img)
        self.cache[cle] = fond
        return fond

    def dessiner(self, frame, t):
        g = self.groupe_a(t)
        if not g:
            return
        actif = max((i for i, m in enumerate(g) if m['d'] <= t), default=0)
        img = self.image(g, actif)
        # petit « pop » à l'apparition du groupe
        age = t - g[0]['d']
        s = 1.0 + 0.12 * max(0.0, 1 - age / 0.12) if age < 0.12 else 1.0
        if s != 1.0:
            img = img.resize((int(img.width * s), int(img.height * s)), Image.BILINEAR)
        x = (W - img.width) // 2
        y = int(H * 0.64) - img.height // 2
        frame.alpha_composite(img, (x, y))


# ---------- titre ----------
def image_titre(texte, couleur):
    mots = texte.upper().split()
    for taille in (70, 62, 56, 50, 46):  # la police rétrécit jusqu'à tenir sur 3 lignes
        f = police(taille, 900)
        lignes, cur = [], ''
        for m in mots:
            essai = (cur + ' ' + m).strip()
            if f.getlength(essai) > 860 and cur:
                lignes.append(cur)
                cur = m
            else:
                cur = essai
        lignes.append(cur)
        if len(lignes) <= 3:
            break
    lignes = lignes[:3]
    hl = int(taille * 1.23)
    larg = max(int(f.getlength(l)) for l in lignes) + 70
    img = Image.new('RGBA', (larg + 20, hl * len(lignes) + 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([10, 10, larg + 10, hl * len(lignes) + 46], 26, fill=(255, 255, 255, 245))
    d.rectangle([10, 10, 24, hl * len(lignes) + 46], fill=couleur + (255,))
    for i, l in enumerate(lignes):
        d.text(((larg + 20 - f.getlength(l)) / 2 + 6, 26 + i * hl), l, font=f, fill=(12, 12, 16))
    return img


def ease_out(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


# ---------- audio ----------
def lire_audio(path, debut=None, duree=None):
    cmd = ['ffmpeg', '-nostdin', '-v', 'error']
    if debut is not None:
        cmd += ['-ss', f'{debut:.3f}']
    if duree is not None:
        cmd += ['-t', f'{duree:.3f}']
    cmd += ['-i', path, '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-']
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def moyenne(x, k):
    k = max(1, int(k))
    c = np.cumsum(np.concatenate([np.zeros(k // 2 + 1), x, np.zeros(k)]))
    return ((c[k:] - c[:-k]) / k)[:len(x)]


def piste_audio(plan, chrono, src, a_audio, sfx_auto, tmp):
    n = int(math.ceil(chrono.duree * SR)) + SR // 10
    voix = np.zeros((n, 2), np.float32)
    v = chrono.v
    if a_audio:
        for (a, b), d in zip(chrono.segs, chrono.debuts):
            filt = []
            if abs(v - 1) > 1e-3:
                filt = ['-af', f'atempo={v:.4f}']
            cmd = ['ffmpeg', '-nostdin', '-v', 'error', '-ss', f'{a:.3f}', '-t', f'{b - a:.3f}', '-i', src, *filt,
                   '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-']
            x = np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.float32).reshape(-1, 2).copy()
            k = min(len(x) // 2, int(0.012 * SR))  # micro-fondus aux coupes (pas de clic)
            if k > 0:
                x[:k] *= np.linspace(0, 1, k)[:, None]
                x[-k:] *= np.linspace(1, 0, k)[:, None]
            i = int(d * SR)
            j = min(n, i + len(x))
            voix[i:j] += x[:j - i]
        voix *= float(plan.get('voix_volume', 1.0))
    # présence de voix -> baisse de la musique
    mono = np.abs(voix.mean(1))
    env = moyenne(moyenne(mono, 0.05 * SR), 0.3 * SR)
    vivant = env[env > 1e-4]
    seuil = np.percentile(vivant, 30) if len(vivant) else 1.0
    parle = np.clip((env - seuil * 0.4) / (seuil * 1.2 + 1e-9), 0, 1)

    mix = voix.copy()
    mus = plan.get('musique')
    if mus and mus.get('fichier'):
        chemin = mus['fichier'] if os.path.isabs(mus['fichier']) else os.path.join(ICI, mus['fichier'])
        if os.path.exists(chemin):
            m = lire_audio(chemin, float(mus.get('debut', 0)))
            if len(m):
                while len(m) < n:
                    m = np.concatenate([m, m])
                m = m[:n]
                pk = np.sqrt(np.mean(m ** 2)) + 1e-9
                m = m / pk * 0.12  # niveau de référence
                k = int(0.5 * SR)
                m[:k] *= np.linspace(0, 1, k)[:, None]
                k2 = min(n, int(2.0 * SR))
                m[-k2:] *= np.linspace(1, 0, k2)[:, None]
                vol = float(mus.get('volume', 0.18)) / 0.18
                gain = 10 ** ((-6 - 12 * parle) / 20) * vol if a_audio else np.full(n, 10 ** (-2 / 20) * vol)
                mix += m * gain[:, None]
    sfx = np.zeros((n, 2), np.float32)
    for e in list(plan.get('bruitages') or []) + sfx_auto:
        t = e['t_sortie'] if 't_sortie' in e else chrono.sortie(float(e['t']))
        if t is None:
            continue
        p = os.path.join(ICI, 'sons', f"{e['son']}.mp3")
        if not os.path.exists(p):
            print(f"[son introuvable] {e['son']}", flush=True)
            continue
        s = lire_audio(p)[:int(SR * 3.5)]
        if not len(s):
            continue
        s = s / (np.abs(s).max() + 1e-6) * 0.5
        i = int(t * SR)
        j = min(n, i + len(s))
        if j > i:
            sfx[i:j] += s[:j - i] * float(e.get('volume', 0.8)) * 0.6
    sfx *= (10 ** ((-6 * parle) / 20))[:, None]  # les bruitages ne couvrent jamais la voix
    mix += sfx
    brut = os.path.join(tmp, 'mix-brut.wav')
    import wave
    pcm = (np.clip(mix, -1, 1) * 32767).astype('<i2')
    with wave.open(brut, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    final = os.path.join(tmp, 'mix.wav')
    run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', brut, '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.89:level=false',
         '-ar', str(SR), final])
    return final


# ---------- image ----------
def filtre_cadrage(cadrage, taille, focus_x):
    w, h = taille
    if cadrage == 'auto':
        cadrage = 'plein' if w / max(h, 1) < 0.8 else 'flou'
    if cadrage == 'plein':
        fx = min(1, max(0, focus_x))
        return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}:(iw-{W})*{fx:.3f}:(ih-{H})/2,setsar=1"
    return (f"split[a][b];[a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},boxblur=12:2,"
            f"scale={W}:{H},eq=brightness=-0.10:saturation=1.15[bg];[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")


def zoom_frame(arr, s, cx=0.5, cy=0.45, dx=0, dy=0):
    if s <= 1.0005 and not dx and not dy:
        return arr
    cw, ch = int(W / s), int(H / s)
    x0 = int(min(max(cx * W - cw / 2 + dx, 0), W - cw))
    y0 = int(min(max(cy * H - ch / 2 + dy, 0), H - ch))
    crop = arr[y0:y0 + ch, x0:x0 + cw]
    if cv2 is not None:
        return cv2.resize(crop, (W, H), interpolation=cv2.INTER_LINEAR)
    return np.array(Image.fromarray(crop).resize((W, H), Image.BILINEAR))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--exemple':
        print(json.dumps(EXEMPLE, ensure_ascii=False, indent=1))
        return
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    plan = json.load(open(sys.argv[1], encoding='utf-8'))
    sortie = sys.argv[2]
    src = plan['source']
    duree, taille, a_audio = sonde(src)
    segs = [[max(0.0, float(a)), min(duree, float(b))] for a, b in (plan.get('segments') or [[0, duree]])]
    segs = [s for s in segs if s[1] - s[0] > 0.2] or [[0.0, duree]]
    vitesse = min(1.3, max(0.8, float(plan.get('vitesse', 1.0))))
    chrono = Chrono(segs, vitesse)
    total = int(round(chrono.duree * FPS))
    couleur = hex_rgb(plan.get('couleur', '#FFD60A'))
    log(2)

    # effets en heures de sortie
    sfx_auto, flashs = [], []
    if plan.get('transitions_auto', True):
        for c in chrono.coupes():
            flashs.append(c)
            sfx_auto.append({'t_sortie': max(0, c - 0.12), 'son': 'whoosh-court', 'volume': 0.7})
    for t in plan.get('flashs') or []:
        o = chrono.sortie(float(t))
        if o is not None:
            flashs.append(o)
    zooms = []
    for z in plan.get('zooms') or []:
        o = chrono.sortie(float(z['t']))
        if o is not None:
            zooms.append((o, float(z.get('duree', 1.0)) / vitesse, float(z.get('echelle', 1.15))))
    secousses = [o for o in (chrono.sortie(float(t)) for t in plan.get('secousses') or []) if o is not None]
    titre = plan.get('titre') or {}
    img_titre = image_titre(titre['texte'], couleur) if titre.get('texte') else None
    t_titre = float(titre.get('duree', 3.0))
    if img_titre is not None:
        sfx_auto.append({'t_sortie': 0.05, 'son': 'impact-cinema', 'volume': 0.55})
    st = SousTitres(plan, chrono)
    # zoom léger automatique sur les mots forts (style mot_cle)
    if st.style == 'mot_cle' and st.forts:
        for g in st.groupes:
            for m in g:
                if nettoie(m['m']) in st.forts and not any(abs(m['d'] - z[0]) < 1.0 for z in zooms):
                    zooms.append((m['d'], 0.9, 1.08))
    flous = plan.get('flou_zones') or []
    barre = bool(plan.get('barre_progression', True))

    with tempfile.TemporaryDirectory() as tmp:
        audio = piste_audio(plan, chrono, src, a_audio, sfx_auto, tmp)
        log(12)
        video_tmp = os.path.join(tmp, 'video.mp4')
        enc = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS),
                                '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', video_tmp],
                               stdin=subprocess.PIPE)
        filt = filtre_cadrage(plan.get('cadrage', 'auto'), taille, float(plan.get('focus_x', 0.5)))
        fait = 0
        taille_frame = W * H * 3
        for (a, b), d0 in zip(chrono.segs, chrono.debuts):
            n_seg = int(round(((b - a) / vitesse) * FPS))
            vf = (f"setpts=PTS/{vitesse:.4f}," if abs(vitesse - 1) > 1e-3 else '') + filt + f",fps={FPS}"
            dec = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-ss', f'{a:.3f}', '-t', f'{b - a:.3f}', '-i', src, '-an',
                                    '-filter_complex', vf, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
            precedent = None
            for k in range(n_seg):
                raw = dec.stdout.read(taille_frame)
                if len(raw) < taille_frame:
                    if precedent is None:
                        break
                    arr = precedent  # vidéo un peu plus courte que prévu : on tient la dernière image
                else:
                    arr = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
                    precedent = arr
                t = d0 + k / FPS
                # zoom + secousse
                s = 1.0
                for (zt, zd, ze) in zooms:
                    if zt - 0.15 <= t <= zt + zd:
                        u = (t - zt + 0.15) / 0.15 if t < zt else 1.0
                        v = 1.0 if t < zt + zd - 0.25 else max(0.0, (zt + zd - t) / 0.25)
                        s = max(s, 1 + (ze - 1) * ease_out(min(u, 1)) * v)
                dx = dy = 0
                for st_t in secousses:
                    if st_t <= t < st_t + 0.35:
                        amp = 22 * (1 - (t - st_t) / 0.35)
                        dx, dy = amp * math.sin(t * 90), amp * math.cos(t * 77)
                        s = max(s, 1.04)
                arr = zoom_frame(arr, s, dx=dx, dy=dy)
                img = Image.fromarray(arr).convert('RGBA')
                for z in flous:
                    if float(z.get('debut', 0)) <= t <= float(z.get('fin', 1e9)):
                        box = (int(z['x'] * W), int(z['y'] * H), int((z['x'] + z['l']) * W), int((z['y'] + z['h']) * H))
                        img.paste(img.crop(box).filter(ImageFilter.GaussianBlur(28)), box[:2])
                if img_titre is not None and t < t_titre:
                    u = ease_out(t / 0.35)
                    sortie_t = max(0.0, (t - (t_titre - 0.3)) / 0.3)
                    sc = 0.6 + 0.4 * u
                    ti = img_titre.resize((max(1, int(img_titre.width * sc)), max(1, int(img_titre.height * sc))), Image.BILINEAR)
                    if sortie_t > 0:
                        al = np.array(ti)
                        al[..., 3] = (al[..., 3] * (1 - sortie_t)).astype(np.uint8)
                        ti = Image.fromarray(al)
                    img.alpha_composite(ti, ((W - ti.width) // 2, int(H * 0.17)))
                st.dessiner(img, t)
                if barre:
                    dr = ImageDraw.Draw(img)
                    dr.rectangle([0, 0, int(W * (t / chrono.duree)), 9], fill=couleur + (255,))
                out = np.array(img.convert('RGB'))
                for ft in flashs:
                    if ft - 0.03 <= t < ft + 0.18:
                        al = 0.85 * (1 - (t - ft + 0.03) / 0.21)
                        out = (out * (1 - al) + 255 * al).astype(np.uint8)
                enc.stdin.write(out.tobytes())
                fait += 1
                if fait % 30 == 0:
                    log(12 + 80 * fait / max(total, 1))
            dec.stdout.close()
            dec.wait()
        enc.stdin.close()
        enc.wait()
        log(94)
        run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', video_tmp, '-i', audio, '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
             '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', sortie])
    log(100)
    print(f"OK {sortie} ({chrono.duree:.1f} s)", flush=True)


if __name__ == '__main__':
    main()
