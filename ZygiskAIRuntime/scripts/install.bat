@echo off
rem 把模块推到设备并提示刷入。
rem 依赖 adb；默认路径为本机已装的 platform-tools。

set ROOT=%~dp0..
set ADB=C:\Program Files\platform-tools\adb.exe
if not exist "%ADB%" set ADB=adb

"%ADB%" devices
"%ADB%" push "%ROOT%\module" /data/local/tmp/zygisk-packettool-tearhacker
echo.
echo 已推到 /data/local/tmp/zygisk-packettool-tearhacker
echo 接下来请在 Magisk App 中「安装 → 从本地安装」选中目录内的 zip（见 package.bat），
echo 或直接在 Magisk 中刷入打包好的 zip。
echo.
echo 提示：先运行 scripts\build.bat 生成 module\zygisk\arm64-v8a.so
