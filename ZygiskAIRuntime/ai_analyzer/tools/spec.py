# -*- coding: utf-8 -*-
"""Tool 契约模型。

依据：总基线 §11 Tool Surface Manager · §11.5 工具四件套 · §11.7 Token 预算。

每个工具必备四件套：name / title / description + inputSchema + outputSchema + annotations。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..protocol.commands import COMMANDS


class Surface(str, Enum):
    """工具分面。Core 常驻 ≤25，Expert 按需动态挂载。"""

    CORE = "core"
    EXPERT = "expert"


class Latency(str, Enum):
    """耗时档位。必须在 description 里告诉 AI，否则它会盲等。"""

    FAST = "fast"        # < 1s
    MEDIUM = "medium"    # < 30s
    SLOW = "slow"        # < 5min

    @property
    def label(self) -> str:
        return {"fast": "快 <1s", "medium": "中 <30s", "slow": "慢 <5min"}[self.value]


@dataclass(frozen=True)
class ToolSpec:
    """一个 MCP 工具的完整规格。"""

    name: str
    title: str
    description: str
    command: str
    surface: Surface
    latency: Latency
    read_only: bool
    destructive: bool
    idempotent: bool
    open_world: bool = False
    group: str = ""
    """Expert 分面所属组名（Device+ / APK+ / Memory+ …）。Core 为空。"""
    requires: tuple[tuple[str, str], ...] = ()
    """能力依赖 [(能力组, 能力名), ...]。任一不满足即从可见集摘除。"""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.command not in COMMANDS:
            raise ValueError(f"{self.name}: 命令 {self.command} 不在 commands.COMMANDS 中")
        if self.surface is Surface.CORE and self.group:
            raise ValueError(f"{self.name}: Core 工具不应有 group")
        if self.surface is Surface.EXPERT and not self.group:
            raise ValueError(f"{self.name}: Expert 工具必须声明 group")

    @property
    def annotations(self) -> dict[str, bool]:
        """MCP annotations 四件套，全部显式给出。"""
        return {
            "readOnlyHint": self.read_only,
            "destructiveHint": self.destructive,
            "idempotentHint": self.idempotent,
            "openWorldHint": self.open_world,
        }

    @property
    def description_with_latency(self) -> str:
        """description 必须自带耗时档位。"""
        return f"[{self.latency.label}] {self.description}"

    def capability_gaps(self, capabilities: dict[str, dict[str, bool]]) -> list[str]:
        """返回未满足的能力依赖。空列表表示能力齐备。"""
        gaps = []
        for group, key in self.requires:
            if not capabilities.get(group, {}).get(key, False):
                gaps.append(f"{group}.{key}")
        return gaps


# ---------------------------------------------------------------------------
# JSON Schema 片段
# ---------------------------------------------------------------------------

ADDRESS = {
    "type": "string",
    "pattern": r"^0x[0-9a-fA-F]+$",
    "description": "内存地址，必须是 '0x...' 字符串（不要传 number，避免精度丢失）",
}

ADDRESS_OR_INT = {
    "type": ["string", "integer"],
    "description": "地址，'0x...' 字符串或整数",
}


def obj(
    props: dict[str, Any], required: tuple[str, ...] = (), *, strict: bool = True
) -> dict[str, Any]:
    """构造对象 schema。

    - `strict=True`（inputSchema 用）：`additionalProperties=false`，
      防止两端字段名悄悄漂移。总基线 §11.5 硬要求。
    - `strict=False`（outputSchema 用）：只约束 required 字段与类型，
      允许后端在 payload 里追加诊断字段而不至于让契约测试脆断。
    """
    out: dict[str, Any] = {
        "type": "object",
        "required": list(required),
        "properties": props,
    }
    if strict:
        out["additionalProperties"] = False
    return out


def list_of(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item}


def page_schema(item: dict[str, Any]) -> dict[str, Any]:
    """列表类统一分页结构（总基线 §11.7）。"""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["total", "truncated"],
        "properties": {
            "total": {"type": "integer", "minimum": 0},
            "truncated": {"type": "boolean"},
            "next_cursor": {"type": ["string", "null"]},
            "items": list_of(item),
        },
    }
