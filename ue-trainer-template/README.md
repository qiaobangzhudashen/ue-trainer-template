# UE 通用修改器源码模板

> 给 agent 看的源码,不是给玩家的手填表.新游戏流程固定:
> 你报游戏根目录 + 需求,我负责 CE 里搜断反补丁 + Lua 里定位官方发奖链,
> 填进 `games/<slug>/game.yaml`,调通后再 `tools/build.py` 打成单 exe.

## 目录

```
engine/memory.py      内存引擎 (bytes + cave,游戏无关,不动;module 取 game.yaml)
engine/lua_bridge.py  cmd.txt + 日志桥,不动 (UE)
engine/deploy.py      注入体检三件套,不动 (UE ue_auto_setup / Unity ensure_bepinex_present 同构)
engine/items.py       items.txt 读取 (不动;原名 db.py,与 toolbox 查表 db 重名已改)
ui/app.py             通用界面 (读 game.yaml 驱动,不动;exe 同目录优先;自动定位+一键部署+运行检测)
tools/steam_find.py   Steam 自动定位 + 进程检测,不动 (UE/Unity 通用)
lua/template_main.lua Lua 模板 (每个游戏复制改 MOD_NAME/GIVE/HOOK 段)
games/_template/      空配置 (新游戏起点,含 engine/bridge 分流字段)
games/lostvillage/    UE 示例 (4 个 bytes 补丁已迁移验证,仅归档)
tools/asm.py          cave 组装(keystone)+反汇编复核(capstone,制作期用)
tools/build.py        PyInstaller 单 exe 打包 (UE 打 Trainer, Unity 打 Setup 安装器)
tools/new_game.py     新游戏脚手架 (--engine ue|unity-mono|unity-il2cpp)
```

## 新游戏分工

1. 你:给游戏根目录 + 一句话需求 (如建筑免材料 / 加物品).
2. 我:先扫目录判引擎填 `game.yaml: engine` (UE 走 UE4SS+CE, Unity-Mono 转 BepInEx 内挂不走 AOB) →
   静态侦察 → 定位发奖函数/官方 API → 抓检查/扣除 → 填 game.yaml →
   UI 联调 (Lua hook + 内存补丁同开同关；Unity 纯安装器，进游戏用内挂窗口) → 打包 exe.
3. 复杂补丁 (条件分支/寄存器保护,原来 CE 里要 alloc 的) 用 `type: cave`,
   机器码贴 `cave_hex`,申请/跳入/跳回/释放全由引擎包办,开关即恢复.

## 依赖

```
pip install pymem pyinstaller pyyaml
```

64 位 Python 对 64 位游戏.单机无反作弊,有驱动保护的游戏本路线不适用.
