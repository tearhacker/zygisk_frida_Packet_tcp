# -*- coding: utf-8 -*-
"""Tool Surface Manager。

依据：总基线 §11.2 Core Surface（常驻 ≤25）· §11.3 Expert Surface（动态挂载）· §11.7 Token 预算。

两条硬规则
----------
1. **不为了省工具数量砍功能**。功能数量 ≠ 常驻工具数量。
   Core 超预算时把工具降级到 Expert 动态挂载，而不是删掉。
2. **后端能力不可用时主动摘除并通知客户端**，不是等 AI 调了才报错。
   摘除必须通知，避免 AI 反复调不存在的工具。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..protocol.constants import MAX_RESIDENT_TOOLS, MAX_TOOLS_HARD_LIMIT
from ..tools.spec import Surface, ToolSpec
from ..tools.specs import ALL_SPECS, CORE_SPECS, EXPERT_GROUPS, EXPERT_SPECS


@dataclass(frozen=True)
class RemovalNotice:
    """工具摘除通知。必须能告诉客户端「为什么没了」。"""

    tool: str
    reason: str
    missing_capabilities: tuple[str, ...] = ()


@dataclass
class SurfaceReport:
    """当前可见集快照。"""

    visible: list[ToolSpec] = field(default_factory=list)
    removed: list[RemovalNotice] = field(default_factory=list)
    mounted_groups: tuple[str, ...] = ()
    core_count: int = 0
    expert_count: int = 0
    over_budget: bool = False

    @property
    def visible_names(self) -> list[str]:
        return [s.name for s in self.visible]

    @property
    def removed_names(self) -> list[str]:
        return [r.tool for r in self.removed]

    def to_dict(self) -> dict:
        return {
            "visible_total": len(self.visible),
            "core": self.core_count,
            "expert": self.expert_count,
            "mounted_groups": list(self.mounted_groups),
            "over_budget": self.over_budget,
            "removed": [
                {
                    "tool": r.tool,
                    "reason": r.reason,
                    "missing_capabilities": list(r.missing_capabilities),
                }
                for r in self.removed
            ],
        }


class SurfaceManager:
    """Core / Expert 分面的唯一管理者。"""

    def __init__(
        self,
        *,
        core: Iterable[ToolSpec] = CORE_SPECS,
        expert: Iterable[ToolSpec] = EXPERT_SPECS,
        mounted_groups: Iterable[str] = (),
        max_resident: int = MAX_RESIDENT_TOOLS,
        hard_limit: int = MAX_TOOLS_HARD_LIMIT,
    ) -> None:
        self._core = tuple(core)
        self._expert = tuple(expert)
        self._mounted: set[str] = set(mounted_groups)
        self._max_resident = max_resident
        self._hard_limit = hard_limit

        names = [s.name for s in self._core + self._expert]
        if len(names) != len(set(names)):
            dupes = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"工具名重复：{dupes}")

    # ------------------------------------------------------------------
    # 分组挂载
    # ------------------------------------------------------------------

    @property
    def all_groups(self) -> tuple[str, ...]:
        return EXPERT_GROUPS

    @property
    def mounted_groups(self) -> tuple[str, ...]:
        return tuple(g for g in EXPERT_GROUPS if g in self._mounted)

    def mount(self, group: str) -> None:
        if group not in EXPERT_GROUPS:
            raise KeyError(f"未知 Expert 组：{group}；可用 {EXPERT_GROUPS}")
        self._mounted.add(group)

    def unmount(self, group: str) -> None:
        self._mounted.discard(group)

    def set_mounted(self, groups: Iterable[str]) -> None:
        unknown = [g for g in groups if g not in EXPERT_GROUPS]
        if unknown:
            raise KeyError(f"未知 Expert 组：{unknown}")
        self._mounted = set(groups)

    def mount_all(self) -> None:
        self._mounted = set(EXPERT_GROUPS)

    def unmount_all(self) -> None:
        self._mounted.clear()

    # ------------------------------------------------------------------
    # 挂载状态快照（供「临时全挂载」类校验使用）
    # ------------------------------------------------------------------

    def mounted_snapshot(self) -> set[str]:
        """取当前挂载组快照。"""
        return set(self._mounted)

    def restore_mounted(self, groups: Iterable[str]) -> None:
        """恢复挂载组。校验代码临时全挂载后**必须**调用，否则会污染真实挂载状态。"""
        self._mounted = set(groups)

    # ------------------------------------------------------------------
    # 可见集
    # ------------------------------------------------------------------

    def _expert_candidates(self) -> tuple[ToolSpec, ...]:
        return tuple(s for s in self._expert if s.group in self._mounted)

    def report(self, capabilities: dict[str, dict[str, bool]] | None = None) -> SurfaceReport:
        """计算当前可见集与摘除清单。

        capabilities 为 None 时不做能力过滤（用于"链路未就绪"的静态视图）。
        """
        caps = capabilities or {}
        filter_caps = capabilities is not None and bool(caps)

        visible: list[ToolSpec] = []
        removed: list[RemovalNotice] = []

        for spec in self._core + self._expert_candidates():
            if filter_caps:
                gaps = spec.capability_gaps(caps)
                if gaps:
                    removed.append(
                        RemovalNotice(
                            tool=spec.name,
                            reason=f"能力不可用：{', '.join(gaps)}",
                            missing_capabilities=tuple(gaps),
                        )
                    )
                    continue
            visible.append(spec)

        core_n = sum(1 for s in visible if s.surface is Surface.CORE)
        expert_n = len(visible) - core_n

        return SurfaceReport(
            visible=visible,
            removed=removed,
            mounted_groups=self.mounted_groups,
            core_count=core_n,
            expert_count=expert_n,
            over_budget=core_n > self._max_resident,
        )

    def visible(self, capabilities: dict[str, dict[str, bool]] | None = None) -> list[ToolSpec]:
        return self.report(capabilities).visible

    def visible_names(self, capabilities: dict[str, dict[str, bool]] | None = None) -> list[str]:
        return [s.name for s in self.visible(capabilities)]

    # ------------------------------------------------------------------
    # 预算自检
    # ------------------------------------------------------------------

    def budget_report(self) -> dict:
        """Core 常驻预算自检。超预算必须降级到 Expert，不能删功能。"""
        core_n = len(self._core)
        return {
            "core_declared": core_n,
            "core_limit": self._max_resident,
            "core_within_budget": core_n <= self._max_resident,
            "expert_declared": len(self._expert),
            "expert_groups": list(EXPERT_GROUPS),
            "total_declared": len(ALL_SPECS),
            "hard_limit": self._hard_limit,
            "within_hard_limit": len(ALL_SPECS) <= self._hard_limit,
        }

    def assert_budget(self) -> None:
        rep = self.budget_report()
        if not rep["core_within_budget"]:
            raise ValueError(
                f"Core Surface 超预算：{rep['core_declared']} > {rep['core_limit']}。"
                "处理方式是把工具降级到 Expert 动态挂载，**不是删掉功能**。"
            )
        if not rep["within_hard_limit"]:
            raise ValueError(
                f"工具总数超硬上限：{rep['total_declared']} > {rep['hard_limit']}"
            )
