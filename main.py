import argparse

from arcane_hands.app import build_config, run
from arcane_hands.config import QUALITY_ORDER


def main() -> None:
    parser = argparse.ArgumentParser(description="Arcane Hands: efek sihir dengan gerakan tangan")
    parser.add_argument("--quality", choices=QUALITY_ORDER, help="preset kualitas awal (default LOW)")
    parser.add_argument("--camera-index", type=int, help="indeks webcam (default 0)")
    parser.add_argument("--no-camera", action="store_true", help="mulai tanpa webcam, spell diuji dengan keyboard")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--debug", action="store_true", help="cetak ringkasan FPS, kamera, dan waktu deteksi tiap detik")
    args = parser.parse_args()
    run(build_config(args.quality, args.camera_index, args.no_camera, args.fullscreen, args.debug))


if __name__ == "__main__":
    main()
