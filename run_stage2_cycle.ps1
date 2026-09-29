param(
    [switch]$SnapshotsOnly
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectDir "weiboSpider\venv\Scripts\python.exe"
$LockPath = Join-Path $ProjectDir "stage2_cycle.lock"
$LogPath = Join-Path $ProjectDir "stage2_scheduler.log"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = "D:\python\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "No project Python interpreter was found."
}
if (Test-Path -LiteralPath $LockPath) {
    $age = (Get-Date) - (Get-Item -LiteralPath $LockPath).LastWriteTime
    if ($age.TotalHours -lt 3) {
        Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) skipped: active lock"
        exit 0
    }
}

try {
    Set-Content -LiteralPath $LockPath -Value $PID
    Push-Location $ProjectDir
    if (-not $SnapshotsOnly) {
        & $PythonExe prospective_study.py discover --pages 3 --delay 2 *>> $LogPath
        if ($LASTEXITCODE -ne 0) { throw "Discovery failed with exit code $LASTEXITCODE" }
    }
    & $PythonExe prospective_study.py snapshots --window all --delay 2 *>> $LogPath
    if ($LASTEXITCODE -ne 0) { throw "Snapshot collection failed with exit code $LASTEXITCODE" }
    & $PythonExe prospective_study.py audit *>> $LogPath
    if ($LASTEXITCODE -ne 0) { throw "Audit failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
    Remove-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue
}
