@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem ============================================================
rem  Zygisk AI Runtime —— 发布版构建 (release)
rem
rem  特点：Release 编译、NDEBUG（断言关闭）、strip 调试信息
rem        产物：build\out\zygisk-ai-runtime.zip
rem
rem  strip 后会校验 zygisk_module_entry 是否仍在；万一丢了会自动
rem  回退到未 strip 版本（副本留为 *.so.unstripped，仅排查用，
rem  不会打进 zip）。
rem
rem  联调阶段请用「测试版.bat」。
rem  实际逻辑在 scripts\build_all.py（本文件只是入口）。
rem ============================================================

set "PY=C:\Users\52334\.workbuddy-ai\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo ============================================================
echo   Zygisk AI Runtime  -  发布版 (release)
echo   产物: build\out\zygisk-ai-runtime.zip
echo ============================================================
echo.

"%PY%" "%~dp0scripts\build_all.py" --mode release
if errorlevel 1 (
    echo.
    echo [失败] 构建未完成，请看上方错误输出。
    echo.
    pause
    exit /b 1
)

echo.
echo [完成] 发布版 zip 已生成: build\out\zygisk-ai-runtime.zip
echo 刷机: Magisk App -^> 模块 -^> 从本地安装 -^> 选该 zip -^> 重启
echo.
pause
