# -*- coding: utf-8 -*-
"""工具装配与注册三件套自检。

依据：总基线 §19.2 注册三件套（新工具静默不暴露的头号根因）。

三处必须同时成立：
    1. `ai_analyzer.tools.REGISTERED_TOOL_MODULES`  —— 模块被加载
    2. `ai_analyzer.tools._LAZY_IMPORTS`            —— payload 可懒加载
    3. `SurfaceManager` 的可见集             —— 分面可见

并且必须**实际注册到 MCPServer 并 list 出来**才算数 —— 光看代码文件存在不算。
"""

from __future__ import annotations

import importlib
from typing import Any

from ..tools import REGISTERED_TOOL_MODULES, resolve_lazy
from ..tools.spec import ToolSpec
from ..tools.specs import SPECS_BY_NAME
from .surfaces import SurfaceManager


def verify_three_point_registration(
    surfaces: SurfaceManager | None = None,
) -> list[str]:
    """校验注册三件套一致性。返回问题列表，空列表表示全部通过。"""
    sm = surfaces or SurfaceManager()
    problems: list[str] = []

    # --- 第 1 处：模块可加载 ---
    for module_path in REGISTERED_TOOL_MODULES:
        try:
            importlib.import_module(module_path)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"[模块注册] {module_path} 无法导入：{exc}")

    # --- 第 2 处：懒加载表可解析 ---
    for name in SPECS_BY_NAME:
        try:
            fn = resolve_lazy(name)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"[懒加载] {name} 解析失败：{exc}")
            continue
        if not callable(fn):
            problems.append(f"[懒加载] {name} 解析结果不可调用：{fn!r}")

    # --- 第 3 处：分面可见（Core 必然可见；Expert 需挂载）---
    #
    # ⚠️ 曾经的真实 bug：这里调用 sm.mount_all() 后**没有恢复**，
    #    而 build_server() 是先校验、再 bind_tools()，于是无论 --mount 传什么
    #    （甚至不传），Expert 10 个都会被永久挂载 —— 实测默认暴露 35 个，
    #    Core/Expert 分面门控形同虚设。
    #    校验属于"临时"行为，必须原样恢复调用方的挂载状态。
    saved = sm.mounted_snapshot()
    try:
        sm.mount_all()
        visible_all = set(sm.visible_names())
        missing = sorted(set(SPECS_BY_NAME) - visible_all)
        if missing:
            problems.append(f"[分面可见] 未挂载全部 Expert 组时缺失：{missing}")

        core_visible = set(sm.visible_names(None))
        for spec in SPECS_BY_NAME.values():
            if spec.surface.value == "core" and spec.name not in core_visible:
                problems.append(f"[分面可见] Core 工具不可见：{spec.name}")
    finally:
        sm.restore_mounted(saved)

    return problems


def bind_tools(
    server: Any,
    handlers: Any,
    surfaces: SurfaceManager,
    *,
    capabilities: dict[str, dict[str, bool]] | None = None,
) -> list[str]:
    """把当前可见工具注册到 MCPServer。返回注册的工具名列表。

    只有可见集里的工具会被注册 —— 不可用的工具**不注册**，
    而不是注册了再报错（总基线 §11.3：后端能力不可用时主动摘除）。
    """
    from mcp.types import ToolAnnotations

    from ..tools.handlers import method_name_for
    from .error_mapping import wrap_tool

    registered: list[str] = []
    for spec in surfaces.visible(capabilities):
        fn = getattr(handlers, method_name_for(spec.name), None)
        if fn is None:
            raise AttributeError(
                f"工具 {spec.name} 在 ToolHandlers 上没有对应方法 "
                f"{method_name_for(spec.name)}"
            )
        server.add_tool(
            wrap_tool(fn),
            name=spec.name,
            title=spec.title,
            description=spec.description_with_latency,
            annotations=ToolAnnotations(
                title=spec.title,
                read_only_hint=spec.read_only,
                destructive_hint=spec.destructive,
                idempotent_hint=spec.idempotent,
                open_world_hint=spec.open_world,
            ),
        )
        registered.append(spec.name)
    return registered


def spec_for(tool_name: str) -> ToolSpec:
    spec = SPECS_BY_NAME.get(tool_name)
    if spec is None:
        raise KeyError(f"未登记的工具：{tool_name}")
    return spec
