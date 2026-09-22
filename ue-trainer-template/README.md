# UE 通用修改器源码模板

> 给 agent 看的源码,不是给玩家的手填表.新游戏流程固定:
> 你报游戏根目录 + 需求,我负责 CE 里搜断反补丁 + Lua 里定位官方发奖链,
> 填进 `games/<slug>/game.yaml`,调通后再 `tools/build.py` 打成单 exe.

## 目录

```
engine/memory.py      内存引擎 (bytes + cave,游戏无关,不动)
engine/lua_bridge.py  cmd.txt + 日志桥 (不动)
engine/db.py          items.txt 读取 (不动)
ui/app.py             通用界面 (读 game.yaml 驱动,不动)
lua/template_main.lua Lua 模板 (每个游戏复制改 GIVE/HOOK 段)
games/_template/      空配置 (新游戏起点)
games/lostvillage/    山门示例 (4 个 bytes 补丁已迁移验证)
tools/build.py        PyInstaller 单 exe 打包
tools/new_game.py     新游戏脚手架
```

## 新游戏分工

1. 你:给游戏根目录 + 一句话需求 (如建筑免材料 / 加物品).
2. 我:静态侦察 → UE4SS 定位发奖函数 → CE 抓检查/扣除 → 填 game.yaml →
   UI 联调 (Lua hook + 内存补丁同开同关) → 打包 exe.
3. 复杂补丁 (条件分支/寄存器保护,原来 CE 里要 alloc 的) 用 `type: cave`,
   机器码贴 `cave_hex`,申请/跳入/跳回/释放全由引擎包办,开关即恢复.

## 依赖

```
pip install pymem pyinstaller pyyaml
```

64 位 Python 对 64 位游戏.单机无反作弊,有驱动保护的游戏本路线不适用.
