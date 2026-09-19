# 外部工具（不编译进核心）

这些工具**一律不链接、不 copy 源码进 `libai_analyzer.so`**。它们运行在 PC 侧或独立进程，
通过 IPC / 独立 App 与 Runtime 协作。

```text
PC ── AI ── MCP Host ── MCP Bridge ── IPC ── Android ── Zygisk Runtime
                  │
                  ├── JADX ────── 分析 APK/DEX → 结果回流 AI/MCP
                  ├── rizin ───── Native 静态分析（独立进程 CLI）
                  └── mitmproxy ── PC 网络侧捕获/改包
```

| 目录 | 工具 | 形态 | 约束 |
|---|---|---|---|
| `frida/` | Frida | 参考，不作为运行时 | 运行时是 Frida-Gum，不是 frida-server |
| `jadx/` | JADX | Host 侧调用 | Apache-2.0，可 CLI 调用 |
| `rizin/` | Rizin | Host 侧独立进程 CLI | 🔴 GPL-3.0：源码不得并入 `host/`，只能进程外调用 |
| `mitmproxy/` | mitmproxy | Host 侧 Adapter | MIT |
| `wireshark/` | Wireshark / tshark | PC 侧分析 | 只消费 pcap，不参与运行时 |

Android 侧网络能力走独立 App（PCAPdroid / NetBare），经 IPC 集成，
源码在 `../../external/network/`，同样不进本工程树。

> 🔴 PCAPdroid 是 **GPL-3.0**：禁止链接或 copy 源码，只能作为独立 App 经 IPC 集成。
> 详见 `../../docs/00-权威基线/LICENSES.md`。

---

## 作者与社区

**泪心独立研发 —— APP 逆向 / 封包 / 动态内存调试工具。**

```text
开发者    泪心
QQ        2254013571
Q群       435539500
Discord   https://discord.gg/yghYHcEdD
官网      http://teargamestorem.top/
```
