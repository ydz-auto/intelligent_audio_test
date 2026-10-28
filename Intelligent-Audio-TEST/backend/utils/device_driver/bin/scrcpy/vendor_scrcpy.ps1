# 把 scrcpy 4.1 便携版里"音频抓取必需的 9 个文件"拷到本目录。
# 用法（仓库根目录）： powershell -ExecutionPolicy Bypass -File <本文件>
# 需要时可用 -Source 指定其他便携版目录。
param(
    [string]$Source = 'D:\work\_android\scrcpy-win64-v4.1'
)

$ErrorActionPreference = 'Stop'
$Dest = Split-Path -Parent $MyInvocation.MyCommand.Path
$Files = @(
    'scrcpy.exe', 'scrcpy-server', 'SDL3.dll', 'avcodec-62.dll',
    'avformat-62.dll', 'avutil-60.dll', 'swresample-6.dll',
    'libusb-1.0.dll', 'LICENSE.txt'
)

if (-not (Test-Path (Join-Path $Source 'scrcpy.exe'))) {
    throw "源目录里没有 scrcpy.exe：$Source（用 -Source 指定便携版目录）"
}

foreach ($f in $Files) {
    $s = Join-Path $Source $f
    if (-not (Test-Path $s)) { Write-Warning "缺少 $f，跳过"; continue }
    Copy-Item $s (Join-Path $Dest $f) -Force
    Write-Host "copied $f"
}

$sum = (Get-ChildItem $Dest -File | Measure-Object Length -Sum).Sum
Write-Host ("done: {0} files, {1:N2} MB" -f (Get-ChildItem $Dest -File).Count, ($sum / 1MB))
& (Join-Path $Dest 'scrcpy.exe') --version
