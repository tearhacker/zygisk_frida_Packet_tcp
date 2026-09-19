#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""递归预拉 meson subprojects。

为什么需要它
------------
Frida-Gum 的 24 个 `.wrap` 依赖**全部是 `[wrap-git]`**，指向 github.com /
gitlab.gnome.org。本机代理对 git 协议返回 `CONNECT tunnel failed, 502`，
meson 自己拉必然失败：

    third_party\\frida-gum\\17.18.0\\subprojects\\glib\\meson.build:2149:10:
    ERROR: Git command failed: [... 'git.EXE', 'fetch', '--depth', '1', ...]

但 **codeload zip 通道是通的**（实测 capstone 8.4MB / xz 1.19MB / parallel-hashmap 2.1MB
均 HTTP 200）。所以本脚本用归档通道把依赖预先铺到 `subprojects/<name>/`，
meson 检测到目录已存在就直接复用，不再 clone。

**必须递归**：glib 自己还有 8 个嵌套 wrap（pcre2 / zlib / libffi / libiconv /
proxy-libintl / gvdb / gtk-doc / sysprof），只拉顶层会在 glib 阶段炸。

用法::

    python scripts/prefetch_subprojects.py                     # 拉全部可达的
    python scripts/prefetch_subprojects.py --gum-root <path>   # 指定 frida-gum 根
    python scripts/prefetch_subprojects.py --list              # 只列清单，不下载
    python scripts/prefetch_subprojects.py --skip-optional     # 跳过可选项（v8/quickjs/文档等）
"""

from __future__ import annotations

import argparse
import configparser
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_GUM = Path(__file__).resolve().parents[1] / "third_party" / "frida-gum" / "17.18.0"

# 明确不需要的（本项目 gumjs / gumpp / quickjs / tests / inspector / graft_tool 全 disabled）
OPTIONAL = {
    "v8",            # 只有 gumjs 需要
    "quickjs",       # 只有 gumjs 需要
    "sqlite",        # database 选项
    # tinycc **不能**列在这里。
    # frida-gum/meson.build:438 的 required 条件是
    #   (host_abi in ['arm','arm64'] and little endian) or (...)
    # arm64 必然命中 → libtcc 是**必需**依赖，与 graft_tool 是否 disabled 无关。
    # 缺了它 meson setup 会报
    #   ERROR: Subproject tinycc is buildable: NO
    #   ERROR: Automatic wrap-based subproject downloading is disabled
    "gtk-doc",       # 文档
    "sysprof",       # 性能剖析
    "libsoup",       # inspector
    "glib-networking",  # inspector / tls
    "libdwarf",      # 可选调试信息
    "libunwind",     # 可选栈回溯
    "minizip-ng",    # 可选
    "xz",            # 只有 tests 需要
    "openssl",       # frida-gum 里是 required:false —— 本项目不需要 TLS，直接跳过
}

GITHUB_HOSTS = ("github.com",)
GITLAB_HOSTS = ("gitlab.gnome.org", "gitlab.com")


class WrapError(Exception):
    pass


def parse_wrap(path: Path) -> dict:
    """解析一个 .wrap 文件。支持 wrap-git / wrap-file / wrap-redirect。"""
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        cp.read(path, encoding="utf-8")
    except configparser.Error as exc:
        raise WrapError(f"解析失败：{exc}") from exc

    for section in cp.sections():
        data = dict(cp[section])
        if section == "wrap-git":
            return {
                "kind": "git",
                "url": data.get("url", "").strip(),
                "revision": data.get("revision", "").strip(),
            }
        if section == "wrap-file":
            return {
                "kind": "file",
                "source_url": data.get("source_url", "").strip(),
                "filename": data.get("source_filename", "").strip(),
            }
        if section == "wrap-redirect":
            return {"kind": "redirect", "filename": data.get("filename", "").strip()}
    raise WrapError("没有找到 [wrap-git] / [wrap-file] / [wrap-redirect] 段")


def split_repo(url: str) -> tuple[str, str, str]:
    """https://github.com/frida/glib.git -> ('github.com', 'frida', 'glib')"""
    if "://" not in url:
        raise WrapError(f"不支持的 url：{url}")
    _, _, rest = url.partition("://")
    host, _, path = rest.partition("/")
    path = path[:-4] if path.endswith(".git") else path
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise WrapError(f"无法从 url 解析 owner/repo：{url}")
    return host, parts[0], "/".join(parts[1:])


def archive_url(url: str, revision: str) -> str:
    """把 git url + revision 转成归档下载地址（走通了的通道）。"""
    host, owner, repo = split_repo(url)
    if host in GITHUB_HOSTS:
        # codeload 支持直接给 commit sha / ref / tag
        return f"https://codeload.github.com/{owner}/{repo}/zip/{revision}"
    if host in GITLAB_HOSTS:
        project = f"{owner}/{repo}"
        return f"https://{host}/{project}/-/archive/{revision}/{repo}-{revision}.zip"
    raise WrapError(f"未知 host，没有对应的归档通道：{host}")


def curl_download(url: str, dest: Path) -> int:
    """用 curl.exe 下载（Windows 自带；Python urllib 会踩代理环境变量的坑）。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl", "-sSL",
        "--retry", "3", "--retry-all-errors",
        "--connect-timeout", "20",
        "-o", str(dest), url,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    except FileNotFoundError:
        raise WrapError("找不到 curl，请确认 Windows 自带 curl 在 PATH 中") from None
    except subprocess.CalledProcessError as exc:
        raise WrapError(f"curl 失败：{exc.stderr.decode('utf-8', 'replace')[:200]}") from exc
    except subprocess.TimeoutExpired:
        raise WrapError("curl 超时") from None
    return dest.stat().st_size if dest.exists() else 0


def extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """解压并上移一层（归档里是 <repo>-<ref>/ 单层目录）。"""
    with tempfile.TemporaryDirectory(prefix="zai-pf-") as tmp:
        tmp_path = Path(tmp)
        # Windows 自带 bsdtar 能解 zip；Python zipfile 也行，但长路径/符号链接更麻烦
        try:
            subprocess.run(
                ["tar", "-xf", str(zip_path), "-C", str(tmp_path)],
                check=True, capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            import zipfile

            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp_path)

        tops = [p for p in tmp_path.iterdir() if p.is_dir()]
        if len(tops) != 1:
            raise WrapError(f"归档里顶层目录不是 1 个（{len(tops)} 个），拒绝落位")
        src = tops[0]

        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
        shutil.copytree(src, dest_dir, symlinks=True)


def looks_populated(dest: Path) -> bool:
    """目录里已有构建入口就算已就绪。"""
    if not dest.is_dir():
        return False
    return any(
        (dest / marker).exists()
        for marker in ("meson.build", "CMakeLists.txt", "configure", "configure.ac", "Makefile.am")
    )


def collect_wraps(gum_root: Path) -> list[Path]:
    subs = gum_root / "subprojects"
    if not subs.is_dir():
        raise WrapError(f"找不到 subprojects 目录：{subs}")
    return sorted(p for p in subs.rglob("*.wrap") if "build" not in p.parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="递归预拉 meson subprojects")
    ap.add_argument("--gum-root", type=Path, default=DEFAULT_GUM)
    ap.add_argument("--list", action="store_true", help="只列清单，不下载")
    ap.add_argument("--skip-optional", action="store_true",
                    help="跳过本项目用不到的依赖（v8 / quickjs / 文档 / 剖析）")
    ap.add_argument("--force", action="store_true", help="已存在的也重拉")
    args = ap.parse_args(argv)

    gum_root: Path = args.gum_root
    if not gum_root.is_dir():
        print(f"ERROR: frida-gum 根目录不存在：{gum_root}", file=sys.stderr)
        return 2

    wraps = collect_wraps(gum_root)
    print(f"发现 {len(wraps)} 个 .wrap（含嵌套）")
    print()

    ok = skipped = failed = 0
    failures: list[tuple[str, str]] = []

    for wrap in wraps:
        rel = wrap.relative_to(gum_root)
        name = wrap.stem
        dest = wrap.parent / name

        try:
            info = parse_wrap(wrap)
        except WrapError as exc:
            failed += 1
            failures.append((str(rel), str(exc)))
            print(f"  [FAIL] {rel}  — {exc}")
            continue

        if info["kind"] == "redirect":
            print(f"  [skip] {rel}  — redirect → {info['filename']}")
            skipped += 1
            continue

        if args.skip_optional and name in OPTIONAL:
            print(f"  [skip] {rel}  — 本项目不需要（可选依赖）")
            skipped += 1
            continue

        if not args.force and looks_populated(dest):
            print(f"  [have] {rel}  — 已就绪")
            skipped += 1
            continue

        try:
            url = (info["source_url"] if info["kind"] == "file"
                   else archive_url(info["url"], info["revision"]))
        except WrapError as exc:
            failed += 1
            failures.append((str(rel), str(exc)))
            print(f"  [FAIL] {rel}  — {exc}")
            continue

        if args.list:
            print(f"  [need] {rel}\n         {url}")
            continue

        print(f"  [get ] {rel}\n         {url}", flush=True)
        zip_path = gum_root / "subprojects" / ".zai-cache" / f"{name}.zip"
        try:
            size = curl_download(url, zip_path)
            if size < 1000:
                raise WrapError(f"下载过小（{size} 字节），可能是错误页")
            extract_zip(zip_path, dest)
            if not looks_populated(dest):
                print(f"         ⚠️ 落位后没找到构建入口，可能不是预期内容")
            ok += 1
            print(f"         ok  {size} bytes  ->  {dest.relative_to(gum_root)}")
        except WrapError as exc:
            failed += 1
            failures.append((str(rel), str(exc)))
            print(f"  [FAIL] {rel}  — {exc}")

    print()
    print(f"完成：新增/更新 {ok} · 跳过 {skipped} · 失败 {failed}")
    if failures:
        print()
        print("失败明细：")
        for rel, msg in failures:
            print(f"  {rel}\n    {msg}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
