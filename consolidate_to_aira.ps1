<#
consolidate_to_aira.ps1

TUJUAN:
Menggabungkan root project lama (agent/, tools/, backend/, scripts/) ke
dalam AIRA_ECOSYSTEM/ sehingga hanya ada SATU kode aktif, sesuai
MIGRATION_PLAN.md.

CARA PAKAI:
1. Tutup semua proses python/uvicorn yang sedang jalan (agent.main,
   uvicorn backend.main:app, dll) - supaya tidak ada file yang lagi
   dipakai/lock saat dipindah.
2. Buka PowerShell di root project (D:\data\agent_ai\).
3. Jalankan:
       powershell -ExecutionPolicy Bypass -File consolidate_to_aira.ps1
4. Baca ringkasan di akhir, lalu jalankan test di bagian "Testing
   setelah migrasi" di bawah script ini.

APA YANG DILAKUKAN SCRIPT INI:
- Membuat folder backup "_legacy_backup_<timestamp>/" berisi SALINAN
  utuh agent/, tools/, backend/, scripts/ SEBELUM dihapus - jadi kalau
  ada yang salah, tidak ada data yang benar-benar hilang.
- Memindahkan database lama (data/long_term_memory.db,
  data/chat_sessions.db) ke AIRA_ECOSYSTEM/database/ supaya semua
  fakta yang sudah tersimpan (nama Lingga, threshold CPU, dst) TIDAK
  hilang.
- Menghapus folder lama: agent/, tools/, backend/, scripts/ dari root
  (BUKAN dari dalam AIRA_ECOSYSTEM/, itu tetap dipertahankan).
- .env TIDAK dipindah - tetap di root, karena
  agents/rei/provider_client.py sudah otomatis membaca .env dari root
  DAN dari dalam AIRA_ECOSYSTEM/.

APA YANG TIDAK DILAKUKAN (harus manual):
- requirements.txt / requirements-web.txt tetap di root - tidak perlu
  dipindah, cukup dipakai untuk install dependency seperti biasa.
- Kalau kamu punya virtual environment (.venv) di root, itu tetap
  dipakai, tidak perlu bikin baru.
#>

$ErrorActionPreference = "Stop"

$RootDir = Get-Location
$AiraDir = Join-Path $RootDir "AIRA_ECOSYSTEM"

if (-not (Test-Path $AiraDir)) {
    Write-Host "ERROR: Folder AIRA_ECOSYSTEM tidak ditemukan di $RootDir" -ForegroundColor Red
    Write-Host "Pastikan kamu menjalankan script ini dari root project (D:\data\agent_ai\)." -ForegroundColor Red
    exit 1
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $RootDir "_legacy_backup_$Timestamp"

Write-Host "=== KONSOLIDASI PROJECT KE AIRA_ECOSYSTEM ===" -ForegroundColor Cyan
Write-Host "Root project : $RootDir"
Write-Host "Target akhir : $AiraDir"
Write-Host "Backup ke    : $BackupDir"
Write-Host ""

# ------------------------------------------------------------------
# 1. BACKUP folder lama dulu, sebelum apa pun dihapus
# ------------------------------------------------------------------
$FoldersToBackup = @("agent", "tools", "backend", "scripts")

New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

foreach ($folder in $FoldersToBackup) {
    $src = Join-Path $RootDir $folder
    if (Test-Path $src) {
        Write-Host "Backup: $folder -> $BackupDir\$folder"
        Copy-Item -Path $src -Destination (Join-Path $BackupDir $folder) -Recurse -Force
    } else {
        Write-Host "Lewati (tidak ada): $folder" -ForegroundColor DarkGray
    }
}

# ------------------------------------------------------------------
# 2. PINDAHKAN DATABASE LAMA (jangan sampai facts/memory hilang)
# ------------------------------------------------------------------
$OldDataDir = Join-Path $RootDir "data"
$NewDatabaseDir = Join-Path $AiraDir "database"

New-Item -ItemType Directory -Path $NewDatabaseDir -Force | Out-Null

$DbFiles = @("long_term_memory.db", "chat_sessions.db")

foreach ($dbFile in $DbFiles) {
    $src = Join-Path $OldDataDir $dbFile
    $dst = Join-Path $NewDatabaseDir $dbFile

    if (Test-Path $src) {
        if (Test-Path $dst) {
            Write-Host "PERINGATAN: $dbFile sudah ada di database/, backup dulu jadi $dbFile.old" -ForegroundColor Yellow
            Move-Item -Path $dst -Destination "$dst.old" -Force
        }
        Write-Host "Migrasi DB: data\$dbFile -> AIRA_ECOSYSTEM\database\$dbFile"
        Copy-Item -Path $src -Destination $dst -Force
    } else {
        Write-Host "Lewati (tidak ada): data\$dbFile" -ForegroundColor DarkGray
    }
}

# ------------------------------------------------------------------
# 3. HAPUS FOLDER LAMA DARI ROOT (sudah aman, sudah di-backup)
# ------------------------------------------------------------------
foreach ($folder in $FoldersToBackup) {
    $src = Join-Path $RootDir $folder
    if (Test-Path $src) {
        Write-Host "Menghapus: $folder" -ForegroundColor Yellow
        Remove-Item -Path $src -Recurse -Force
    }
}

Write-Host ""
Write-Host "=== SELESAI ===" -ForegroundColor Green
Write-Host "Kode lama sudah dibackup ke: $BackupDir"
Write-Host "Database lama sudah dimigrasikan ke: AIRA_ECOSYSTEM\database\"
Write-Host "Folder agent/, tools/, backend/, scripts/ di root SUDAH DIHAPUS."
Write-Host ""
Write-Host "Satu-satunya kode aktif sekarang: AIRA_ECOSYSTEM\" -ForegroundColor Cyan
Write-Host "Jalankan dari sana (lihat instruksi testing di bawah)."
