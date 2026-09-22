# -*- coding: utf-8 -*-
"""新游戏脚手架: python tools/new_game.py --slug mygame --exe Game-Win64-Shipping.exe --engine ue
生成 games/mygame/{game.yaml,items.txt,MOD-MEMORY.md},之后 agent 按六问填空.

--engine ue | unity-mono | unity-il2cpp (默认 ue):
- ue: UE4SS 外部桥, 之后填发奖函数 + AOB
- unity-mono: BepInEx 内挂, bridge=none, module=//harmony-only (不走 AOB, 走 Harmony)
- unity-il2cpp: 内存补丁走 GameAssembly.dll, bridge 按需选
"""
import argparse
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENGINE_PRESET = {
    'ue': ('ue', 'ue4ss', "''"),
    'unity-mono': ('unity-mono', 'none', "'//harmony-only'"),
    'unity-il2cpp': ('unity-il2cpp', 'bepinex-file', "'GameAssembly.dll'"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--slug', required=True)
    ap.add_argument('--exe', required=True)
    ap.add_argument('--engine', default='ue', choices=('ue', 'unity-mono', 'unity-il2cpp'))
    ap.add_argument('--app-id', default='')
    ap.add_argument('--dirname', default='')
    a = ap.parse_args()
    dst = os.path.join(BASE, 'games', a.slug)
    os.makedirs(dst, exist_ok=True)
    src = os.path.join(BASE, 'games', '_template', 'game.yaml')
    text = open(src, encoding='utf-8').read()
    text = text.replace('Game-Win64-Shipping.exe', a.exe)
    text = re.sub(r'^game:\s*.+$', 'game: %s' % a.slug, text, flags=re.M)
    eng, bridge, module = ENGINE_PRESET[a.engine]
    text = re.sub(r'^engine:\s*.+$', 'engine: %s' % eng, text, flags=re.M)
    text = re.sub(r'^bridge:\s*.+$', 'bridge: %s' % bridge, text, flags=re.M)
    text = re.sub(r'^module:\s*.+$', 'module: %s' % module, text, flags=re.M)
    if a.app_id:
        text = re.sub(r"^steam_app_id:\s*'.*'$", "steam_app_id: '%s'" % a.app_id, text, flags=re.M)
    if a.dirname:
        text = re.sub(r"^game_dirname:\s*'.*'$", "game_dirname: '%s'" % a.dirname, text, flags=re.M)
    open(os.path.join(dst, 'game.yaml'), 'w', encoding='utf-8').write(text)
    open(os.path.join(dst, 'items.txt'), 'w', encoding='utf-8').write(
        '# ID\t名称\t分类 (agent 填目标游戏 ID 库)\n')
    open(os.path.join(dst, 'MOD-MEMORY.md'), 'w', encoding='utf-8').write(
        '# %s MOD-MEMORY\n\n## 环境\n- exe: %s\n- engine: %s\n\n## 六问\n(UE 按 ue-MODS.md, Unity 按 unity-MODS.md 填写)\n'
        % (a.slug, a.exe, a.engine))
    print('已生成 %s (engine=%s), 下一步 agent 按六问填空.' % (dst, a.engine))


if __name__ == '__main__':
    main()
