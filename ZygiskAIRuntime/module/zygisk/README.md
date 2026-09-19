# Zygisk 产物目录

构建产物按 ABI 命名落在这里，**Zygisk 只从这一层加载**：

```text
module/zygisk/arm64-v8a.so      ← libai_analyzer.so（64 位进程）
module/zygisk/armeabi-v7a.so    ← libai_analyzer.so（32 位进程）
```

安装后的落点是 `/data/adb/modules/zygisk-packettool-tearhacker/zygisk/<abi>.so`。
**不存在"另一个专门放 so 的目录"** —— 这就是唯一的那一个。

要点：

- aarch64 机上两个 so **都会被 open**；只打 arm64 的话，32 位 App 不会被注入。
- 判定开关是「`zygisk/` 目录存在」，与 module.prop 里写不写 `zygisk=true` 无关
  （官方 module.prop 字段表里没有这个字段）。
- 本目录**只应放 `<abi>.so`**，其它文件一律被 `scripts/package.py` 排除（不会进 zip）。
- 本目录是 release/debug 的**共用暂存位**，打包前必须先拷对应变体。

⚠️ 若这里出现 `unloaded` 文件，表示 Magisk 判定本机库 incompatible，之后**永不加载**
本模块。删掉它即可恢复。

当前产物（2026-09-19 实测）：arm64 13254560 B / armv7 10912688 B；
两者导出符号均只有 `zygisk_module_entry` 与 `zygisk_companion_entry`。
