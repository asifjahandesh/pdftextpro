param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDir
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $BackupDir)) {
    throw "Backup directory not found: $BackupDir"
}

$envMap = @{}
Get-Content ".\.env" | ForEach-Object {
    if ($_ -match '^\s*([^#=]+?)\s*=\s*(.+?)\s*$') {
        $envMap[$matches[1]] = $matches[2]
    }
}

$dbUrl = $envMap["DATABASE_URL"] -replace '^postgresql\+psycopg://', 'postgresql://'
$uploadDir = if ($envMap["UPLOAD_DIR"]) { $envMap["UPLOAD_DIR"] } else { ".\data\uploads" }
$pgRestore = "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe"

$dumpFile = Join-Path $BackupDir "pdftext_pro.dump"
if (-not (Test-Path $dumpFile)) { throw "Dump file not found: $dumpFile" }

& $pgRestore --dbname="$dbUrl" --clean --if-exists --no-owner "$dumpFile"
if ($LASTEXITCODE -ne 0) { throw "pg_restore failed with exit code $LASTEXITCODE" }

$uploadsSrc = Join-Path $BackupDir "uploads"
if (Test-Path $uploadsSrc) {
    New-Item -ItemType Directory -Force -Path $uploadDir | Out-Null
    Copy-Item -Path "$uploadsSrc\*" -Destination $uploadDir -Recurse -Force
}

Write-Output "RESTORE_OK: $BackupDir"
