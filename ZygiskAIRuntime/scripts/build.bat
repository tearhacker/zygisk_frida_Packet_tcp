@echo off
rem ===========================================================================
rem  ZygiskAIRuntime - Windows build entry (batch)
rem ===========================================================================
rem
rem  Usage:
rem      scripts\build.bat [stage] [/abi:arm64-v8a]
rem
rem  Stages:
rem      check     Verify toolchain only (no build). Runs first in "all".
rem      prefetch  Pre-download Frida-Gum's subprojects via codeload.
rem      submodules Fetch LSPlant's build-critical git submodules via codeload.
rem                (codeload zips NEVER contain submodules - this is required)
rem      gum       Build Frida-Gum -> third_party\frida-gum\17.18.0\build\<abi>\libgum.a
rem      lsplant   Check LSPlant source (compiled together with native/)
rem      native    Build libai_analyzer.so (+ liblsplant.so)
rem      package   Pack Magisk flashable zip
rem      all       check + prefetch + submodules + gum + lsplant + native + package
rem      clean     Remove build outputs (sources untouched)
rem
rem  NOTE: this file is intentionally ASCII-only.
rem        The project path contains non-ASCII characters; keeping this script
rem        pure ASCII avoids cmd.exe codepage corruption on Chinese Windows.
rem
rem  Toolchain paths can be overridden by setting these env vars beforehand:
rem      ZAI_NDK   ZAI_CMAKE   ZAI_NINJA   ZAI_MESON   ZAI_PYTHON
rem  Defaults match this machine (see build\config\toolchain.env).
rem ===========================================================================

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.." || (echo ERROR: cannot enter project root & exit /b 1)
set "ROOT=%CD%"

set "ABI=arm64-v8a"
set "STAGE=all"

rem ---------------------------------------------------------------- args -----
:parse_args
if "%~1"=="" goto args_done
set "ARG=%~1"
if /i "!ARG!"=="check"    ( set "STAGE=check"    & shift & goto parse_args )
if /i "!ARG!"=="prefetch" ( set "STAGE=prefetch" & shift & goto parse_args )
if /i "!ARG!"=="submodules" ( set "STAGE=submodules" & shift & goto parse_args )
if /i "!ARG!"=="gum"      ( set "STAGE=gum"      & shift & goto parse_args )
if /i "!ARG!"=="lsplant"  ( set "STAGE=lsplant"  & shift & goto parse_args )
if /i "!ARG!"=="native"   ( set "STAGE=native"   & shift & goto parse_args )
if /i "!ARG!"=="package"  ( set "STAGE=package"  & shift & goto parse_args )
if /i "!ARG!"=="all"      ( set "STAGE=all"      & shift & goto parse_args )
if /i "!ARG!"=="clean"    ( set "STAGE=clean"    & shift & goto parse_args )
if /i "!ARG!"=="/abi:arm64-v8a"   ( set "ABI=arm64-v8a"   & shift & goto parse_args )
if /i "!ARG!"=="/abi:armeabi-v7a" ( set "ABI=armeabi-v7a" & shift & goto parse_args )
if /i "!ARG!"=="/abi:x86_64"      ( set "ABI=x86_64"      & shift & goto parse_args )
echo ERROR: unknown argument: !ARG!
echo Run "scripts\build.bat" with no args for default (all) behaviour.
popd & exit /b 2
:args_done

echo ===========================================================================
echo  ZygiskAIRuntime build
echo  root  : %ROOT%
echo  abi   : %ABI%
echo  stage : %STAGE%
echo ===========================================================================

rem ============================================================ toolchain =====
rem Order: env override -> known local path.

if not defined ZAI_NDK    set "ZAI_NDK=D:\ProgramerDevelop\windowsNDK27"
if not defined ZAI_CMAKE  set "ZAI_CMAKE=D:\ProgramerDevelop\VS2026\SDK\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
if not defined ZAI_NINJA  set "ZAI_NINJA=D:\ProgramerDevelop\VS2026\SDK\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
if not defined ZAI_MESON  set "ZAI_MESON=C:\Users\52334\.workbuddy-ai\binaries\python\envs\default\Scripts\meson.exe"
if not defined ZAI_PYTHON set "ZAI_PYTHON=C:\Users\52334\.workbuddy-ai\binaries\python\envs\default\Scripts\python.exe"

set "NDK_HOME=%ZAI_NDK%"
set "CMAKE_EXE=%ZAI_CMAKE%"
set "NINJA_EXE=%ZAI_NINJA%"
set "MESON_EXE=%ZAI_MESON%"
set "PYTHON_EXE=%ZAI_PYTHON%"

rem meson probes the VS install; if VSINSTALLDIR is unset its vsenv lookup
rem crashes with "TypeError: ... not 'NoneType'". Setting it also short-circuits
rem the probe. Discovered the hard way - do not remove.
if not defined VSINSTALLDIR set "VSINSTALLDIR=D:\ProgramerDevelop\VS2026\SDK"

rem meson requires ninja on PATH.
for %%i in ("%NINJA_EXE%") do set "NINJA_DIR=%%~dpi"
set "PATH=%NINJA_DIR%;%PATH%"

set "GUM_SRC=%ROOT%\third_party\frida-gum\17.18.0"
set "GUM_OUT=%GUM_SRC%\build\%ABI%"
set "LSPLANT_SRC=%ROOT%\third_party\lsplant\lsplant\src\main\jni"
set "NATIVE_OUT=%ROOT%\build\out\%ABI%"
set "MODULE_SO=%ROOT%\module\zygisk\%ABI%.so"

set "API_LEVEL=30"
if "%ABI%"=="arm64-v8a"   ( set "CPU_FAMILY=aarch64" & set "CPU=aarch64" & set "TRIPLE=aarch64-linux-android" )
if "%ABI%"=="armeabi-v7a" ( set "CPU_FAMILY=arm"     & set "CPU=armv7a"  & set "TRIPLE=armv7a-linux-androideabi" )
if "%ABI%"=="x86_64"      ( set "CPU_FAMILY=x86_64"  & set "CPU=x86_64"  & set "TRIPLE=x86_64-linux-android" )
if not defined TRIPLE echo ERROR: unsupported abi %ABI%
if not defined TRIPLE goto fail

rem ------------------------------------------------------------ dispatch ----
if /i "%STAGE%"=="clean" goto stage_clean
if /i "%STAGE%"=="check" goto stage_check
if /i "%STAGE%"=="prefetch" goto stage_prefetch
if /i "%STAGE%"=="submodules" goto stage_submodules
if /i "%STAGE%"=="gum" goto stage_gum
if /i "%STAGE%"=="lsplant" goto stage_lsplant
if /i "%STAGE%"=="native" goto stage_native
if /i "%STAGE%"=="package" goto stage_package

rem STAGE=all -> run every step in order
call :do_check
if errorlevel 1 goto fail
call :do_prefetch
if errorlevel 1 goto fail
call :do_submodules
if errorlevel 1 goto fail
call :do_gum
if errorlevel 1 goto fail
call :do_lsplant
if errorlevel 1 goto fail
call :do_native
if errorlevel 1 goto fail
call :do_package
if errorlevel 1 goto fail
goto done


rem ============================================================ stage: check ==
:stage_check
call :do_check
if errorlevel 1 goto fail
goto done

:do_check
echo.
echo [check] toolchain
set "FAILED=0"

call :probe "%NDK_HOME%\build\cmake\android.toolchain.cmake" "Android NDK"
if errorlevel 1 set "FAILED=1"
if exist "%NDK_HOME%\source.properties" (
    for /f "tokens=2 delims==" %%v in ('findstr /b "Pkg.Revision" "%NDK_HOME%\source.properties"') do echo          revision %%v
)

call :probe "%CMAKE_EXE%" "CMake"
if errorlevel 1 set "FAILED=1"
if exist "%CMAKE_EXE%" for /f "tokens=3" %%v in ('"%CMAKE_EXE%" --version 2^>nul ^| findstr /b "cmake version"') do (
    echo          version %%v
    for /f "tokens=1,2 delims=." %%a in ("%%v") do (
        if %%a LSS 3 ( echo          [FAIL] CMake %%v ^< 3.28 - LSPlant needs C++20 modules & set "FAILED=1" )
    )
)

call :probe "%NINJA_EXE%" "Ninja"
if errorlevel 1 set "FAILED=1"

call :probe "%MESON_EXE%" "Meson"
if errorlevel 1 set "FAILED=1"

call :probe "%PYTHON_EXE%" "Python venv"
if errorlevel 1 set "FAILED=1"

call :probe "%GUM_SRC%\meson.build" "Frida-Gum source"
if errorlevel 1 set "FAILED=1"

call :probe "%LSPLANT_SRC%\include\lsplant.hpp" "LSPlant source"
if errorlevel 1 set "FAILED=1"

if "!FAILED!"=="1" (
    echo [check] FAILED - fix the items marked above
    exit /b 1
)
echo [check] OK
exit /b 0

rem No parenthesised block here on purpose: a label containing "(" or ")"
rem would be parsed as the end of the block. Keep it goto-based.
:probe
if not exist "%~1" goto probe_miss
echo   [ok]   %~2
exit /b 0

:probe_miss
echo   [MISS] %~2  -^> %~1
exit /b 1


rem ========================================================= stage: prefetch ==
rem Why a Python helper instead of parsing .wrap files in cmd:
rem   * the dependency graph is NESTED (glib carries 8 subprojects of its own)
rem   * .wrap files are INI with 3 section kinds (wrap-git / wrap-file / wrap-redirect)
rem   * 20 deps come from github (codeload zip) and 3 from gitlab.gnome.org (archive API)
rem Parsing that in cmd is not worth the fragility.
rem
rem Why prefetch at all: every .wrap is [wrap-git], and the local proxy answers the
rem git protocol with "CONNECT tunnel failed, 502", so meson's own fetch always
rem fails with "ERROR: Git command failed: [... 'git.EXE', 'fetch', ...]".
rem codeload / archive zips go through fine.
:stage_prefetch
call :do_prefetch
if errorlevel 1 goto fail
goto done

:do_prefetch
echo.
echo [prefetch] Frida-Gum subprojects via codeload (recursive)

if not exist "%PYTHON_EXE%" (
    echo ERROR: python not found at %PYTHON_EXE%
    echo        set ZAI_PYTHON, or skip this stage with "scripts\build.bat gum"
    exit /b 1
)

set "PF_ARGS=--skip-optional"
if /i "%ZAI_PREFETCH_ALL%"=="1" set "PF_ARGS="

"%PYTHON_EXE%" "%ROOT%\scripts\prefetch_subprojects.py" --gum-root "%GUM_SRC%" %PF_ARGS%
if errorlevel 1 (
    echo.
    echo WARN: prefetch reported failures; meson will fail on whatever is missing.
    echo       Re-run this stage, or fetch them by hand and re-run.
    exit /b 1
)
echo [prefetch] done
exit /b 0


rem ======================================================= stage: submodules ==
rem codeload zips never contain git submodules, so any submodule a dependency
rem needs at BUILD time has to be fetched by hand. LSPlant has 4 submodules;
rem only dex_builder is needed to build (the other 3 are docs/tests).
rem DexBuilder in turn needs parallel_hashmap.
rem
rem Missing them shows up as:
rem   CMakeLists.txt:25 (add_subdirectory): ... does not contain a CMakeLists.txt file
:stage_submodules
call :do_submodules
if errorlevel 1 goto fail
goto done

:do_submodules
echo.
echo [submodules] fetching build-critical git submodules via codeload

if not defined DL set "DL=%ROOT%\build\_submodule_cache"
if not exist "%DL%" mkdir "%DL%"

set "LS_ROOT=%ROOT%\third_party\lsplant\lsplant\src\main\jni"

call :fetch_repo "LSPosed" "DexBuilder" "refs/heads/master" "%LS_ROOT%\external\dex_builder"
if errorlevel 1 exit /b 1

set "DB_ROOT=%LS_ROOT%\external\dex_builder"
call :fetch_repo "greg7mdp" "parallel-hashmap" "refs/heads/master" "%DB_ROOT%\external\parallel_hashmap"
if errorlevel 1 exit /b 1

echo [submodules] done
exit /b 0

rem fetch_repo <owner> <repo> <ref> <target_dir>
rem   Skips when target already looks populated; verifies the download size and
rem   that the zip really produced a single top-level directory before moving.
:fetch_repo
set "F_OWNER=%~1"
set "F_REPO=%~2"
set "F_REF=%~3"
set "F_DST=%~4"

if exist "!F_DST!\CMakeLists.txt" (
    echo   [skip] !F_REPO!  ^(already present^)
    exit /b 0
)
if not exist "!F_DST!" mkdir "!F_DST!"

set "F_ZIP=%DL%\!F_REPO!.zip"
echo   [get ] !F_REPO!  !F_OWNER!/!F_REPO!@!F_REF!
curl -sSL --retry 3 --retry-all-errors -o "!F_ZIP!" "https://codeload.github.com/!F_OWNER!/!F_REPO!/zip/!F_REF!"
if not exist "!F_ZIP!" ( echo   [FAIL] download failed: !F_REPO! & exit /b 1 )
for %%A in ("!F_ZIP!") do if %%~zA LSS 1000 ( echo   [FAIL] download too small: !F_REPO! & exit /b 1 )

set "F_TMP=%DL%\y_!F_REPO!"
if exist "!F_TMP!" rmdir /s /q "!F_TMP!"
mkdir "!F_TMP!"
tar -xf "!F_ZIP!" -C "!F_TMP!" 2>nul
if errorlevel 1 ( echo   [FAIL] extract failed: !F_REPO! & exit /b 1 )

set "F_SRC="
for /d %%d in ("!F_TMP!\*") do set "F_SRC=%%~fd"
rem Guard: if the zip had no top-level dir, F_SRC stays empty and a naive
rem "copy from empty path" would copy the drive root. Fail loudly instead.
if not defined F_SRC ( echo   [FAIL] zip contained no top-level directory: !F_REPO! & exit /b 1 )
if not exist "!F_SRC!\CMakeLists.txt" ( echo   [FAIL] no CMakeLists.txt in zip: !F_REPO! & exit /b 1 )

xcopy /E /I /Y /Q "!F_SRC!" "!F_DST!" >nul
if errorlevel 1 ( echo   [FAIL] copy failed: !F_REPO! & exit /b 1 )
rmdir /s /q "!F_TMP!" 2>nul
echo   [ok  ] !F_REPO!
exit /b 0


rem ============================================================== stage: gum ==
:stage_gum
call :do_gum
if errorlevel 1 goto fail
goto done

:do_gum
echo.
echo [gum] building Frida-Gum 17.18.0 for %ABI%
if not exist "%GUM_SRC%\meson.build" ( echo ERROR: frida-gum source missing at %GUM_SRC% & exit /b 1 )
if not exist "%NDK_HOME%\build\cmake\android.toolchain.cmake" ( echo ERROR: NDK not found at %NDK_HOME% & exit /b 1 )

set "NDK_BIN=%NDK_HOME%\toolchains\llvm\prebuilt\windows-x86_64\bin"
set "NDK_BIN_F=%NDK_BIN:\=/%"
if not exist "%GUM_OUT%" mkdir "%GUM_OUT%"
set "CROSS=%GUM_OUT%\android-%ABI%.txt"

rem Use clang.exe with an explicit --target, NOT the .cmd wrapper:
rem meson crashes on the .cmd wrapper (it is a cmd batch file, not a PE binary).
rem
rem subsystem is REQUIRED: frida-gum's meson.build line 29 calls
rem host_machine.subsystem(), and meson cannot autodetect it for android.
rem Without it you get:
rem   meson.build:29:23: ERROR: Subsystem not defined or could not be autodetected.
(
echo [host_machine]
echo system = 'android'
echo subsystem = 'android'
echo cpu_family = '!CPU_FAMILY!'
echo cpu = '!CPU!'
echo endian = 'little'
echo.
echo [binaries]
echo c     = '!NDK_BIN_F!/clang.exe'
echo cpp   = '!NDK_BIN_F!/clang++.exe'
echo ar    = '!NDK_BIN_F!/llvm-ar.exe'
echo strip = '!NDK_BIN_F!/llvm-strip.exe'
echo.
echo [built-in options]
echo c_args        = ['--target=!TRIPLE!!API_LEVEL!', '-DANDROID', '-fPIC', '-O2']
echo cpp_args      = ['--target=!TRIPLE!!API_LEVEL!', '-DANDROID', '-fPIC', '-O2', '-std=c++17']
echo c_link_args   = ['--target=!TRIPLE!!API_LEVEL!']
echo cpp_link_args = ['--target=!TRIPLE!!API_LEVEL!']
) > "!CROSS!"
echo   cross file: !CROSS!

if exist "%GUM_OUT%\builddir" rmdir /s /q "%GUM_OUT%\builddir"

rem --wrap-mode=nodownload: only use subprojects already on disk (our prefetch),
rem never let meson fetch. It also makes optional deps (openssl is required:false)
rem resolve to "not found" and get skipped instead of pulling a subproject.
"%MESON_EXE%" setup "%GUM_OUT%\builddir" "%GUM_SRC%" ^
  --cross-file "%CROSS%" ^
  --wrap-mode=nodownload ^
  --buildtype release ^
  --default-library static ^
  -Dfrida_version=17.18.0 ^
  -Dgumjs=disabled -Dgumpp=disabled -Dquickjs=disabled ^
  -Dtests=disabled -Dinspector=disabled -Dgraft_tool=disabled
if errorlevel 1 ( echo ERROR: meson setup failed & exit /b 1 )

"%MESON_EXE%" compile -C "%GUM_OUT%\builddir"
if errorlevel 1 ( echo ERROR: meson compile failed & exit /b 1 )

set "GUM_LIB=%GUM_OUT%\builddir\libgum.a"
if not exist "!GUM_LIB!" for /r "%GUM_OUT%\builddir" %%f in (libgum.a) do set "GUM_LIB=%%f"
if not exist "!GUM_LIB!" ( echo ERROR: libgum.a not produced & exit /b 1 )
copy /y "!GUM_LIB!" "%GUM_OUT%\libgum.a" >nul
if not exist "%GUM_OUT%\include" mkdir "%GUM_OUT%\include"
echo   [ok] %GUM_OUT%\libgum.a
exit /b 0


rem =========================================================== stage: lsplant ==
rem LGPL-3.0: LSPlant MUST be a separate shared library.
rem It is compiled as part of the native/ CMake build (see native\CMakeLists.txt),
rem which forces LSPLANT_BUILD_SHARED=ON.
:stage_lsplant
call :do_lsplant
if errorlevel 1 goto fail
goto done

:do_lsplant
echo.
echo [lsplant] source check
if not exist "%LSPLANT_SRC%\CMakeLists.txt" ( echo ERROR: LSPlant source missing at %LSPLANT_SRC% & exit /b 1 )
echo   source: %LSPLANT_SRC%
echo   mode  : SHARED  ^(LGPL-3.0 constraint - do not change^)
echo   note  : liblsplant.so is produced by "build.bat native"
exit /b 0


rem ============================================================ stage: native ==
:stage_native
call :do_native
if errorlevel 1 goto fail
goto done

:do_native
echo.
echo [native] building libai_analyzer.so
if not exist "%GUM_OUT%\libgum.a" (
    echo ERROR: libgum.a missing at %GUM_OUT%\libgum.a
    echo        run "scripts\build.bat gum" first
    exit /b 1
)
if not exist "%ROOT%\native\CMakeLists.txt" ( echo ERROR: native\CMakeLists.txt missing & exit /b 1 )

"%CMAKE_EXE%" -S "%ROOT%\native" -B "%NATIVE_OUT%" -G Ninja ^
  -DCMAKE_TOOLCHAIN_FILE="%NDK_HOME%\build\cmake\android.toolchain.cmake" ^
  -DANDROID_ABI=%ABI% ^
  -DANDROID_PLATFORM=android-%API_LEVEL% ^
  -DANDROID_STL=c++_shared ^
  -DCMAKE_MAKE_PROGRAM="%NINJA_EXE%" ^
  -DGUM_BUILD_DIR="%GUM_OUT%"
if errorlevel 1 ( echo ERROR: cmake configure failed & exit /b 1 )

"%CMAKE_EXE%" --build "%NATIVE_OUT%"
if errorlevel 1 ( echo ERROR: cmake build failed & exit /b 1 )

set "BUILT="
for /r "%NATIVE_OUT%" %%f in (libai_analyzer.so) do set "BUILT=%%f"
if not defined BUILT ( echo ERROR: libai_analyzer.so not produced & exit /b 1 )
if not exist "%ROOT%\module\zygisk" mkdir "%ROOT%\module\zygisk"
copy /y "!BUILT!" "%MODULE_SO%" >nul
echo   [ok] !BUILT!
echo   [ok] %MODULE_SO%

for /r "%NATIVE_OUT%" %%f in (liblsplant.so) do (
    copy /y "%%f" "%ROOT%\module\zygisk\" >nul
    echo   [ok] %%f  ^(ship as a separate file - LGPL-3.0^)
)
exit /b 0


rem =========================================================== stage: package ==
:stage_package
call :do_package
if errorlevel 1 goto fail
goto done

:do_package
echo.
echo [package] packing Magisk zip
if not exist "%MODULE_SO%" (
    echo ERROR: %MODULE_SO% missing - run "scripts\build.bat native" first
    exit /b 1
)
set "ZIP=%ROOT%\build\out\zygisk-ai-runtime.zip"
if exist "%ZIP%" del /q "%ZIP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path '%ROOT%\module\*' -DestinationPath '%ZIP%' -Force"
if not exist "%ZIP%" ( echo ERROR: packaging failed & exit /b 1 )
echo   [ok] %ZIP%
exit /b 0


rem ============================================================= stage: clean ==
:stage_clean
echo.
echo [clean] removing build outputs
if exist "%ROOT%\build\out" rmdir /s /q "%ROOT%\build\out"
if exist "%ROOT%\module\zygisk\*.so" del /q "%ROOT%\module\zygisk\*.so"
echo   removed: build\out, module\zygisk\*.so
echo   kept   : third_party\frida-gum\**\build  ^(large; delete manually if needed^)
goto done


rem ================================================================ tail ======
:done
echo.
echo ===========================================================================
echo  BUILD OK - stage: %STAGE%
echo ===========================================================================
popd
endlocal
exit /b 0

:fail
echo.
echo ===========================================================================
echo  BUILD FAILED - stage: %STAGE%
echo ===========================================================================
popd
endlocal
exit /b 1
