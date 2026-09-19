# -*- coding: utf-8 -*-
"""MCP Host 层：门面（server）· 能力（runtime_bridge）· 分面（surfaces）· 装配（registry）。"""

from .registry import bind_tools, spec_for, verify_three_point_registration
from .runtime_bridge import RuntimeBridge
from .server import build_from_endpoint, build_server, describe
from .surfaces import RemovalNotice, SurfaceManager, SurfaceReport

__all__ = [
    "RuntimeBridge",
    "SurfaceManager",
    "SurfaceReport",
    "RemovalNotice",
    "build_from_endpoint",
    "build_server",
    "describe",
    "bind_tools",
    "spec_for",
    "verify_three_point_registration",
]
