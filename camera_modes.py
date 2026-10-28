import time
import cv2

MODES = [(320, 240, None), (640, 480, None), (640, 360, None), (1280, 720, None),
         (320, 240, "MJPG"), (640, 480, "MJPG"), (1280, 720, "MJPG")]

for width, height, fourcc in MODES:
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("kamera tidak bisa dibuka")
        break
    if fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    warm = time.time()
    while time.time() - warm < 1.5:      # buang frame awal saat kamera menyesuaikan diri
        cap.read()
    count, start = 0, time.time()
    while time.time() - start < 4:
        ok, _ = cap.read()
        count += ok
    got = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    cap.release()
    print(f"minta {width}x{height} {fourcc or 'default'} -> dapat {got[0]}x{got[1]}: {count / 4:.1f} fps", flush=True)