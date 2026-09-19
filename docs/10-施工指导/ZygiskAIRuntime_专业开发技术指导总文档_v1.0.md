# ZygiskAIRuntime 专业开发技术指导总文档 v1.0

**用途：交给 WorkBuddy AI 作为长期开发执行总规约**

**文档定位：开发路线、实施顺序、技术研究顺序、验收方法、代码交付纪律、优化与深入研究路线。**

**当前原则：不重新设计已经冻结的总体架构，不为了"看起来完整"而制造假功能。先把工程真正跑起来，再逐层扩大能力。**

------------------------------------------------------------------------

## 0. 文档使用规则

这份文档不是产品介绍，也不是单纯的 API
说明，而是整个项目的**施工顺序说明书**。

WorkBuddy AI 后续写代码时必须遵循：

1.  先阅读本项目总基线、STRUCTURE、SOURCE_LOCK、LICENSES
    和本开发指导文档。
2.  不自行重新设计已经冻结的架构。
3.  不因为某个功能暂时做不到就偷偷改成模拟实现。
4.  不把 Frida、LSPlant、PCAPdroid、mitmproxy 等第三方能力直接暴露给上层
    AI。
5.  不跨越阶段开发。
6.  每完成一个阶段，必须先验证，再进入下一阶段。
7.  所有"成功"必须对应真实执行证据。
8.  如果环境、源码、版本、许可证、API
    或真机条件不满足，先报告阻塞点，不允许用假代码绕过。
9.  修改协议时，先修改协议文档和 Golden Sample，再修改双方代码。
10. 修改架构边界时，必须先停止编码并回到架构评审。

------------------------------------------------------------------------

# 1. 当前项目真实状态

当前工程不是从零开始，而是处于：

> **架构冻结 + 供应链准备 + 工程骨架完成 + 尚未完成首次编译和真机验证**

当前清单记录：

-   自有文件：81 个
-   自有 C/C++：22 个文件、约 1215 行
-   `third_party`：约 34MB
-   `external`：约 274MB
-   已编译次数：0
-   NDK/CMake 当前仍是实际落地阻塞项
-   `native/` 实现与 `tests/{native,runtime,semantic}` 仍为待填状态；
    Host 侧（`ai_analyzer/`）与 `tests/{protocol,integration,mcp}` 已落地并通过验收
-   `module/zygisk/arm64-v8a.so` 当前不存在

因此，当前最重要的目标不是"马上实现 Hook"，而是：

> **把设计态工程逐步转化成能够编译、加载、运行、通信、验证的真实工程。**

------------------------------------------------------------------------

# 2. 总体施工路线

项目严格按以下顺序推进：

``` text
P-1 落地准备审计
        ↓
M0 协议 / Schema / Golden Samples
        ↓
M1 构建系统与依赖真正编译
        ↓
M2 Zygisk + Runtime + IPC + Session
        ↓
M3 Frida-Gum Native Runtime + Native Hook
        ↓
M3.5 LSPlant ART / Java Hook
        ↓
M4 Memory + Network + HTTP
        ↓
M4.5 HTTPS 五级能力验证
        ↓
M5 Packet / HEX / Correlation / Artifact
        ↓
M5.5 MCP 全工具面
        ↓
M6 真机稳定性 / 兼容性 / 性能 / 安全
        ↓
Release Candidate
        ↓
持续优化与深入研究
```

这里增加 `P-1` 和
`M3.5/M4.5/M5.5`，不是改变原架构，而是把实际开发过程拆得更细，防止
WorkBuddy 一次跨太多层。

------------------------------------------------------------------------

# 3. 第一阶段 P-1：落地前准备审计

## 3.1 目标

这一阶段**原则上不写业务代码**。

只确认：

``` text
项目文件
第三方源码
版本
许可证
构建工具
Android SDK
Android NDK
CMake
Ninja
Meson
Python
Git
ADB
真机
Magisk
Zygisk
```

全部是否满足后续开发要求。

## 3.2 工程文件审计

检查：

``` text
ZygiskAIRuntime/
├── zygisk/
├── runtime/
├── native/
├── third_party/
├── module/
├── ai_analyzer/
├── build/
├── scripts/
├── tools/
├── docs/
└── tests/
```

要求：

-   目录结构与 STRUCTURE.md 一致。
-   `third_party/` 只有锁定的核心依赖。
-   外部源码位于 `../external/`。
-   不把 GPL 项目复制进核心 Runtime。
-   不修改上游第三方源码。
-   所有脚本引用的路径真实存在。
-   所有 README 中的路径和实际路径一致。

## 3.3 供应链审计

逐项确认：

### Android Runtime

-   Magisk
-   Zygisk API
-   Zygisk Module Sample

### Native Runtime

-   Frida-Gum 17.18.0
-   LSPlant

### Host / Analysis

-   JADX
-   Apktool
-   Rizin
-   r2frida
-   MobSF

### Network

-   PCAPdroid
-   mitmproxy
-   NetBare
-   Wireshark

### MCP

-   MCP Python SDK
-   MCP Specification

每一个依赖都必须有：

``` text
名称
版本
来源
许可证
实际目录
是否核心依赖
是否独立进程
是否允许静态链接
是否允许动态链接
```

## 3.4 工具链审计

建立环境检查表：

``` text
Android SDK       PASS/FAIL
Android NDK       PASS/FAIL
CMake             PASS/FAIL
Ninja             PASS/FAIL
Python            PASS/FAIL
Git               PASS/FAIL
Meson             PASS/FAIL
adb               PASS/FAIL
Java/JDK          PASS/FAIL
Gradle            PASS/FAIL
```

如果任何关键工具缺失：

> **停止后续 M1。**

不要通过"临时脚本""下载一个预编译 DLL""复制别人 build
目录"来伪装环境已经准备好。

## 3.5 真机审计

需要确认：

``` text
设备可连接
adb devices 正常
ARM64
Android SDK/API
Android 版本
Magisk
Zygisk
目标 APK
日志获取
模块安装
模块卸载
```

同时记录：

``` text
设备型号
Android 版本
API Level
ABI
16KB page size 支持情况
Magisk 版本
Zygisk 状态
```

不要只依赖单一测试设备。第一阶段可以先用一台主力设备，但 M6
必须扩展兼容性矩阵。

## 3.6 P-1 交付物

必须形成：

``` text
docs/20-构建与审计/ENVIRONMENT.md
docs/20-构建与审计/SUPPLY_CHAIN_CHECK.md
docs/20-构建与审计/DEVICE_MATRIX.md
docs/20-构建与审计/BUILD_BLOCKERS.md
```

并输出：

``` text
P-1 READY
```

只有 READY 才能进入 M0/M1。

------------------------------------------------------------------------

# 4. M0：协议、Schema、Golden Sample

M0 的目标不是实现 MCP，而是先让 Android Runtime 和 PC
端拥有同一份"语言"。

## 4.1 先写什么

优先顺序：

``` text
protocol.md
constants.py / Android constants
message schemas
command schemas
error schemas
event schemas
Golden Samples
protocol tests
```

## 4.2 协议核心

冻结：

``` text
PROTOCOL_VERSION = 1.0
FRAME_HEADER = 4 bytes uint32
HEARTBEAT_INTERVAL = 5s
HEARTBEAT_TIMEOUT = 30s
FAST_COMMAND_TIMEOUT = 10s
JOB_COMMAND_TIMEOUT = 300s
SESSION_IDLE_TIMEOUT = 600s
MAX_RESPONSE_TOKENS = 4096
```

Frame：

``` text
4-byte length
+
JSON payload
```

长度使用 network byte order。

## 4.3 生命周期

``` text
CONNECT
  ↓
HELLO
  ↓
HELLO_ACK
  ↓
READY
  ↓
REQUEST / RESPONSE / EVENT
```

版本不匹配：

``` text
ERROR_PROTOCOL_VERSION
```

并且不能进入 READY。

## 4.4 心跳

``` text
PING → PONG
```

状态：

``` text
CONNECTED
   ↓ timeout
DEGRADED
   ↓ consecutive timeout
DISCONNECTED
```

重连：

``` text
1s
2s
4s
8s
16s
30s max
```

重连以后：

> 旧 Session 全部失效。

不能偷偷恢复旧 Session。

## 4.5 Golden Samples

至少准备：

``` text
hello.json
hello_ack.json
ready.json
request_runtime_status.json
response_runtime_status.json
request_process_list.json
event_runtime_ready.json
event_hook_enter.json
event_hook_leave.json
event_packet_captured.json
error_not_ready.json
error_session_stale.json
ping.json
pong.json
```

Golden Sample 必须被：

``` text
Android IPC
PC Bridge
MCP Server
Protocol Test
```

共同使用。

------------------------------------------------------------------------

# 5. M1：真正建立编译能力

M1 是项目第一次从"文档/骨架"进入"真实二进制"。

## 5.1 第一目标

不是 Hook。

不是 AI。

不是网络。

第一目标只有：

> **成功生成 `libai_analyzer.so`。**

## 5.2 Frida-Gum 单独构建

先不要把整个项目一起编译。

单独验证：

``` text
Frida-Gum source
        ↓
Android arm64
        ↓
libgum.a
```

必须解决：

-   Meson
-   Android cross file
-   NDK toolchain
-   15 个 `.wrap` 子项目
-   依赖获取
-   编译参数
-   arm64
-   static library
-   reproducibility

如果这里失败：

> 先解决 Frida-Gum，不进入 Runtime 功能开发。

## 5.3 LSPlant 单独构建

验证：

``` text
LSPlant
   ↓
Android
   ↓
C++20 modules / C++23
   ↓
liblsplant.so
```

重点检查：

-   CMake 版本
-   NDK
-   C++ 标准
-   module 编译
-   shared library
-   Android 15+
-   16KB page size

## 5.4 本项目 Native 构建

最后：

``` text
zygisk/
runtime/
native/
Frida-Gum
LSPlant
        ↓
libai_analyzer.so
```

验证：

``` text
ELF
ABI
SONAME
依赖
RPATH/加载策略
符号
strip
debug/release
```

## 5.5 M1 DoD

必须满足：

``` text
[PASS] Frida-Gum 编译
[PASS] LSPlant 编译
[PASS] Native 编译
[PASS] libai_analyzer.so 生成
[PASS] Magisk zip 生成
[PASS] 安装脚本可执行
```

没有这些，不进入 M2。

------------------------------------------------------------------------

# 6. M2：Zygisk + Runtime + IPC + Session

这是第一个完整"活起来"的阶段。

## 6.1 Zygisk 的职责

Zygisk 只负责：

``` text
Entry
 ↓
目标进程过滤
 ↓
Bootstrap
 ↓
Runtime 启动
```

不得把：

``` text
Hook
Memory
Network
AI
MCP
```

写进 Zygisk 层。

## 6.2 Runtime Bootstrap

Runtime 必须能够获得：

``` text
package
pid
uid
abi
sdk
process name
session
```

启动日志统一：

``` text
ZAI:
```

## 6.3 IPC

实现：

``` text
UDS
length prefix
JSON
HELLO
HELLO_ACK
READY
PING/PONG
REQUEST
RESPONSE
EVENT
```

先实现最小命令：

``` text
runtime.status
process.list
process.info
process.modules
process.threads
```

## 6.4 Session

状态：

``` text
CREATED
STARTING
RUNTIME_READY
NETWORK_READY
RUNNING
PAUSED
STOPPING
CLOSED
DEGRADED
FAILED
ERROR
```

Session 是唯一状态边界。

不要让：

``` text
Hook Manager
Memory Manager
Network
MCP
```

各自创建自己的 Session。

## 6.5 M2 真机验收

真实流程：

``` text
安装模块
 ↓
启动 APK
 ↓
Zygisk 进入
 ↓
Runtime 启动
 ↓
IPC
 ↓
HELLO
 ↓
READY
 ↓
MCP
 ↓
runtime.status
 ↓
真实返回
```

然后杀掉 App：

``` text
Session DEGRADED
 ↓
cleanup
 ↓
CLOSED
```

重连：

``` text
新 Session B
```

旧 Session A 不得复活。

------------------------------------------------------------------------

# 7. M3：Frida-Gum Native Runtime

这一阶段才开始真正的动态 Hook。

## 7.1 Backend 隔离

上层：

``` text
Hook Manager
```

不能知道：

``` text
gum_interceptor
gum_invocation_context
```

这些具体 API。

调用链：

``` text
runtime.hook
 ↓
Hook Manager
 ↓
Gum Backend
 ↓
Frida-Gum
```

## 7.2 gum_backend 的边界

工程规则：

> `gum_*` 只能出现在 `runtime/backend/gum/gum_backend.cpp`。

其他模块不能直接：

``` cpp
#include <gum/...>
```

## 7.3 第一个 Hook

不要一开始实现复杂 Hook DSL。

先做：

``` text
指定模块
+
指定地址
+
安装 Hook
+
ENTER
+
LEAVE
```

事件必须带：

``` text
hook_id
session_id
pid
tid
timestamp
module
address
arguments
backtrace
```

## 7.4 Hook 状态

``` text
pending
 ↓
active
 ↓
disabled
 ↓
active
 ↓
removed
```

失败：

``` text
failed
```

## 7.5 Hook 真成功的定义

不能：

``` text
调用 install()
→ 返回 true
→ 就认为成功
```

真正成功至少需要：

``` text
HOOK_INSTALLED
+
HOOK_ENTER
+
HOOK_LEAVE
```

否则只能报告：

``` text
accepted / installed_pending
```

不能伪装成已经生效。

------------------------------------------------------------------------

# 8. M3.5：LSPlant / ART / Java Hook

Native Hook 成功后，再进入 Java/ART。

## 8.1 层次

``` text
ART Backend
 ↓
LSPlant Adapter
 ↓
LSPlant
 ↓
ART
```

只有：

``` text
lsplant_adapter.cpp
```

允许直接使用：

``` text
lsplant::
```

## 8.2 SDK 分级

必须设计：

``` text
Android SDK
 ↓
capability detection
 ↓
supported
degraded
unsupported
```

不要因为某个 Android 版本不同就整个 Runtime 崩溃。

## 8.3 Java Hook

第一阶段只验证：

``` text
类
方法
参数
返回值
调用线程
调用栈
```

然后逐步增加：

``` text
参数修改
返回值修改
异常场景
多线程
重载方法
类加载时机
```

------------------------------------------------------------------------

# 9. M4：Memory Engine

## 9.1 Read

实现：

``` text
memory.read
```

必须验证：

``` text
address
length
mapped
permission
read
```

返回：

``` text
address
length
hex
```

## 9.2 Write

`memory.write` 是高风险操作。

固定流程：

``` text
REQUEST
 ↓
VALIDATE
 ↓
PREVIEW
 ↓
BACKUP
 ↓
CONFIRM
 ↓
EXECUTE
 ↓
VERIFY
 ↓
COMMIT
```

失败：

``` text
ROLLBACK
```

## 9.3 WriteResult

至少区分：

``` text
accepted
executed
verified
```

成功必须返回：

``` text
original
new
verified
```

不要只返回：

``` text
success=true
```

## 9.4 Search / Dump / Compare

顺序：

``` text
read
 ↓
write
 ↓
search
 ↓
compare
 ↓
dump
 ↓
pointer
```

Dump 等大数据走 Artifact Manager。

------------------------------------------------------------------------

# 10. M4.5：Network Plane

Runtime 与 Network 是两个并行观察面。

``` text
Runtime Plane
    ↕
EventBus
    ↕
Correlation
    ↕
Network Plane
```

## 10.1 Network Adapter

适配：

``` text
PCAPdroid
mitmproxy
VPNAdapter
RuntimeNetworkAdapter
```

GPL 项目不能直接塞进核心 so。

## 10.2 Capture

首先实现：

``` text
network.capture_start
network.connections
network.capture_stop
```

验证真实：

``` text
DNS
TCP
UDP
HTTP
HTTPS
WebSocket
```

## 10.3 HTTP

先完成：

``` text
request
response
headers
body
connection
timestamp
```

大 body：

``` text
Artifact Manager
```

不要把完整 body 塞进 MCP JSON。

------------------------------------------------------------------------

# 11. HTTPS 必须严格分五级

这是项目的重要防误判规则。

能力状态：

``` text
captured
decoded
decrypted
interceptable
modifiable
```

不能因为：

``` text
“抓到了 HTTPS”
```

就告诉 AI：

``` text
“已经解密”
```

更不能告诉 AI：

``` text
“可以修改”
```

每一级都必须有自己的证据。

例如：

``` text
captured
= 看到了连接/包

decoded
= 协议结构能够解析

decrypted
= 明文内容真实获得

interceptable
= 可以在指定点暂停/修改

modifiable
= 修改后真实到达下一阶段
```

------------------------------------------------------------------------

# 12. Packet / HEX Modify

数据流程固定：

``` text
原始 Packet
 ↓
Decode
 ↓
original_hex
 ↓
Modify
 ↓
modified_hex
 ↓
length validation
 ↓
protocol validation
 ↓
confirm
 ↓
send
 ↓
verify
```

必须保留：

``` text
original_hex
modified_hex
offset
changed_length
timestamp
rule
session
```

禁止：

``` text
收到修改请求
→ 数据库记录 modified
→ 返回 success
```

这种实现属于假成功。

------------------------------------------------------------------------

# 13. EventBus

所有 Runtime / Network 事件统一进入 EventBus。

统一结构：

``` text
version
type
event_id
session_id
timestamp
pid
tid
event_type
source
payload
```

P0 优先：

``` text
PROCESS_STARTED
AGENT_CONNECTED
RUNTIME_READY
MODULE_LOADED
THREAD_CREATED
HOOK_ENTER
HOOK_LEAVE
NETWORK_CONNECTED
HTTP_REQUEST
HTTP_RESPONSE
PACKET_CAPTURED
```

P1：

``` text
DEX_LOADED
CLASS_LOADED
JNI_CALL
SO_LOADED
MEMORY_CHANGED
WEBSOCKET_FRAME
HOOK_INSTALLED
PACKET_MODIFIED
PACKET_REPLAYED
```

------------------------------------------------------------------------

# 14. Correlation Engine

不要让 AI 自己从几百条日志里猜关系。

系统应该把：

``` text
HTTP
 ↓
Connection
 ↓
PID
 ↓
TID
 ↓
Java Stack
 ↓
JNI
 ↓
Native Stack
 ↓
Module
 ↓
Function
 ↓
Hook
```

组合成：

``` text
AnalysisObject
```

AI 主要分析：

``` text
AnalysisObject
```

而不是直接消费几十种底层原始日志。

## 14.1 Correlation 证据链

每条关系都需要 evidence：

``` text
source event
timestamp
pid
tid
connection
stack
module
function
confidence/evidence state
```

最终验证：

``` text
CORRELATION_VERIFIED
```

不能凭时间接近就直接声称两个事件一定属于同一调用。

------------------------------------------------------------------------

# 15. Artifact Manager

所有大对象统一：

``` text
Tool
 ↓
Artifact Manager
 ↓
Filesystem
 ↓
Metadata
 ↓
MCP
```

类型：

``` text
PCAP
MEMORY_DUMP
APK
DECOMPILED_PROJECT
TRACE
HEX
HTTP_BODY
HTTPS_BODY
REPORT
LOG
```

MCP 只返回：

``` text
artifact_id
type
size
path
sha256
created_at
```

这样可以避免 MCP 响应爆炸。

------------------------------------------------------------------------

# 16. MCP Server

MCP 是控制面，不是 Runtime。

架构：

``` text
AI
 ↓
Tool Surface Manager
 ↓
MCP Server
 ↓
Bridge
 ↓
Session
 ↓
IPC
 ↓
Runtime / Network
```

AI 不允许：

``` text
直接 Frida
直接 ADB
直接 mitmproxy
直接 Gum
直接 LSPlant
```

## 16.1 Core Surface

常驻不超过 25 个。

包括：

``` text
device.list/info
apk.list/launch/stop
session.list/info/capabilities
process.list/info/modules/threads
runtime.status/hook/unhook/trace
memory.read/write/search
network.capture_start/stop/connections
packet.get/modify
artifact.get
```

## 16.2 Expert Surface

动态挂载：

``` text
Device+
APK+
Runtime+
Memory+
Network+
Packet+
Automation
Analysis
Artifact+
```

------------------------------------------------------------------------

# 17. Tool Contract 开发顺序

每个工具不是只写一个函数。

必须同时定义：

``` text
name
title
description
inputSchema
outputSchema
annotations
```

Description 包含：

``` text
use_case
important_notes
next_step
latency
```

Schema 必须：

``` text
required
default
min/max
maxItems
additionalProperties=false
```

Annotations：

``` text
readOnlyHint
destructiveHint
idempotentHint
openWorldHint
```

------------------------------------------------------------------------

# 18. Tool 注册三处一致性

新增工具必须检查：

``` text
tools/__init__.py
        ↓
REGISTERED_TOOL_MODULES

server
        ↓
_LAZY_IMPORTS

surface manager
        ↓
Core / Expert visible set
```

最后必须实际运行：

``` text
tools/list
```

确认真实暴露。

不能只检查代码文件存在。

------------------------------------------------------------------------

# 19. FAST 与 JOB

## FAST

适用于：

``` text
process.list
process.info
runtime.status
memory.read
network.connections
network.dns
packet.get
```

目标：

> 毫秒到秒级快速响应。

## JOB

适用于：

``` text
memory.dump
packet.export
apk.decompile
network.capture_start
runtime.trace
大型分析
```

统一：

``` text
submit
 ↓
job_id
 ↓
job.status
 ↓
job.result
 ↓
job.cancel
```

不能让大任务堵塞 MCP 主事件循环。

------------------------------------------------------------------------

# 20. Write Guard

所有修改行为都必须进入 Write Guard。

适用：

``` text
memory.write
packet.modify
hook argument modification
hook return modification
network response modification
```

统一：

``` text
Validate
Preview
Backup
Confirm
Execute
Verify
Commit
Rollback
```

默认：

``` text
WRITE_CONFIRM_DEFAULT=false
```

AI 不得绕过 Write Guard 直接修改底层数据。

------------------------------------------------------------------------

# 21. 错误体系

至少统一：

``` text
ERROR_PROTOCOL_VERSION
E_BAD_ARGS
E_UNKNOWN_CMD
E_NOT_READY
E_SESSION_STALE
E_READ_FAILED
E_WRITE_FAILED
E_MAP_STALE
E_TIMEOUT
E_CANCELLED
E_NOT_FOUND
E_PERMISSION_DENIED
E_INTERNAL
```

错误必须说明：

``` text
发生在哪一层
为什么失败
是否可重试
下一步应该做什么
```

不要返回模糊：

``` text
failed
error
not found
```

------------------------------------------------------------------------

# 22. "不做负面结论"原则

AI 工具不能轻易返回：

``` text
没有这个函数
没有这个 Hook
不存在这个类
没有这个网络请求
```

扫描 0 命中时，应尽可能返回：

``` text
best candidate
search evidence
search scope
neutral status
```

因为：

``` text
未找到
≠
不存在
```

------------------------------------------------------------------------

# 23. 测试顺序

测试绝对不能最后才做。

## T0 协议

``` text
frame encode/decode
length
JSON
version
heartbeat
reconnect
session stale
```

## T1 Runtime

``` text
Zygisk injection
Runtime startup
process info
module list
thread list
```

## T2 Hook

``` text
installed
enter
leave
disable
enable
remove
```

## T3 Memory

``` text
read
write
read-back
compare
rollback
```

## T4 Network

``` text
capture
connection
HTTP
HTTPS state
```

## T5 Packet

``` text
get
modify
HEX
verify
```

## T6 Correlation

``` text
HTTP
→ connection
→ thread
→ stack
→ native
→ module
→ hook
```

## T7 Artifact

``` text
create
metadata
sha256
retrieve
```

------------------------------------------------------------------------

# 24. 双层验收标准

## 第一层：功能链

必须完成：

``` text
01 自动注入
02 Native Hook
03 Java Hook
04 Memory Read
05 Memory Write
06 Network Capture
07 HTTP Intercept
08 HTTPS 五级
09 Packet HEX Modify
10 Correlation
```

## 第二层：语义真实性

### Hook

必须存在：

``` text
HOOK_INSTALLED
HOOK_ENTER
HOOK_LEAVE
pid
tid
timestamp
arguments
backtrace
```

### Memory Write

必须：

``` text
read original
write
read back
compare
verified
```

### Network

必须存在真实网络流量。

### HTTPS

必须明确五级状态。

### Correlation

必须有真实证据链。

------------------------------------------------------------------------

# 25. 每个阶段的固定开发纪律

WorkBuddy 每完成一个功能必须输出：

``` text
1. 修改了哪些文件
2. 为什么修改
3. 依赖了哪些 API
4. 是否改变架构
5. 编译结果
6. 单元测试结果
7. 真机结果
8. 日志证据
9. 未完成项
10. 下一步
```

禁止只说：

``` text
“已经完成。”
```

------------------------------------------------------------------------

# 26. WorkBuddy 的单任务模式

不要一次让 AI：

> "把整个项目全部写完。"

正确方式是：

``` text
任务 001
只做 P-1 环境审计

任务 002
只修复构建环境

任务 003
只验证 Frida-Gum

任务 004
只验证 LSPlant

任务 005
只生成 libai_analyzer.so

任务 006
只实现 Zygisk Bootstrap

任务 007
只实现 IPC Frame

任务 008
只实现 HELLO

任务 009
只实现 Session

任务 010
只做 runtime.status
```

每一个任务都有：

``` text
输入
范围
禁止事项
输出
验收
```

这样比让 AI 自由发挥稳定得多。

------------------------------------------------------------------------

# 27. 推荐的 WorkBuddy 提示词模板

以后每次让 WorkBuddy 干活，使用：

``` text
你现在是本项目的实现工程师。

先阅读：
1. docs/00-权威基线/项目总基线_v1.1.md
2. docs/00-权威基线/STRUCTURE.md
3. docs/00-权威基线/SOURCE_LOCK.md
4. docs/00-权威基线/LICENSES.md
5. docs/10-施工指导/ZygiskAIRuntime_专业开发技术指导总文档_v1.0.md

当前阶段：
[填写 M0/M1/M2...]

本次唯一任务：
[只写一个任务]

允许修改：
[列文件/目录]

禁止修改：
[列边界]

必须遵守：
- 不改变冻结架构
- 不添加未经批准的第三方依赖
- 不制造 mock/fake success
- 不绕过 Write Guard
- 不绕过 Session
- 不让 AI 直接调用底层第三方库
- 不跨阶段实现

完成后必须报告：
1. 修改文件
2. 核心实现
3. 构建命令
4. 构建结果
5. 测试结果
6. 真机结果
7. 日志证据
8. 未完成项
9. 风险
10. 下一步

如果当前环境不足，停止编码并报告阻塞原因。
```

------------------------------------------------------------------------

# 28. 优化顺序

功能跑通以后，不要立即大规模优化。

严格：

``` text
正确性
 ↓
稳定性
 ↓
兼容性
 ↓
可观测性
 ↓
性能
 ↓
内存
 ↓
启动速度
 ↓
并发
 ↓
代码结构
 ↓
用户体验
```

不能为了性能牺牲：

``` text
Hook correctness
Memory verification
Packet verification
Session correctness
```

------------------------------------------------------------------------

# 29. 深入研究顺序

项目稳定以后再进入研究。

## Runtime

研究：

``` text
Frida-Gum Interceptor
Stalker
Instruction relocation
AArch64 ABI
register/context
thread-local state
signal safety
loader/linker
/proc maps
memory permission
```

## ART

研究：

``` text
ART runtime
ClassLinker
ArtMethod
JNI
Dex loading
Class loading
Android SDK differences
16KB page
```

## Network

研究：

``` text
TLS
certificate pinning
HTTP/2
HTTP/3
QUIC
WebSocket
Cronet
OkHttp
native socket
VPN capture
```

## Correlation

研究：

``` text
timestamp correlation
PID/TID correlation
stack correlation
connection correlation
hook correlation
causal graph
confidence/evidence
```

## AI

研究：

``` text
tool planning
evidence-based reasoning
automatic workflow
rule generation
breakpoint automation
analysis object reasoning
artifact reasoning
```

------------------------------------------------------------------------

# 30. 性能优化原则

优先优化：

``` text
EventBus
IPC
Stack capture
Packet capture
Memory scanning
Logging
Artifact I/O
```

不要一开始就做：

``` text
全进程 Stalker
全内存扫描
所有线程持续回溯
所有网络包全部转 MCP
```

应当：

``` text
采样
过滤
分页
后台任务
事件降噪
服务端过滤
Artifact
```

------------------------------------------------------------------------

# 31. Android 兼容性路线

第一阶段：

``` text
ARM64
主力 Android 版本
```

稳定后扩展：

``` text
Android 版本
SDK
ART 差异
16KB page
不同厂商
不同 ROM
不同 SELinux 环境
```

每增加一个兼容环境，都必须记录：

``` text
device
Android
API
ABI
Magisk
Zygisk
result
limitations
```

形成 DEVICE_MATRIX。

------------------------------------------------------------------------

# 32. 日志与可观测性

所有重要状态必须能够从日志证明：

``` text
Zygisk entered
package matched
runtime started
gum initialized
art initialized
ipc connected
hello
ready
session created
hook installed
hook enter
hook leave
memory write
memory verify
network capture
packet modified
correlation verified
artifact created
```

日志不是最终数据源。

日志用于：

> **证明系统确实发生了某件事。**

正式分析数据进入 EventBus / Session / Artifact。

------------------------------------------------------------------------

# 33. 崩溃与异常策略

任何以下异常都必须可控：

``` text
Hook install failure
Hook callback exception
invalid address
stale memory map
IPC disconnect
App death
Network adapter death
MCP disconnect
LSPlant unsupported SDK
Gum initialization failure
```

原则：

> 一个能力失败，不应该让整个 Runtime 无条件崩溃。

例如：

``` text
LSPlant failed
```

不应自动导致：

``` text
Native Runtime 全部失效
```

应进入：

``` text
DEGRADED
```

并明确 capability。

------------------------------------------------------------------------

# 34. Release 前检查

最终 Release Candidate 必须逐项：

``` text
[ ] clean build
[ ] reproducible build
[ ] arm64
[ ] module package
[ ] install
[ ] uninstall
[ ] Zygisk injection
[ ] Runtime startup
[ ] IPC
[ ] Session
[ ] Native Hook
[ ] Java Hook
[ ] Memory Read
[ ] Memory Write Verify
[ ] Network Capture
[ ] HTTP
[ ] HTTPS levels
[ ] Packet modify
[ ] Correlation
[ ] Artifact
[ ] MCP tools/list
[ ] Core surface <=25
[ ] Tool contract validation
[ ] heartbeat
[ ] reconnect
[ ] app death
[ ] session cleanup
[ ] crash handling
[ ] logs
[ ] license notices
```

------------------------------------------------------------------------

# 35. 永久禁止事项

以下行为以后任何 AI 工程师都不能自行做：

### 禁止 1：重新设计架构

已经冻结的：

``` text
Zygisk
Runtime
Frida-Gum
LSPlant
Network
EventBus
Correlation
Session
Protocol
MCP
Write Guard
Artifact
```

不能随意替换。

### 禁止 2：增加第三方依赖解决简单问题

先使用项目已有能力。

### 禁止 3：Mock 真实 Runtime

尤其禁止：

``` text
fake PID
fake hook
fake memory
fake packet
fake HTTPS decrypt
fake correlation
```

### 禁止 4：把 GPL 项目塞入核心 so

必须保持独立边界。

### 禁止 5：让 MCP 直接操作底层

MCP 只能经过：

``` text
Session
Capability
Backend
```

### 禁止 6：一次跨越多个阶段

WorkBuddy 每次只解决一个垂直切片。

------------------------------------------------------------------------

# 36. 最终开发哲学

整个项目的正确开发方式不是：

``` text
先把所有代码写出来
→ 最后测试
```

而是：

``` text
设计
 ↓
契约
 ↓
最小实现
 ↓
编译
 ↓
真实运行
 ↓
证据
 ↓
测试
 ↓
扩大能力
 ↓
优化
 ↓
深入研究
```

每个能力都采用：

``` text
最小垂直切片
```

例如 Hook：

``` text
API
 ↓
Backend
 ↓
真实安装
 ↓
真实 ENTER
 ↓
真实 LEAVE
 ↓
事件
 ↓
MCP
 ↓
AI
```

跑通之后再：

``` text
多 Hook
参数修改
返回值修改
条件 Hook
规则
自动化
```

Memory、Network、Packet、Correlation 同理。

------------------------------------------------------------------------

# 37. 项目最终完成的判定

不要用：

``` text
代码多少行
文件多少个
工具多少个
GitHub 项目多少个
```

判断完成度。

真正的完成标准是：

``` text
真实 APK
    ↓
Zygisk 自动进入
    ↓
Runtime
    ↓
Frida-Gum / LSPlant
    ↓
真实 Hook
    ↓
Event
    ↓
Memory
    ↓
Network
    ↓
Packet
    ↓
Correlation
    ↓
Artifact
    ↓
MCP
    ↓
AI
```

并且每一个关键节点都存在：

``` text
真实执行
+
真实结果
+
可追溯事件
+
错误处理
+
验收测试
```

------------------------------------------------------------------------

# 38. 当前项目下一步的唯一正确动作

当前不要让 WorkBuddy 开始：

``` text
Hook
Memory
Network
MCP
AI
```

第一步应该是：

> **执行 P-1《落地前准备审计》。**

审计完成以后，生成：

``` text
docs/20-构建与审计/ENVIRONMENT.md
docs/20-构建与审计/SUPPLY_CHAIN_CHECK.md
docs/20-构建与审计/DEVICE_MATRIX.md
docs/20-构建与审计/BUILD_BLOCKERS.md
```

然后再根据实际结果决定：

``` text
M0
```

还是：

``` text
先解决 M1 环境阻塞
```

------------------------------------------------------------------------

# 39. 一句话总路线

> **先准备，再契约；先编译，再注入；先 Runtime，再能力；先真实执行，再
> MCP；先证据，再
> AI；先正确稳定，再性能优化；最后才进入深入逆向与自动化研究。**

这份顺序就是后续 WorkBuddy AI 的"施工总规约"。
