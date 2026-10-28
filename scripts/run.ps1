# Menjalankan Arcane Hands dari folder proyek, dengan membuat .venv dan memasang dependensi bila belum ada.
param(
    [ValidateSet("LOW", "MEDIUM", "HIGH")][string]$Quality = "LOW",
    [switch]$NoCamera
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Error "Python 3.11 tidak ditemukan. Cek dengan: py -3.11 --version"; exit 1 }
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Write-Error "Instalasi dependensi gagal"; exit 1 }
}

$args = @("main.py", "--quality", $Quality)
if ($NoCamera) { $args += "--no-camera" }
& .\.venv\Scripts\python.exe @args
