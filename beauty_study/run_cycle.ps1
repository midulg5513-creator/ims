# 每小时采集周期：抓到期快照 → 刷新特征 → 质量报告
# Windows 计划任务建议：触发器「每天，重复间隔 1 小时，持续 12 小时」，
#   程序：powershell.exe
#   参数：-NoProfile -ExecutionPolicy Bypass -File "d:\AI\爬虫\beauty_study\run_cycle.ps1"

$ErrorActionPreference = "Continue"
$PY   = "d:\AI\爬虫\.venv\Scripts\python.exe"
$ROOT = "d:\AI\爬虫\beauty_study"
$LOCK = Join-Path $ROOT "data\.cycle.lock"
$env:PYTHONIOENCODING = "utf-8"

Push-Location $ROOT
try {
    if (Test-Path $LOCK) {
        $age = (Get-Date) - (Get-Item $LOCK).LastWriteTime
        if ($age.TotalMinutes -lt 30) {
            Write-Host "[skip] 上一周期仍在运行或刚结束（$([int]$age.TotalMinutes) 分钟前）"
            return
        }
        Write-Host "[warn] 发现过期锁，已忽略"
    }
    New-Item -ItemType File -Path $LOCK -Force | Out-Null

    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "===== 采集周期 $stamp ====="

    Write-Host "--- 1/3 到期快照 ---"
    & $PY code\snapshot.py --due

    Write-Host "--- 2/3 刷新特征 ---"
    & $PY code\features.py

    Write-Host "--- 3/3 质量报告 ---"
    & $PY code\quality.py
}
finally {
    Remove-Item $LOCK -Force -ErrorAction SilentlyContinue
    Pop-Location
}
