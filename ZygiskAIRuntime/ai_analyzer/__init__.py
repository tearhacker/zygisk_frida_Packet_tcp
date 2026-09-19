# -*- coding: utf-8 -*-
"""MCP 层（PC 侧，不进 Native Runtime）。

Android 侧 Runtime 不需要知道 MCP / LLM 的任何概念，
它只处理 Command / Request / Response / Event。

    protocol/   两端共用的 IPC 契约（常量 / 帧 / 消息 / 错误 / 命令分级）
    bridge/     与 Android 侧的连接管理（HELLO / heartbeat / reconnect / Session）
    mock/       Mock Runtime 后端，无真机时用于端到端验证
    host/       MCP Server：工具注册与分面（Core ≤25 / Expert 动态挂载）
    schemas/    工具参数与事件的 JSON Schema，两端契约的单一源
"""
