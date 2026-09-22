---
name: bepinex
description: Unity BepInEx MOD 开发. Use when user mentions BepInEx, Unity MOD, IL2CPP/Mono 插件, Harmony 补丁, 读改写物品属性, 或 Unity 游戏新功能开工. Covers 构型判定, 目标系统六问, 读改写实现规范, IMGUI 窗口约定. Use ONLY for Unity BepInEx mod work, not UE trainer work (那是 ue-trainer).
---

# BepInEx

Unity 游戏 BepInEx 插件式 MOD 开发：游戏内 DLL，走官方 API 读改写。

## 触发后先读（按顺序）

1. 同目录 `unity-MODS.md` —— 通用方法论全文（构型判定、六问、读改写、生命周期、UI 约定）。
2. 同目录 `GAME-SCOUT.template.md` —— 新游戏/新类目先填侦察表再动手。
3. 同目录 `MOD-MEMORY.template.md` —— 结论归档用。

## 开工流程

静态侦察 → 构型判定（Mono/IL2CPP 证据）→ 确认 BepInEx 分支与启动 → 六问未完成不写业务代码 → 最小用例（读一改一重读）→ 归档。

## 铁律

- 通用方法进 `unity-MODS.md`，游戏私货（类名、枚举、签名、路径）只进该游戏 `MOD-MEMORY.md`。
- 写之前先读，改最小字段，增量 API 先算 diff，写完验证（缓存/事件/UI/场景切换/重复操作）。
- 不要从旧项目复制结论：BepInEx 分支、插件基类、输入后端、常驻入口每个游戏重验。
