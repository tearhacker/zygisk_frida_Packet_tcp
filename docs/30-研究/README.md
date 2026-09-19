# 30-研究

深入研究记录落点。**项目稳定以后才进入研究**，顺序见
`../10-施工指导/ZygiskAIRuntime_专业开发技术指导总文档_v1.0.md` §29。

---

## 记录格式

每条研究记录必须注明：

```text
日期
版本
来源
实验环境
结论
```

**禁止**：看到一个 GitHub 项目 → 直接复制 → 改变架构。

---

## 研究方向（按上位文档 §29）

| 面 | 主题 |
|---|---|
| **Runtime** | Frida-Gum Interceptor · Stalker · 指令重定位 · AArch64 ABI · register/context · 线程局部状态 · 信号安全 · loader/linker · /proc maps · 内存权限 |
| **ART** | ART runtime · ClassLinker · ArtMethod · JNI · Dex 加载 · 类加载时机 · Android SDK 差异 · 16KB 页 |
| **Network** | TLS · 证书固定 · HTTP/2 · HTTP/3 · QUIC · WebSocket · Cronet · OkHttp · native socket · VPN 抓包 |
| **Correlation** | 证据链构建 · 时序推断的置信边界 · AnalysisObject 结构 |

---

## 当前状态

无研究记录。项目尚未完成首次编译，未进入研究阶段。

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
