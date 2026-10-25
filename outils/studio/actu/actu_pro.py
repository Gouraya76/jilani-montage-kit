#!/usr/bin/env python3
"""Montage actu « pro » 9:16 : transitions 3D/2D, compteurs 3D animés, jauge de vent, particules météo, tremblements, habillage C1 News."""
import json, math, subprocess, sys, random
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

P = json.load(open(sys.argv[1])); OUT = sys.argv[2]
APERCU = [float(x) for x in sys.argv[3].split(',')] if len(sys.argv) > 3 else None
W, H, FPS = 1080, 1920, 30
POL = '/workspace/pack/polices/Montserrat-{}.ttf'
def font(p, s): return ImageFont.truetype(POL.format(p), s)
ROUGE = (226, 30, 38); BLANC = (255, 255, 255); ORANGE = (255, 140, 0)
DUREE = P['duree']; N = int(DUREE * FPS); COUPES = P['coupes']
MOTS = json.load(open(P['mots']))
def ease(x): x = min(max(x, 0), 1); return 1 - (1 - x) ** 3
def ease_io(x): x = min(max(x, 0), 1); return x * x * (3 - 2 * x)
def back(x, s=1.7): x = min(max(x, 0), 1) - 1; return 1 + x * x * ((s + 1) * x + s)

# ---------------------------------------------------------------- 3D : perspective d'un calque
def persp(img, rx=0, ry=0, sc=1.0, f=1400):
    """Fait pivoter un calque RGBA (numpy HxWx4) autour de son centre (degrés), projection perspective."""
    h, w = img.shape[:2]; cx, cy = w / 2, h / 2
    a, b = math.radians(rx), math.radians(ry)
    pts = []
    for x, y in [(-cx, -cy), (cx, -cy), (cx, cy), (-cx, cy)]:
        x, y = x * sc, y * sc
        y2 = y * math.cos(a); z = y * math.sin(a)
        x2 = x * math.cos(b) + z * math.sin(b); z2 = -x * math.sin(b) + z * math.cos(b)
        k = f / (f + z2); pts.append((cx + x2 * k, cy + y2 * k))
    M = cv2.getPerspectiveTransform(np.float32([(0, 0), (w, 0), (w, h), (0, h)]), np.float32(pts))
    return cv2.warpPerspective(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
def coller(fond, calque, x, y):
    """Colle un calque RGBA numpy sur une image RGB float (sur place)."""
    h, w = calque.shape[:2]; x0, y0 = max(0, x), max(0, y); x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0: return
    c = calque[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32); a = c[..., 3:4] / 255
    fond[y0:y1, x0:x1] = fond[y0:y1, x0:x1] * (1 - a) + c[..., :3] * a

# ---------------------------------------------------------------- transitions 3D / 2D
def flou_dir(img, n):
    n = int(n)
    if n < 3: return img
    k = np.zeros((1, n), np.float32); k[0] = 1 / n; return cv2.filter2D(img, -1, k)
def t_cube(A, B, p):
    """Cube 3D qui tourne autour de l'axe vertical : A part à gauche, B arrive de la droite."""
    e = ease_io(p); fond = np.zeros_like(A); hw = W / 2; D = 1800
    for img, th in ((A, -90 * e), (B, 90 * (1 - e))):
        a = math.radians(th)
        if math.cos(a) <= 0.02: continue
        pts = []
        for x in (-hw, hw):
            X = x * math.cos(a) - hw * math.sin(a); Z = x * math.sin(a) + hw * math.cos(a) - hw
            k = D / (D + Z); pts.append((W / 2 + X * k, k))
        (xl, kl), (xr, kr) = pts
        q = np.float32([(xl, H / 2 - H / 2 * kl), (xr, H / 2 - H / 2 * kr), (xr, H / 2 + H / 2 * kr), (xl, H / 2 + H / 2 * kl)])
        M = cv2.getPerspectiveTransform(np.float32([(0, 0), (W, 0), (W, H), (0, H)]), q)
        wi = cv2.warpPerspective(img, M, (W, H)); m = cv2.warpPerspective(np.ones((H, W), np.float32), M, (W, H))[..., None]
        fond = fond * (1 - m) + wi * m * (0.55 + 0.45 * math.cos(a))
    return fond
def t_flip(A, B, p):
    e = ease_io(p); img, ang = (A, 90 * e * 2) if e < 0.5 else (B, -90 * (1 - e) * 2)
    rgba = np.dstack([img, np.full((H, W), 255, np.float32)]).astype(np.uint8)
    w = persp(rgba, ry=ang, sc=1 - 0.15 * math.sin(math.pi * e)).astype(np.float32)
    a = w[..., 3:4] / 255; return w[..., :3] * a * (1 - 0.4 * abs(math.sin(math.radians(ang))))
def t_whip(A, B, p, sens=1):
    e = ease_io(p); off = int(e * W) * sens; out = np.zeros_like(A)
    if sens > 0: out[:, :W - off] = A[:, off:]; out[:, W - off:] = B[:, :off]
    else: off = -off; out[:, off:] = A[:, :W - off]; out[:, :off] = B[:, W - off:]
    return flou_dir(out, 140 * math.sin(math.pi * e))
def t_zoom(A, B, p):
    e = ease_io(p); img = A if e < 0.5 else B; z = 1 + 0.6 * math.sin(math.pi * e)
    sw, sh = int(W / z), int(H / z); x0, y0 = (W - sw) // 2, (H - sh) // 2
    im = cv2.resize(img[y0:y0 + sh, x0:x0 + sw], (W, H))
    bl = cv2.GaussianBlur(im, (0, 0), 1 + 14 * math.sin(math.pi * e)); return bl
def t_glitch(A, B, p, t):
    img = (A if p < 0.5 else B).copy(); amp = math.sin(math.pi * p)
    rnd = random.Random(int(t * 1000))
    for _ in range(9):
        y = rnd.randint(0, H - 60); hh = rnd.randint(20, 120); dx = int(rnd.uniform(-90, 90) * amp)
        img[y:y + hh] = np.roll(img[y:y + hh], dx, axis=1)
    d = int(22 * amp); out = img.copy(); out[..., 0] = np.roll(img[..., 0], d, axis=1); out[..., 2] = np.roll(img[..., 2], -d, axis=1)
    return out
TYPES = P.get('transitions_cycle', ['cube', 'whipG', 'flip', 'zoom', 'glitch', 'whipD'])
TRANS = {c: TYPES[k % len(TYPES)] for k, c in enumerate(COUPES)}
DT = 0.42

# ---------------------------------------------------------------- en-tête, titre, sous-titres
def boite(txt, f, fg, bg, padx, h):
    b = f.getbbox(txt); im = Image.new('RGBA', (b[2] - b[0] + 2 * padx, h), bg + (255,)); d = ImageDraw.Draw(im)
    d.text((padx - b[0], (h - (b[3] + b[1])) // 2), txt, font=f, fill=fg); return im
ENTETE = Image.new('RGBA', (W, 340), (0, 0, 0, 0)); d = ImageDraw.Draw(ENTETE)
g = np.clip(1 - np.arange(340) / 340, 0, 1) ** 1.6; ENTETE = Image.fromarray(np.dstack([np.zeros((340, W, 3), np.uint8), (np.ones((340, W)) * 140 * g[:, None]).astype(np.uint8)]), 'RGBA')
d = ImageDraw.Draw(ENTETE)
d.text((96, 214), P['date'], font=font(800, 32), fill=BLANC); d.text((96, 256), P['lieu'], font=font(800, 26), fill=(208, 211, 217))
LOGO = Image.open(P['logo']).convert('RGBA'); LOGO = LOGO.resize((205, int(205 * LOGO.height / LOGO.width)), Image.LANCZOS)
ENTETE.alpha_composite(LOGO, (W - 53 - LOGO.width, 236 - LOGO.height // 2))
ENTETE = np.asarray(ENTETE)
FT = font(900, 46)
def etiquette(txt):
    b = FT.getbbox(txt); w, h = b[2] - b[0] + 56, 74
    im = Image.new('RGBA', (w, h), BLANC + (255,)); dd = ImageDraw.Draw(im)
    dd.rectangle([0, 0, 10, h], fill=ROUGE); dd.text((32 - b[0], (h - (b[3] + b[1])) // 2), txt, font=FT, fill=(12, 12, 14)); return np.asarray(im)
TITRE = [etiquette(l) for l in P['titre']]
GROUPES, gr = [], []
for m in MOTS:
    gr.append(m)
    if len(gr) >= 3 or m['m'][-1] in '.,?!:…': GROUPES.append(gr); gr = []
if gr: GROUPES.append(gr)
FST = font(900, 70)
def sous_titre(gg):
    txt = ' '.join(m['m'] for m in gg).upper(); lignes, cur = [], ''
    for w_ in txt.split():
        t = (cur + ' ' + w_).strip()
        if FST.getlength(t) > W - 120 and cur: lignes.append(cur); cur = w_
        else: cur = t
    lignes.append(cur)
    im = Image.new('RGBA', (W, 82 * len(lignes) + 30), (0, 0, 0, 0)); dd = ImageDraw.Draw(im)
    for k, l in enumerate(lignes):
        x = (W - FST.getlength(l)) / 2; yy = 12 + k * 82
        dd.text((x + 5, yy + 6), l, font=FST, fill=(0, 0, 0, 230)); dd.text((x, yy), l, font=FST, fill=BLANC, stroke_width=3, stroke_fill=(0, 0, 0))
    return np.asarray(im)
ST = [(gg[0]['debut'], (GROUPES[i + 1][0]['debut'] if i + 1 < len(GROUPES) else gg[-1]['fin'] + 0.8), sous_titre(gg)) for i, gg in enumerate(GROUPES)]

# ---------------------------------------------------------------- motion design : icônes, compteurs 3D, jauge
def icone(kind, s=150):
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    if kind == 'alerte':
        d.polygon([(s / 2, 8), (s - 8, s - 14), (8, s - 14)], fill=ORANGE, outline=BLANC, width=6)
        d.rectangle([s / 2 - 7, s * 0.36, s / 2 + 7, s * 0.66], fill=BLANC); d.ellipse([s / 2 - 9, s * 0.72, s / 2 + 9, s * 0.72 + 18], fill=BLANC)
    elif kind == 'eclair':
        d.ellipse([4, 4, s - 4, s - 4], fill=(255, 196, 0)); d.polygon([(s * .56, s * .14), (s * .3, s * .56), (s * .48, s * .56), (s * .40, s * .88), (s * .72, s * .42), (s * .53, s * .42)], fill=(20, 20, 24))
    elif kind == 'sirene':
        d.ellipse([4, 4, s - 4, s - 4], fill=ROUGE); d.pieslice([s * .25, s * .26, s * .75, s * .76], 180, 360, fill=BLANC); d.rectangle([s * .22, s * .56, s * .78, s * .68], fill=BLANC)
    elif kind == 'pluie':
        d.ellipse([s * .12, s * .2, s * .88, s * .62], fill=(225, 230, 240))
        for k in range(4): x = s * (.22 + .18 * k); d.line([(x, s * .7), (x - 10, s * .92)], fill=(90, 170, 255), width=8)
    elif kind == 'croix':
        d.ellipse([4, 4, s - 4, s - 4], fill=(30, 30, 34), outline=BLANC, width=5); d.rectangle([s * .44, s * .2, s * .56, s * .8], fill=BLANC); d.rectangle([s * .3, s * .36, s * .7, s * .48], fill=BLANC)
    return im
FCH = font(900, 150); FSO = font(900, 46)
def fmt(v): return f"{int(v):,}".replace(',', ' ')
def calque_chiffre(c, val):
    txt = c['texte'] if 'valeur' not in c else fmt(val) + c.get('suffixe', '')
    f = FCH if FCH.getlength(txt) < W - 260 else font(900, int(150 * (W - 260) / FCH.getlength(txt)))
    ic = icone(c['icone']) if c.get('icone') else None
    tw = f.getlength(txt) + (170 if ic else 0)
    im = Image.new('RGBA', (W, 300), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    x = (W - tw) / 2
    if ic: im.alpha_composite(ic, (int(x), 30)); x += 170
    d.text((x + 6, 22), txt, font=f, fill=(0, 0, 0, 200)); d.text((x, 14), txt, font=f, fill=BLANC, stroke_width=4, stroke_fill=(0, 0, 0))
    if c.get('sous'):
        b = FSO.getbbox(c['sous']); w2 = b[2] - b[0] + 40; x2 = (W - w2) // 2
        d.rectangle([x2, 200, x2 + w2, 268], fill=ROUGE); d.text((x2 + 20 - b[0], 234 - (b[3] + b[1]) // 2), c['sous'], font=FSO, fill=BLANC)
    return np.asarray(im)
def jauge(v, vmax=200):
    s = 520; im = Image.new('RGBA', (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse([10, 10, s - 10, s - 10], fill=(10, 12, 16, 190), outline=(255, 255, 255, 90), width=4)
    a0, a1 = 135, 405
    d.arc([50, 50, s - 50, s - 50], a0, a1, fill=(255, 255, 255, 60), width=26)
    av = a0 + (a1 - a0) * min(v, vmax) / vmax
    for k in range(int(a0), int(av), 3):
        col = (255, int(220 - 180 * (k - a0) / (a1 - a0)), 40)
        d.arc([50, 50, s - 50, s - 50], k, k + 3.5, fill=col, width=26)
    for k in range(0, vmax + 1, 20):
        a = math.radians(a0 + (a1 - a0) * k / vmax); r1, r2 = s / 2 - 92, s / 2 - 112
        d.line([(s / 2 + r1 * math.cos(a), s / 2 + r1 * math.sin(a)), (s / 2 + r2 * math.cos(a), s / 2 + r2 * math.sin(a))], fill=BLANC, width=4)
    a = math.radians(av); r = s / 2 - 120
    d.line([(s / 2, s / 2), (s / 2 + r * math.cos(a), s / 2 + r * math.sin(a))], fill=ROUGE, width=12); d.ellipse([s / 2 - 22, s / 2 - 22, s / 2 + 22, s / 2 + 22], fill=ROUGE)
    f = font(900, 96); txt = str(int(v)); d.text(((s - f.getlength(txt)) / 2, s * 0.58), txt, font=f, fill=BLANC)
    f2 = font(900, 34); d.text(((s - f2.getlength('KM/H')) / 2, s * 0.80), 'KM/H', font=f2, fill=(255, 200, 60))
    return np.asarray(im)
CH = P.get('chiffres', [])

# ---------------------------------------------------------------- particules météo (vent + pluie)
rng = np.random.default_rng(7)
NP = 140
PX, PY, PV, PL = rng.uniform(0, W, NP), rng.uniform(0, H, NP), rng.uniform(1400, 2600, NP), rng.uniform(40, 140, NP)
def particules(img, t):
    over = np.zeros((H, W), np.float32)
    dx, dy = math.cos(math.radians(160)), math.sin(math.radians(160))      # vent de l'ouest, pluie qui tombe en biais
    for i in range(NP):
        x = (PX[i] - PV[i] * t * 0.55) % (W + 300) - 150; y = (PY[i] + PV[i] * t * 0.85) % (H + 300) - 150
        cv2.line(over, (int(x), int(y)), (int(x + dx * PL[i] * -1), int(y - dy * PL[i] * -1 * 0 - PL[i] * 1.3)), 1.0, 2, cv2.LINE_AA)
    over = cv2.GaussianBlur(over, (0, 0), 1.2)[..., None]
    return img * (1 - 0.22 * over) + 235 * 0.22 * over

# ---------------------------------------------------------------- rendu
def lire():
    return subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-i', P['fond'], '-vf', f'fps={FPS},scale={W}:{H}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
lect = lire()
if not APERCU:
    ecr = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                            '-c:v', 'libx264', '-crf', '17', '-preset', 'medium', '-pix_fmt', 'yuv420p', '/tmp/news_video.mp4'], stdin=subprocess.PIPE)
bords = [0] + COUPES; prev = None; dernier_A = {}
cibles = set(int(a * FPS) for a in APERCU) if APERCU else None
for i in range(N):
    t = i / FPS
    raw = lect.stdout.read(W * H * 3)
    fr = np.frombuffer(raw, np.uint8).reshape(H, W, 3) if len(raw) == W * H * 3 else prev
    prev = fr
    if cibles is not None and i not in cibles and not any(c - DT <= t < c + DT for c in COUPES): continue
    k = max(j for j, c in enumerate(bords) if c <= t); t0 = bords[k]; t1 = bords[k + 1] if k + 1 < len(bords) else DUREE
    u = (t - t0) / max(t1 - t0, 0.1)
    z = 1.04 + 0.08 * u                                        # lente poussée caméra (+ léger balancement)
    sw, sh = int(W / z), int(H / z); ox = min(max((W - sw) // 2 + int(14 * math.sin(t * 0.7)), 0), W - sw); oy = (H - sh) // 2
    img = cv2.resize(fr[oy:oy + sh, ox:ox + sw], (W, H)).astype(np.float32)
    # mémoire de la dernière image de chaque plan (pour les transitions)
    if k + 1 < len(bords) and t >= bords[k + 1] - 1.5 / FPS: dernier_A[k + 1] = img.copy()
    # transition 3D/2D juste après la coupe (A = dernière image du plan précédent, B = plan courant)
    if k > 0 and t - t0 < DT and k in dernier_A:
        p = (t - t0) / DT; A = dernier_A[k]; ty = TRANS[COUPES[k - 1]]
        if ty == 'cube': img = t_cube(A, img, p)
        elif ty == 'flip': img = t_flip(A, img, p)
        elif ty == 'whipG': img = t_whip(A, img, p, 1)
        elif ty == 'whipD': img = t_whip(A, img, p, -1)
        elif ty == 'zoom': img = t_zoom(A, img, p)
        elif ty == 'glitch': img = t_glitch(A.astype(np.float32), img, p, t)
        fl = max(0, 1 - abs(p - 0.5) / 0.18) * 0.35; img = img * (1 - fl) + 255 * fl
    if cibles is not None and i not in cibles: continue
    img = particules(img, t)
    # tremblement caméra sur les impacts
    sh_ = sum(max(0, 1 - (t - c['t']) / 0.35) for c in CH if c['t'] <= t)
    if sh_ > 0:
        M = np.float32([[1, 0, 18 * sh_ * math.sin(t * 90)], [0, 1, 14 * sh_ * math.cos(t * 77)]]); img = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    # vignette
    if i == 0 or not hasattr(sys, '_vig'):
        yy, xx = np.mgrid[0:H, 0:W]; sys._vig = (1 - 0.35 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2).clip(0, 1) ** 1.5)[..., None].astype(np.float32)
    img = img * sys._vig
    # en-tête
    coller(img, ENTETE, 0, 0)
    pr = int(W * t / DUREE); img[0:8, :pr] = ROUGE                            # barre de progression
    pulse = 0.5 + 0.5 * math.sin(t * 6); cv2.circle(img, (70, 232), int(10 + 3 * pulse), ROUGE, -1, cv2.LINE_AA)
    # titre unique 3D (pivote depuis la gauche)
    tf = P['titre_fin']
    if t < tf:
        for j, et in enumerate(TITRE):
            a = ease((t - 0.15 * j) / 0.5) - ease((t - tf + 0.45) / 0.45)
            if a <= 0.01: continue
            w3 = persp(et, ry=-75 * (1 - a), sc=1)
            coller(img, w3, int(60 - 140 * (1 - a)), 1210 + j * 80)
    # chiffres / jauge en 3D
    for c in CH:
        c0, cd = c['t'], c.get('duree', 1.7)
        if not (c0 <= t < c0 + cd): continue
        q = (t - c0); ap = back(q / 0.45); sortie = ease((t - (c0 + cd - 0.3)) / 0.3)
        if c.get('jauge'):
            v = c['jauge'] * ease_io(q / 1.1)
            cal = jauge(v); cal = persp(cal, rx=60 * (1 - ap) + 70 * sortie, sc=0.6 + 0.4 * min(ap, 1))
            coller(img, cal, (W - cal.shape[1]) // 2, 520)
        else:
            val = c.get('valeur', 0) * ease_io(q / 0.9)
            cal = calque_chiffre(c, val)
            cal = persp(cal, rx=-70 * (1 - min(ap, 1.2)) + 80 * sortie, sc=0.7 + 0.3 * min(ap, 1.1))
            if c.get('icone') == 'alerte':
                pass
            coller(img, cal, 0, 560)
    # sous-titres (pas pendant le titre)
    if t >= tf:
        for a0, a1, st in ST:
            if a0 <= t < a1:
                p = ease((t - a0) / 0.1); sc = 0.88 + 0.12 * p
                s2 = cv2.resize(st, (int(st.shape[1] * sc), int(st.shape[0] * sc)))
                coller(img, s2, (W - s2.shape[1]) // 2, 1296 - s2.shape[0] // 2); break
    out = np.clip(img, 0, 255).astype(np.uint8)
    if APERCU:
        Image.fromarray(out).save(f'/workspace/news2/ap-{t:05.2f}.jpg', quality=85)
    else:
        ecr.stdin.write(out.tobytes())
        if i % 300 == 0: print('PROGRESSION', int(100 * i / N), flush=True)
lect.kill()
if APERCU: sys.exit()
ecr.stdin.close(); ecr.wait()

# ---------------------------------------------------------------- son
S = '/workspace/pack/sons/'
SON_T = {'cube': 'whoosh-grave', 'flip': 'swish', 'whipG': 'whoosh-court', 'whipD': 'whoosh-court', 'zoom': 'whoosh-inverse', 'glitch': 'glitch-court'}
entrees = ['-i', '/tmp/news_video.mp4', '-i', P['voix'], '-stream_loop', '-1', '-i', P['musique'], '-i', S + 'impact-cinema.mp3']
filt = ['[1:a]volume=1.0[v]', f'[2:a]atrim=0:{DUREE},volume=0.13,afade=t=out:st={DUREE - 2}:d=2[m]', '[3:a]volume=0.55[i0]']
mix = ['[v]', '[m]', '[i0]']; n = 4
def sfx(nom, t, vol):
    global n
    entrees.extend(['-i', S + nom + '.mp3']); ms = max(0, int(t * 1000))
    filt.append(f'[{n}:a]adelay={ms}|{ms},volume={vol}[s{n}]'); mix.append(f'[s{n}]'); n += 1
for c, ty in TRANS.items(): sfx(SON_T[ty], c - 0.1, 0.35)
for c in CH: sfx('impact-metal' if c.get('jauge') else 'coup-poing', c['t'], 0.55); sfx('hud-bips', c['t'] + 0.1, 0.3)
for c in CH:
    if c.get('jauge'): sfx('riser-court', c['t'] + 0.1, 0.3)
filt.append(''.join(mix) + f'amix=inputs={len(mix)}:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]')
subprocess.run(['ffmpeg', '-v', 'error', '-y', *entrees, '-filter_complex', ';'.join(filt), '-map', '0:v', '-map', '[a]',
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-t', str(DUREE), OUT], check=True)
print('ok', OUT)
