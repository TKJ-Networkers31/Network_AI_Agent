<#
download_kokoro_model.ps1

Download 2 file model Kokoro (TTS) yang dibutuhkan
agents/yuki/tts_engine.py: kokoro-v0_19.onnx dan voices.bin.

CARA PAKAI:
    cd AIRA_ECOSYSTEM
    powershell -ExecutionPolicy Bypass -File scripts\download_kokoro_model.ps1

File akan otomatis ditaruh di AIRA_ECOSYSTEM/models/kokoro/ (dibuat
kalau belum ada). Total unduhan sekitar ~310MB, pastikan koneksi
internet stabil - kalau proses terputus, hapus file yang tidak
lengkap lalu jalankan ulang script ini (file yang sudah lengkap
otomatis dilewati).
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AiraDir = Split-Path -Parent $ScriptDir
$ModelDir = Join-Path $AiraDir "models\kokoro"

New-Item -ItemType Directory -Path $ModelDir -Force | Out-Null

$Files = @{
    "kokoro-v0_19.onnx" = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx"
    "voices.bin"        = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin"
}

Write-Host "=== Download model Kokoro ===" -ForegroundColor Cyan
Write-Host "Target folder: $ModelDir"
Write-Host ""

foreach ($name in $Files.Keys) {

    $dest = Join-Path $ModelDir $name

    if (Test-Path $dest) {
        Write-Host "Sudah ada, dilewati: $name" -ForegroundColor DarkGray
        continue
    }

    Write-Host "Mengunduh $name ..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $Files[$name] -OutFile $dest
    Write-Host "  -> selesai: $dest" -ForegroundColor Green
}

Write-Host ""
Write-Host "Selesai. Restart backend (uvicorn api.main:app --reload) supaya model dimuat ulang." -ForegroundColor Green