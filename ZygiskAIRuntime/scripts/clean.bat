@echo off
rem 清理构建产物。源码与第三方源码不动。

set ROOT=%~dp0..

if exist "%ROOT%\build\out" rmdir /s /q "%ROOT%\build\out"
if exist "%ROOT%\module\zygisk\*.so" del /q "%ROOT%\module\zygisk\*.so"

echo cleaned: build\out, module\zygisk\*.so
echo note: third_party\frida-gum\**\build 需手动清理（体积大，避免误删）
