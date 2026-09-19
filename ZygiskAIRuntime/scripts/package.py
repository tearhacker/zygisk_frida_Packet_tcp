#!/usr/bin/env python3
"""把 module/ 打包成 Magisk 可刷的 zip。

为什么要有这个脚本（而不是只用 scripts/package.bat）：
    package.bat 依赖 cmd.exe + PowerShell，两者在当前沙箱里均不可用
    （cmd.exe 被安全策略禁用，PowerShell 工具跑不了原生 exe）。
    本脚本是等价实现，且不依赖外部压缩工具。

用法：
    python scripts/package.py [--out build/out/zygisk-ai-runtime.zip]

产物：
    build/out/zygisk-ai-runtime.zip
    结构：zip 根下直接是模块内容（module.prop / zygisk/<abi>.so / *.sh），
          这是 Magisk 要求的布局（不能多包一层 module/ 目录）。
"""

from __future__ import annotations

import argparse
import os
import sys
import zipfile
from pathlib import Path


# Magisk 对模块内文件权限的常规要求：脚本可执行，其余 0644。
EXEC_SUFFIXES = {".sh"}
# 目录权限
DIR_MODE = 0o755
FILE_MODE = 0o644
EXEC_MODE = 0o755


def _mode_for(path: Path) -> int:
    return EXEC_MODE if path.suffix.lower() in EXEC_SUFFIXES else FILE_MODE


def build_zip(module_dir: Path, out_path: Path) -> int:
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

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    n = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(module_dir.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(module_dir).as_posix()
            info = zipfile.ZipInfo(rel, date_time=(2026, 9, 19, 0, 0, 0))
            mode = _mode_for(path)
            # 高 16 位存 Unix 权限；DOS 属性位也要设，否则部分工具读不出来。
            info.external_attr = (mode & 0xFFFF) << 16
            info.create_system = 3  # 3 = Unix，让 Magisk 按 Unix 权限解包
            zf.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
            n += 1

    print(f"packaged: {out_path}  ({n} files)")
    for p in so_files:
        print(f"  zygisk lib: {p.name}  {p.stat().st_size} bytes")
    return 0


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(root / "build" / "out" / "zygisk-ai-runtime.zip"))
    ap.add_argument("--module-dir", default=str(root / "module"))
    args = ap.parse_args()
    return build_zip(Path(args.module_dir), Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
