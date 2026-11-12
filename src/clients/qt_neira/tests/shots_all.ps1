# shots_all.ps1 - variant comparison shots: both variants, normal and wide (>= 2300 px).
# ASCII only: PowerShell 5.1 reads BOM-less UTF-8 as ANSI. Pass the Cyrillic output dir as an argument.
param([Parameter(Mandatory=$true)][string]$OutDir, [string[]]$Variants = @("a", "b"))
$shot = Join-Path $PSScriptRoot "shot.ps1"
foreach ($v in $Variants) {
    & powershell -File $shot -Variant $v -Size 1280x820 -Scene main -Out (Join-Path $OutDir "var-$v-main.png")
    & powershell -File $shot -Variant $v -Size 2400x1300 -Scene main -Out (Join-Path $OutDir "var-$v-wide.png") -Delay 2200
}
