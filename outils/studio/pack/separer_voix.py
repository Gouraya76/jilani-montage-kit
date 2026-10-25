#!/usr/bin/env python3
"""Sépare la voix et la musique d'une vidéo (modèle MDX-Net « Kim Vocal 2 », ONNX, sans carte graphique).

Pourquoi : quand on ajoute une nouvelle musique, celle de la vidéo d'origine reste sous la voix et les deux se mélangent.
On garde donc la voix seule (voix.wav), et on peut réutiliser la musique d'origine seule (musique.wav) si on la préfère.

Utilisation :
    python3 separer_voix.py source.mp4 dossier_sortie/
Écrit voix.wav, musique.wav et analyse.json : {"musique_presente": bool, "part_musique": 0..1, "voix_presente": bool}.
Le modèle (65 Mo) est téléchargé une fois depuis huggingface.co dans ~/.cache/jm/.
"""
import json, os, subprocess, sys, urllib.request
import numpy as np

URL = 'https://huggingface.co/seanghay/uvr_models/resolve/main/Kim_Vocal_2.onnx'
SR, N_FFT, HOP, DIM_F, DIM_T, COMPENSE = 44100, 7680, 1024, 3072, 256, 1.009


def modele():
    d = os.path.expanduser('~/.cache/jm'); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, 'Kim_Vocal_2.onnx')
    if not os.path.exists(p) or os.path.getsize(p) < 60_000_000:
        urllib.request.urlretrieve(URL, p + '.tmp'); os.replace(p + '.tmp', p)
    return p


def lire(src):
    b = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', src, '-vn', '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-'],
                       capture_output=True, check=True).stdout
    return np.frombuffer(b, np.float32).reshape(-1, 2).T.copy()


def ecrire(path, a):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', '-', '-c:a', 'pcm_s16le', path],
                   input=np.ascontiguousarray(a.T, np.float32).tobytes(), check=True)


FEN = np.hanning(N_FFT + 1)[:-1].astype(np.float32)


def stft(x):  # x : (2, n) déjà complété ; renvoie (2, bins, trames)
    n = 1 + (x.shape[1] - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    return np.stack([np.fft.rfft(c[idx] * FEN, axis=1).T for c in x])


def istft(X, longueur):
    n = X.shape[2]; out = np.zeros((2, N_FFT + HOP * (n - 1)), np.float32); norme = np.zeros(out.shape[1], np.float32)
    for k in range(n):
        s = k * HOP
        out[:, s:s + N_FFT] += np.fft.irfft(X[:, :, k], n=N_FFT, axis=1) * FEN
        norme[s:s + N_FFT] += FEN ** 2
    out /= np.maximum(norme, 1e-8)
    return out[:, :longueur]


def separer(audio):
    import onnxruntime as ort
    sess = ort.InferenceSession(modele(), providers=['CPUExecutionProvider'])
    taille = HOP * (DIM_T - 1)                     # échantillons utiles par morceau
    marge = N_FFT // 2
    n = audio.shape[1]
    pad = (taille - n % taille) % taille
    x = np.pad(audio, ((0, 0), (marge, pad + marge)))
    voix = np.zeros_like(audio[:, :n + pad])
    for i in range(0, n + pad, taille):
        morceau = x[:, i:i + taille + 2 * marge]
        if morceau.shape[1] < taille + 2 * marge: morceau = np.pad(morceau, ((0, 0), (0, taille + 2 * marge - morceau.shape[1])))
        X = stft(morceau)[:, :DIM_F, :DIM_T]
        if X.shape[2] < DIM_T: X = np.pad(X, ((0, 0), (0, 0), (0, DIM_T - X.shape[2])))
        entree = np.concatenate([X.real, X.imag])[None].astype(np.float32)   # (1, 4, 3072, 256)
        y = sess.run(None, {'input': entree})[0][0]
        Y = np.zeros((2, N_FFT // 2 + 1, DIM_T), np.complex64)
        Y[:, :DIM_F] = y[:2] + 1j * y[2:]
        v = istft(Y, taille + 2 * marge)[:, marge:marge + taille]
        voix[:, i:i + taille] = v[:, :voix.shape[1] - i]
    voix = voix[:, :n] * COMPENSE
    return voix, audio - voix


def rms(a):
    return float(np.sqrt(np.mean(a.astype(np.float64) ** 2)) + 1e-9)


if __name__ == '__main__':
    src, dossier = sys.argv[1], sys.argv[2]
    os.makedirs(dossier, exist_ok=True)
    audio = lire(src)
    voix, musique = separer(audio)
    ecrire(os.path.join(dossier, 'voix.wav'), voix)
    ecrire(os.path.join(dossier, 'musique.wav'), musique)
    rv, rm = rms(voix), rms(musique)
    part = rm / (rv + rm)
    infos = {'musique_presente': bool(part > 0.22 and rm > 0.01), 'part_musique': round(part, 2), 'voix_presente': bool(rv > 0.008)}
    json.dump(infos, open(os.path.join(dossier, 'analyse.json'), 'w'))
    print(json.dumps(infos))
