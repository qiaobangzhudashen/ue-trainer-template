# -*- coding: utf-8 -*-
"""打包单 exe (双击即用): python tools/build.py --game lostvillage
产物 dist/<Game>Trainer.exe,双击即用,无需装 Python (pymem 已打进包).
64位 Python 对 64 位游戏,管理员运行.
"""
import argparse
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default='lostvillage')
    ap.add_argument('--root', default='')
    a = ap.parse_args()
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile',
           '--name', '%sTrainer' % a.game.capitalize(),
           '--paths', os.path.join(BASE, 'engine'),
           os.path.join(BASE, 'ui', 'app.py')]
    print(' '.join(cmd))
    subprocess.check_call(cmd, cwd=BASE)
    print('产物在 dist/ 下.把 games/%s/game.yaml + items.txt 放到 exe 同目录 games/%s/ 下.' % (a.game, a.game))


if __name__ == '__main__':
    main()
