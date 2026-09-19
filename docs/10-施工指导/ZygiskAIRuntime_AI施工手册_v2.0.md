# ZygiskAIRuntime

# AI 施工手册 v2.0

## ------逐阶段、逐任务、逐文件、逐验收的 WorkBuddy AI 开发执行规约

**版本：v2.0**\
**定位：工程施工手册，不重新设计总体架构**\
**适用对象：WorkBuddy AI / 后续协作 AI / 单人开发者**\
**上位依据：`docs/00-权威基线/`（项目总基线 v1.1 · STRUCTURE.md · SOURCE_LOCK.md · LICENSES.md）**\
**当前工程状态：架构冻结、供应链准备、工程骨架已建立、首次真实编译尚未完成**

------------------------------------------------------------------------

# 0. 这份手册到底解决什么问题

本项目已经不再缺"宏观想法"。

真正缺的是：

> **如何让 AI
> 一步一步把已经冻结的设计，变成真实可以编译、安装、运行、Hook、读写内存、抓包、改包、关联分析、最终由
> MCP/AI 控制的工程。**

因此 v2.0 不再停留在：

``` text
M1：做编译
M2：做 IPC
M3：做 Hook
```

而进一步规定：

``` text
这一阶段为什么做
→
先研究什么
→
检查哪些文件
→
允许修改哪些文件
→
禁止修改哪些文件
→
先做哪一个最小切片
→
如何编译
→
如何运行
→
如何收集证据
→
什么结果才算完成
→
失败以后从哪里排查
→
完成后才能进入什么阶段
```

这份文档是给 WorkBuddy AI 当作**施工总规约**使用的。

------------------------------------------------------------------------

# 1. AI 总施工原则

## 1.1 不允许"自由发挥式开发"

禁止向 AI 下达：

``` text
“把整个项目做完”
“把 Hook 写出来”
“把 MCP 全部实现”
“把所有功能补齐”
```

必须使用：

``` text
阶段
→
任务
→
文件
→
验收
```

四级约束。

------------------------------------------------------------------------

# 2. AI 每次接任务前必须执行的固定流程

WorkBuddy 每次收到开发任务，第一步不是写代码，而是：

``` text
① 判断当前阶段
② 阅读上位文档
③ 检查当前代码实际状态
④ 检查任务依赖
⑤ 检查环境
⑥ 明确本次修改范围
⑦ 明确禁止范围
⑧ 制定最小实现
⑨ 修改
⑩ 编译
⑪ 测试
⑫ 输出证据
```

如果第 ①～⑤ 步发现前置条件不满足：

> **停止本任务，不得跨阶段。**

------------------------------------------------------------------------

# 3. 文档优先级

发生冲突时严格按以下优先级：

``` text
P0 项目总基线 v1.1
P1 SOURCE_LOCK
P2 LICENSES
P3 STRUCTURE
P4 DEVELOPMENT_GUIDE v1.0
P5 AI施工手册 v2.0
P6 当前任务 Prompt
P7 AI 自己的推测
```

任何 AI 推测不得覆盖上位冻结文档。

如果当前代码与文档冲突：

``` text
先报告冲突
→
不要擅自选择一边
→
由人工确认
```

------------------------------------------------------------------------

# 4. 工程现实状态

当前项目应始终被视为：

``` text
架构：已冻结
供应链：已锁定
工程目录：已建立
核心代码：骨架态
第三方源码：已准备
构建环境：待完整验证
首次编译：未完成
真机运行：未完成
```

**进度更新（2026-09-19）**：

```text
P-1  落地准备审计          未开工（NDK/CMake 阻塞 → 建议拆 P-1a / P-1b）
M0   协议契约               ✅ 已完成（常量单一源 + 帧 + 9 消息 + 黄金样例 + 114 项测试）
M1   构建                   ⛔ 阻塞（本机无 NDK / CMake）
M2   Zygisk / Runtime / IPC ⛔ 阻塞（依赖 M1）
──   Host 侧 MVP（先行）     ✅ 已完成（Bridge + Mock 后端 + MCP Server 35 工具）
                            证据：199 项测试全绿 + tests/accept_mvp.py 28/28
```

Host 侧之所以能先行，是因为它**不依赖 NDK 与真机**：
协议、连接管理、工具面全部可在 PC 侧跑通，Android 侧接入时只需换掉端点。

因此：

> **任何"代码文件存在"都不能证明功能已经实现。**

真正的完成必须同时满足：

``` text
源码
+
编译
+
运行
+
真实执行
+
测试
+
证据
```

------------------------------------------------------------------------

# 5. 总施工地图

``` text
P-1 落地准备审计
│
├─ P-1.1 工程目录审计
├─ P-1.2 供应链审计
├─ P-1.3 License 审计
├─ P-1.4 PC 构建环境审计
├─ P-1.5 Android/NDK 审计
├─ P-1.6 真机/Magisk/Zygisk 审计
└─ P-1.7 阻塞项清零
        ↓
M0 协议契约
│
├─ M0.1 constants
├─ M0.2 frame
├─ M0.3 messages
├─ M0.4 schemas
├─ M0.5 Golden Samples
└─ M0.6 protocol tests
        ↓
M1 构建
│
├─ M1.1 Frida-Gum
├─ M1.2 LSPlant
├─ M1.3 Native CMake
├─ M1.4 Zygisk Module
├─ M1.5 package
└─ M1.6 clean build
        ↓
M2 Runtime 骨架真正运行
│
├─ M2.1 Zygisk Entry
├─ M2.2 Bootstrap
├─ M2.3 Runtime Context
├─ M2.4 IPC
├─ M2.5 HELLO
├─ M2.6 heartbeat
├─ M2.7 Session
└─ M2.8 reconnect / app death
        ↓
M3 Native Runtime
│
├─ M3.1 Gum init
├─ M3.2 module map
├─ M3.3 thread
├─ M3.4 Hook Manager
├─ M3.5 Native Hook
├─ M3.6 events
└─ M3.7 backtrace
        ↓
M3.5 ART / Java
│
├─ ART capability
├─ LSPlant adapter
├─ class/method resolution
├─ Java Hook
└─ Java → JNI → Native chain
        ↓
M4 Memory + Network
│
├─ Memory read
├─ Memory write
├─ Search
├─ Network capture
├─ Connections
├─ HTTP
└─ runtime/network correlation
        ↓
M4.5 HTTPS
│
├─ captured
├─ decoded
├─ decrypted
├─ interceptable
└─ modifiable
        ↓
M5 Packet / Correlation / Artifact
│
├─ Packet get
├─ Packet modify
├─ HEX
├─ verify
├─ Correlation Engine
└─ Artifact Manager
        ↓
M5.5 MCP
│
├─ Core Surface
├─ Expert Surface
├─ schemas
├─ tool registry
├─ job system
└─ AI workflow
        ↓
M6 稳定化
│
├─ crash
├─ reconnect
├─ compatibility
├─ performance
├─ observability
└─ release
        ↓
Research / Optimization
```

------------------------------------------------------------------------

# 6. 每一个任务必须有 DoD

DoD = Definition of Done。

一个任务只有同时满足以下条件才算 Done：

``` text
[ ] 修改范围符合任务
[ ] 没有越过架构边界
[ ] 没有增加未经批准依赖
[ ] 编译成功
[ ] 对应测试成功
[ ] 如果涉及 Runtime，已进行真实运行验证
[ ] 如果涉及 Hook/Memory/Network，存在真实证据
[ ] 日志可追踪
[ ] 错误路径已处理
[ ] 文档已同步
[ ] Git diff 可解释
[ ] WorkBuddy 输出完整报告
```

------------------------------------------------------------------------

# 7. P-1：落地前准备审计

# P-1.1 工程目录审计

## 目标

确认代码树与 STRUCTURE 完全一致。

## 检查

``` text
ZygiskAIRuntime/
├── README.md
├── VERSION
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

## AI 操作

只允许：

``` text
查看
统计
对照
记录
```

不允许：

``` text
重构目录
移动第三方
删除“看起来没用”的文件
```

## 输出

``` text
docs/20-构建与审计/PROJECT_TREE_AUDIT.md
```

必须包含：

``` text
实际文件数
实际代码行数
空目录
缺失文件
多余文件
目录冲突
脚本引用不存在路径
```

------------------------------------------------------------------------

# P-1.2 供应链审计

逐项建立表：

  -----------------------------------------------------------------------------------
  依赖        版本       来源       License      实际路径      核心/外置   状态
  ----------- ---------- ---------- ------------ ------------- ----------- ----------
  Frida-Gum   17.18.0    锁定源     wxWindows    third_party   核心        待验证

  LSPlant     锁定版本   锁定源     LGPL-3.0     third_party   核心        待验证

  JADX        current    锁定源     Apache-2.0   external      外置        待验证
              stable                                                       

  Apktool     current    锁定源     Apache-2.0   external      外置        待验证
              stable                                                       

  Rizin       mainline   锁定源     GPL-3.0      external      外置        待验证

  PCAPdroid   current    锁定源     GPL-3.0      external      外置        待验证

  mitmproxy   current    锁定源     MIT          external      外置        待验证
  -----------------------------------------------------------------------------------

不要在本阶段升级版本。

------------------------------------------------------------------------

# P-1.3 License 审计

必须确认：

``` text
LICENSES.md
THIRD_PARTY_NOTICES
```

未来 Release 前必须能够回答：

``` text
这个源码从哪里来？
哪个版本？
什么许可证？
是否静态链接？
是否动态链接？
是否独立进程？
是否需要保留版权声明？
```

------------------------------------------------------------------------

# P-1.4 PC 构建环境审计

检查：

``` text
Windows
Android SDK
Android NDK
CMake
Ninja
Python
Git
Meson
JDK
Gradle
ADB
```

输出：

``` text
docs/20-构建与审计/ENVIRONMENT.md
```

格式：

``` text
Tool
Version
Path
Expected
Actual
PASS/FAIL
```

------------------------------------------------------------------------

# P-1.5 Android 真机审计

记录：

``` text
device
model
manufacturer
Android
API
ABI
kernel
page size
Magisk
Zygisk
SELinux mode
adb
```

生成：

``` text
docs/20-构建与审计/DEVICE_MATRIX.md
```

------------------------------------------------------------------------

# P-1.6 P-1 阻塞规则

以下任何一项失败：

``` text
NDK
CMake
ADB
ARM64
Magisk/Zygisk
Frida-Gum source
LSPlant source
```

都不得假装 P-1 完成。

输出：

``` text
docs/20-构建与审计/BUILD_BLOCKERS.md
```

------------------------------------------------------------------------

# 8. M0：协议施工

M0 的原则：

> **先把"双方说什么"确定，再写双方怎么说。**

------------------------------------------------------------------------

# M0.1 constants

唯一常量源：

``` text
ai_analyzer/protocol/constants.py
```

Android 对应头文件必须与其一致。

冻结：

``` text
PROTOCOL_VERSION=1.0
FRAME_HEADER=4
HEARTBEAT_INTERVAL=5
HEARTBEAT_TIMEOUT=30
FAST_TIMEOUT=10
JOB_TIMEOUT=300
SESSION_IDLE_TIMEOUT=600
MAX_RESPONSE_TOKENS=4096
```

增加新常量前必须检查是否已有定义。

------------------------------------------------------------------------

# M0.2 Frame Codec

实现最小：

``` text
encode(payload)
decode(stream)
```

规则：

``` text
uint32 length
network byte order
JSON payload
```

必须测试：

``` text
0 bytes
1 byte
normal
large
invalid length
truncated
extra data
malformed JSON
```

------------------------------------------------------------------------

# M0.3 Message

实现：

``` text
HELLO
HELLO_ACK
READY
REQUEST
RESPONSE
EVENT
PING
PONG
ERROR
```

每一种消息必须有 schema。

------------------------------------------------------------------------

# M0.4 Golden Sample

目录建议：

``` text
ai_analyzer/schemas/
├── hello.json
├── hello_ack.json
├── ready.json
├── request.json
├── response.json
├── event.json
├── ping.json
├── pong.json
└── errors/
```

测试样例：

``` text
ai_analyzer/schemas/examples/
```

------------------------------------------------------------------------

# M0.5 Protocol Contract Test

必须能够让 PC 和 Android 都验证：

``` text
同一个 JSON
→
同样解析
→
同样字段
→
同样类型
→
同样错误
```

------------------------------------------------------------------------

# M0.6 M0 DoD

必须：

``` text
[ ] constants 一致
[ ] frame 测试通过
[ ] schema 验证通过
[ ] Golden Samples 完整
[ ] version mismatch 测试
[ ] heartbeat 测试
[ ] reconnect 测试
[ ] stale session 测试
```

------------------------------------------------------------------------

# 9. M1：构建系统施工

M1 是工程第一次真正产生 Android 二进制。

------------------------------------------------------------------------

# M1.1 Frida-Gum

## 目标

先单独证明：

``` text
Frida-Gum
→ Android arm64
→ libgum.a
```

## 施工顺序

``` text
检查源码
→
检查 Meson
→
检查 subprojects
→
准备 Android cross file
→
准备 NDK
→
配置
→
编译
→
检查静态库
```

## 禁止

不要同时调：

``` text
Gum
+
LSPlant
+
Zygisk
+
MCP
```

否则出现错误时无法定位。

------------------------------------------------------------------------

# M1.2 LSPlant

目标：

``` text
LSPlant
→
Android arm64
→
liblsplant.so
```

重点：

``` text
C++20 modules
C++23
CMake
SHARED
16KB page compatibility
```

------------------------------------------------------------------------

# M1.3 Native CMake

只在两个第三方单独成功后接入。

目标：

``` text
native/CMakeLists.txt
```

形成：

``` text
native
 ↓
Frida-Gum
 ↓
LSPlant
 ↓
runtime
 ↓
zygisk
 ↓
libai_analyzer.so
```

------------------------------------------------------------------------

# M1.4 Zygisk Module

验证：

``` text
module.prop
customize.sh
post-fs-data.sh
service.sh
uninstall.sh
zygisk/arm64-v8a.so
```

没有最终 so 时：

``` text
customize.sh
```

应该拒绝安装，而不是安装一个空模块。

------------------------------------------------------------------------

# M1.5 Package

最终：

``` text
build/out/arm64-v8a/
module/zygisk/arm64-v8a.so
```

再：

``` text
package.bat
```

生成可安装包。

------------------------------------------------------------------------

# M1.6 M1 DoD

``` text
[ ] clean build
[ ] Frida-Gum
[ ] LSPlant
[ ] libai_analyzer.so
[ ] module package
[ ] package validation
[ ] install/uninstall
```

------------------------------------------------------------------------

# 10. M2：Zygisk / Runtime / IPC

这是第一个"系统真的活起来"的阶段。

------------------------------------------------------------------------

# M2.1 Zygisk Entry

文件：

``` text
zygisk/entry.cpp
zygisk/module.cpp
zygisk/bootstrap.cpp
```

只负责：

``` text
REGISTER
→
process match
→
bootstrap
```

------------------------------------------------------------------------

# M2.2 Runtime Context

必须能够记录：

``` text
package
pid
uid
process name
abi
sdk
session_id
```

禁止让多个模块各自维护一套上下文。

------------------------------------------------------------------------

# M2.3 Runtime 启动

顺序：

``` text
Runtime start
 ↓
Gum Backend init
 ↓
ART Backend init
 ↓
Manager init
 ↓
IPC init
```

如果某个能力失败：

``` text
capability unavailable
```

不要直接制造假成功。

------------------------------------------------------------------------

# M2.4 IPC Client

先只实现：

``` text
connect
send
receive
close
```

然后：

``` text
HELLO
HELLO_ACK
READY
```

------------------------------------------------------------------------

# M2.5 Heartbeat

独立线程/任务：

``` text
PING
 ↓
PONG
```

不得阻塞普通 command。

------------------------------------------------------------------------

# M2.6 Session

Session 是唯一状态边界。

禁止：

``` text
Hook Manager 自己创建 session
Network 自己创建 session
MCP 自己创建 session
```

所有状态都属于：

``` text
Session
```

------------------------------------------------------------------------

# M2.7 Runtime 最小命令

第一批只做：

``` text
runtime.status
process.list
process.info
process.modules
process.threads
```

这五个命令足以验证：

``` text
Zygisk
Runtime
IPC
Session
Process
```

------------------------------------------------------------------------

# M2.8 M2 真机测试

真实：

``` text
启动 APK
→
Zygisk
→
Runtime
→
HELLO
→
READY
→
runtime.status
```

然后：

``` text
杀 App
→
DEGRADED
→
CLOSED
```

重连：

``` text
Session B
```

旧 Session A 必须失效。

------------------------------------------------------------------------

# 11. M3：Native Runtime / Frida-Gum

------------------------------------------------------------------------

# M3.1 Gum Backend

文件：

``` text
runtime/backend/gum/gum_backend.h
runtime/backend/gum/gum_backend.cpp
```

唯一规则：

``` text
gum_* 只能在 gum_backend.cpp
```

------------------------------------------------------------------------

# M3.2 Module Engine

首先解决：

``` text
/proc/self/maps
```

与 Gum module map 的一致性。

输出：

``` text
module
base
size
path
permissions
```

地址统一：

``` text
"0x..."
```

------------------------------------------------------------------------

# M3.3 Thread Engine

实现：

``` text
tid
name
state
```

并为后续 Stack/Correlation 做准备。

------------------------------------------------------------------------

# M3.4 Hook Manager

实现状态机：

``` text
pending
active
disabled
removed
failed
```

操作：

``` text
create
info
list
enable
disable
remove
```

------------------------------------------------------------------------

# M3.5 第一个 Native Hook

最小垂直切片：

``` text
指定 module
+
指定 address
+
安装
+
ENTER
+
LEAVE
```

必须产生：

``` text
HOOK_INSTALLED
HOOK_ENTER
HOOK_LEAVE
```

------------------------------------------------------------------------

# M3.6 Hook Event

字段至少：

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

------------------------------------------------------------------------

# M3.7 Backtrace

顺序：

``` text
Native stack
→
module
→
function
```

第一阶段允许：

``` text
address-only
```

第二阶段再：

``` text
symbol
```

第三阶段：

``` text
source mapping
```

------------------------------------------------------------------------

# M3.8 M3 DoD

不是：

``` text
hook.create 返回成功
```

而是：

``` text
真实安装
+
真实进入
+
真实退出
+
PID
+
TID
+
时间
+
参数
+
回溯
```

------------------------------------------------------------------------

# 12. M3.5：ART / LSPlant / Java Hook

------------------------------------------------------------------------

# M3.5.1 ART Capability

先检测：

``` text
SDK
ART
LSPlant capability
```

结果：

``` text
supported
degraded
unsupported
```

------------------------------------------------------------------------

# M3.5.2 Adapter

唯一直接调用：

``` text
lsplant::
```

的位置：

``` text
runtime/backend/art/lsplant_adapter.cpp
```

------------------------------------------------------------------------

# M3.5.3 Java Hook 最小切片

只做：

``` text
class
method
overload
arguments
return
thread
stack
```

先不要加入复杂规则系统。

------------------------------------------------------------------------

# M3.5.4 Java → JNI → Native

目标：

``` text
Java Hook
 ↓
JNI event
 ↓
Native stack
 ↓
Module
```

这是后续 Correlation 的基础。

------------------------------------------------------------------------

# 13. M4：Memory Engine

------------------------------------------------------------------------

# M4.1 Read

输入：

``` text
address
length
```

验证：

``` text
mapped
read permission
```

输出：

``` text
address
length
hex
```

------------------------------------------------------------------------

# M4.2 Write

严格：

``` text
validate
→
preview
→
backup
→
confirm
→
execute
→
verify
→
commit
```

结果：

``` text
accepted
executed
verified
```

------------------------------------------------------------------------

# M4.3 Write Failure

如果：

``` text
write success
```

但：

``` text
read-back mismatch
```

最终不能报告成功。

应该：

``` text
E_WRITE_FAILED
verified=false
```

并尝试 rollback。

------------------------------------------------------------------------

# M4.4 Search

先：

``` text
exact bytes
```

再：

``` text
integer
float
pointer
range
```

所有大结果：

``` text
pagination
```

------------------------------------------------------------------------

# M4.5 Dump

Dump：

``` text
JOB
```

结果：

``` text
artifact_id
sha256
size
```

不要把 dump 本身放 MCP JSON。

------------------------------------------------------------------------

# 14. M4.5：Network Plane

------------------------------------------------------------------------

# M4.5.1 Adapter 边界

核心 Runtime 不直接依赖 GPL 网络应用。

使用：

``` text
adapter
+
IPC/API
```

------------------------------------------------------------------------

# M4.5.2 Capture

先：

``` text
network.capture_start
network.connections
network.capture_stop
```

验证：

``` text
真实流量
```

------------------------------------------------------------------------

# M4.5.3 HTTP

实现：

``` text
request
response
headers
body
connection
timestamp
```

Body 大于 MCP 安全阈值：

``` text
Artifact
```

------------------------------------------------------------------------

# 15. HTTPS 五级验收

每一次 HTTP/HTTPS 分析必须明确：

``` text
captured
decoded
decrypted
interceptable
modifiable
```

禁止从低等级推导高等级。

例如：

``` text
captured=true
```

不能自动变成：

``` text
decrypted=true
```

------------------------------------------------------------------------

# 16. M5：Packet Engine

------------------------------------------------------------------------

# M5.1 Packet Get

必须返回：

``` text
packet_id
timestamp
direction
connection
length
hex / artifact
```

------------------------------------------------------------------------

# M5.2 Packet Modify

流程：

``` text
get
→
decode
→
original_hex
→
preview
→
modified_hex
→
validate
→
confirm
→
execute
→
verify
```

------------------------------------------------------------------------

# M5.3 HEX

至少支持：

``` text
offset
original
modified
length
```

验证：

``` text
changed_length
```

如果协议禁止长度变化：

``` text
拒绝
```

不能偷偷截断。

------------------------------------------------------------------------

# 17. M5：Correlation Engine

Correlation 不等于"按时间排序"。

需要构建证据链：

``` text
Packet
 ↓
Connection
 ↓
PID
 ↓
TID
 ↓
Java
 ↓
JNI
 ↓
Native
 ↓
Module
 ↓
Function
 ↓
Hook
```

------------------------------------------------------------------------

# 18. AnalysisObject

AI 最终主要消费：

``` text
AnalysisObject
```

而不是：

``` text
5000 条日志
```

AnalysisObject 至少包含：

``` text
object_id
session_id
timestamp
process
connection
request/response
thread
java_stack
jni_chain
native_stack
module
function
hook
packet
evidence
```

------------------------------------------------------------------------

# 19. Correlation 证据等级

建议区分：

``` text
observed
linked
supported
verified
```

只有真实证据链完整时：

``` text
CORRELATION_VERIFIED
```

不要因为：

``` text
两个事件相差 2ms
```

就直接认为它们一定存在因果关系。

------------------------------------------------------------------------

# 20. M5：Artifact Manager

所有大数据：

``` text
PCAP
dump
APK
decompiled project
trace
HEX
HTTP body
HTTPS body
report
log
```

走：

``` text
Artifact Manager
```

MCP 返回：

``` text
artifact_id
type
size
path
sha256
created_at
```

------------------------------------------------------------------------

# 21. M5.5：MCP Server

MCP 是控制面。

------------------------------------------------------------------------

# 21.1 Core Surface

保持 ≤25。

优先：

``` text
device
apk
session
process
runtime
memory
network
packet
artifact
```

------------------------------------------------------------------------

# 21.2 Tool Surface Manager

工具状态：

``` text
registered
enabled
mounted
disabled
```

Core 与 Expert 不应该各写一套工具逻辑。

只是：

``` text
同一 Tool
不同 surface visibility
```

------------------------------------------------------------------------

# 21.3 Tool 三点注册

每个工具必须同步：

``` text
REGISTERED_TOOL_MODULES
_LAZY_IMPORTS
surface visible set
```

然后运行：

``` text
tools/list
```

做实际验证。

------------------------------------------------------------------------

# 22. Tool Schema 施工模板

每个工具：

``` text
name
title
description
inputSchema
outputSchema
annotations
```

Description 必须说明：

``` text
use_case
important_notes
next_step
latency
```

Input：

``` text
required
default
min
max
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

# 23. FAST Tool 施工

先做：

``` text
device.list
session.info
runtime.status
process.list
process.modules
process.threads
memory.read
network.connections
packet.get
```

这些工具是整个 AI 控制面的基础。

------------------------------------------------------------------------

# 24. JOB Tool 施工

后做：

``` text
memory.dump
packet.export
apk.decompile
runtime.trace
large capture
analysis
```

统一：

``` text
submit
→
job_id
→
status
→
result
```

------------------------------------------------------------------------

# 25. Error Contract

每个工具都必须区分：

``` text
bad args
not ready
stale session
timeout
permission
execution failure
internal error
```

错误应该给：

``` text
code
message
context
retryable
next_step
```

------------------------------------------------------------------------

# 26. Automation / Rule Engine

基础工具稳定以后才开发规则：

``` text
WHEN HTTP_REQUEST
WHERE path == /login
THEN capture_stack
AND capture_packet
AND create_analysis_object
```

以及：

``` text
WHEN FUNCTION_ENTER
WHERE module == target
THEN capture_arguments
```

------------------------------------------------------------------------

# 27. Workflow Engine

再往后：

``` text
trigger
→
condition
→
action
→
verification
→
artifact
→
report
```

每个 Action 都要有执行结果。

不能：

``` text
action requested
→
直接认为 completed
```

必须：

``` text
accepted
executed
verified
```

------------------------------------------------------------------------

# 28. AI Agent 层

AI 不是 Runtime。

AI 也不是 MCP Server。

AI 是：

``` text
规划
→
选择 Tool
→
观察结果
→
形成 AnalysisObject
→
继续调用 Tool
→
验证
→
报告
```

例如：

``` text
用户：
“帮我定位这个请求是谁发出的”

AI：
1 network.connections
2 HTTP request
3 correlation
4 capture_stack
5 runtime hook
6 inspect native
7 artifact
8 report
```

------------------------------------------------------------------------

# 29. AI 不允许自己"猜"

AI 必须区分：

``` text
observed
inferred
candidate
verified
```

例如：

``` text
候选函数：
0x12345678

证据：
HTTP request timestamp
TID
Native stack
Module
```

而不是：

``` text
“这个函数就是发送函数。”
```

除非证据已经验证。

------------------------------------------------------------------------

# 30. 每个功能的垂直切片方法

不要横向一次写完整系统。

错误：

``` text
先写完整 Hook Manager
再写完整 EventBus
再写完整 MCP
```

更推荐：

``` text
一个最小真实 Hook
 ↓
Hook Manager
 ↓
Gum Backend
 ↓
EventBus
 ↓
IPC
 ↓
MCP
 ↓
AI
```

跑通后再扩展第二种 Hook。

Memory：

``` text
memory.read
→
Runtime
→
IPC
→
MCP
→
AI
```

Network：

``` text
capture
→
Event
→
IPC
→
MCP
→
AI
```

这样每一步都是完整闭环。

------------------------------------------------------------------------

# 31. Debug 优先级

出现错误时严格：

``` text
编译错误
 ↓
链接错误
 ↓
加载错误
 ↓
Runtime init
 ↓
IPC
 ↓
Session
 ↓
Backend
 ↓
功能
 ↓
MCP
 ↓
AI
```

不要在底层没运行时调 AI Prompt。

------------------------------------------------------------------------

# 32. Android 崩溃排查顺序

``` text
logcat
→
tombstone
→
signal
→
backtrace
→
fault address
→
module
→
symbol
→
source
```

必须保存：

``` text
crash artifact
```

不要只复制一句：

``` text
SIGSEGV
```

------------------------------------------------------------------------

# 33. Gum 问题排查顺序

``` text
Gum 初始化
→
Process architecture
→
Module map
→
Address validity
→
Instruction boundary
→
Interceptor
→
Callback
→
Thread state
→
Backtrace
```

一次只改一个变量。

------------------------------------------------------------------------

# 34. LSPlant 问题排查顺序

``` text
SDK
→
ART capability
→
LSPlant library load
→
JNI environment
→
class
→
method
→
overload
→
hook
→
callback
```

------------------------------------------------------------------------

# 35. Network 问题排查顺序

``` text
adapter alive
→
capture
→
connection
→
DNS
→
TCP/UDP
→
protocol decode
→
TLS state
→
HTTP
→
intercept
→
modify
→
verify
```

------------------------------------------------------------------------

# 36. MCP 问题排查顺序

``` text
server start
→
bridge
→
UDS
→
HELLO
→
READY
→
Session
→
tools/list
→
tool input validation
→
Runtime command
→
response
```

------------------------------------------------------------------------

# 37. 每次提交前必须检查 Git Diff

WorkBuddy 必须检查：

``` text
git status
git diff --stat
git diff
```

确认：

``` text
没有偷偷修改 third_party
没有偷偷修改 zygisk.hpp
没有增加依赖
没有修改无关目录
没有删除测试
没有删除旧日志
```

------------------------------------------------------------------------

# 38. 第三方源码绝对不直接修改

如果发现：

``` text
Frida-Gum
LSPlant
PCAPdroid
```

需要修改：

不要直接改：

``` text
third_party/
```

必须：

``` text
记录问题
→
确认是否真的需要 fork
→
建立 external/fork
→
更新 LICENSES
→
更新 SOURCE_LOCK
```

------------------------------------------------------------------------

# 39. 每阶段结束必须生成报告

格式：

``` text
阶段：
完成任务：
修改文件：
新增文件：
删除文件：
新增依赖：
编译：
测试：
真机：
日志：
Artifacts：
失败项：
风险：
下一阶段：
```

------------------------------------------------------------------------

# 40. WorkBuddy 单任务 Prompt

以后直接使用：

``` text
你现在是 ZygiskAIRuntime 项目的实施工程师。

先阅读：
- docs/00-权威基线/项目总基线_v1.1.md
- docs/00-权威基线/STRUCTURE.md
- docs/00-权威基线/SOURCE_LOCK.md
- docs/00-权威基线/LICENSES.md
- docs/10-施工指导/ZygiskAIRuntime_专业开发技术指导总文档_v1.0.md
- docs/10-施工指导/ZygiskAIRuntime_AI施工手册_v2.0.md

当前阶段：
[M0/M1/M2/M3...]

本次唯一任务：
[只填写一个具体任务]

任务目标：
[一个可验证结果]

允许修改：
[明确文件]

禁止修改：
[明确文件]

禁止事项：
1. 不改变冻结架构。
2. 不新增未经批准的第三方依赖。
3. 不修改 third_party。
4. 不制造 mock/fake success。
5. 不绕过 Session。
6. 不绕过 Write Guard。
7. 不跨阶段。
8. 不把底层第三方 API 暴露给 AI。
9. 不删除现有测试或证据。

执行步骤：
1. 先检查当前实际文件。
2. 先检查依赖。
3. 说明实现方案。
4. 再修改代码。
5. 编译。
6. 测试。
7. 如果涉及真机，进行真机验证。
8. 收集日志/Artifact。
9. 检查 git diff。

如果发现前置条件不足：
停止编码，报告阻塞项。

最终必须输出：
- 修改文件
- 实现内容
- 编译命令
- 编译结果
- 测试结果
- 真机结果
- 日志证据
- 未完成项
- 风险
- 下一步
```

------------------------------------------------------------------------

# 41. M1 专用 Prompt

``` text
当前只允许做 M1 构建链。

不要实现 Hook。
不要实现 Memory。
不要实现 Network。
不要实现 MCP Tool。
不要增加业务逻辑。

目标：
证明 Frida-Gum、LSPlant 和 ZygiskAIRuntime 能形成真实 Android arm64 二进制。

顺序：
1. 环境检查
2. Frida-Gum 单独构建
3. LSPlant 单独构建
4. Native CMake
5. libai_analyzer.so
6. module package

任何一步失败都停下来。

禁止用预编译假库替代真实依赖。
禁止创建 fake libgum.a。
禁止创建 fake liblsplant.so。
禁止返回“理论上可以编译”。

必须给出真实构建输出和产物路径。
```

------------------------------------------------------------------------

# 42. M2 专用 Prompt

``` text
当前只允许实现 Zygisk + Runtime + IPC + Session。

目标：
启动真实 APK 后，Zygisk 自动进入目标进程，Runtime 建立 IPC，完成 HELLO/READY，并创建真实 Session。

第一阶段只实现：
runtime.status
process.list
process.info
process.modules
process.threads

禁止：
Hook
Memory Write
Network
Packet
AI automation

必须真实真机验证。
```

------------------------------------------------------------------------

# 43. M3 Hook 专用 Prompt

``` text
当前只允许实现 Native Hook 最小垂直切片。

Backend：
Frida-Gum。

要求：
gum_* 只能位于 gum_backend.cpp。

最小目标：
指定 module + address
→ install
→ HOOK_INSTALLED
→ HOOK_ENTER
→ HOOK_LEAVE

事件必须包含：
hook_id
session_id
pid
tid
timestamp
module
address
arguments
backtrace

没有真实 ENTER/LEAVE 就不能报告 Hook 已成功。
```

------------------------------------------------------------------------

# 44. Memory 专用 Prompt

``` text
当前只允许实现 memory.read / memory.write。

read 必须真实读取目标进程。

write 必须：
validate
preview
backup
confirm
execute
read-back
verify
commit

返回 original/new/verified。

禁止：
数据库模拟
缓存模拟
fake success
```

------------------------------------------------------------------------

# 45. Network 专用 Prompt

``` text
当前只实现 Network Capture + HTTP。

先验证真实网络流量。

不要宣称 HTTPS 已解密。
不要实现 Packet Modify，除非本任务明确要求。

必须明确：
captured
decoded
decrypted
interceptable
modifiable

五个状态不可互相推导。
```

------------------------------------------------------------------------

# 46. Packet 专用 Prompt

``` text
当前只实现 packet.get / packet.modify。

packet.modify 必须真实作用于网络数据路径。

必须保存：
original_hex
modified_hex
offset
changed_length
timestamp
rule
session

必须验证执行结果。

不能只修改数据库或 MCP 返回值。
```

------------------------------------------------------------------------

# 47. Correlation 专用 Prompt

``` text
当前只实现一个最小可验证 correlation：

HTTP Request
→ Connection
→ PID/TID
→ Native/Java stack
→ Module
→ Function

每个链接必须保留 evidence。

不能仅根据时间接近做确定性结论。

最终只有证据完整才标记 CORRELATION_VERIFIED。
```

------------------------------------------------------------------------

# 48. MCP 专用 Prompt

``` text
当前只实现 MCP Server 与一个 Tool。

先完成：
server
→ bridge
→ session
→ runtime.status

确认 tools/list 能看到该工具。

完成一个工具后再扩展第二个。

禁止一次性生成所有工具。
```

------------------------------------------------------------------------

# 49. 优化阶段

功能完全真实运行后，才进入优化。

顺序：

``` text
正确性
→
稳定性
→
兼容性
→
可观测性
→
性能
→
内存
→
启动速度
→
并发
→
AI体验
```

------------------------------------------------------------------------

# 50. 性能优化指标

后续逐步建立：

``` text
Runtime startup
IPC RTT
Tool latency
Hook overhead
Event throughput
Memory overhead
Network throughput
Artifact write speed
MCP response size
```

优化必须有：

``` text
before
after
test method
environment
result
```

不要凭感觉说：

``` text
“性能提高很多”
```

------------------------------------------------------------------------

# 51. 稳定性优化

必须测试：

``` text
长时间运行
大量 Hook
大量 Event
高频网络
大量 Memory Search
MCP reconnect
App crash
Runtime crash
device disconnect
```

------------------------------------------------------------------------

# 52. 兼容性矩阵

最终至少维度：

``` text
Android version
API
device
ROM
ABI
page size
Magisk
Zygisk
target app
```

每个组合记录：

``` text
PASS
DEGRADED
FAIL
```

并记录具体原因。

------------------------------------------------------------------------

# 53. 深入研究阶段

功能稳定以后再进入源码级研究。

## Frida-Gum

研究：

``` text
Interceptor
GumInvocationContext
instruction relocation
AArch64
Stalker
thread state
exception
```

## ART / LSPlant

研究：

``` text
ArtMethod
ClassLinker
Dex
JNI
ClassLoader
SDK differences
```

## Network

研究：

``` text
TLS
HTTP/2
HTTP/3
QUIC
WebSocket
Cronet
OkHttp
native socket
```

## Correlation

研究：

``` text
causal graph
timestamp
PID/TID
connection
stack
hook
evidence
confidence
```

## AI

研究：

``` text
planning
tool selection
automatic correlation
workflow
rules
artifact reasoning
```

------------------------------------------------------------------------

# 54. 研究纪律

深入研究时：

``` text
先问题
→
再假设
→
再资料
→
再实验
→
再证据
→
再代码
```

禁止：

``` text
看到一个 GitHub 项目
→
直接复制
→
改变架构
```

研究结果应该进入：

``` text
docs/30-研究/
```

并注明：

``` text
日期
版本
来源
实验环境
结论
限制
```

------------------------------------------------------------------------

# 55. 文档同步纪律

任何以下变化：

``` text
协议
版本
第三方
目录
工具
Session
Error
Artifact
Capability
```

必须同步对应文档。

代码不能成为唯一真相。

------------------------------------------------------------------------

# 56. Golden Test 思维

每个关键功能都应该有：

``` text
输入
→
预期状态
→
预期事件
→
预期结果
```

例如 Hook：

``` text
create
→
pending
→
installed
→
ENTER
→
LEAVE
→
active
```

Memory：

``` text
read original
→
write
→
read back
→
verified
```

Packet：

``` text
original
→
modified
→
send
→
observed
```

------------------------------------------------------------------------

# 57. 最终项目完整闭环

最终不是：

``` text
MCP 看起来能用
```

而是：

``` text
真实 APK
 ↓
Zygisk
 ↓
libai_analyzer.so
 ↓
Runtime
 ↓
Frida-Gum / LSPlant
 ↓
Hook
 ↓
EventBus
 ↓
IPC
 ↓
Session
 ↓
MCP
 ↓
AI
```

Network：

``` text
真实网络
 ↓
Network Adapter
 ↓
EventBus
 ↓
Correlation
 ↓
MCP
 ↓
AI
```

Memory：

``` text
AI
 ↓
MCP
 ↓
Session
 ↓
Runtime
 ↓
真实进程
 ↓
Read/Write
 ↓
Verify
 ↓
Event
 ↓
AI
```

Packet：

``` text
AI
 ↓
MCP
 ↓
Write Guard
 ↓
Network
 ↓
Modify
 ↓
Verify
 ↓
Artifact/Event
 ↓
AI
```

------------------------------------------------------------------------

# 58. 最终十项验收

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

每一项都要求：

``` text
真实执行
+
真实证据
+
错误处理
+
可复现
```

------------------------------------------------------------------------

# 59. 最终 Release Gate

没有以下内容不得进入 Release Candidate：

``` text
[ ] clean build
[ ] dependency audit
[ ] license audit
[ ] protocol tests
[ ] real device
[ ] Zygisk
[ ] Runtime
[ ] IPC
[ ] Session
[ ] Native Hook
[ ] Java Hook
[ ] Memory
[ ] Network
[ ] HTTPS
[ ] Packet
[ ] Correlation
[ ] Artifact
[ ] MCP
[ ] heartbeat
[ ] reconnect
[ ] crash handling
[ ] compatibility matrix
[ ] performance baseline
[ ] documentation
```

------------------------------------------------------------------------

# 60. 给 WorkBuddy AI 的最终总命令

``` text
你不是本项目的架构设计者。

你是本项目的实施工程师。

架构已经冻结。

你的职责不是重新发明系统，而是按照项目文档，把系统逐阶段真实落地。

任何任务开始前：

1. 阅读上位文档。
2. 检查当前实际代码。
3. 检查依赖和环境。
4. 确认前置阶段已经完成。
5. 明确本次唯一任务。
6. 只修改允许范围。
7. 完成后真实编译。
8. 涉及 Runtime 时进行真实运行。
9. 涉及 Hook/Memory/Network 时必须取得真实执行证据。
10. 输出完整验收报告。

如果不能真实实现：
不要 mock。
不要 fake。
不要返回 success。
不要用数据库模拟 Runtime。
不要用静态 JSON 模拟事件。
不要把“代码已经写了”当成“功能已经完成”。

如果遇到未知问题：
先定位。
再验证。
再修改。
一次解决一个问题。

如果发现架构冲突：
停止编码。
报告冲突。
等待人工决定。

本项目的唯一完成标准：

真实 APK
→
真实 Zygisk
→
真实 Runtime
→
真实 Backend
→
真实 Hook / Memory / Network
→
真实 Event
→
真实 Correlation
→
真实 Artifact
→
真实 MCP
→
真实 AI 控制。

任何中间环节没有真实证据，都不能宣称整个能力已经完成。
```

------------------------------------------------------------------------

# 61. 项目开发节奏总结

真正推荐的节奏：

``` text
第一轮：
把环境准备好

第二轮：
把协议说清楚

第三轮：
把第三方编译起来

第四轮：
让 Zygisk 真进入 App

第五轮：
让 Runtime 真活起来

第六轮：
让 IPC 真通信

第七轮：
让 Session 真管理生命周期

第八轮：
让一个 Native Hook 真生效

第九轮：
让一个 Java Hook 真生效

第十轮：
让 Memory 真读写

第十一轮：
让 Network 真抓到

第十二轮：
让 HTTP 真拦截

第十三轮：
验证 HTTPS 五级

第十四轮：
让 Packet 真修改并验证

第十五轮：
建立 Correlation

第十六轮：
Artifact

第十七轮：
MCP Tool Surface

第十八轮：
AI Agent Workflow

第十九轮：
稳定性

第二十轮：
性能

第二十一轮：
兼容性

第二十二轮：
深入源码研究

第二十三轮：
持续优化
```

------------------------------------------------------------------------

# 62. 最重要的一条

> **不要追求"代码量完成度"，追求"真实闭环完成度"。**

一个真实完成的：

``` text
runtime.status
```

比 30 个没有真实 Runtime 的工具更有价值。

一个真实生效的：

``` text
Native Hook
```

比 100 个 Hook API 壳更有价值。

一次真实：

``` text
Memory Write → Read-back → Verify
```

比一个漂亮的 Memory UI 更有价值。

一次真实：

``` text
HTTP → Thread → Stack → Native → Module → Function
```

比几十页 AI 分析报告更有价值。

因此整个工程永远遵循：

``` text
小切片
→
真实执行
→
证据
→
验收
→
扩大能力
→
优化
→
深入研究
```

**这就是 ZygiskAIRuntime 后续交给 WorkBuddy AI 的正式施工方法。**
