# 新机器开工 SETUP（一次配好，以后只报游戏目录+需求）

> 以后新机器，你只需要告诉 AI 四样东西，剩下的按本文走：
> 1. 本仓库地址（技能+模板）：`https://github.com/qiaobangzhudashen/ue-trainer-template`，固定clone到 `D:/github-ue`（技能注册路径即此，新旧电脑一致）
> 2. CE 安装目录（Bridge Lua 放 autorun 自启用）
> 3. 游戏根目录（装游戏的那台机器上的路径）
> 4. 一句话需求（如“建筑免材料”）+ 口令“通用修改器”（Unity 内挂路线同属该技能，引擎由 AI 按目录判定分流）

## 1. 装前置（Windows 10/11，64 位 Python 对 64 位游戏）

- [Cheat Engine 7.x](https://www.cheatengine.org)（仅 UE 修改器路线需要；BepInEx 路线不需要 CE）
- Python 3.10+（64 位）

```powershell
pip install pymem pyinstaller pyyaml pywin32 pillow capstone
# 可选：pip install paddleocr keystone-engine（OCR 看画面 / cave 组装制作期用）
```

## 2. 拉两个仓库

```powershell
git clone https://github.com/qiaobangzhudashen/ue-trainer-template.git D:/github-ue
git clone https://github.com/miscusi-peek/cheatengine-mcp-bridge.git D:/opencode/ce-bridge
```

`ce_direct.py`（Python 直连脚本）与本技能同协议，若 `D:/opencode/ce-bridge` 下没有，从老机器拷一份过去即可。

## 3. CE 配置（三件事，做一次）

1. 把 `D:/opencode/ce-bridge/MCP_Server/ce_mcp_bridge.lua` 放进 **CE 安装目录下的 `autorun`**，以后 CE 启动自动加载。
   看到 `[MCP v12.0.0] MCP Server Listening on: CE_MCP_Bridge_v99` 即成功。
2. CE → Settings → Extra → **关掉 "Query memory region routines"**（开着扫保护页会蓝屏，硬性要求）。
3. CE 里 attach 上目标游戏进程。

## 4. 挂载技能（二选一）

```json
// opencode.json（新旧电脑统一注册到本仓库位置）
{ "$schema": "https://opencode.ai/config.json",
  "skills": { "paths": ["D:/github-ue"] } }
```

或把 `D:/github-ue/generic-trainer/`、`D:/github-ue/bepinex/` 拷到 `~/.config/opencode/skills/` 下。

## 5. 冒烟检查（AI 开工前自己跑）

```powershell
cd D:/github-ue
python -m toolbox info            # 看 pe/shot/ocr/db/ce 哪些可用
python -m toolbox ce action=ping  # CE 在线应返回 success；不通则按提示自查第 3 步
```

`toolbox` 用法：`import toolbox; toolbox.run("ce", action="scan", value="15000")`，
完整清单看 `toolbox/README.md`。注意默认路径都是本说明的 `D:/github-ue`，
换盘符/换目录时开工告诉 AI 覆盖即可（通用修改器技能“本机路径”条、模板位置即本仓库位置）。

## 6. 开工口令

- 通用口令：报**游戏根目录** + **一句话需求** + 说“**通用修改器**”。
  AI 先扫目录判引擎：UE 走 UE4SS+CE 路线，Unity-Mono 转 BepInEx 路线，IL2CPP 六问后再定。
  新游戏的 `MOD-MEMORY.md` 由 AI 新建，你不用准备。

之后流程（AI 按技能执行）：静态侦察 → 官方链/Hook → CE 搜断反补丁 → 截图验证 →
填 `ue-trainer-template/games/<新游戏>/game.yaml` → 联调 → `tools/build.py` 打单 exe。
需要你做的只有游戏里的**触发动作**（让数值变化/让断点命中）。
