---
name: generic-trainer
description: 通用单机游戏修改器开发（UE/Unity 通用，先判引擎再选路线）. Use when user mentions 通用修改器, 游戏修改器, UE4SS, CE 内存补丁, AOB, 免材料升级, 物品添加, code cave, GameAssembly, 单窗口开关式修改器, 或新游戏开工. Covers 开工引擎判定路由，UE4SS Lua 逻辑层 + CE/AOB native 补丁 + Unity 引擎判定分流 + PyInstaller 单 exe 一体机. Use ONLY for game-trainer work.
---

# 通用修改器

单机游戏实时修改器开发（UE/Unity 通用：开工先判引擎，UE 走 UE4SS + 内存补丁，Unity-Mono 走 BepInEx 内挂）。

## 触发后先读（按顺序）

1. 同目录 `generic-MODS.md` —— 通用方法论全文（引擎判定、分层、六问、搜断反补丁、cave 约定）。
2. 同目录 `MOD-MEMORY.template.md` —— 新游戏建档用。
3. 模板 `../ue-trainer-template/README.md` —— 源码结构（`engine/` 不动，只填 `games/<slug>/game.yaml`）。

## 开工三件套（缺一就问用户要）

游戏根目录 / 需求原文（一句话）/ 该游戏的 `MOD-MEMORY.md`（新游戏则新建）。

## 开工第 0 步：引擎判定（先于一切，不猜）

拿到游戏根目录先扫目录定引擎，结果填 `game.yaml: engine`，后续路线、桥、打包全跟它走：

- `Engine/` 目录（`Content/Paks/*.pak` 常嵌在内层游戏目录下）→ Likely UE，走本技能（UE4SS + CE/AOB，打包 Trainer）。
- `*_Data/` + `UnityPlayer.dll`，且有 `Managed/*.dll` → Likely Unity-Mono，转 bepinex 技能（BepInEx + Harmony，不走 AOB，打包 Setup 安装器）。
- `GameAssembly.dll` + `global-metadata.dat` → Likely Unity-IL2CPP，两边文档都读，六问后再定。
- 冲突或都无 → 停下问用户，不套用上一游戏的结论。

`BepInEx/`、`ue4ss/` 目录只能证明已改装，不能证明引擎。判错路线比不判更贵。

## 工具（toolbox 包，不点 CE 界面）

`D:/github-ue/toolbox/`（`import toolbox; toolbox.run(...)`，CLI 在 `D:/github-ue` 下 `python -m toolbox`）：

| 步骤 | 调用 |
|---|---|
| 看游戏画面/数值 | `run("shot_ocr", window="游戏标题")`，改完再截一次验证 |
| 搜值/收窄 | `run("ce", action="scan"/"next"/"results", ...)` |
| 反汇编门后判断 | `run("ce", action="dis", address=...)`；静态看文件用 `run("pe", ...)` |
| 断点找写入者 | `run("ce", action="watch"/"hits", ...)`（≈CE的F5/F6），触发动作由用户做 |
| 回溯调用/单步找解密 | `run("ce", action="lbr", op="start")`→做动作→`op="read"`；`run("ce", action="step", thread=..., count=...)`看`[CRYPTO?]` |
| 定稿：唯一AOB/AA注入/指针链 | `run("ce", action="signature"/"aa"/"ptrchain", ...)`，AA先`aacheck`验语法 |
| 查 dump 表 | `run("db", action="search", keyword=..., db=...)` |

前置：CE 已启动+桥已加载+已 attach；CE 设置 Extra 里关掉 Query memory。
CE 未就绪时 `ce` 返回 Error 自查提示，不抛异常。

## 铁律

- 通用方法进 `generic-MODS.md`，游戏私货（类名、AOB、补丁字节、ID）只进该游戏 `MOD-MEMORY.md`。
- 上传云端死规：用户说上传/推送/同步到云端时，先问要不要先检测一遍，经用户明确确认后再执行 `git add/commit/push`；未经确认绝不推送。
- 模板目录边界：只改模板通用层（`engine/`、`ui/`、`tools/`、`lua/`、`games/_template/`）；新游戏从 `_template` 复制到自家工程目录再填，验证完也不写回模板（模板内已有示例仅归档）。
- 物品添加走官方发奖链（Lua），免材料/不扣/锁值走内存补丁；一勾联动，同开同关，退出即恢复。
- CE 只做开发期，成品走 `engine/memory.py`（bytes + cave + data 区），`tools/build.py` 打单 exe。
- 本机路径（换机器时覆盖）：模板在本仓库 `ue-trainer-template/`（挂载路径即仓库位置，游戏私货里的旧 `D:/skills/...` 写法一律以此为准），CE 桥 Lua 侧 `D:/opencode/ce-bridge/MCP_Server/ce_mcp_bridge.lua`（放 CE autorun），Python 直连脚本 `D:/opencode/ce-bridge/ce_direct.py`（toolbox 的 `ce` 工具与它同协议）。
- 路线图：把 CE 桥 MCP 化（原生工具替代桥脚本），实战前顺手做。
