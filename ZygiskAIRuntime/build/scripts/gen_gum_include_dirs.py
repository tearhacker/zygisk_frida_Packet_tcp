#!/usr/bin/env python3
"""把 meson 实际编译 gum 时用的 include 目录 + 依赖静态库导出给 CMake。

为什么需要它
------------
native/CMakeLists.txt 原来靠 `file(GLOB subprojects/*/include)` 猜 gum 的头文件位置，
猜错了两处：

  1. capstone 的头文件在 `subprojects/capstone/include/**capstone/**` 下，
     只挂 `include` 会得到 `fatal error: 'capstone.h' file not found`
     （gumdefs.h:12 直接 `#include <capstone.h>`）。
  2. glib 的头文件分散在 glib/ · gobject/ · gio/ · gmodule/ 各自的子目录，
     且 `glibconfig.h` 等是 **meson 生成在 builddir 里** 的，源码树上根本没有。

与其继续猜，不如直接读 meson 生成的 compile_commands.json —— 那里是 meson 真正的编译命令，
include 路径是权威的。本脚本把它们抽出来，生成一个 cmake 片段供 CMakeLists include。

产物：build/generated/gum_includes.cmake（自动生成，勿手改）

用法：
    python build/scripts/gen_gum_include_dirs.py [--abi arm64-v8a]
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUILD = ROOT / "third_party" / "frida-gum" / "17.18.0" / "build"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abi", default="arm64-v8a")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    builddir = DEFAULT_BUILD / args.abi / "builddir"
    cc = builddir / "compile_commands.json"
    if not cc.is_file():
        print(f"ERROR: {cc} not found — 先跑 build/scripts/build-gum.sh", file=sys.stderr)
        return 1

    db = json.loads(cc.read_text(encoding="utf-8"))

    # --- include 目录 -------------------------------------------------------
    def unwanted(p: Path) -> bool:
        """过滤掉不需要、且会让命令行爆炸的目录。

        必须过滤的原因：不加筛选会得到 179 个目录，拼出来的编译命令超过 Windows
        32767 字符上限，ninja 直接报「命令行太长」。
        """
        for seg in p.parts:
            # meson 给每个 target 生成的私有目录（xxx.p / xxx.a.p），只放临时产物
            if seg.endswith(".p"):
                return True
            # 可执行程序与测试代码所在目录，头文件不在意
            if seg in {"test", "tests", "tools", "bin", "fuzz"}:
                return True
        return False

    incs: set[str] = set()
    for entry in db:
        cmd = entry.get("command") or ""
        base = entry.get("directory") or str(builddir)
        for raw in re.findall(r"-I\s*(\"[^\"]+\"|[^\s]+)", cmd):
            raw = raw.strip('"')
            p = Path(os.path.normpath(os.path.join(base, raw)))
            if p.is_dir() and not unwanted(p):
                incs.add(p.resolve().as_posix())

    # --- 依赖静态库 ---------------------------------------------------------
    # libgum.a 本身不含 glib / capstone / libffi / json-glib / libunwind / libdwarf / xz，
    # 链接时必须把这些一起带上，否则满屏 undefined symbol。
    libs: list[str] = []
    for a in sorted(builddir.rglob("*.a")):
        name = a.name
        if name in ("libfrida-gum-1.0.a",):
            continue  # 本体由 CMakeLists 里的 imported target `gum` 负责
        libs.append(a.resolve().as_posix())

    out = Path(args.out) if args.out else ROOT / "build" / "generated" / "gum_includes.cmake"
    out.parent.mkdir(parents=True, exist_ok=True)

    def cmake_list(name: str, items) -> str:
        body = "\n".join(f'  "{i}"' for i in items)
        return f"set({name}\n{body}\n)\n"

    out.write_text(
        "# 自动生成，勿手改 —— 由 build/scripts/gen_gum_include_dirs.py 从\n"
        "# third_party/frida-gum/17.18.0/build/<abi>/builddir/compile_commands.json 提取。\n"
        "# 每次重新构建 Frida-Gum 后请重跑该脚本。\n\n"
        + cmake_list("GUM_INCLUDE_DIRS", sorted(incs))
        + "\n"
        + cmake_list("GUM_DEP_LIBS", libs),
        encoding="utf-8",
    )

    print(f"include dirs: {len(incs)}")
    print(f"dep libs    : {len(libs)}")
    print(f"written     : {out}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
