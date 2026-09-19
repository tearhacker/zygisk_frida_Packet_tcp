# -*- coding: utf-8 -*-
"""Schema 与黄金样例测试。

黄金样例是**冻结的参考数据**，代码必须满足它，而不是它迁就代码。
本测试同时用 JSON Schema 和 messages.validate() 两套独立路径校验同一批样例，
任意一套不通过即失败。
"""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from ai_analyzer.protocol import messages as M
from ai_analyzer.protocol.constants import MessageType
from ai_analyzer.protocol.errors import ProtocolError

#: 消息类型 → schema 文件名
TYPE_TO_SCHEMA = {
    MessageType.HELLO.value: "hello",
    MessageType.HELLO_ACK.value: "hello_ack",
    MessageType.READY.value: "ready",
    MessageType.REQUEST.value: "request",
    MessageType.RESPONSE.value: "response",
    MessageType.EVENT.value: "event",
    MessageType.PING.value: "ping",
    MessageType.PONG.value: "pong",
    MessageType.ERROR.value: "error",
}

EXPECTED_SCHEMA_FILES = set(TYPE_TO_SCHEMA.values())

EXPECTED_EXAMPLES = {
    "hello",
    "hello_ack",
    "ready",
    "request_runtime_status",
    "response_runtime_status",
    "request_process_list",
    "response_process_list",
    "event_runtime_ready",
    "event_hook_enter",
    "event_hook_leave",
    "event_packet_captured",
    "ping",
    "pong",
}

EXPECTED_ERROR_EXAMPLES = {
    "error_not_ready",
    "error_session_stale",
    "error_protocol_version",
}


# ---------------------------------------------------------------------------
# schema 文件自检
# ---------------------------------------------------------------------------


def test_all_nine_schemas_present(schemas_dir):
    found = {p.stem for p in schemas_dir.glob("*.json")}
    assert found == EXPECTED_SCHEMA_FILES, f"schema 文件不齐：{found ^ EXPECTED_SCHEMA_FILES}"


@pytest.mark.parametrize("name", sorted(EXPECTED_SCHEMA_FILES))
def test_schema_is_valid_json_schema(schemas_dir, name):
    schema = json.loads((schemas_dir / f"{name}.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_schemas_forbid_additional_properties(schemas_dir):
    """每个消息 schema 都必须 additionalProperties=false，防止字段悄悄漂移。"""
    for name in EXPECTED_SCHEMA_FILES:
        schema = json.loads((schemas_dir / f"{name}.json").read_text(encoding="utf-8"))
        assert schema.get("additionalProperties") is False, name


# ---------------------------------------------------------------------------
# 黄金样例齐全性
# ---------------------------------------------------------------------------


def test_expected_examples_present(examples_dir):
    found = {p.stem for p in examples_dir.glob("*.json")}
    assert found == EXPECTED_EXAMPLES, f"黄金样例不齐：{found ^ EXPECTED_EXAMPLES}"


def test_expected_error_examples_present(examples_dir):
    found = {p.stem for p in (examples_dir / "errors").glob("*.json")}
    assert found == EXPECTED_ERROR_EXAMPLES, f"错误样例不齐：{found ^ EXPECTED_ERROR_EXAMPLES}"


# ---------------------------------------------------------------------------
# 双路径校验：JSON Schema + messages.validate
# ---------------------------------------------------------------------------


def test_every_example_passes_both_validators(example_files, schemas_dir):
    assert example_files, "没有找到任何黄金样例"
    for label, msg in sorted(example_files.items()):
        mtype = msg.get("type")
        assert mtype in TYPE_TO_SCHEMA, f"{label}: 未知消息类型 {mtype!r}"

        schema_name = TYPE_TO_SCHEMA[mtype]
        schema = json.loads(
            (schemas_dir / f"{schema_name}.json").read_text(encoding="utf-8")
        )

        errors = sorted(
            Draft202012Validator(schema).iter_errors(msg), key=lambda e: list(e.path)
        )
        assert not errors, (
            f"{label} 未通过 JSON Schema："
            + "; ".join(f"{list(e.path)}: {e.message}" for e in errors)
        )

        try:
            assert M.validate(msg, strict=True) == mtype
        except ProtocolError as exc:  # pragma: no cover - 失败路径
            pytest.fail(f"{label} 未通过 messages.validate：{exc.to_dict()}")


def test_request_response_examples_are_paired(example_files):
    """request_id 必须成对出现，且 response 的 session 与 request 一致。"""
    pairs = [
        ("request_runtime_status", "response_runtime_status"),
        ("request_process_list", "response_process_list"),
    ]
    for req_name, resp_name in pairs:
        req = example_files[req_name]
        resp = example_files[resp_name]
        assert resp["request_id"] == req["request_id"], f"{resp_name} 的 request_id 对不上"
        assert resp["session_id"] == req["session_id"]
        assert resp["timestamp"] >= req["timestamp"]


def test_error_examples_cover_both_layers(example_files):
    layers = {m["error"]["layer"] for k, m in example_files.items() if k.startswith("errors/")}
    assert layers == {"protocol", "execution"}, f"错误样例未覆盖两层：{layers}"


def test_error_examples_have_actionable_next_step(example_files):
    """错误消息必须可行动 —— 只说"操作失败"会让 AI 无限重试。"""
    for label, msg in example_files.items():
        if not label.startswith("errors/"):
            continue
        err = msg["error"]
        assert err["next_step"] and len(err["next_step"]) > 4, label
        assert isinstance(err["retryable"], bool), label


def test_hook_examples_share_hook_id(example_files):
    """HOOK_ENTER / HOOK_LEAVE 必须指向同一个 hook_id，否则关联链断了。"""
    enter = example_files["event_hook_enter"]
    leave = example_files["event_hook_leave"]
    assert enter["payload"]["hook_id"] == leave["payload"]["hook_id"]
    assert enter["tid"] == leave["tid"]
    assert leave["timestamp"] >= enter["timestamp"]


def test_ready_example_reports_https_decrypt_false(example_files):
    """冻结纪律：抓到 HTTPS ≠ 能解密。样例必须如实上报 false。"""
    caps = example_files["ready"]["capabilities"]
    assert caps["network"]["https_capture"] is True
    assert caps["network"]["https_decrypt"] is False


def test_packet_example_does_not_embed_payload(example_files):
    """大对象不进协议 JSON —— 只传 metadata + sha256 或 artifact_id。"""
    payload = example_files["event_packet_captured"]["payload"]
    assert "raw_hex" not in payload
    assert "data" not in payload
    assert "length" in payload
    assert ("artifact_id" in payload) or ("sha256" in payload)


FIXED_IDS = {
    "sess_0000000000a0",
    "sess_0000000000a1",
    "req_0000000000b1",
    "req_0000000000b2",
    "req_0000000000b3",
    "req_0000000000b4",
    "evt_0000000000c1",
    "evt_0000000000c2",
    "evt_0000000000c3",
    "evt_0000000000c4",
    "hook_0000000000d1",
    "pkt_0000000000e1",
    "conn_0000000000f1",
}

FIXED_TS = 1789788000000


def test_examples_use_fixed_ids_and_timestamps(example_files):
    """黄金样例必须是固定值，不能是随机生成的 —— 否则无法作为冻结参考。"""
    for label, msg in sorted(example_files.items()):
        for key in ("request_id", "event_id", "session_id"):
            value = msg.get(key)
            if value is not None:
                assert value in FIXED_IDS, f"{label}.{key} 不是固定样例值：{value}"
        if "timestamp" in msg:
            assert FIXED_TS <= msg["timestamp"] <= FIXED_TS + 100_000, label

    # 嵌套 id 同样要固定
    assert example_files["event_hook_enter"]["payload"]["hook_id"] in FIXED_IDS
    assert example_files["event_packet_captured"]["payload"]["packet_id"] in FIXED_IDS
    assert (
        example_files["event_packet_captured"]["payload"]["connection_id"] in FIXED_IDS
    )
    assert (
        example_files["errors/error_session_stale"]["error"]["context"]["current"]
        in FIXED_IDS
    )
    assert (
        example_files["errors/error_session_stale"]["error"]["context"]["got"]
        in FIXED_IDS
    )

