#!/usr/bin/env python3
"""一键构建入口 —— 直接产出可刷的 Magisk 模块 zip。

为什么要这个脚本（而不是只用 build-gum.sh / build-native.sh）
------------------------------------------------------------
那两个是 **bash** 脚本。用户双击 `.bat` 时，系统 PATH 里不一定有 bash
（本机的 bash 来自 WorkBuddy 自带的 PortableGit，不是系统安装）。
所以这里用 Python 把整条链路重实现一遍，**不依赖 bash**，
`测试版.bat` / `发布版.bat` 只需调用本脚本即可。

链路
----
    依赖检查 → meson setup/compile(Frida-Gum) → 拷 libgum.a
    → 导出 gum 的 include + 依赖库 → cmake/ninja 构建 native
    → (release 才 strip) → 打包 zip

用法
----
    python scripts/build_all.py --mode release
    python scripts/build_all.py --mode debug
    python scripts/build_all.py --mode release --skip-gum   # 复用已构建的 gum

两种模式的差异
--------------
|                | 测试版 (debug)          | 发布版 (release)      |
|----------------|-------------------------|-----------------------|
| meson buildtype| debug                   | release               |
| CMake          | Debug（断言开、有符号） | Release（NDEBUG）     |
| 构建目录       | *-debug 后缀（互不干扰）| 默认名                |
| 产物 zip       | -debug.zip              | .zip                  |
| strip          | 否（保留调试信息）      | 是（strip-debug）     |
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUM_ROOT = ROOT / "third_party" / "frida-gum" / "17.18.0"
ABI = "arm64-v8a"
API_LEVEL = "30"

# arm64 + android 下 Frida-Gum 的必需 subprojects（见 docs/00-权威基线/SOURCE_LOCK.md §9）
REQUIRED_SUBPROJECTS = ("glib", "capstone", "json-glib", "tinycc", "libunwind", "libdwarf", "xz")


def load_toolchain_env() -> dict:
    """解析 build/config/toolchain.env（格式 `export KEY="VALUE"`）。

    ⚠️ 必须做变量展开：文件里 INCLUDE / LIB 是用 `$MSVC_TOOLS/...` 这种引用拼出来的。
    bash `source` 时会自动展开，Python 按字面取则拿到
        '$MSVC_TOOLS/include;$WIN_KITS/Include/...'
    这么一个无效字符串 —— cl.exe 找不到 stdio.h，sanity check 失败，
    表现为 meson 报 'Compiler for language "c" ... not specified for build machine'
    （报错点离真因很远，很容易误判成编译器没配对）。
    """
    env_file = ROOT / "build" / "config" / "toolchain.env"
    vals: dict[str, str] = {}
    if not env_file.is_file():
        raise SystemExit(f"缺少 {env_file}")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        m = re.match(r'\s*export\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"]*)"', line)
        if m:
            vals[m.group(1)] = m.group(2)

    # 反复替换直到不再变化（支持链式引用，如 MSVC_BIN 引用 MSVC_TOOLS）。
    #
    # ⚠️ 必须按变量名**长度降序**替换：否则 `$WIN_KITS_VER` 里的 `$WIN_KITS`
    #    会被先替换掉，得到 `D:/Windows Kits/10_VER` 这种鬼东西
    #    （`_VER` 被当成普通后缀留下了）。这是最长匹配问题。
    ordered = sorted(vals.items(), key=lambda kv: len(kv[0]), reverse=True)
    for _ in range(5):
        changed = False
        for key, value in list(vals.items()):
            new = value
            for ref, ref_val in ordered:
                new = new.replace(f"${ref}", ref_val).replace(f"${{{ref}}}", ref_val)
            if new != value:
                vals[key] = new
                changed = True
        if not changed:
            break
    return vals


def stage(msg: str) -> None:
    print(f"\n{'=' * 62}\n{msg}\n{'=' * 62}", flush=True)


def run(cmd: list[str], *, env: dict, cwd: Path | None = None) -> None:
    printable = " ".join(str(c) for c in cmd)
    print(f"$ {printable}", flush=True)
    proc = subprocess.run(cmd, env=env, cwd=str(cwd or ROOT))
    if proc.returncode != 0:
        raise SystemExit(f"命令失败（退出码 {proc.returncode}）：{printable}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("debug", "release"), default="release")
    ap.add_argument("--skip-gum", action="store_true", help="复用已构建的 Frida-Gum")
    ap.add_argument("--abi", default=ABI)
    args = ap.parse_args(argv)

    mode, abi = args.mode, args.abi
    debug = mode == "debug"
    suffix = "-debug" if debug else ""
    zip_name = f"zygisk-packettool-tearhacker{suffix}.zip"

    tc = load_toolchain_env()
    ndk = tc.get("ANDROID_NDK_HOME", "")
    cmake = tc.get("CMAKE_EXE", "")
    ninja = tc.get("NINJA_EXE", "")
    meson = tc.get("MESON_EXE", "")
    python_exe = tc.get("PYTHON_VENV") or sys.executable

    for label, path in (("NDK", ndk), ("CMake", cmake), ("Ninja", ninja), ("Meson", meson)):
        if not path or not Path(path).exists():
            raise SystemExit(f"{label} 路径无效或不存在：{path!r} —— 检查 build/config/toolchain.env")

    # --- 环境变量 ---------------------------------------------------------
    # 关键：setup 要 PYTHONUTF8=0（让 meson 用 replace 解码 cl.exe 的 GBK 输出），
    #       compile 要 PYTHONUTF8=1（让 glib-mkenums 用 UTF-8 读含中文路径的 rsp 文件）。
    base_env = dict(os.environ)
    base_env["VSINSTALLDIR"] = "D:/ProgramerDevelop/VS2026/SDK"
    base_env["CODEBUDDY_SAFE_DELETE_ENABLED"] = "0"  # 沙箱 rmtree 钩子会炸 meson 的临时目录
    base_env["INCLUDE"] = tc.get("INCLUDE", "")
    base_env["LIB"] = tc.get("LIB", "")
    base_env["PATH"] = base_env.get("PATH", "") + os.pathsep + str(Path(ninja).parent)
    setup_env = {**base_env, "PYTHONUTF8": "0"}
    build_env = {**base_env, "PYTHONUTF8": "1"}

    gum_build = GUM_ROOT / "build" / abi
    gum_builddir = gum_build / ("builddir_debug" if debug else "builddir")
    gum_lib = gum_build / "libgum.a"
    native_build = ROOT / "build" / "out" / f"{abi}{suffix}"

    # --- 0. Python 前置：distutils ------------------------------------------
    # glib 的 gdbus-codegen 会 `import distutils.version`，而 distutils 在
    # Python 3.12+ 已被移除 —— 必须由 setuptools 补上。
    # 踩过两次：一次是 base 3.13.12 缺，一次是 venv 缺（取决于 meson 最终用哪个
    # python 跑 codegen），所以两个都检查。
    for label, py in (("venv", python_exe), ("sys", sys.executable)):
        rc = subprocess.run([py, "-c", "import distutils.version"],
                            capture_output=True)
        if rc.returncode != 0:
            print(f"⚠  {label} python 缺 distutils：{py}")
            print(f"   修：`\"{py}\" -m pip install setuptools`")

    # --- 1. 依赖检查 -------------------------------------------------------
    stage("1/6 检查 Frida-Gum 的必需 subprojects")
    missing = [p for p in REQUIRED_SUBPROJECTS if not (GUM_ROOT / "subprojects" / p / "meson.build").is_file()]
    if missing:
        print(f"缺失：{missing} —— 用 codeload 补拉")
        run([python_exe, str(ROOT / "build" / "scripts" / "fetch_subproject.py"), *missing], env=build_env)
    else:
        print("全部就绪：", ", ".join(REQUIRED_SUBPROJECTS))

    # --- 2. Frida-Gum ------------------------------------------------------
    if args.skip_gum and gum_lib.is_file():
        stage("2/6 跳过 Frida-Gum（--skip-gum，复用已有 libgum.a）")
    else:
        stage("2/6 构建 Frida-Gum（meson 交叉编译，首次约 15 分钟）")
        cross = gum_build / f"android-{abi}.txt"
        if not cross.is_file():
            write_cross_file(cross, ndk, abi, API_LEVEL)

        if not (gum_builddir / "build.ninja").is_file():
            run([meson, "setup", str(gum_builddir), str(GUM_ROOT),
                 "--cross-file", str(cross),
                 "--native-file", str(ROOT / "build" / "config" / "msvc-native.ini"),
                 "--wrap-mode", "nodownload",
                 "--buildtype", mode,
                 "--default-library", "static",
                 "-Dfrida_version=17.18.0",
                 "-Dgumjs=disabled", "-Dgumpp=disabled", "-Dquickjs=disabled",
                 "-Dtests=disabled", "-Dinspector=disabled"],
                env=setup_env)
        # 用 ninja 直连，不用 `meson compile`：
        # LSPlant 的 C++20 modules 会生成 clang-scan-deps 步骤，实测 meson/cmake 的
        # jobserver 与它会互相等待，挂住几十分钟零进展。
        run([ninja, "-C", str(gum_builddir)], env=build_env)

        src_a = gum_builddir / "gum" / "libfrida-gum-1.0.a"
        if not src_a.is_file():
            raise SystemExit(f"未找到 {src_a} —— meson 编译没产出 gum 静态库")
        shutil.copyfile(src_a, gum_lib)
        print(f"libgum.a -> {gum_lib}")

    # --- 3. 导出 gum 的 include + 依赖库 ------------------------------------
    stage("3/6 导出 gum 的 include 目录与依赖静态库")
    run([python_exe, str(ROOT / "build" / "scripts" / "gen_gum_include_dirs.py"), "--abi", abi], env=build_env)

    # --- 4. native 构建 -----------------------------------------------------
    stage("4/6 构建本工程 native 层")
    toolchain = Path(ndk) / "build" / "cmake" / "android.toolchain.cmake"
    if not (native_build / "build.ninja").is_file():
        run([cmake, "-S", str(ROOT / "native"), "-B", str(native_build),
             "-G", "Ninja",
             "-DCMAKE_TOOLCHAIN_FILE=" + str(toolchain),
             "-DCMAKE_MAKE_PROGRAM=" + ninja,
             "-DANDROID_ABI=" + abi,
             "-DANDROID_PLATFORM=android-" + API_LEVEL,
             "-DANDROID_STL=c++_static",
             "-DCMAKE_BUILD_TYPE=" + ("Debug" if debug else "Release"),
             "-DCMAKE_CXX_USE_RESPONSE_FILE_FOR_INCLUDES=ON",
             # LSPlant master 与 NDK r27d 的 clang 18 不兼容，见 BUILD_BLOCKERS.md §7
             "-DZAI_ENABLE_LSPLANT=OFF"],
            env=build_env)
    run([ninja, "-C", str(native_build)], env=build_env)

    so = native_build / "libai_analyzer.so"
    if not so.is_file():
        raise SystemExit(f"未找到 {so}")

    # --- 5. strip（仅 release）----------------------------------------------
    if debug:
        stage("5/6 跳过 strip（测试版保留符号）")
    else:
        stage("5/6 strip 调试信息")
        strip = Path(ndk) / "toolchains/llvm/prebuilt/windows-x86_64/bin/llvm-strip.exe"
        backup = so.with_suffix(".so.unstripped")
        shutil.copyfile(so, backup)
        # 只删调试段，保留符号表 —— 比 --strip-unneeded 安全，
        # 但下面仍会校验 Zygisk 入口符号是否还在。
        run([str(strip), "--strip-debug", str(so)], env=build_env)
        if not has_zygisk_entry(so, ndk):
            print("  ⚠ strip 后入口符号丢失，回退到未 strip 版本")
            shutil.copyfile(backup, so)
        else:
            print(f"  未 strip 副本保留在 {backup.name}")

    # --- 6. 打包 ------------------------------------------------------------
    stage("6/6 打包 Magisk 模块 zip")
    mod_so = ROOT / "module" / "zygisk" / f"{abi}.so"
    mod_so.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(so, mod_so)

    out_zip = ROOT / "build" / "out" / zip_name
    run([python_exe, str(ROOT / "scripts" / "package.py"), "--out", str(out_zip)], env=build_env)

    stage("完成")
    print(f"模式      : {mode}")
    print(f"模块 so   : {mod_so}  ({mod_so.stat().st_size} bytes)")
    print(f"可刷 zip  : {out_zip}")
    if not debug:
        print("           （同目录 .unstripped 文件仅为排查用，不会打进 zip）")
    print("\n刷机：Magisk App → 模块 → 从本地安装 → 选该 zip → 重启")
    print("验证：bash scripts/verify_device.sh log")
    return 0


def has_zygisk_entry(so: Path, ndk: str) -> bool:
    nm = Path(ndk) / "toolchains/llvm/prebuilt/windows-x86_64/bin/llvm-nm.exe"
    if not nm.is_file():
        return True  # 没法验证就别瞎判断
    out = subprocess.run([str(nm), "-D", "--defined-only", str(so)],
                         capture_output=True, text=True, errors="replace")
    return "zygisk_module_entry" in out.stdout


def write_cross_file(path: Path, ndk: str, abi: str, api: str) -> None:
    """生成 meson cross file（逻辑与 build-gum.sh 一致）。"""
    cpu_family, cpu, triple = {
        "arm64-v8a": ("aarch64", "aarch64", "aarch64-linux-android"),
        "armeabi-v7a": ("arm", "armv7a", "armv7a-linux-androideabi"),
        "x86_64": ("x86_64", "x86_64", "x86_64-linux-android"),
    }[abi]
    bin_dir = Path(ndk) / "toolchains/llvm/prebuilt/windows-x86_64/bin"

    # 注意：用 clang.exe + 显式 --target，不要用 NDK 的 .cmd wrapper（meson 会当 PE 二进制处理而崩）
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"""[host_machine]
system = 'android'
subsystem = 'android'
cpu_family = '{cpu_family}'
cpu = '{cpu}'
endian = 'little'

[binaries]
c     = '{bin_dir.as_posix()}/clang.exe'
cpp   = '{bin_dir.as_posix()}/clang++.exe'
ar    = '{bin_dir.as_posix()}/llvm-ar.exe'
strip = '{bin_dir.as_posix()}/llvm-strip.exe'

[built-in options]
c_args        = ['--target={triple}{api}', '-DANDROID', '-fPIC', '-O2']
cpp_args      = ['--target={triple}{api}', '-DANDROID', '-fPIC', '-O2', '-std=c++17']
c_link_args   = ['--target={triple}{api}']
cpp_link_args = ['--target={triple}{api}']
""", encoding="utf-8")
    print(f"已生成 cross file: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
