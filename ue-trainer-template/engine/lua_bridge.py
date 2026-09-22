# -*- coding: utf-8 -*-
"""Lua 桥:往 Mod 目录写 cmd.txt (写.tmp再整体替换,防读半截),tail UE4SS.log 取 [LVT] 行.

游戏侧 Lua 约定 (见 lua/template_main.lua):
  游戏内 LoopAsync 轮询 cmd.txt,执行完清空,结果只写 UE4SS.log.
"""
import os
import time


def game_paths(root, mod_rel):
    # mod_rel 如 TheLostVillage/Binaries/Win64/ue4ss/Mods/Xxx
    moddir = os.path.join(root, mod_rel)
    uedir = os.path.normpath(os.path.join(moddir, '..', '..'))
    return {
        'moddir': moddir,
        'cmd': os.path.join(moddir, 'cmd.txt'),
        'log': os.path.normpath(os.path.join(moddir, '..', '..', 'UE4SS.log')),
        'modstxt': os.path.normpath(os.path.join(moddir, '..', 'mods.txt')),
    }


def send_lines(cmd_path, lines):
    tmp = cmd_path + '.tmp'
    with open(tmp, 'w', encoding='ascii') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(tmp, cmd_path)


def wait_lvt(log_path, start_size, nlines, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.5)
        try:
            with open(log_path, encoding='utf-8', errors='replace') as f:
                f.seek(start_size)
                new = f.read()
        except OSError:
            continue
        if new.count('exec done') >= nlines:
            return [ln for ln in new.splitlines() if '[LVT]' in ln]
    return []
