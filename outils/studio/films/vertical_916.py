import cv2, numpy as np, subprocess, sys
src, out = sys.argv[1], sys.argv[2]
cap = cv2.VideoCapture(src); fps = cap.get(5); W = int(cap.get(3)); H = 192; Y0 = 30
cw = int(H * 9 / 16) // 2 * 2
frames = []; xs = []; prev = None
while True:
    ok, f = cap.read()
    if not ok: break
    f = f[Y0:Y0 + H, 46:46 + 420]; frames.append(f)
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    cut = prev is not None and np.mean(cv2.absdiff(g, prev)) > 40
    if True:
        sal = cv2.Sobel(g, cv2.CV_32F, 1, 0) ** 2 + cv2.Sobel(g, cv2.CV_32F, 0, 1) ** 2
        col = sal.sum(0); cx = float((col * np.arange(len(col))).sum() / (col.sum() + 1e-6)) if col.sum() else 210
    xs.append((cx, cut)); prev = g
# lissage, avec remise à zéro aux coupes
sm = []; cur = None
for cx, cut in xs:
    cur = cx if cur is None or cut else cur * 0.92 + cx * 0.08; sm.append(cur)
Wc = frames[0].shape[1]
p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{cw}x{H}', '-r', str(fps), '-i', '-',
    '-vf', 'scale=1080:1920:flags=lanczos,unsharp=7:7:0.9,hqdn3d=1.5:1.5:3:3', '-c:v', 'libx264', '-crf', '16', '-preset', 'fast', '-pix_fmt', 'yuv420p', out], stdin=subprocess.PIPE)
for f, cx in zip(frames, sm):
    x0 = int(min(max(cx - cw / 2, 0), Wc - cw)); p.stdin.write(np.ascontiguousarray(f[:, x0:x0 + cw]).tobytes())
p.stdin.close(); p.wait(); print('ok', cw, H)
