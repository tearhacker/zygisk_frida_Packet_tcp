#!/usr/bin/env python3
"""最小 pkg-config 替身 —— 只为绕开 meson「必须为 build machine 编一份 glib」。

背景
----
frida-gum 的 meson.build:404 无条件调用

    dependency('glib-2.0', version: '>=2.72', native: true)

`native: true` 要的是 **build machine**（本机 Windows）的 glib。本机没有 pkg-config，
也没有已安装的 glib，meson 只能去编译 `subprojects/glib` 的 build machine 版本 —— 而这条
路在本机走不通：

    meson 1.12：glib 被 host + build 两台机器各配置一次，
                `add_test_setup('default', is_default: true)` 第二次调用即
                ERROR: 'glib:default' is already set as default.
    meson 1.4 ：build machine 那份 glib 注册不上依赖，
                ERROR: Dependency 'glib-2.0' is required but not found.

关键认识：**我们并不需要 build machine 的 glib 产物**。
它只被用于 meson.build:406 的一次探测：

    if glib_dep_native.type_name() == 'internal' or native_cc.compiles(frida_glib_probe, ...)
        add_project_arguments('-DHAVE_FRIDA_GLIB=1', ...)

检测的是"本机 glib 是不是 Frida 的 fork"（有没有 g_thread_set_callbacks）。
答案是"不是"，所以探测失败 → 不加宏，正是期望结果。

因此这里提供一个 pkg-config 替身，让 meson 认为"系统里有 glib"，从而
**不再回落去编译 build machine 那份 glib**，两台机器只配置 host 一次。

用法（由 build/config/msvc-native.ini 的 pkgconfig 项引用，不要手工调用）
------------------------------------------------------------------------
    [binaries]
    pkgconfig = ['<python.exe>', '<本文件>']

它只认识 glib 系模块；其它模块一律返回"未找到"（退出码 1），
这样不会误伤 meson 对其它依赖的判断。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path as _Path

# 只声明 glib 家族。版本号取 subprojects/glib 的实际版本。
KNOWN = {
    "glib-2.0": "2.75.0",
    "gobject-2.0": "2.75.0",
    "gio-2.0": "2.75.0",
    "gio-unix-2.0": "2.75.0",
    "gmodule-2.0": "2.75.0",
    "gmodule-no-export-2.0": "2.75.0",
    "gthread-2.0": "2.75.0",
}

# 头文件搜索路径由外部注入（各机器的 glib 源码位置不同）：
#   ZAI_PC_CFLAGS_<MOD>  或统一的 ZAI_PC_CFLAGS
# 留空是安全的：那只是让 meson 的 frida_glib_probe 探测失败 → 不加 HAVE_FRIDA_GLIB。
def _cflags_for(mod: str) -> str:
    return os.environ.get(f"ZAI_PC_CFLAGS_{mod.replace('-', '_').replace('.', '_')}") \
        or os.environ.get("ZAI_PC_CFLAGS") \
        or ""


def _libs_for(mod: str) -> str:
    return os.environ.get("ZAI_PC_LIBS") or ""


# --- pkg-config 变量 -------------------------------------------------------
# json-glib 的 gnome.mkenums_simple() 会问 pkg-config 要 glib_mkenums / glib_genmarshal。
# 这两个脚本是 glib 配置阶段由 configure_file 生成的 **模板实例化产物**，
# 源码树里只有 glib-mkenums.in，真身在 builddir 下。
# 不返回它们 meson 会报：
#   ERROR: Could not get pkg-config variable and no default provided for <...glib-2.0...>
_ROOT = _Path(__file__).resolve().parents[2]  # build/scripts -> ZygiskAIRuntime
_GLIB_BUILD = _ROOT / "third_party" / "frida-gum" / "17.18.0" / "build" / "arm64-v8a" / "builddir" / "subprojects" / "glib"

def _variables() -> dict:
    gobject = _GLIB_BUILD / "gobject"
    return {
        "glib_mkenums": str(gobject / "glib-mkenums"),
        "glib_genmarshal": str(gobject / "glib-genmarshal"),
        # 下面这些给个不为空的兜底值，避免 meson 因取不到而报错
        "prefix": str(_GLIB_BUILD),
        "exec_prefix": str(_GLIB_BUILD),
        "includedir": str(_GLIB_BUILD),
        "libdir": str(_GLIB_BUILD),
        "bindir": str(_GLIB_BUILD),
        "datarootdir": str(_GLIB_BUILD),
        "girdir": str(_GLIB_BUILD / "gir"),
        "typelibdir": str(_GLIB_BUILD / "typelib"),
    }


def main(argv: list[str]) -> int:
    args = argv[1:]
    mods = [a for a in args if not a.startswith("-")]
    flags = [a for a in args if a.startswith("-")]

    # meson 会先问版本
    if "--version" in flags:
        print("0.29.2")
        return 0

    unknown = [m for m in mods if m not in KNOWN]
    if not mods:
        return 1
    if unknown:
        for m in unknown:
            sys.stderr.write(f"Package {m} was not found in the pkg-config search path.\n")
        return 1

    if "--exists" in flags:
        return 0
    if "--modversion" in flags:
        for m in mods:
            print(KNOWN[m])
        return 0
    # pkg-config 变量：json-glib 的 mkenums_simple() 依赖这个
    want_var = None
    for f in flags:
        if f.startswith("--variable="):
            want_var = f.split("=", 1)[1]
        elif f.startswith("--define-variable") and "=" in f:
            continue  # 只接受重新定义，不影响我们返回值
    if want_var is not None:
        val = _variables().get(want_var)
        if not val:
            return 1
        print(val)
        return 0
    if "--print-requires" in flags or "--print-requires-private" in flags:
        return 0

    out: list[str] = []
    for m in mods:
        if any(f in ("--cflags", "--cflags-only-I", "--cflags-only-other") for f in flags) or "--cflags" in flags:
            out.append(_cflags_for(m))
        if any(f in ("--libs", "--libs-only-L", "--libs-only-l", "--libs-only-other") for f in flags) or "--libs" in flags:
            out.append(_libs_for(m))
    # 若只给了裸模块名（meson 有时这么调），输出 cflags + libs
    if not flags:
        for m in mods:
            out.append(_cflags_for(m))
            out.append(_libs_for(m))

    print(" ".join(x for x in out if x))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
