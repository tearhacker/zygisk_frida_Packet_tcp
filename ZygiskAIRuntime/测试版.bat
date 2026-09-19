@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem ============================================================
rem  Zygisk AI Runtime —— 测试版构建 (debug)
rem
rem  特点：Debug 编译、断言开启、保留调试符号、不 strip
rem        产物：build\out\zygisk-packettool-tearhacker-debug.zip
rem
rem  用于手机联调：日志更全、崩溃更好定位，但体积大、运行慢。
rem  要正式出包请改用「发布版.bat」。
rem
rem  实际逻辑在 scripts\build_all.py（本文件只是入口）。
rem  工程路径含中文，cmd 代码页下写死中文路径会乱码，
rem  所以路径全部由 Python 内部用 __file__ 推导，不经过 cmd。
rem ============================================================

set "PY=C:\Users\52334\.workbuddy-ai\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo ============================================================
echo   Zygisk AI Runtime  -  测试版 (debug)
echo   产物: build\out\zygisk-packettool-tearhacker-debug.zip
echo ============================================================
echo.

"%PY%" "%~dp0scripts\build_all.py" --mode debug
if errorlevel 1 (
    echo.
    echo [失败] 构建未完成，请看上方错误输出。
    echo.
    pause
    exit /b 1
)

echo.
echo [完成] 测试版 zip 已生成: build\out\zygisk-packettool-tearhacker-debug.zip
echo 刷机: Magisk App -^> 模块 -^> 从本地安装 -^> 选该 zip -^> 重启
echo.
pause
