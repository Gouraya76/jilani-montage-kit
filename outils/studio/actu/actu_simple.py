#!/usr/bin/env python3
"""Habillage actu « carte » 9:16 : fond sombre, vidéo dans une carte arrondie, en-tête date/lieu, logo, titre unique, sous-titres."""
import json, subprocess, sys
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

P = json.load(open(sys.argv[1])); OUT = sys.argv[2]
W, H, FPS = 1080, 1920, 30
POL = '/workspace/pack/polices/Montserrat-{}.ttf'
def font(p, s): return ImageFont.truetype(POL.format(p), s)
ROUGE = (226, 30, 38); BLANC = (255, 255, 255)
DUREE = P['duree']; N = int(DUREE * FPS); COUPES = P['coupes']
MOTS = json.load(open(P['mots']))
CX, CY, CW, CH = 0, 0, 1080, 1920                     # carte vidéo
def ease(x): x = min(max(x, 0), 1); return 1 - (1 - x) ** 3

# ---------- fond sombre fixe (dégradé + grille discrète)
a = np.zeros((H, W, 4), np.uint8); g_ = np.clip(1 - np.arange(H) / 420, 0, 1) ** 1.5
a[..., 3] = (150 * g_)[:, None]
FOND = Image.fromarray(a, 'RGBA')            # léger dégradé sombre en haut pour lire l'en-tête

# en-tête : point rouge + date, lieu en gris ; logo à droite
d = ImageDraw.Draw(FOND)
d.ellipse([60, 222, 80, 242], fill=ROUGE)
d.text((96, 214), P['date'], font=font(800, 32), fill=BLANC)
d.text((96, 256), P['lieu'], font=font(800, 26), fill=(205, 208, 214))
LOGO = Image.open(P['logo']).convert('RGBA'); LOGO = LOGO.resize((205, int(205 * LOGO.height / LOGO.width)), Image.LANCZOS)
FOND.alpha_composite(LOGO, (W - 53 - LOGO.width, 236 - LOGO.height // 2))

# ---------- titre unique : étiquettes blanches à barre rouge
FT = font(900, 46)
def etiquette(txt):
    b = FT.getbbox(txt); w, h = b[2] - b[0] + 56, 74
    im = Image.new('RGBA', (w, h), BLANC + (255,)); dd = ImageDraw.Draw(im)
    dd.rectangle([0, 0, 10, h], fill=ROUGE); dd.text((32 - b[0], (h - (b[3] + b[1])) // 2), txt, font=FT, fill=(12, 12, 14)); return im
TITRE = [etiquette(l) for l in P['titre']]

# ---------- sous-titres : groupes de mots, majuscules
GROUPES, g = [], []
for m in MOTS:
    g.append(m)
    if len(g) >= 3 or m['m'][-1] in '.,?!:…': GROUPES.append(g); g = []
if g: GROUPES.append(g)
FST = font(900, 70)
def sous_titre(gr):
    txt = ' '.join(m['m'] for m in gr).upper(); lignes, cur = [], ''
    for w_ in txt.split():
        t = (cur + ' ' + w_).strip()
        if FST.getlength(t) > W - 120 and cur: lignes.append(cur); cur = w_
        else: cur = t
    lignes.append(cur)
    hl = 82; im = Image.new('RGBA', (W, hl * len(lignes) + 30), (0, 0, 0, 0)); dd = ImageDraw.Draw(im)
    for k, l in enumerate(lignes):
        x = (W - FST.getlength(l)) / 2; yy = 12 + k * hl
        dd.text((x + 5, yy + 6), l, font=FST, fill=(0, 0, 0, 230))           # ombre portée nette
        dd.text((x, yy), l, font=FST, fill=BLANC, stroke_width=3, stroke_fill=(0, 0, 0))
    return im
ST = [(gr[0]['debut'], (GROUPES[i + 1][0]['debut'] if i + 1 < len(GROUPES) else gr[-1]['fin'] + 0.8), sous_titre(gr)) for i, gr in enumerate(GROUPES)]

# ---------- rendu
lect = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-i', P['fond'], '-vf', f'fps={FPS},scale={CW}:{CH}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
ecr = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                        '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-pix_fmt', 'yuv420p', '/tmp/news_video.mp4'], stdin=subprocess.PIPE)
bords = [0] + COUPES; prev = None
for i in range(N):
    t = i / FPS
    raw = lect.stdout.read(CW * CH * 3)
    fr = np.frombuffer(raw, np.uint8).reshape(CH, CW, 3) if len(raw) == CW * CH * 3 else prev
    prev = fr
    k = max(j for j, c in enumerate(bords) if c <= t); t0 = bords[k]; t1 = bords[k + 1] if k + 1 < len(bords) else DUREE
    u = (t - t0) / max(t1 - t0, 0.1)
    z = 1.0 + 0.06 * u + 0.10 * max(0, 1 - (t - t0) / 0.25) * (k > 0)
    sw, sh = int(CW / z), int(CH / z); ox, oy = (CW - sw) // 2, (CH - sh) // 2
    fr = cv2.resize(fr[oy:oy + sh, ox:ox + sw], (CW, CH), interpolation=cv2.INTER_LINEAR)
    carte = Image.fromarray(fr).convert('RGBA')
    fl = max([max(0, 1 - abs(t - c) / 0.09) for c in COUPES] + [0])
    if fl > 0: carte = Image.blend(carte, Image.new('RGBA', (CW, CH), (255, 255, 255, 255)), 0.8 * fl)
    im = carte; im.alpha_composite(FOND)
    # titre unique (0 → titre_fin)
    tf = P['titre_fin']
    if t < tf:
        for j, et in enumerate(TITRE):
            a = ease((t - 0.15 * j) / 0.4) - ease((t - tf + 0.4) / 0.4)
            im.alpha_composite(et, (int(60 - (et.width + 80) * (1 - a)), 1210 + j * 80))
    # sous-titres (sur la bande basse de la carte)
    for a0, a1, st in ST:
        if a0 <= t < a1 and t >= tf:
            p = ease((t - a0) / 0.1); sc = 0.88 + 0.12 * p
            s2 = st.resize((int(st.width * sc), int(st.height * sc)), Image.LANCZOS)
            yb = 1296
            im.alpha_composite(s2, ((W - s2.width) // 2, yb - s2.height // 2)); break
    ecr.stdin.write(np.asarray(im.convert('RGB')).tobytes())
    if i % 300 == 0: print('PROGRESSION', int(100 * i / N), flush=True)
ecr.stdin.close(); ecr.wait(); lect.kill()

# ---------- son
S = '/workspace/pack/sons/'
entrees = ['-i', '/tmp/news_video.mp4', '-i', P['voix'], '-stream_loop', '-1', '-i', P['musique'], '-i', S + 'impact-cinema.mp3']
filt = ['[1:a]volume=1.0[v]', f'[2:a]atrim=0:{DUREE},volume=0.12,afade=t=out:st={DUREE - 2}:d=2[m]', '[3:a]volume=0.5[i0]']
mix = ['[v]', '[m]', '[i0]']
for j, c in enumerate(COUPES):
    entrees += ['-i', S + 'whoosh-court.mp3']; n = 4 + j
    filt.append(f'[{n}:a]adelay={int((c - 0.15) * 1000)}|{int((c - 0.15) * 1000)},volume=0.4[w{j}]'); mix.append(f'[w{j}]')
filt.append(''.join(mix) + f'amix=inputs={len(mix)}:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]')
subprocess.run(['ffmpeg', '-v', 'error', '-y', *entrees, '-filter_complex', ';'.join(filt), '-map', '0:v', '-map', '[a]',
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-t', str(DUREE), OUT], check=True)
print('ok', OUT)
