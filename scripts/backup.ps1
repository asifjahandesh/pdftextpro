param(
    [string]$BackupRoot = ".\backups",
    [int]$RetentionDays = 14
)

$ErrorActionPreference = "Stop"

# Load .env
$envFile = ".\.env"
if (-not (Test-Path $envFile)) {
    throw ".env file not found at $envFile"
}
$envMap = @{}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=]+?)\s*=\s*(.+?)\s*$') {
        $envMap[$matches[1]] = $matches[2]
    }
}

$dbUrl = $envMap["DATABASE_URL"]
if (-not $dbUrl) { throw "DATABASE_URL not found in .env" }
$pgDumpUrl = $dbUrl -replace '^postgresql\+psycopg://', 'postgresql://'

$uploadDir = if ($envMap["UPLOAD_DIR"]) { $envMap["UPLOAD_DIR"] } else { ".\data\uploads" }
$pgDump = "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"
if (-not (Test-Path $pgDump)) {
    throw "pg_dump.exe not found at $pgDump"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$destDir = Join-Path $BackupRoot $stamp
New-Item -ItemType Directory -Force -Path $destDir | Out-Null

$dumpFile = Join-Path $destDir "pdftext_pro.dump"
& $pgDump --dbname="$pgDumpUrl" --format=custom --file="$dumpFile"
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }

if (Test-Path $uploadDir) {
    $uploadsDest = Join-Path $destDir "uploads"
    Copy-Item -Path $uploadDir -Destination $uploadsDest -Recurse -Force
}

# Prune old backups
$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem -Path $BackupRoot -Directory | Where-Object { $_.CreationTime -lt $cutoff } | Remove-Item -Recurse -Force

Write-Output "BACKUP_OK: $destDir"
