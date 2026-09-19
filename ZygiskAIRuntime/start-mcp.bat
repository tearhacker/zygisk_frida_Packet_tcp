@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem ============================================================
rem  Zygisk AI Runtime —— MCP Server 启动器（Windows）
rem
rem  两个接入形态：
rem
rem   A) stdio（推荐，客户端自动拉起）—— 客户端 mcp.json 填 mcp_server.py 路径：
rem        {"mcpServers":{"zy_packet_tearhacker":{
rem          "command":"<python.exe>",
rem          "args":["<...>\ZygiskAIRuntime\mcp_server.py"]}}}
rem      端口和 adb 一个都不写也行，默认值就是对的。
rem      这种形态**不需要本 bat**（客户端自己 spawn 进程）。
rem
rem   B) SSE 常驻 —— 本 bat 的默认行为。SSE 必须先起服务客户端才连得上。
rem
rem  ⚠️ 别在 AI 会话的后台任务里起服务：实测两次都随会话被回收
rem     （46 分钟 / 数分钟后即 failed）。要常驻就用独立窗口（双击本文件）。
rem
rem  用法（参数原样透传给 mcp_server.py）：
rem    双击本文件                      → SSE 常驻，连真机（自动 adb forward 60500）
rem    start-mcp.bat --mock            → SSE 常驻，mock 后端（不需要真机）
rem    start-mcp.bat --adb D:\adb.exe  → 指定 adb
rem
rem  默认值（不传就是这些）：
rem    --adb           C:/Program Files/platform-tools/adb.exe
rem    --device-port   60500   PC <-> 手机 Runtime IPC（adb forward 用）
rem    --port          60501   MCP 客户端 <-> 本服务（仅 SSE 生效）
rem
rem  🔴 60500 != 60501，改之前先想清楚动的是哪一层。
rem ============================================================

set "PY=C:\Users\52334\.workbuddy-ai\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

rem 收集全部命令行参数，原样透传
set "ARGS="
:collect
if "%~1"=="" goto run
set "ARGS=%ARGS% %1"
shift
goto collect

:run
rem 没显式给 --transport 才补 SSE 默认值
set "HAS_TRANSPORT=0"
echo.%ARGS% | findstr /i "transport" >nul
if not errorlevel 1 set "HAS_TRANSPORT=1"
if "%HAS_TRANSPORT%"=="0" set "ARGS=%ARGS% --transport sse --port 60501"

echo ============================================================
echo   Zygisk AI Runtime - MCP Server
echo   入口: mcp_server.py
echo   参数:%ARGS%
echo   关闭本窗口即停止服务
echo ============================================================
echo.

"%PY%" mcp_server.py %ARGS%
if errorlevel 1 (
  echo.
  echo [失败] 服务退出，请看上方错误输出。
)

echo.
pause
