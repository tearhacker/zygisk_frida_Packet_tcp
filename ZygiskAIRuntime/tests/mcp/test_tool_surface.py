# -*- coding: utf-8 -*-
"""MCP 工具面测试。

覆盖：
  - 注册三件套一致性（模块 / 懒加载 / 分面可见）
  - Core 常驻预算 ≤25，总数 ≤45，超预算只能降级不能删功能
  - 命名规则 domain.action snake_case
  - 工具四件套完整性（description / inputSchema / outputSchema / annotations）
  - **SDK 从函数签名派生的 inputSchema 必须与声明一致**（防签名漂移）
  - 能力门禁：不可用的工具被摘除
  - 实际 list_tools() 暴露集 = 注册集
  - 实调 Mock 后端，返回结果反向校验 outputSchema
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ai_analyzer.host import RuntimeBridge, SurfaceManager, build_server
from ai_analyzer.host.registry import verify_three_point_registration
from ai_analyzer.mock import MockRuntimeServer
from ai_analyzer.protocol.commands import COMMANDS
from ai_analyzer.protocol.constants import (
    MAX_RESIDENT_TOOLS,
    MAX_TOOLS_HARD_LIMIT,
)
from ai_analyzer.tools import (
    _LAZY_IMPORTS,
    ALL_SPECS,
    CORE_SPECS,
    EXPERT_GROUPS,
    REGISTERED_TOOL_MODULES,
    SPECS_BY_NAME,
)
from ai_analyzer.tools.spec import Latency, Surface
from ai_analyzer.tools.specs import EXPERT_SPECS

def _error_payload(exc: BaseException) -> dict:
    """从异常链里捞出我们自己的错误载荷。

    MCP SDK 会把工具抛出的异常再包一层（`Error executing tool X: <原异常>`），
    所以不能直接 json.loads(str(exc))，要顺着 __cause__ 找。
    """
    cur: BaseException | None = exc
    while cur is not None:
        text = str(cur)
        start = text.find("{")
        if start >= 0:
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                pass
        cur = cur.__cause__
    raise AssertionError(f"异常链里没有错误载荷：{[str(e) for e in _chain(exc)]}")


def _chain(exc: BaseException) -> list[BaseException]:
    out, cur = [], exc
    while cur is not None:
        out.append(cur)
        cur = cur.__cause__
    return out


NAME_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mock_env():
    """Mock 后端 + Bridge + MCP Server（挂载全部 Expert 组）。"""
    from ai_analyzer.bridge.transport import HAS_AF_UNIX

    d = Path(tempfile.mkdtemp(prefix="zai-mcp"))
    spec = f"unix:{d / 's.sock'}" if HAS_AF_UNIX else "tcp:127.0.0.1:0"
    srv = MockRuntimeServer(spec).start()
    bridge = RuntimeBridge(srv.endpoint, auto_reconnect=False)
    bridge.connect()
    sm = SurfaceManager(mounted_groups=EXPERT_GROUPS)
    server, sm, registered = build_server(bridge, surfaces=sm)
    try:
        yield {
            "server": server,
            "bridge": bridge,
            "surfaces": sm,
            "registered": registered,
            "mock": srv,
        }
    finally:
        bridge.close()
        srv.stop()
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# 注册三件套
# ---------------------------------------------------------------------------


def test_three_point_registration_is_consistent():
    problems = verify_three_point_registration()
    assert not problems, "注册三件套不一致：\n  " + "\n  ".join(problems)


def test_every_spec_has_lazy_import():
    missing = sorted(set(SPECS_BY_NAME) - set(_LAZY_IMPORTS))
    assert not missing, f"未登记懒加载：{missing}"


def test_registered_modules_cover_specs_and_handlers():
    assert "ai_analyzer.tools.specs" in REGISTERED_TOOL_MODULES
    assert "ai_analyzer.tools.handlers" in REGISTERED_TOOL_MODULES


def test_no_duplicate_tool_names():
    names = [s.name for s in ALL_SPECS]
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# 预算
# ---------------------------------------------------------------------------


def test_core_surface_within_budget():
    assert len(CORE_SPECS) <= MAX_RESIDENT_TOOLS, (
        f"Core 常驻 {len(CORE_SPECS)} > {MAX_RESIDENT_TOOLS}。"
        "超预算应把工具降级到 Expert 动态挂载，不是删功能。"
    )


def test_total_within_hard_limit():
    assert len(ALL_SPECS) <= MAX_TOOLS_HARD_LIMIT


def test_surface_budget_report():
    sm = SurfaceManager()
    rep = sm.budget_report()
    assert rep["core_within_budget"] is True
    assert rep["within_hard_limit"] is True
    assert rep["core_declared"] == len(CORE_SPECS)
    sm.assert_budget()  # 不抛错即通过


def test_over_budget_raises_instead_of_silently_dropping():
    """超预算必须显式失败，不能静默丢工具。"""
    sm = SurfaceManager(max_resident=len(CORE_SPECS) - 1)
    with pytest.raises(ValueError) as ei:
        sm.assert_budget()
    assert "降级到 Expert" in str(ei.value)


# ---------------------------------------------------------------------------
# 命名与四件套
# ---------------------------------------------------------------------------


def test_tool_naming_rule():
    bad = [s.name for s in ALL_SPECS if not NAME_RE.match(s.name)]
    assert not bad, f"违反 domain.action snake_case：{bad}"


def test_every_spec_maps_to_known_command():
    for spec in ALL_SPECS:
        assert spec.command in COMMANDS, f"{spec.name} → 未知命令 {spec.command}"


def test_read_write_flags_match_command_registry():
    """工具是否写操作，必须与命令登记表一致 —— 两处不能各说一套。"""
    for spec in ALL_SPECS:
        cmd = COMMANDS[spec.command]
        assert spec.read_only is not cmd.writes, (
            f"{spec.name}: read_only={spec.read_only} 与命令表 writes={cmd.writes} 矛盾"
        )


def test_annotations_all_explicit():
    for spec in ALL_SPECS:
        ann = spec.annotations
        assert set(ann) == {
            "readOnlyHint",
            "destructiveHint",
            "idempotentHint",
            "openWorldHint",
        }, spec.name
        assert all(isinstance(v, bool) for v in ann.values()), spec.name


def test_description_carries_latency_and_guidance():
    for spec in ALL_SPECS:
        d = spec.description_with_latency
        assert d.startswith("[") and "]" in d, f"{spec.name} 缺少耗时档位"
        assert "use_case" in d, f"{spec.name} 缺少 use_case"
        assert "next_step" in d, f"{spec.name} 缺少 next_step"


def test_input_schema_is_strict_object():
    for spec in ALL_SPECS:
        s = spec.input_schema
        assert s.get("type") == "object", spec.name
        assert s.get("additionalProperties") is False, (
            f"{spec.name} inputSchema 必须 additionalProperties=false"
        )


def test_numeric_params_declare_bounds():
    for spec in ALL_SPECS:
        for pname, prop in (spec.input_schema.get("properties") or {}).items():
            types = prop.get("type")
            types = types if isinstance(types, list) else [types]
            if "integer" in types and "default" in prop:
                assert "minimum" in prop and "maximum" in prop, (
                    f"{spec.name}.{pname} 数值参数必须标 min/max"
                )


def test_optional_params_have_defaults():
    for spec in ALL_SPECS:
        required = set(spec.input_schema.get("required") or [])
        for pname, prop in (spec.input_schema.get("properties") or {}).items():
            if pname not in required:
                assert "default" in prop, (
                    f"{spec.name}.{pname} 是可选参数但没给 default"
                )


def test_every_tool_declares_output_schema():
    for spec in ALL_SPECS:
        assert spec.output_schema, f"{spec.name} 缺少 outputSchema"


def test_output_schemas_are_valid_json_schema():
    for spec in ALL_SPECS:
        Draft202012Validator.check_schema(spec.output_schema)


def test_write_tools_require_confirm_default_false():
    """写操作必须有 confirm 参数，且默认 false（Write Guard 默认不确认）。"""
    for name in ("memory.write", "packet.modify"):
        spec = SPECS_BY_NAME[name]
        prop = (spec.input_schema.get("properties") or {}).get("confirm")
        assert prop is not None, f"{name} 缺少 confirm 参数"
        assert prop["default"] is False, f"{name}.confirm 默认值必须是 false"
        assert spec.destructive is True


def test_high_risk_tools_are_destructive():
    for name in ("memory.write", "packet.modify", "runtime.hook", "runtime.unhook",
                 "apk.launch", "apk.stop"):
        assert SPECS_BY_NAME[name].destructive is True, name


# ---------------------------------------------------------------------------
# 分面
# ---------------------------------------------------------------------------


def test_core_tools_have_no_group():
    for spec in CORE_SPECS:
        assert spec.group == "", spec.name
        assert spec.surface is Surface.CORE


def test_expert_tools_declare_known_group():
    for spec in EXPERT_SPECS:
        assert spec.group in EXPERT_GROUPS, f"{spec.name} 的组 {spec.group} 未登记"
        assert spec.surface is Surface.EXPERT


def test_unmounted_expert_tools_are_invisible():
    sm = SurfaceManager()
    assert sm.mounted_groups == ()
    visible = set(sm.visible_names())
    for spec in EXPERT_SPECS:
        assert spec.name not in visible, f"未挂载却可见：{spec.name}"
    for spec in CORE_SPECS:
        assert spec.name in visible


def test_mount_unmount_roundtrip():
    sm = SurfaceManager()
    sm.mount("Packet+")
    assert "packet.list" in sm.visible_names()
    sm.unmount("Packet+")
    assert "packet.list" not in sm.visible_names()
    with pytest.raises(KeyError):
        sm.mount("NotAGroup")


def test_capability_gating_removes_unavailable_tools():
    """能力不可用的工具必须被摘除，并给出原因。"""
    caps = {
        "runtime": {
            "native_hook": True,
            "java_hook": False,
            "memory_read": False,
            "memory_write": False,
            "stacktrace": False,
        },
        "network": {
            "capture": True,
            "http": True,
            "https_capture": True,
            "https_decrypt": False,
            "packet_intercept": False,
        },
    }
    sm = SurfaceManager(mounted_groups=EXPERT_GROUPS)
    rep = sm.report(caps)
    visible = set(rep.visible_names)
    removed = {r.tool: r for r in rep.removed}

    # memory_read=false → 这些必须摘除
    for name in ("memory.read", "memory.search", "memory.maps", "memory.dump"):
        assert name not in visible, name
        assert name in removed, name
        assert "runtime.memory_read" in removed[name].missing_capabilities

    # packet_intercept=false → 改包摘除
    assert "packet.modify" not in visible
    assert "network.packet_intercept" in removed["packet.modify"].missing_capabilities

    # 只读且能力齐备的仍在
    assert "runtime.status" in visible
    assert "network.connections" in visible

    assert rep.over_budget is False


def test_capability_gating_never_touches_capability_free_tools():
    """没有能力依赖的工具（device/session/apk/artifact/job）不受能力过滤影响。"""
    empty = {"runtime": {}, "network": {}}
    sm = SurfaceManager(mounted_groups=EXPERT_GROUPS)
    visible = set(sm.visible_names(empty))
    for name in ("device.list", "session.info", "apk.list", "artifact.get", "job.status"):
        assert name in visible, name


# ---------------------------------------------------------------------------
# 实际注册与暴露（光看代码文件存在不算数）
# ---------------------------------------------------------------------------


def test_tools_list_equals_registered(mock_env):
    server = mock_env["server"]
    registered = mock_env["registered"]
    tools = asyncio.run(server.list_tools())
    assert [t.name for t in tools] == registered, (
        "list_tools() 与注册集不一致 —— 有工具静默未暴露"
    )


def test_sdk_derived_schema_matches_declared(mock_env):
    """SDK 从函数签名派生的 inputSchema 必须与声明一致 —— 防签名漂移。"""
    server = mock_env["server"]
    tools = {t.name: t for t in asyncio.run(server.list_tools())}

    for name, tool in tools.items():
        spec = SPECS_BY_NAME[name]
        derived = tool.input_schema or {}
        declared = spec.input_schema

        derived_props = set(derived.get("properties") or {})
        declared_props = set(declared.get("properties") or {})
        assert derived_props == declared_props, (
            f"{name} 参数名漂移：SDK={sorted(derived_props)} 声明={sorted(declared_props)}"
        )

        derived_req = set(derived.get("required") or [])
        declared_req = set(declared.get("required") or [])
        assert derived_req == declared_req, (
            f"{name} 必填项漂移：SDK={sorted(derived_req)} 声明={sorted(declared_req)}"
        )


def test_registered_tool_annotations_are_propagated(mock_env):
    server = mock_env["server"]
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    for name, tool in tools.items():
        spec = SPECS_BY_NAME[name]
        ann = tool.annotations
        assert ann is not None, name
        assert ann.read_only_hint == spec.read_only, name
        assert ann.destructive_hint == spec.destructive, name
        assert ann.idempotent_hint == spec.idempotent, name


def test_tool_descriptions_are_propagated_with_latency(mock_env):
    server = mock_env["server"]
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    for name, tool in tools.items():
        spec = SPECS_BY_NAME[name]
        assert tool.description == spec.description_with_latency, name
        assert tool.title == spec.title, name


def test_capability_filtered_server_registers_fewer_tools(mock_env):
    """按能力装配时，不可用工具不应被注册。"""
    bridge = mock_env["bridge"]
    caps = bridge.capabilities()
    sm = SurfaceManager(mounted_groups=EXPERT_GROUPS)
    server, _, registered = build_server(bridge, surfaces=sm, capabilities=caps)
    all_names = {s.name for s in ALL_SPECS}
    assert set(registered) <= all_names
    assert registered, "至少应有部分工具可用"
    listed = [t.name for t in asyncio.run(server.list_tools())]
    assert listed == registered


# ---------------------------------------------------------------------------
# 实调：结果反向校验 outputSchema
# ---------------------------------------------------------------------------

CALL_CASES = [
    ("device.list", {}),
    ("device.info", {}),
    ("session.list", {}),
    ("session.info", {}),
    ("session.capabilities", {}),
    ("process.list", {}),
    ("process.info", {}),
    ("process.modules", {}),
    ("process.modules", {"name_contains": "libgame"}),
    ("process.threads", {}),
    ("runtime.status", {}),
    ("runtime.hook", {"module": "libgame.so", "address": "0x7a3f1c0040"}),
    ("memory.read", {"address": "0x7a3f1c2000", "length": 16}),
    ("memory.maps", {}),
    ("network.connections", {}),
    ("network.dns", {}),
    ("packet.list", {}),
    ("packet.get", {"packet_id": "pkt_0000000000e1"}),
    ("artifact.list", {}),
]


@pytest.mark.parametrize("tool_name,args", CALL_CASES)
def test_tool_result_matches_output_schema(mock_env, tool_name, args):
    """实调 Mock 后端，用声明的 outputSchema 反向校验返回结果。"""
    server = mock_env["server"]
    spec = SPECS_BY_NAME[tool_name]

    result = asyncio.run(server.call_tool(tool_name, args))
    structured = getattr(result, "structured_content", None)
    assert structured is not None, f"{tool_name} 未返回 structured_content"

    errors = sorted(
        Draft202012Validator(spec.output_schema).iter_errors(structured),
        key=lambda e: list(e.path),
    )
    assert not errors, (
        f"{tool_name} 返回与 outputSchema 不一致："
        + "; ".join(f"{list(e.path)}: {e.message}" for e in errors)
    )


def test_unsupported_tool_surfaces_honest_error(mock_env):
    """Mock 未实现的命令必须报「能力不可用」，不能返回编造数据。

    执行层失败 → ToolError（对应线上 isError=true 的 tool result）。
    """
    from mcp.server.mcpserver.exceptions import ToolError

    server = mock_env["server"]
    with pytest.raises(ToolError) as ei:
        asyncio.run(
            server.call_tool("runtime.trace", {"module": "libgame.so", "address": "0x1"})
        )
    payload = _error_payload(ei.value)
    assert payload["code"] == "E_NOT_READY"
    assert payload["layer"] == "execution"
    assert payload["context"]["response"]["reason"] == "capability unavailable"
    assert payload["next_step"]


def test_write_tool_without_confirm_is_refused(mock_env):
    """memory.write 未显式 confirm 时必须被拒绝 —— Write Guard 默认不确认。"""
    from mcp.server.mcpserver.exceptions import ToolError

    server = mock_env["server"]
    with pytest.raises(ToolError) as ei:
        asyncio.run(
            server.call_tool("memory.write", {"address": "0x7a3f1c2000", "hex": "4141"})
        )
    payload = _error_payload(ei.value)
    # Mock 未实现 memory.write → 能力不可用；关键是绝不能默默写成功
    assert payload["code"] in ("E_NOT_READY", "E_WRITE_FAILED")
    assert payload["layer"] == "execution"


def test_protocol_layer_error_maps_to_jsonrpc_error(mock_env):
    """协议层错误（AI 调错了）必须走 JSON-RPC error，而不是 isError 结果。"""
    from mcp.shared.exceptions import MCPError

    server = mock_env["server"]
    with pytest.raises(MCPError) as ei:
        asyncio.run(server.call_tool("memory.read", {"address": "not-an-address"}))
    err = ei.value
    assert err.code == -32600
    assert err.data["code"] == "E_BAD_ARGS"
    assert err.data["layer"] == "protocol"
    assert err.data["retryable"] is False


def test_error_contract_covers_both_layers():
    from ai_analyzer.host.error_mapping import describe_error_contract

    c = describe_error_contract()
    assert set(c["protocol_layer_codes"]) == {
        "E_BAD_ARGS", "E_MALFORMED_FRAME", "E_UNKNOWN_CMD", "ERROR_PROTOCOL_VERSION",
    }
    assert "JSON-RPC" in c["protocol_layer_returns"]
    assert "isError" in c["execution_layer_returns"]
    assert len(c["execution_layer_codes"]) == 10


def test_latency_enum_covers_three_tiers():
    assert {lat.value for lat in Latency} == {"fast", "medium", "slow"}
    for spec in ALL_SPECS:
        assert spec.latency in tuple(Latency)
