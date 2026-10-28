# Arcane Hands

Efek sihir fantasy real-time yang dikendalikan gerakan tangan lewat webcam.
Python 3.11 (64-bit), Windows 11. Pygame untuk render 2D, MediaPipe untuk hand tracking, NumPy untuk partikel.

## Instalasi

```powershell
py -3.11 --version
cd arcane-hands
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Jika PowerShell menolak mengaktifkan venv:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
Alternatif satu perintah: `.\scripts\run.ps1` (membuat `.venv` otomatis).

Opsi: `python main.py --quality MEDIUM --camera-index 1 --no-camera --fullscreen`

Versi di `requirements.txt` belum diuji bersama di laptop target. MediaPipe harus
`0.10.14` karena versi yang lebih baru menghapus API `solutions` yang dipakai
`camera/hand_tracker.py`. Jika `pip` melaporkan konflik, kirimkan pesan errornya.

## Tes

Tes tidak memerlukan webcam atau pygame:

```powershell
python -m unittest discover -s tests -t .
```

## Kontrol

| Tombol | Fungsi |
|---|---|
| 1-4 / Tab | Pilih elemen Fire, Ice, Lightning, Arcane |
| Z X C V | Uji spell ke-1 sampai ke-4 pada elemen aktif (tanpa tangan) |
| F1 F2 F3 | Kualitas LOW, MEDIUM, HIGH |
| A | Adaptive quality on/off |
| [ ] | Sensitivitas |
| - = | Ukuran efek |
| F / F11 | Fullscreen |
| B | Webcam on/off |
| J | Tampilkan titik landmark |
| Backspace | Hapus semua efek |
| H | Bantuan |
| Esc | Keluar |

Panel HUD juga bisa diklik dengan mouse.

## Gestur per spell

Satu gestur hanya memicu satu spell pada elemen aktif.

| Elemen | Spell | Gestur |
|---|---|---|
| Fire | Fireball | Kepalkan tangan (charge), lalu dorong |
| Fire | Flame Burst | Telapak terbuka (charge), lalu dorong |
| Fire | Inferno | Dua tangan didekatkan, lalu direntangkan |
| Ice | Frost Nova | Telapak terbuka (charge), lalu kepalkan |
| Ice | Ice Shards | Cubit ibu jari + telunjuk, lalu dorong |
| Ice | Blizzard | Menunjuk atau mengepal sambil menggerakkan tangan melingkar |
| Lightning | Lightning Bolt | Tunjuk dengan telunjuk ke arah tujuan |
| Lightning | Thunder Storm | Angkat kedua telapak terbuka ke bagian atas layar |
| Arcane | Arcane Orb | Cubit (bola membesar), lepas cubitan untuk meledak |
| Arcane | Magic Shield | Tahan satu telapak terbuka |
| Arcane | Energy Beam | Dua tangan didekatkan, lalu direntangkan |
| Arcane | Arcane Vortex | Menunjuk atau mengepal sambil menggerakkan tangan melingkar |

Tahan gestur lebih lama agar energi (ukuran efek) bertambah. Jika tangan hilang dari
kamera, tidak ada spell baru yang dimulai dan efek yang sudah dilepas selesai sendiri.

## Performa

Preset awal LOW (sekitar 450 partikel, render internal 960x540, kamera 640x480, target 30 FPS).
Semua angka ada di `arcane_hands/config.py`. Adaptive quality menurunkan preset bila FPS
konsisten di bawah target dan menaikkannya hanya setelah stabil cukup lama; pilihan manual
lewat HUD atau F1-F3 menimpa keputusannya. Angka FPS belum diukur di laptop target.

## Troubleshooting

- **Webcam: unavailable**: tutup aplikasi lain yang memakai kamera, coba `--camera-index 1`,
  atau ubah `backend` di `CameraConfig` ke `"msmf"`. Cek juga izin kamera di Windows Settings.
- **Tracking: unavailable**: MediaPipe belum terpasang atau versinya bukan `0.10.14`.
  Spell masih bisa diuji dengan Z X C V.
- **FPS rendah**: pilih LOW, matikan feed webcam dengan B, atau turunkan `render_size` di `config.py`.
- **Gestur tidak terdeteksi**: nyalakan landmark dengan J, pastikan tangan terang dan seluruh telapak
  terlihat. Naikkan sensitivitas dengan `]` bila dorongan tidak terbaca.

## Struktur

```
main.py                    entry point
arcane_hands/app.py        siklus hidup, loop utama
arcane_hands/config.py     konfigurasi dan preset kualitas
arcane_hands/camera/       webcam (thread, frame terbaru saja) dan MediaPipe
arcane_hands/gestures/     landmark -> gestur (tanpa dependensi pygame/mediapipe)
arcane_hands/spells/       katalog spell dan state machine
arcane_hands/graphics/     partikel (pool NumPy), sprite cache, renderer, efek per elemen
arcane_hands/interface/    HUD dan kontrol
tests/                     tes gestur, batas partikel, dan siklus spell
```
