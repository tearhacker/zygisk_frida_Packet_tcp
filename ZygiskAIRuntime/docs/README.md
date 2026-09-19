# 文档索引

架构与协议的**唯一权威**是 `../../docs/00-权威基线/项目总基线_v1.1.md`。
本目录只放工程实施层面的细节文档，与之冲突时以总基线为准。

| 子目录 | 内容 |
|---|---|
| `architecture/` | 分层说明、Runtime 与 Backend 的边界 |
| `build/` | 构建流程、NDK/meson 参数、产物落位 |
| `runtime/` | Runtime Core：启动顺序、生命周期、降级路径 |
| `hook/` | Hook 状态机、Native/Java 两条路径的分发 |
| `memory/` | Memory Engine、Write Guard 强制路径、read-back 校验 |
| `art/` | ART Backend、LSPlant 适配、SDK 分级降级 |
| `mcp/` | MCP 分面、工具注册表、Expert Surface 挂载 |
| `deployment/` | 模块打包、刷入、真机验证步骤 |

## 项目级文档（已全部归拢到 `../../docs/`，按优先级分层）

```text
../../docs/README.md            文档中心索引（先看这个）

  P0  ../../docs/00-权威基线/项目总基线_v1.1.md
  P1  ../../docs/00-权威基线/SOURCE_LOCK.md
  P2  ../../docs/00-权威基线/LICENSES.md
  P3  ../../docs/00-权威基线/STRUCTURE.md
  P4  ../../docs/10-施工指导/ZygiskAIRuntime_专业开发技术指导总文档_v1.0.md
  P5  ../../docs/10-施工指导/ZygiskAIRuntime_AI施工手册_v2.0.md

      ../../docs/20-构建与审计/    P-1 交付物（环境 / 设备 / 阻塞）
      ../../docs/30-研究/         深入研究记录
      ../../docs/90-历史归档/     历史归档，不作实施依据
```
