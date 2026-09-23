# -*- coding: utf-8 -*-
"""注入体检三件套（UE4SS / BepInEx 同构，见 skill 方法论文档）。

UE 侧对应 generic-MODS.md §1.2，Unity BepInEx 侧对应 unity-MODS.md §4.3。
只用标准库；各游戏 trainer 从这里 import，不要每家各写一份。

实锤来源：LostVillage 新用户模拟——experimental 3.x 真认 mods.json、
自带包 EnableHotReloadSystem=0 致 Ctrl+R 全死、启动时缺文件本局注定无通道。
"""
import json
import os
import shutil
import zipfile

# UE4SS 官方自带 Mod 的期望顺序（mods.txt load order）。
# 自家 Mod 固定排末尾；未知行追加保留，保证干净无空行无注释。
_DEFAULT_WANT = [
    'CheatManagerEnablerMod : 1',
    'ConsoleCommandsMod : 1',
    'ConsoleEnablerMod : 1',
    'SplitScreenMod : 0',
    'LineTraceMod : 0',
    'BPML_GenericFunctions : 1',
    'BPModLoaderMod : 1',
    'Keybinds : 1',
]


def _mods_paths(uedir):
    mods = os.path.join(uedir, 'Mods')
    return (os.path.join(mods, 'mods.txt'),
            os.path.join(mods, 'mods.json'))


def ensure_ue4ss_registered(uedir, mod_name, want_order=None):
    """双注册修复：mods.txt + mods.json 都要有 mod_name。

    返回 {'txt': bool, 'json': bool}（修复后是否在位）。
    """
    want = list(want_order or _DEFAULT_WANT)
    want.append('%s : 1' % mod_name)
    txt_p, json_p = _mods_paths(uedir)
    txt_ok = json_ok = False
    try:
        cur = []
        if os.path.isfile(txt_p):
            with open(txt_p, encoding='utf-8', errors='replace') as f:
                for ln in f.read().splitlines():
                    s = ln.strip()
                    if s and not s.startswith(';') and ':' in s:
                        cur.append(s)
        if '%s : 1' % mod_name not in cur and mod_name not in [
                c.split(':')[0].strip() for c in cur]:
            cur.append('%s : 1' % mod_name)
        order = [w.split(':')[0].strip() for w in want]
        out = [w for w in want if w.split(':')[0].strip() in order]
        seen = set(w.split(':')[0].strip() for w in out)
        for c in cur:
            if c.split(':')[0].strip() not in seen:
                out.append(c)
                seen.add(c.split(':')[0].strip())
        os.makedirs(os.path.dirname(txt_p), exist_ok=True)
        with open(txt_p, 'w', encoding='ascii') as f:
            f.write('\n'.join(out) + '\n')
        txt_ok = True
    except Exception:
        pass
    try:
        data = []
        if os.path.isfile(json_p):
            with open(json_p, encoding='utf-8', errors='replace') as f:
                data = json.load(f)
        if not any(isinstance(d, dict) and d.get('mod_name') == mod_name
                   for d in data):
            data.append({'mod_name': mod_name, 'mod_enabled': True})
            with open(json_p, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        json_ok = any(isinstance(d, dict) and d.get('mod_name') == mod_name
                      and d.get('mod_enabled') for d in data)
    except Exception:
        pass
    return {'txt': txt_ok, 'json': json_ok}


def ensure_hotreload_enabled(uedir):
    """自带包默认 EnableHotReloadSystem=0（Ctrl+R 全死），强制改 1。

    EnableAutoReloadingLuaMods 不碰（保持 0，自动重载崩溃实锤）。
    返回 True 表示文件在位且为 1（含本次改的）。
    """
    sp = os.path.join(uedir, 'UE4SS-settings.ini')
    try:
        if not os.path.isfile(sp):
            return False
        with open(sp, encoding='utf-8', errors='replace') as f:
            txt = f.read()
        if 'EnableHotReloadSystem = 0' in txt:
            txt = txt.replace('EnableHotReloadSystem = 0',
                              'EnableHotReloadSystem = 1')
            with open(sp, 'w', encoding='utf-8') as f:
                f.write(txt)
        return 'EnableHotReloadSystem = 1' in txt
    except Exception:
        return False


def ensure_ue4ss_present(win64_dir, zip_path=None):
    """注入本体校验：代理 dll + ue4ss/UE4SS.dll，缺即用自带 zip 补。

    返回 (ok, msg, changed)。补完本局必须重启游戏（调用方提示）。
    """
    dll = os.path.join(win64_dir, 'dwmapi.dll')
    core = os.path.join(win64_dir, 'ue4ss', 'UE4SS.dll')
    if os.path.isfile(dll) and os.path.isfile(core):
        return True, 'UE4SS完整', False
    if not zip_path or not os.path.isfile(zip_path):
        return False, 'UE4SS缺文件，且找不到自带包（把它放 exe 旁边）', False
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(win64_dir)
        if os.path.isfile(dll) and os.path.isfile(core):
            return True, 'UE4SS缺文件，已自动补齐（重启游戏后生效）', True
        return False, 'UE4SS补齐后校验失败（dll 仍不存在）', True
    except Exception as ex:
        return False, 'UE4SS补齐失败: %s' % ex, False


def ue_auto_setup(win64_dir, mod_name, zip_path=None, want_order=None):
    """修改器启动一键体检：本体 + 双注册 + 热重载。

    返回 (ok, msgs)：ok 为三件全齐；msgs 逐行给 UI 日志。
    本体刚补齐（changed）时调用方必须提示重启游戏。
    """
    msgs = []
    ok, msg, changed = ensure_ue4ss_present(win64_dir, zip_path)
    msgs.append(msg)
    uedir = os.path.join(win64_dir, 'ue4ss')
    reg = ensure_ue4ss_registered(uedir, mod_name, want_order)
    msgs.append('双注册: txt=%s json=%s' % (reg['txt'], reg['json']))
    hr = ensure_hotreload_enabled(uedir)
    msgs.append('热重载: %s' % ('开' if hr else '未知'))
    return ok and reg['txt'] and reg['json'], msgs, changed


# BepInEx 劫持链按分支二选一（某游戏只用其中一种，不要要求同时存在）。
_HIJACK_VARIANTS = (('winhttp.dll',), ('version.dll', 'doorstop_config.ini'))
_BEPINEX_PREFIX = 'BepInEx' + os.sep


def _bepinex_status(game_root, mod_dll_name):
    dll_ok = os.path.isfile(
        os.path.join(game_root, 'BepInEx', 'plugins', mod_dll_name))
    hijack_ok = any(
        all(os.path.isfile(os.path.join(game_root, n)) for n in variant)
        for variant in _HIJACK_VARIANTS)
    return dll_ok, hijack_ok


def bepinex_status(game_root, mod_dll_name):
    """只读状态：返回 (dll_ok, hijack_ok)，UI 自检用，不写文件。"""
    return _bepinex_status(game_root, mod_dll_name)


def ensure_bepinex_present(game_root, mod_dll_name, payload_dir=None):
    """BepInEx 版三件套：劫持链 + 本体目录 + plugins/<mod>.dll。

    payload_dir 为自带包目录（含 BepInEx/ 与目标 dll），缺项即补。
    返回 (ok, msg, changed)。补完必须重启一次游戏。
    """
    dll_ok, hijack_ok = _bepinex_status(game_root, mod_dll_name)
    if dll_ok and hijack_ok:
        return True, 'BepInEx完整', False
    if not payload_dir or not os.path.isdir(payload_dir):
        return False, 'BepInEx缺文件，且无自带包', False
    try:
        changed = False
        for src_root, _, files in os.walk(payload_dir):
            for fn in files:
                src = os.path.join(src_root, fn)
                rel = os.path.relpath(src, payload_dir)
                # 只接受：顶层劫持文件，或 BepInEx/ 下任意文件
                is_top_hijack = (os.path.dirname(rel) == ''
                                 and os.path.basename(rel) in (
                                     'winhttp.dll', 'version.dll',
                                     'doorstop_config.ini'))
                if not (is_top_hijack or rel.startswith(_BEPINEX_PREFIX)):
                    continue
                dst = os.path.join(game_root, rel)
                if os.path.isfile(dst):
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy(src, dst)
                changed = True
        dll_ok, hijack_ok = _bepinex_status(game_root, mod_dll_name)
        if dll_ok and hijack_ok:
            return True, 'BepInEx缺文件，已自动补齐（重启游戏后生效）', True
        return False, 'BepInEx补齐后劫持链/DLL仍不齐', True
    except Exception as ex:
        return False, 'BepInEx补齐失败: %s' % ex, False
