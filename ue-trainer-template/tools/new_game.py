# -*- coding: utf-8 -*-
"""新游戏脚手架: python tools/new_game.py --slug mygame --exe Game-Win64-Shipping.exe
生成 games/mygame/{game.yaml,items.txt,MOD-MEMORY.md},之后 agent 按六问填空.
"""
import argparse
import os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--slug', required=True)
    ap.add_argument('--exe', required=True)
    a = ap.parse_args()
    dst = os.path.join(BASE, 'games', a.slug)
    os.makedirs(dst, exist_ok=True)
    src = os.path.join(BASE, 'games', '_template', 'game.yaml')
    text = open(src, encoding='utf-8').read()
    text = text.replace('Game-Win64-Shipping.exe', a.exe)
    open(os.path.join(dst, 'game.yaml'), 'w', encoding='utf-8').write(text)
    open(os.path.join(dst, 'items.txt'), 'w', encoding='utf-8').write(
        '# ID\t名称\t分类 (agent 填目标游戏 ID 库)\n')
    open(os.path.join(dst, 'MOD-MEMORY.md'), 'w', encoding='utf-8').write(
        '# %s MOD-MEMORY\n\n## 环境\n- exe: %s\n\n## 六问\n(按 ue-MODS.md 填写)\n' % (a.slug, a.exe))
    print('已生成 %s,下一步 agent 填发奖函数 + AOB.' % dst)


if __name__ == '__main__':
    main()
