# Zygisk 产物目录

构建产物按 ABI 命名落在这里，由 Zygisk 直接加载：

```text
module/zygisk/arm64-v8a.so     ← libai_analyzer.so
```

首发只做 `arm64-v8a`。`.gitignore` 已排除 `*.so`，但显式放行本目录。

⚠️ 当前本机无 NDK / CMake，产物尚未构建过。
