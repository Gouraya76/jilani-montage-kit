#!/usr/bin/env python3
"""Habillage « journal télé » 9:16 : fond vidéo + bandeaux + logo + sous-titres + son."""
import json, math, subprocess, sys
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

P = json.load(open(sys.argv[1])); OUT = sys.argv[2]
W, H, FPS = 1080, 1920, 30
POL = '/workspace/pack/polices/Montserrat-{}.ttf'
def font(p, s): return ImageFont.truetype(POL.format(p), s)
ROUGE = (214, 18, 28); BLANC = (255, 255, 255)
DUREE = P['duree']; N = int(DUREE * FPS)
COUPES = P['coupes']
MOTS = json.load(open(P['mots']))

def ease(x): x = min(max(x, 0), 1); return 1 - (1 - x) ** 3

# ---------- éléments fixes
def boite_txt(txt, f, fg, bg, padx=18, pady=8):
    b = f.getbbox(txt); w, h = b[2] - b[0] + 2 * padx, f.size + 2 * pady
    im = Image.new('RGBA', (w, h), bg + (255,)); d = ImageDraw.Draw(im)
    d.text((padx - b[0], pady + (f.size - (b[3] + b[1])) // 2 + 2), txt, font=f, fill=fg); return im
LIEU = boite_txt(P['lieu'], font(900, 15), BLANC, ROUGE, 7, 3)
DATE = boite_txt(P['date'], font(900, 15), ROUGE, BLANC, 7, 3)
LOGO = Image.open(P['logo']).convert('RGBA'); LOGO = LOGO.resize((125, int(125 * LOGO.height / LOGO.width)), Image.LANCZOS)

def bandeau(lignes):
    f = font(900, 64); ims = [boite_txt(l, f, ROUGE, BLANC, 26, 10) for l in lignes]
    wmax = max(i.width for i in ims); h = sum(i.height for i in ims)
    im = Image.new('RGBA', (W, h + 60), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    y = 30
    for k, i in enumerate(ims):
        x = 70 if k != 1 else 90               # léger décalage comme sur le modèle
        im.alpha_composite(i, (x, y)); y += i.height
    # crochet rouge à gauche
    d.rectangle([0, 0, 22, h + 60], fill=ROUGE); d.rectangle([0, 0, 150, 22], fill=ROUGE); d.rectangle([0, h + 38, 150, h + 60], fill=ROUGE)
    return im
BANDEAUX = [(b['t'], bandeau(b['lignes'])) for b in P['bandeaux']]

# ---------- sous-titres : groupes de mots
GROUPES = []; g = []
for m in MOTS:
    g.append(m)
    if len(g) >= 4 or m['m'][-1] in '.,?!:…':
        GROUPES.append(g); g = []
if g: GROUPES.append(g)
FST = font(800, 76)
def sous_titre(gr):
    txt = ' '.join(m['m'] for m in gr)
    mots = txt.split(); lignes = []; cur = ''
    for w_ in mots:
        t = (cur + ' ' + w_).strip()
        if FST.getlength(t) > W - 140 and cur: lignes.append(cur); cur = w_
        else: cur = t
    lignes.append(cur)
    hl = FST.size + 14; im = Image.new('RGBA', (W, hl * len(lignes) + 20), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for k, l in enumerate(lignes):
        x = (W - FST.getlength(l)) / 2; y = 10 + k * hl
        d.text((x, y), l, font=FST, fill=BLANC, stroke_width=7, stroke_fill=(0, 0, 0))
    return im
ST = [(gr[0]['debut'], (GROUPES[i + 1][0]['debut'] if i + 1 < len(GROUPES) else gr[-1]['fin'] + 0.6), sous_titre(gr)) for i, gr in enumerate(GROUPES)]

# ---------- rendu
lect = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-i', P['fond'], '-vf', f'fps={FPS},scale={W}:{H}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
ecr = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                        '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-pix_fmt', 'yuv420p', '/tmp/news_video.mp4'], stdin=subprocess.PIPE)
bords = [0] + COUPES
prev = None
for i in range(N):
    t = i / FPS
    raw = lect.stdout.read(W * H * 3)
    fr = np.frombuffer(raw, np.uint8).reshape(H, W, 3) if len(raw) == W * H * 3 else prev
    prev = fr
    k = max(j for j, c in enumerate(bords) if c <= t); t0 = bords[k]; t1 = bords[k + 1] if k + 1 < len(bords) else DUREE
    u = (t - t0) / max(t1 - t0, 0.1)
    z = 1.0 + 0.07 * u + 0.12 * max(0, 1 - (t - t0) / 0.25) * (k > 0)       # dérive lente + punch à la coupe
    if z > 1.001:
        sw, sh = int(W / z), int(H / z); x0, y0 = (W - sw) // 2, (H - sh) // 2
        fr = cv2.resize(fr[y0:y0 + sh, x0:x0 + sw], (W, H), interpolation=cv2.INTER_LINEAR)
    im = Image.fromarray(fr).convert('RGBA')
    # flash blanc aux coupes
    fl = max([max(0, 1 - abs(t - c) / 0.09) for c in COUPES] + [0])
    if fl > 0: im = Image.blend(im, Image.new('RGBA', (W, H), (255, 255, 255, 255)), 0.85 * fl)
    # bas sombre pour la lisibilité
    # en-tête lieu / date
    a = ease((t - 0.2) / 0.5); xo = int(-500 * (1 - a))
    im.alpha_composite(LIEU, (50 + xo, 170)); im.alpha_composite(DATE, (58 + xo, 170 + LIEU.height + 3))
    im.alpha_composite(LOGO, (W - LOGO.width - 50, 170 + (LIEU.height + DATE.height + 3 - LOGO.height) // 2))
    # bandeau titre : entrée par la gauche à chaque changement
    if t < P['titre_fin']:                       # un seul titre, au début
        bd = BANDEAUX[0][1]
        e = ease(t / 0.45) - ease((t - P['titre_fin'] + 0.45) / 0.45); x = int(-W * (1 - e))
        im.alpha_composite(bd, (x, 1330))
    # sous-titres
    for a0, a1, s in ST:
        if a0 <= t < a1:
            p = ease((t - a0) / 0.12); sc = 0.85 + 0.15 * p
            s2 = s.resize((int(s.width * sc), int(s.height * sc)), Image.LANCZOS)
            im.alpha_composite(s2, ((W - s2.width) // 2, 990 - s2.height // 2)); break
    ecr.stdin.write(np.asarray(im.convert('RGB')).tobytes())
    if i % 300 == 0: print('PROGRESSION', int(100 * i / N), flush=True)
ecr.stdin.close(); ecr.wait()

# ---------- son : voix + musique basse + bruitages aux coupes
S = '/workspace/pack/sons/'
entrees = ['-i', '/tmp/news_video.mp4', '-i', P['voix'], '-stream_loop', '-1', '-i', P['musique'], '-i', S + 'impact-cinema.mp3']
filt = [f'[1:a]volume=1.0[v]', f'[2:a]atrim=0:{DUREE},volume=0.12,afade=t=out:st={DUREE - 2}:d=2[m]', '[3:a]volume=0.5[i0]']
mix = ['[v]', '[m]', '[i0]']
for j, c in enumerate(COUPES):
    entrees += ['-i', S + 'whoosh-court.mp3']; n = 4 + j
    filt.append(f'[{n}:a]adelay={int((c - 0.15) * 1000)}|{int((c - 0.15) * 1000)},volume=0.45[w{j}]'); mix.append(f'[w{j}]')
filt.append(''.join(mix) + f'amix=inputs={len(mix)}:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]')
subprocess.run(['ffmpeg', '-v', 'error', '-y', *entrees, '-filter_complex', ';'.join(filt), '-map', '0:v', '-map', '[a]',
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-t', str(DUREE), OUT], check=True)
print('ok', OUT)
