---
name: ue-trainer
description: UE/Unity 单机游戏修改器开发. Use when user mentions 游戏修改器, UE4SS, CE 内存补丁, AOB, 免材料升级, 物品添加, code cave, GameAssembly, 单窗口开关式修改器, 或新游戏开工. Covers UE4SS Lua 逻辑层 + CE/AOB native 补丁 + PyInstaller 单 exe 一体机. Use ONLY for game-trainer work.
---

# UE Trainer

单机游戏（UE 引擎为主，Unity IL2CPP 同理）实时修改器开发：外部 UI + UE4SS Lua + 内存补丁，单窗口开关式。

## 触发后先读（按顺序）

1. 同目录 `ue-MODS.md` —— 通用方法论全文（分层、六问、搜断反补丁、cave 约定）。
2. 同目录 `MOD-MEMORY.template.md` —— 新游戏建档用。
3. 模板 `../ue-trainer-template/README.md` —— 源码结构（`engine/` 不动，只填 `games/<slug>/game.yaml`）。

## 开工三件套（缺一就问用户要）

游戏根目录 / 需求原文（一句话）/ 该游戏的 `MOD-MEMORY.md`（新游戏则新建）。

## 工具（toolbox 包，不点 CE 界面）

`D:/skills/toolbox/`（`import toolbox; toolbox.run(...)`，CLI 在 `D:/skills` 下 `python -m toolbox`）：

| 步骤 | 调用 |
|---|---|
| 看游戏画面/数值 | `run("shot_ocr", window="游戏标题")`，改完再截一次验证 |
| 搜值/收窄 | `run("ce", action="scan"/"next"/"results", ...)` |
| 反汇编门后判断 | `run("ce", action="dis", address=...)`；静态看文件用 `run("pe", ...)` |
| 断点找写入者 | `run("ce", action="watch"/"hits", ...)`，触发动作由用户做 |
| 查 dump 表 | `run("db", action="search", keyword=..., db=...)` |

前置：CE 已启动+桥已加载+已 attach；CE 设置 Extra 里关掉 Query memory。
CE 未就绪时 `ce` 返回 Error 自查提示，不抛异常。

## 铁律

- 通用方法进 `ue-MODS.md`，游戏私货（类名、AOB、补丁字节、ID）只进该游戏 `MOD-MEMORY.md`。
- 物品添加走官方发奖链（Lua），免材料/不扣/锁值走内存补丁；一勾联动，同开同关，退出即恢复。
- CE 只做开发期，成品走 `engine/memory.py`（bytes + cave + data 区），`tools/build.py` 打单 exe。
- 本机路径（换机器时覆盖）：模板 `D:/skills/ue-trainer-template`，CE 桥 Lua 侧 `D:/opencode/ce-bridge/MCP_Server/ce_mcp_bridge.lua`（放 CE autorun），Python 直连脚本 `D:/opencode/ce-bridge/ce_direct.py`（toolbox 的 `ce` 工具与它同协议）。
- 路线图：把 CE 桥 MCP 化（原生工具替代桥脚本），实战前顺手做。
