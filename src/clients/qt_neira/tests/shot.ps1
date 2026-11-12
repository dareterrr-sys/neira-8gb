# shot.ps1 — снимок окна Qt-приложения в демо-режиме (без сервера и без GPU).
# Пример: powershell -File shot.ps1 -Variant b -Size 2400x1200 -Scene settings1 -Out D:\...\b-wide.png
param(
    [string]$Variant = "a",
    [string]$Size = "1280x820",
    [string]$Scene = "main",
    [Parameter(Mandatory=$true)][string]$Out,
    [int]$Delay = 1500
)
$exe = Join-Path (Split-Path $PSScriptRoot -Parent) "neira_qt.exe"
$env:NEIRA_QT_DEMO = "1"
$dir = Split-Path $Out -Parent
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
if (Test-Path $Out) { Remove-Item $Out -Force }
$p = Start-Process -FilePath $exe -ArgumentList @("--variant=$Variant", "--size=$Size", "--scene=$Scene", "--shot=$Out", "--delay=$Delay") -PassThru
if (-not $p.WaitForExit(40000)) { $p.Kill(); Write-Output "TIMEOUT (killed)" }
if (Test-Path $Out) { Write-Output "OK $Out" } else { Write-Output "NO FILE" }
