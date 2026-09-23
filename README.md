# 通用修改器模板

单机游戏实时修改器：通用方法论（SKILL）+ 可直接填空的源码模板。UE/Unity 通用，开工先判引擎。

## 四个目录

| 目录 | 是什么 | 先看哪个 |
|---|---|---|
| `generic-trainer/` | 通用修改器 SKILL：引擎判定、分层、侦察六问、搜→断→反→补丁、代码洞约定 | `SKILL.md` → `generic-MODS.md` |
| `bepinex/` | Unity BepInEx 插件 MOD 方法论 SKILL（游戏内 DLL 路线） | `SKILL.md` → `unity-MODS.md` |
| `ue-trainer-template/` | 源码模板：通用 UI + 内存引擎 + Lua 模板，新游戏只填一个 `game.yaml` | `README.md` |
| `toolbox/` | 侦察工具包（截图/OCR/PE/DB/CE桥，只读+CE驱动，不点界面） | `toolbox/README.md` |

`ue-trainer-template/games/` 下带两个实战例子（`lostvillage`、`idledevils`），`_template` 是空脚手架。

## 给 AI 用的方式（opencode）

`generic-trainer/SKILL.md`、`bepinex/SKILL.md` 是标准 SKILL 格式。两种挂载二选一：

```json
// opencode.json
{ "$schema": "https://opencode.ai/config.json",
  "skills": { "paths": ["<本仓库绝对路径>"] } }
```

或把 `generic-trainer/`、`bepinex/` 拷到 `~/.config/opencode/skills/` 下。之后说一句"通用修改器"即自动加载（Unity 内挂路线同属该技能，引擎由 AI 判定分流）。

## 本机路径说明

SKILL 和模板里写的默认路径（如 `D:/github-ue/...`）是作者本机位置，新电脑把本仓库.clone到 `D:/github-ue` 即一致；换位置时按下述覆盖：模板位置即本仓库位置；游戏根目录、CE 桥路径在开工时告诉 AI 即可。

## 工作流（一句话）

报游戏根目录 + 需求 → AI 侦察填 `games/<新游戏>/game.yaml` → 联调 → `tools/build.py` 打单 exe。
通用经验进 SKILL 文档，单游戏私货（类名、AOB、补丁字节）只进该游戏自己的 `MOD-MEMORY.md`。
