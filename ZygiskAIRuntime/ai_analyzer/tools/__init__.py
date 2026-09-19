# -*- coding: utf-8 -*-
"""工具注册层（L5）。

**注册三件套**（新工具静默不暴露的头号根因，总基线 §19.2）
--------------------------------------------------------
新工具必须同时改三处，缺一处就会「代码写了但 AI 看不到」：

    1. 本文件 REGISTERED_TOOL_MODULES      —— 模块被加载
    2. 本文件 _LAZY_IMPORTS                —— payload 可懒加载
    3. ai_analyzer/host/surfaces.py 的可见集 —— 分面可见（由 ToolSpec.surface 派生）

外加：**必须实际跑 `list_tools()` 确认真实暴露**，光看服务端日志不算数。
`tests/mcp/test_tool_surface.py` 会强制校验三处一致 + 实际 list 到。
"""

from __future__ import annotations

import importlib
from typing import Any

from .handlers import ToolHandlers, method_name_for
from .spec import Latency, Surface, ToolSpec
from .specs import (
    ALL_SPECS,
    CORE_SPECS,
    EXPERT_GROUPS,
    EXPERT_SPECS,
    SPECS_BY_NAME,
)

# --- 第 1 处：模块注册 ------------------------------------------------------

REGISTERED_TOOL_MODULES: tuple[str, ...] = (
    "ai_analyzer.tools.specs",
    "ai_analyzer.tools.handlers",
)
"""被加载的工具模块。新增工具模块必须加进来。"""

# --- 第 2 处：懒加载表 ------------------------------------------------------

_LAZY_IMPORTS: dict[str, str] = {
    name: f"ai_analyzer.tools.handlers:ToolHandlers.{method_name_for(name)}"
    for name in SPECS_BY_NAME
}
"""工具名 → 处理函数的懒加载路径。避免门面层一次性 import 全部实现。"""


def resolve_lazy(tool_name: str) -> Any:
    """按懒加载表解析处理函数。"""
    path = _LAZY_IMPORTS.get(tool_name)
    if path is None:
        raise KeyError(f"工具 {tool_name} 未登记在 _LAZY_IMPORTS")
    module_path, _, attr_path = path.partition(":")
    module = importlib.import_module(module_path)
    obj: Any = module
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    return obj


__all__ = [
    "ALL_SPECS",
    "CORE_SPECS",
    "EXPERT_GROUPS",
    "EXPERT_SPECS",
    "SPECS_BY_NAME",
    "REGISTERED_TOOL_MODULES",
    "Latency",
    "Surface",
    "ToolHandlers",
    "ToolSpec",
    "method_name_for",
    "resolve_lazy",
]
