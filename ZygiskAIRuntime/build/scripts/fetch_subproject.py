#!/usr/bin/env python3
"""按名字拉单个 frida-gum subproject（补 dependencies 用）。

为什么单独写这个，而不是只用 scripts/prefetch_subprojects.py：
    prefetch 脚本会遍历 **全部** wrap（含 glib 内嵌的那层），只要其中任意一个失败就整体
    中断 —— 实际就崩在了 json-glib/subprojects/glib（gitlab 下载 + 超长文件名触发
    WinError 3），导致排在后面的依赖根本没机会拉。
    而 meson setup 每次只在真正缺的那个依赖上停一次，一次 9 分钟，
    "跑 setup → 发现缺 X → 拉 X → 再跑 setup" 的循环里，prefetch 全量跑既慢又容易崩。

与 prefetch 的另一个关键差异：
    解压不经过 shutil.copytree，而是**直接用 zipfile 逐成员提取并剥掉顶层目录**，
    绕开 copytree 在 Windows 长路径 / 符号链接上的 WinError 3。

用法：
    python build/scripts/fetch_subproject.py libunwind
    python build/scripts/fetch_subproject.py libunwind libdwarf --force

只支持 frida 的 wrap-git（github.com/frida/*）—— 走 codeload zip 通道：
    本机直连 github 的 git 协议间歇 502，codeload 稳定。
"""

from __future__ import annotations

import argparse
import configparser
import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

DEFAULT_GUM = Path(__file__).resolve().parents[2] / "third_party" / "frida-gum" / "17.18.0"


def parse_wrap(path: Path) -> tuple[str, str]:
    """返回 (zip_url, revision)。只处理 wrap-git + github.com。"""
    cp = configparser.ConfigParser()
    cp.read(path, encoding="utf-8")
    if not cp.has_section("wrap-git"):
        raise SystemExit(f"{path.name}: only wrap-git is supported")
    url = cp.get("wrap-git", "url").rstrip("/")
    revision = cp.get("wrap-git", "revision")
    if not url.startswith("https://github.com/"):
        raise SystemExit(f"{path.name}: unsupported host: {url}")
    repo = url[len("https://github.com/"):]
    # codeload 的 URL 里不能有 .git 后缀，带了会 404：
    #   https://codeload.github.com/frida/libunwind.git/zip/<rev>  → 404
    #   https://codeload.github.com/frida/libunwind/zip/<rev>      → 200
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    zip_url = f"https://codeload.github.com/{repo}/zip/{revision}"
    return zip_url, revision


def fetch(name: str, gum_root: Path, force: bool) -> bool:
    wrap = gum_root / "subprojects" / f"{name}.wrap"
    dest = gum_root / "subprojects" / name

    # .wrap 可能被上游的 .gitignore 挡在仓库外 ——
    # frida-gum 自带的 .gitignore 第 4 行是 `/subprojects/*`，会把整个 subprojects
    #（含我们依赖的 .wrap 锁定清单）排除掉，而且它比仓库根的 .gitignore 更深、
    # 优先级更高，根规则无法反选回来。
    # 所以这里在 build/config/wraps/ 存了一份副本并入库，缺了就自动恢复。
    if not wrap.is_file():
        backup = Path(__file__).resolve().parents[2] / "build" / "config" / "wraps" / f"{name}.wrap"
        if backup.is_file():
            wrap.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(backup, wrap)
            print(f"  [恢复] {name}.wrap ← build/config/wraps/")
        else:
            print(f"  [skip] {name} — 没有 {wrap.name}（备份里也没有）")
            return False
    if dest.is_dir() and (dest / "meson.build").is_file() and not force:
        print(f"  [have] {name} — 已就绪")
        return True

    zip_url, revision = parse_wrap(wrap)
    print(f"  [get ] {name} @ {revision[:12]}")
    print(f"         {zip_url}", flush=True)
    data = urllib.request.urlopen(zip_url, timeout=300).read()
    print(f"         {len(data)} bytes", flush=True)

    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        n = 0
        for member in z.infolist():
            parts = member.filename.split("/")
            # 剥掉 zip 的顶层目录；跳过目录项本身
            if len(parts) <= 1 or parts[-1] == "":
                continue
            member.filename = "/".join(parts[1:])
            z.extract(member, dest)
            n += 1
    print(f"         extracted {n} entries -> {dest}")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="+")
    ap.add_argument("--gum-root", type=Path, default=DEFAULT_GUM)
    ap.add_argument("--force", action="store_true", help="已存在也重拉")
    args = ap.parse_args(argv)

    for name in args.names:
        try:
            fetch(name, args.gum_root, args.force)
        except Exception as exc:  # 一个失败不影响其它
            print(f"  [FAIL] {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
