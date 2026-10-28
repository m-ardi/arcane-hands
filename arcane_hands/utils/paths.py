"""Lokasi folder proyek, dihitung dari lokasi file ini, bukan dari working directory."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def asset_dir(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath("assets", *parts)
