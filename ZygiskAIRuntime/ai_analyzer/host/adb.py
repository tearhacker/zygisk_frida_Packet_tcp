# -*- coding: utf-8 -*-
"""ADB 能力封装（PC 侧最小集）。

为什么要有这个模块
------------------
2026-09-19 真机联调的实际教训：所有 Runtime 工具返回 E_NOT_READY，
排查到最后根因居然是**没人建 adb forward** —— PC 侧 60500 根本没有 LISTENING，
设备侧 60500 却明明在 LISTEN。host 一遍遍重连，重连计数涨到 70+，
而用户看到的只有一句 DISCONNECTED。

adb forward 有三个性质决定了它必须自动化：
  1. 拔线 / 重启手机 / 重启 adb server 之后**立刻失效**，每次都要重建；
  2. 它是幂等的（同一对端口重复执行不会报错），适合每次启动都跑一遍；
  3. 忘了建它，现象和"Runtime 挂了"完全一样，极难区分。

所以 host 启动时自己把它建好，不再靠人记着敲命令。

纪律
----
本模块**禁止 fake success**：
  - adb 找不到 → 说找不到，并给出实际查找的路径；
  - adb 执行失败 → 原样带回 stderr；
  - forward 命令返回 0 也不算成功，必须再用 `adb forward --list` 复核一次
    （accepted → executed → verified 三级，见项目总基线）。
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field

# Windows 上 platform-tools 的默认安装位置。
# 用户明确指定：没给 --adb 时的默认值就是这个。
DEFAULT_ADB_WINDOWS = r"C:/Program Files/platform-tools/adb.exe"
# 非 Windows 走 PATH 查找。
DEFAULT_ADB_FALLBACK = "adb"

# adb 单次调用超时（秒）。adb server 冷启动 + USB 握手可能要好几秒，
# 但也不能无限等：设备 offline 时 adb 会一直卡着。
DEFAULT_ADB_TIMEOUT = 15.0


def default_adb_path() -> str:
    """没给 --adb 时的默认值。

    Windows 优先用 platform-tools 的默认安装路径；
    那个路径不存在时退回 PATH 里的 `adb`（避免硬编码导致完全不可用）。
    """
    if platform.system() == "Windows":
        if os.path.isfile(DEFAULT_ADB_WINDOWS):
            return DEFAULT_ADB_WINDOWS
        # 用户可能装在别的盘，PATH 里有的话就认 PATH。
        found = shutil.which("adb")
        return found or DEFAULT_ADB_WINDOWS
    return shutil.which("adb") or DEFAULT_ADB_FALLBACK


def resolve_adb(path: str | None = None) -> tuple[str | None, str]:
    """确认 adb 可用。

    返回 (可用路径, 说明)。不可用则路径为 None、说明里写清为什么。
    刻意不抛异常：adb 不可用不应该让 MCP Server 起不来 ——
    Runtime 连不上时工具本来就该返回 E_NOT_READY，服务照常可启动。
    """
    candidate = path or default_adb_path()

    # 绝对路径 / 相对路径都按文件查
    if os.path.isfile(candidate):
        return candidate, f"adb={candidate}"

    found = shutil.which(candidate)
    if found:
        return found, f"adb={found}（PATH 命中）"

    return None, (
        f"adb 不可用：既不是文件也不在 PATH 里 —— {candidate}。"
        f"用 --adb 指定 adb.exe 的完整路径（默认 {DEFAULT_ADB_WINDOWS}）。"
    )


@dataclass(frozen=True)
class AdbResult:
    """一次 adb 调用的结果。"""

    ok: bool
    command: tuple[str, ...]
    stdout: str = ""
    stderr: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "command": list(self.command),
            "stdout": self.stdout.strip(),
            "stderr": self.stderr.strip(),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ForwardResult:
    """端口转发的结果。

    ok      = forward 命令返回 0
    verified= 再用 `adb forward --list` 复核，确实能查到这条映射

    只有 verified=True 才算链路真的通。ok 但没 verified 属于
    "命令接受了但没生效"，必须如实上报（本项目的三级纪律）。
    """

    ok: bool
    verified: bool
    adb: str
    local_port: int
    device_port: int
    serial: str | None = None
    command: tuple[str, ...] = ()
    stdout: str = ""
    stderr: str = ""
    detail: str = ""
    forward_list: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "verified": self.verified,
            "adb": self.adb,
            "local_port": self.local_port,
            "device_port": self.device_port,
            "serial": self.serial,
            "command": list(self.command),
            "stdout": self.stdout.strip(),
            "stderr": self.stderr.strip(),
            "detail": self.detail,
            "forward_list": list(self.forward_list),
        }


def _run(adb: str, args: list[str], timeout: float) -> AdbResult:
    """跑一次 adb。所有失败都变成 AdbResult，不上抛。"""
    cmd = [adb, *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
        )
    except FileNotFoundError:
        return AdbResult(False, tuple(cmd), detail=f"adb 无法启动（文件不存在）：{adb}")
    except PermissionError:
        return AdbResult(False, tuple(cmd), detail=f"adb 没有执行权限：{adb}")
    except subprocess.TimeoutExpired:
        return AdbResult(False, tuple(cmd), detail=f"adb 调用超时（{timeout}s）：{' '.join(cmd)}")
    except OSError as exc:  # noqa: BLE001
        return AdbResult(False, tuple(cmd), detail=f"adb 调用异常：{exc}")

    return AdbResult(
        ok=proc.returncode == 0 and "error:" not in (proc.stdout + proc.stderr).lower(),
        command=tuple(cmd),
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        detail="" if proc.returncode == 0 else f"adb 退出码 {proc.returncode}",
    )


def _serial_prefix(serial: str | None) -> list[str]:
    return ["-s", serial] if serial else []


def ensure_forward(
    adb: str,
    local_port: int,
    device_port: int,
    *,
    serial: str | None = None,
    timeout: float = DEFAULT_ADB_TIMEOUT,
) -> ForwardResult:
    """建立 `adb forward tcp:<local> tcp:<device>` 并复核。

    PC 侧端口与设备侧端口刻意分成两个参数：绝大多数情况下两边取同一个值
    （60500），但 adb forward 本来就不要求相同，分开才不会被误以为是一个东西。
    """
    args = [*_serial_prefix(serial), "forward", f"tcp:{local_port}", f"tcp:{device_port}"]
    res = _run(adb, args, timeout)

    if not res.ok:
        return ForwardResult(
            ok=False,
            verified=False,
            adb=adb,
            local_port=local_port,
            device_port=device_port,
            serial=serial,
            command=res.command,
            stdout=res.stdout,
            stderr=res.stderr,
            detail=res.detail or "adb forward 失败",
        )

    # 复核：命令返回 0 不等于映射真的存在。
    listed = forward_list(adb, serial=serial, timeout=timeout)
    lines = tuple(line.strip() for line in listed.stdout.splitlines() if line.strip())
    needle = f"tcp:{local_port}".lower()
    hits = tuple(line for line in lines if needle in line.lower())

    return ForwardResult(
        ok=True,
        verified=bool(hits) and listed.ok,
        adb=adb,
        local_port=local_port,
        device_port=device_port,
        serial=serial,
        command=res.command,
        stdout=res.stdout,
        stderr=res.stderr,
        detail="" if hits else f"forward 已下发但 --list 里查不到 tcp:{local_port}",
        forward_list=lines,
    )


def forward_list(
    adb: str,
    *,
    serial: str | None = None,
    timeout: float = DEFAULT_ADB_TIMEOUT,
) -> AdbResult:
    """`adb forward --list`。输出原样留在 stdout，调用方自行按行解析。"""
    return _run(adb, [*_serial_prefix(serial), "forward", "--list"], timeout)


def list_devices(adb: str, *, timeout: float = DEFAULT_ADB_TIMEOUT) -> AdbResult:
    """`adb devices -l`。用于给出"到底连没连上设备"的现场证据。"""
    return _run(adb, ["devices", "-l"], timeout)


def online_devices(adb: str, *, timeout: float = DEFAULT_ADB_TIMEOUT) -> list[str]:
    """在线设备序列号列表。取不到就返回空列表（不编造）。"""
    res = list_devices(adb, timeout=timeout)
    if not res.ok:
        return []
    out: list[str] = []
    for line in res.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            out.append(parts[0])
    return out
