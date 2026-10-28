import time
import cv2

VARIANTS = [
    ("dshow", cv2.CAP_DSHOW, None),
    ("dshow+MJPG", cv2.CAP_DSHOW, "MJPG"),
    ("msmf", cv2.CAP_MSMF, None),
]

for name, backend, fourcc in VARIANTS:
    print(f"\n== {name} ==", flush=True)
    opened_at = time.time()
    cap = cv2.VideoCapture(0, backend)
    if not cap.isOpened():
        print("tidak bisa dibuka", flush=True)
        continue
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    if fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    levels, failed, shape = [], 0, None
    start = time.time()
    print(f"dibuka dalam {start - opened_at:.1f} detik; lihat jendela preview 6 detik", flush=True)
    while time.time() - start < 6:
        ok, frame = cap.read()
        if not ok:
            failed += 1
            time.sleep(0.02)
            continue
        shape = frame.shape
        levels.append(float(frame.mean()))
        cv2.imshow(name, frame)
        cv2.waitKey(1)
    cap.release()
    cv2.destroyAllWindows()
    if levels:
        dark = sum(1 for v in levels if v < 10)
        print(f"ukuran={shape} frame={len(levels)} (sekitar {len(levels) / 6:.0f}/detik) gagal={failed}")
        print(f"kecerahan min={min(levels):.0f} rata-rata={sum(levels) / len(levels):.0f} maks={max(levels):.0f} frame_gelap={dark}", flush=True)
    else:
        print(f"tidak ada frame, gagal={failed}", flush=True)