# Zygisk AI Runtime —— 主构建入口（PowerShell / Windows）
#
# 用法：
#   .\scripts\build.ps1 -Abi arm64-v8a
#   .\scripts\build.ps1 -Abi arm64-v8a -SkipGum        # libgum.a 已存在时跳过
#
# 🔴 前置：NDK r27c+ 与 CMake 3.28+。本机当前未安装，脚本会直接报错退出，
#    不会尝试联网下载（用户已决定不在本机安装 NDK / CMake）。

param(
    [string]$Abi = "arm64-v8a",
    [switch]$SkipGum
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$OutDir = Join-Path $Root "build/out/$Abi"
$GumLib = Join-Path $Root "third_party/frida-gum/17.18.0/build/$Abi/libgum.a"

function Fail([string]$msg) {
    Write-Host "ERROR: $msg" -ForegroundColor Red
    exit 1
}

# --- 环境校验 ---
if (-not $env:ANDROID_NDK_HOME) { Fail "ANDROID_NDK_HOME not set" }
if (-not (Test-Path $env:ANDROID_NDK_HOME)) { Fail "ANDROID_NDK_HOME points to a missing dir: $env:ANDROID_NDK_HOME" }

$Toolchain = Join-Path $env:ANDROID_NDK_HOME "build/cmake/android.toolchain.cmake"
if (-not (Test-Path $Toolchain)) { Fail "NDK toolchain not found: $Toolchain" }

$cmake = Get-Command cmake -ErrorAction SilentlyContinue
if (-not $cmake) { Fail "cmake not found (need 3.28+)" }

# --- 1. Frida-Gum ---
if ($SkipGum) {
    Write-Host "skip gum build (--SkipGum)" -ForegroundColor Yellow
} elseif (Test-Path $GumLib) {
    Write-Host "gum already built: $GumLib" -ForegroundColor Green
} else {
    Write-Host "building frida-gum ..." -ForegroundColor Cyan
    $bash = Get-Command bash -ErrorAction SilentlyContinue
    if (-not $bash) { Fail "bash not found (need Git Bash to run build/scripts/build-gum.sh)" }
    & bash (Join-Path $Root "build/scripts/build-gum.sh") $Abi
    if ($LASTEXITCODE -ne 0) { Fail "frida-gum build failed" }
}

# --- 2. libai_analyzer.so ---
Write-Host "configuring cmake ($Abi) ..." -ForegroundColor Cyan
cmake -S (Join-Path $Root "native") -B $OutDir `
    -DCMAKE_TOOLCHAIN_FILE=$Toolchain `
    -DANDROID_ABI=$Abi `
    -DANDROID_PLATFORM=android-30 `
    -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { Fail "cmake configure failed" }

cmake --build $OutDir --config Release
if ($LASTEXITCODE -ne 0) { Fail "cmake build failed" }

# --- 3. 落到 module/zygisk/<abi>.so ---
$So = Join-Path $OutDir "libai_analyzer.so"
if (-not (Test-Path $So)) { Fail "output not found: $So" }

$Target = Join-Path $Root "module/zygisk/$Abi.so"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
Copy-Item $So $Target -Force

Write-Host "OK -> $Target" -ForegroundColor Green
