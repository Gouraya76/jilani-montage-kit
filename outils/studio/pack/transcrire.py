#!/usr/bin/env python3
"""Transcription mot par mot (faster-whisper) -> JSON pour jm_montage.py.

    python3 transcrire.py video.mp4 mots.json [modele]     (modele : small par défaut ; base si la machine est lente)

Écrit [{"m": "mot", "debut": s, "fin": s}, ...] et affiche le texte avec les heures.
"""
import json, subprocess, sys
import numpy as np

src, out = sys.argv[1], sys.argv[2]
nom = sys.argv[3] if len(sys.argv) > 3 else 'small'
try:
    from faster_whisper import WhisperModel
except ImportError:
    sys.exit("faster-whisper n'est pas installé : pip install faster-whisper")
modele = WhisperModel(nom, device='cpu', compute_type='int8')
# son décodé par ffmpeg (16 kHz mono) : évite les soucis de version de la bibliothèque « av »
audio = np.frombuffer(subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', src, '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'],
                                     capture_output=True, check=True).stdout, np.float32)
segments, info = modele.transcribe(audio, word_timestamps=True, vad_filter=True, beam_size=5)
mots = []
for seg in segments:
    print(f"[{seg.start:6.2f}-{seg.end:6.2f}] {seg.text.strip()}", flush=True)
    for w in seg.words or []:
        t = w.word.strip()
        if not t: continue
        if mots and t[0] in "'’":                  # « n » + « 'ont » -> « n'ont » (élisions françaises)
            mots[-1]['m'] += t.replace('’', "'"); mots[-1]['fin'] = round(w.end, 3)
        else:
            mots.append({'m': t, 'debut': round(w.start, 3), 'fin': round(w.end, 3)})
json.dump(mots, open(out, 'w', encoding='utf-8'), ensure_ascii=False)
print(f"langue : {info.language} ({info.language_probability:.2f}) ; {len(mots)} mots -> {out}")
