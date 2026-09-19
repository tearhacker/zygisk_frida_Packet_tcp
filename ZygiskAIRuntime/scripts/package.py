#!/usr/bin/env python3
"""把 module/ 打包成 Magisk 可刷的 zip。

为什么要有这个脚本（而不是只用 scripts/package.bat）：
    package.bat 依赖 cmd.exe + PowerShell，两者在当前沙箱里均不可用
    （cmd.exe 被安全策略禁用，PowerShell 工具跑不了原生 exe）。
    本脚本是等价实现，且不依赖外部压缩工具。

用法：
    python scripts/package.py [--out build/out/zygisk-packettool-tearhacker.zip]

产物：
    build/out/zygisk-packettool-tearhacker.zip
    结构：zip 根下直接是模块内容（module.prop / zygisk/<abi>.so / *.sh），
          这是 Magisk 要求的布局（不能多包一层 module/ 目录）。

🔴 META-INF 是硬性要求（2026-09-19 修复）：
    Magisk / KernelSU 靠 META-INF/com/google/android/update-binary 识别模块 zip。
    早期版本只打包了 module/ 下的裸内容，**没有 META-INF** →
    Magisk 判定「此 zip 不是模块」而拒绝安装，表现是「刷完了但
    /data/adb/modules/<id> 目录根本不存在」。
    META-INF 源文件放在 module/META-INF/，本脚本原样打进 zip 并强制校验其存在。
"""

from __future__ import annotations

import argparse
import os
import sys
import zipfile
from pathlib import Path


# Magisk 对模块内文件权限的常规要求：脚本可执行，其余 0644。
EXEC_SUFFIXES = {".sh"}
# 无后缀但必须可执行的文件（META-INF 里的安装入口）。
# 漏了这条 → update-binary 被打成 0644 → 安装器跑不起来 → 模块装不上。
EXEC_NAMES = {"update-binary", "updater-script"}
# 🔴 .so 必须带可执行位（2026-09-19 真机事故）：
#   早期 .so 落在 FILE_MODE=0644 分支里，刷进手机后 zygisk/<abi>.so 是 0644。
#   linker 加载 native lib 时要以 PROT_EXEC 映射，文件缺 x 位 → dlopen 失败，
#   而 Zygisk 对加载失败**只在 zygisk/unloaded 留一个标记、不打任何日志**，
#   现象就是"模块装上了、目录也在、但从头到尾没生效"。
#
#   0755 已足够：owner(root) rwx，其余 r-x。
#   0777 多出来的只是 group/other 的写位，Android 上没有实际收益，
#   坚持要 0777 就传 --so-mode 0777（或改下面这个常量）。
SO_SUFFIXES = {".so"}
# 目录权限
DIR_MODE = 0o755
FILE_MODE = 0o644
EXEC_MODE = 0o755
SO_MODE = 0o755


def _mode_for(path: Path, so_mode: int = SO_MODE) -> int:
    suffix = path.suffix.lower()
    if suffix in SO_SUFFIXES:
        return so_mode
    if suffix in EXEC_SUFFIXES or path.name in EXEC_NAMES:
        return EXEC_MODE
    return FILE_MODE


def _is_excluded(rel: str) -> bool:
    """zygisk/ 是 Zygisk 的加载目录，只认 <abi>.so。

    Magisk 只会去 open  zygisk/{armeabi-v7a,arm64-v8a,x86,x86_64,riscv64}.so，
    其余文件一律不看。把 README 之类的东西打进去不会报错，但会让模块目录变脏，
    也容易让人误以为那些文件会被加载。
    """
    return rel.startswith("zygisk/") and not rel.endswith(".so")


def build_zip(module_dir: Path, out_path: Path, so_mode: int = SO_MODE) -> int:
    if not module_dir.is_dir():
        print(f"ERROR: module dir not found: {module_dir}", file=sys.stderr)
        return 1

    # 产物校验：缺失就中止，避免刷入一个空壳模块（与 module/customize.sh 的校验一致）。
    so_files = sorted((module_dir / "zygisk").glob("*.so")) if (module_dir / "zygisk").is_dir() else []
    if not so_files:
        print(
            "ERROR: no zygisk/*.so found. Build first "
            "(cmake -> libai_analyzer.so -> copy to module/zygisk/<abi>.so).",
            file=sys.stderr,
        )
        return 1

    # META-INF 校验：缺了它 Magisk 不认这个 zip（见文件头注释）。
    meta_inf = module_dir / "META-INF" / "com" / "google" / "android"
    for required in ("update-binary", "updater-script"):
        if not (meta_inf / required).is_file():
            print(
                f"ERROR: missing META-INF/com/google/android/{required}. "
                "Magisk will reject a zip without it (module dir never gets created).",
                file=sys.stderr,
            )
            return 1

    # 打包期就验 ELF：这是最后一道能廉价拦下"坏 so"的关口。
    # 放过它，故障会推迟到真机加载时才暴露 —— 那时只剩一个 unloaded 标记，
    # 排查成本比这里高一个数量级（见 module/customize.sh 的注释）。
    for p in so_files:
        if p.read_bytes()[:4] != b"\x7fELF":
            print(f"ERROR: {p} is not an ELF file (bad magic).", file=sys.stderr)
            return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        try:
            out_path.unlink()
        except OSError:
            # 某些受管控的环境禁止删除文件（会走回收站且失败）。
            # 删除只是为了拿到一个干净的起点，zipfile 用 'w' 打开本身就会截断覆盖，
            # 所以这里删不掉也不该让打包失败。
            pass

    n = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(module_dir.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(module_dir).as_posix()
            if _is_excluded(rel):
                continue
            info = zipfile.ZipInfo(rel, date_time=(2026, 9, 19, 0, 0, 0))
            mode = _mode_for(path, so_mode)
            # 高 16 位存 Unix 权限；DOS 属性位也要设，否则部分工具读不出来。
            info.external_attr = (mode & 0xFFFF) << 16
            info.create_system = 3  # 3 = Unix，让 Magisk 按 Unix 权限解包
            zf.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
            n += 1

    print(f"packaged: {out_path}  ({n} files)")
    for p in so_files:
        # 把权限一起打出来：只看体积看不出 so 有没有 x 位，
        # 而"没 x 位"的表现是装完不生效、日志全无 —— 极难排查（见 SO_SUFFIXES 注释）。
        print(f"  zygisk lib: {p.name}  {p.stat().st_size} bytes  mode={so_mode:04o}")
    return 0


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(root / "build" / "out" / "zygisk-packettool-tearhacker.zip"))
    ap.add_argument("--module-dir", default=str(root / "module"))
    ap.add_argument(
        "--so-mode",
        default=f"{SO_MODE:o}",
        help=f"zygisk/*.so 在 zip 里的权限位，八进制（默认 {SO_MODE:o}）",
    )
    args = ap.parse_args()
    so_mode = int(args.so_mode, 8)
    return build_zip(Path(args.module_dir), Path(args.out), so_mode=so_mode)


if __name__ == "__main__":
    raise SystemExit(main())
