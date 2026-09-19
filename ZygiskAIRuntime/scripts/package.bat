@echo off
rem 打包成 Magisk 可刷 zip（不含签名，Magisk App 本地安装即可）。

set ROOT=%~dp0..
set OUT=%ROOT%\build\out\zygisk-packettool-tearhacker.zip

if not exist "%ROOT%\module\zygisk\arm64-v8a.so" (
    echo ERROR: module\zygisk\arm64-v8a.so missing. Run scripts\build.bat first.
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root='%ROOT%'; $out='%OUT%';" ^
  "New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null;" ^
  "if (Test-Path $out) { Remove-Item $out -Force };" ^
  "Compress-Archive -Path (Join-Path $root 'module\*') -DestinationPath $out;"

echo packaged: %OUT%
