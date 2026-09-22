# -*- coding: utf-8 -*-
"""Steam 游戏根目录自动定位 (UE / Unity 通用, 与引擎无关).

用法:
    from tools.steam_find import find_game
    root = find_game('3863760', 'xiayinglu.exe')  # AppID 与 exe 名按目标游戏填

流程: 注册表 Steam 路径 -> libraryfolders.vdf 枚举各库 ->
appmanifest_<appid>.acf 读 installdir -> 校验 exe 存在.
找不到返回 '' (调用方转手动选择 + ini 记忆, 见山门 trainer_ui / 侠影录 launcher).
"""
import os
import re


def steam_path():
    try:
        import winreg
        for root, sub in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam')):
            try:
                with winreg.OpenKey(root, sub) as k:
                    for val in ('SteamPath', 'InstallPath'):
                        try:
                            p = winreg.QueryValueEx(k, val)[0].replace('/', os.sep)
                            if os.path.isdir(p):
                                return p
                        except OSError:
                            continue
            except OSError:
                continue
    except ImportError:
        pass
    for p in (r'C:\Program Files (x86)\Steam', r'D:\Steam'):
        if os.path.isdir(p):
            return p
    return ''


def exe_path(root, exe_name, maxdepth=4):
    """root 下找 exe (顶层优先, UE 常嵌在 <Game>/Binaries/Win64/ 下, 向下走 maxdepth 层).
    返回完整路径, 找不到返回 ''."""
    if not root or not exe_name:
        return ''
    top = os.path.join(root, exe_name)
    if os.path.isfile(top):
        return top
    try:
        base_depth = root.rstrip(os.sep).count(os.sep)
        for dp, dn, fn in os.walk(root):
            if dp.rstrip(os.sep).count(os.sep) - base_depth > maxdepth:
                dn[:] = []
                continue
            # 剪掉常见大目录, 加速
            dn[:] = [d for d in dn if d not in ('Engine', 'Content', 'Paks')]
            if exe_name in fn:
                return os.path.join(dp, exe_name)
    except Exception:
        pass
    return ''


def find_game(app_id, exe_name, dir_name=''):
    """返回游戏根目录 (exe 可能嵌在子目录, 见 exe_path), 找不到返回 ''."""
    sp = steam_path()
    if not sp:
        return ''
    libs = [sp]
    try:
        with open(os.path.join(sp, 'steamapps', 'libraryfolders.vdf'),
                  encoding='utf-8', errors='replace') as f:
            vdf = f.read()
        for m in re.finditer(r'"path"\s+"([^"]+)"', vdf):
            p = m.group(1).replace('\\\\', os.sep).replace('/', os.sep)
            if os.path.isdir(p) and p not in libs:
                libs.append(p)
    except OSError:
        pass
    for lib in libs:
        try:
            with open(os.path.join(lib, 'steamapps', 'appmanifest_%s.acf' % app_id),
                      encoding='utf-8', errors='replace') as f:
                acf = f.read()
        except OSError:
            continue
        m = re.search(r'"installdir"\s+"([^"]+)"', acf)
        if not m:
            continue
        cand = os.path.join(lib, 'steamapps', 'common', m.group(1))
        if exe_path(cand, exe_name):
            return cand
    if dir_name:
        for lib in libs:
            cand = os.path.join(lib, 'steamapps', 'common', dir_name)
            if exe_path(cand, exe_name):
                return cand
    return ''


def game_running(exe_name):
    """tasklist 进程检测 (部署前调用, 运行中禁止覆盖)."""
    import subprocess
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq %s' % exe_name, '/NH'],
                             capture_output=True, text=True, timeout=10).stdout
        return exe_name.lower() in out.lower()
    except Exception:
        return False
