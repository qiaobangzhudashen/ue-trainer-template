# -*- coding: utf-8 -*-
"""打包单 exe (双击即用, 发给朋友):
  UE:  python tools/build.py --game lostvillage
       产物 dist/LostvillageTrainer.exe (物品下发 + 开关/补丁 + 自动定位/部署/运行检测)
  Unity Mono 内挂 (侠影录路线):
       python tools/build.py --game xiayinglu --plugin-csproj D:\...\XiayingluItemMod.csproj --game-root "D:\Steam\steamapps\common\侠影录"
       产物 dist/XiayingluSetup.exe (安装器: 自动定位 + 只补缺项 + 运行检测, 进游戏用内挂窗口)
  64 位 Python 对 64 位游戏, 内存补丁类需管理员运行; 纯安装器无需管理员.
"""
import argparse
import os
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROOT_FILES = ['winhttp.dll', 'doorstop_config.ini', '.doorstop_version']
ROOT_DIRS = [os.path.join('BepInEx', 'core'), os.path.join('BepInEx', 'patchers')]
SKIP_DIRS = {'cache', 'config', '__pycache__'}


def _load_engine(slug):
    """轻量读 engine, 无 yaml 库也能跑."""
    path = os.path.join(BASE, 'games', slug, 'game.yaml')
    try:
        import yaml
        with open(path, encoding='utf-8') as f:
            return (yaml.safe_load(f.read()) or {}).get('engine') or 'ue'
    except Exception:
        pass
    import re
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
        m = re.search(r'^engine:\s*(.+)$', text, re.M)
        return m.group(1).strip().strip("'\"") if m else 'ue'
    except Exception:
        return 'ue'


def _load_plugin_dll(slug):
    path = os.path.join(BASE, 'games', slug, 'game.yaml')
    import re
    try:
        import yaml
        with open(path, encoding='utf-8') as f:
            return (yaml.safe_load(f.read()) or {}).get('plugin_dll') or ''
    except Exception:
        pass
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
        m = re.search(r'^plugin_dll:\s*(.+)$', text, re.M)
        return m.group(1).strip().strip("'\"") if m else ''
    except Exception:
        return ''


def _build_bepinex_payload(game_root, payload_dir):
    """从本机游戏目录提取 BepInEx 必备文件为展开目录（游戏根相对镜像）。

    布局匹配 engine/deploy.py 的 ensure_bepinex_present：顶层劫持文件 +
    BepInEx/ 下文件；自家 DLL 由 plugin-csproj 步骤另行拷入。
    已有文件不覆盖（删掉 payload 后重跑可刷新）。
    """
    os.makedirs(payload_dir, exist_ok=True)
    n = 0
    for fn in ROOT_FILES:
        src = os.path.join(game_root, fn)
        dst = os.path.join(payload_dir, fn)
        if os.path.isfile(src):
            if not os.path.isfile(dst):
                shutil.copyfile(src, dst)
                n += 1
        else:
            print('警告: 缺 %s (跳过)' % fn)
    for rd in ROOT_DIRS:
        srcdir = os.path.join(game_root, rd)
        for dp, dn, fn in os.walk(srcdir):
            dn[:] = [d for d in dn if d not in SKIP_DIRS]
            for f in fn:
                full = os.path.join(dp, f)
                rel = os.path.relpath(full, game_root)
                dst = os.path.join(payload_dir, rel)
                if not os.path.isfile(dst):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(full, dst)
                    n += 1
    print('payload 就绪: %s (新增 %d 个)' % (payload_dir, n))
    return payload_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default='lostvillage')
    ap.add_argument('--plugin-csproj', default='')
    ap.add_argument('--game-root', default='')
    a = ap.parse_args()

    slug = a.game
    engine = _load_engine(slug)
    is_unity = (engine or 'ue') != 'ue'
    name = '%sSetup' % slug.capitalize() if is_unity else '%sTrainer' % slug.capitalize()
    game_dir = os.path.join(BASE, 'games', slug)
    payload_dir = os.path.join(game_dir, 'payload')

    if is_unity:
        dll = _load_plugin_dll(slug)
        if a.plugin_csproj:
            print('+ dotnet build %s' % a.plugin_csproj)
            subprocess.check_call(['dotnet', 'build', a.plugin_csproj, '-c', 'Release', '--nologo'])
            # 约定: 输出 bin/Release/<dll>
            built = os.path.join(os.path.dirname(a.plugin_csproj), 'bin', 'Release', dll)
            if dll and os.path.isfile(built):
                os.makedirs(payload_dir, exist_ok=True)
                shutil.copyfile(built, os.path.join(payload_dir, dll))
                print('已更新 payload/%s' % dll)
            else:
                print('警告: 未找到编译产物 %s, 沿用 payload 内旧 DLL' % built)
        if a.game_root:
            _build_bepinex_payload(a.game_root, payload_dir)
        if not os.path.isdir(payload_dir) or not os.listdir(payload_dir):
            print('警告: payload/ 为空, EXE 装 BepInEx 本体时会报不完整 (先用 --game-root 提取).')

    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile',
           '--windowed', '--name', name,
           '--paths', os.path.join(BASE, 'engine'),
           '--add-data', '%s%sgames/%s' % (game_dir, os.pathsep, 'games/%s' % slug),
           os.path.join(BASE, 'ui', 'app.py')]
    print(' '.join(cmd))
    subprocess.check_call(cmd, cwd=BASE)
    print('产物: dist/%s.exe (games/%s/ 已打进包, exe 同目录放同名 games/%s/ 可覆盖不用重打).'
          % (name, slug, slug))


if __name__ == '__main__':
    main()
